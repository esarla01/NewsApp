from types import SimpleNamespace

import httpx
import openai
import pytest

from app.clients.openai_client import (
    MAX_BODY_CHARS,
    AnalysisError,
    ArticleAnalysis,
    OpenAIClient,
    SearchQuestion,
)
from app.models import Sentiment

ANALYSIS = ArticleAnalysis(summary="A summary.", sentiment=Sentiment.NEUTRAL, rationale="Factual.")


def make_client(monkeypatch, fake_parse) -> OpenAIClient:
    """An OpenAIClient whose SDK call is replaced by fake_parse."""
    client = OpenAIClient(api_key="test-key", model="gpt-4.1-nano")
    monkeypatch.setattr(client._client.responses, "parse", fake_parse)
    return client


def test_analyse_returns_parsed_analysis(monkeypatch):
    client = make_client(monkeypatch, lambda **kwargs: SimpleNamespace(output_parsed=ANALYSIS))

    assert client.analyse("Headline", "Body") == ANALYSIS


def test_long_body_is_truncated(monkeypatch):
    sent = {}

    def fake_parse(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(output_parsed=ANALYSIS)

    client = make_client(monkeypatch, fake_parse)
    client.analyse("Headline", "x" * (MAX_BODY_CHARS + 500))

    assert sent["input"].count("x") == MAX_BODY_CHARS


def test_openai_error_raises_analysis_error(monkeypatch):
    def fake_parse(**kwargs):
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))

    client = make_client(monkeypatch, fake_parse)

    with pytest.raises(AnalysisError):
        client.analyse("Headline", "Body")


def test_missing_analysis_raises_analysis_error(monkeypatch):
    client = make_client(monkeypatch, lambda **kwargs: SimpleNamespace(output_parsed=None))

    with pytest.raises(AnalysisError):
        client.analyse("Headline", "Body")


def test_interpret_question_returns_parsed_question(monkeypatch):
    question = SearchQuestion(
        keywords="renewable energy",
        section="environment",
        time_period="this_week",
        order_by="newest",
    )
    client = make_client(monkeypatch, lambda **kwargs: SimpleNamespace(output_parsed=question))

    assert client.interpret_question("good news about renewables this week") == question
