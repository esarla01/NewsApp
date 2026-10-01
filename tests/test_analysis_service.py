import pytest
from sqlalchemy import func, select

from app.clients.guardian import GuardianNotFoundError
from app.clients.openai_client import AnalysisError
from app.db import SessionLocal
from app.models import Analysis, Article, Sentiment
from app.services.analysis import analyse_article
from tests.fakes import FakeGuardianClient, FakeOpenAIClient

GUARDIAN_ID = "world/2026/oct/01/example"


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_new_article_is_analysed_and_saved(session):
    analysis, created = analyse_article(
        session, FakeGuardianClient(), FakeOpenAIClient(), GUARDIAN_ID
    )

    assert created is True
    assert analysis.sentiment is Sentiment.NEGATIVE
    assert analysis.model == "fake-model"
    assert analysis.article.body_text == "Full article text."
    assert count(session, Article) == 1


def test_existing_analysis_is_returned_without_calling_openai(session):
    openai = FakeOpenAIClient()

    first, _ = analyse_article(session, FakeGuardianClient(), openai, GUARDIAN_ID)
    second, created = analyse_article(session, FakeGuardianClient(), openai, GUARDIAN_ID)

    assert created is False
    assert second.id == first.id
    assert openai.calls == 1


def test_no_transaction_is_open_during_openai_call(session):
    in_transaction = []
    openai = FakeOpenAIClient(during_call=lambda: in_transaction.append(session.in_transaction()))

    analyse_article(session, FakeGuardianClient(), openai, GUARDIAN_ID)

    assert in_transaction == [False]


def test_openai_failure_saves_nothing(session):
    openai = FakeOpenAIClient(error=AnalysisError("OpenAI is down"))

    with pytest.raises(AnalysisError):
        analyse_article(session, FakeGuardianClient(), openai, GUARDIAN_ID)

    assert count(session, Article) == 0


def test_unknown_article_saves_nothing(session):
    guardian = FakeGuardianClient(error=GuardianNotFoundError("not found"))

    with pytest.raises(GuardianNotFoundError):
        analyse_article(session, guardian, FakeOpenAIClient(), GUARDIAN_ID)

    assert count(session, Article) == 0


def test_concurrent_request_returns_the_saved_analysis(session):
    def another_request_saves_first():
        # A second request analyses the same article and commits while we wait on OpenAI.
        with SessionLocal() as other_session:
            analyse_article(other_session, FakeGuardianClient(), FakeOpenAIClient(), GUARDIAN_ID)

    openai = FakeOpenAIClient(during_call=another_request_saves_first)

    analysis, created = analyse_article(session, FakeGuardianClient(), openai, GUARDIAN_ID)

    assert created is False
    assert analysis.article.guardian_id == GUARDIAN_ID
    assert count(session, Analysis) == 1
