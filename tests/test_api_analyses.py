from datetime import UTC, datetime

import pytest

from app.clients.openai_client import AnalysisError
from app.dependencies import get_guardian_client, get_openai_client
from app.main import app
from app.models import Analysis, Article, Sentiment
from tests.fakes import FakeGuardianClient, FakeOpenAIClient

GUARDIAN_ID = "world/2026/oct/01/example"


def use_fakes(openai: FakeOpenAIClient) -> None:
    app.dependency_overrides[get_guardian_client] = lambda: FakeGuardianClient()
    app.dependency_overrides[get_openai_client] = lambda: openai


@pytest.fixture(autouse=True)
def reset_overrides():
    yield
    app.dependency_overrides.clear()


def save_analysis(session, guardian_id: str, headline: str, sentiment: Sentiment) -> None:
    article = Article(
        guardian_id=guardian_id,
        web_url=f"https://www.theguardian.com/{guardian_id}",
        headline=headline,
        section_name="World news",
        published_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )
    session.add(
        Analysis(
            article=article, summary="A summary.", sentiment=sentiment, rationale="r", model="m"
        )
    )
    session.commit()


def test_analyse_new_article_returns_201(client, session):
    use_fakes(FakeOpenAIClient())

    response = client.post("/api/analyses", json={"guardian_id": GUARDIAN_ID})

    assert response.status_code == 201
    body = response.json()
    assert body["article"]["guardian_id"] == GUARDIAN_ID
    assert body["analysis"]["sentiment"] == "negative"
    assert "body_text" not in body["article"]


def test_analyse_same_article_again_returns_200_without_calling_openai(client, session):
    openai = FakeOpenAIClient()
    use_fakes(openai)

    client.post("/api/analyses", json={"guardian_id": GUARDIAN_ID})
    response = client.post("/api/analyses", json={"guardian_id": GUARDIAN_ID})

    assert response.status_code == 200
    assert openai.calls == 1


def test_invalid_guardian_id_returns_422(client):
    response = client.post("/api/analyses", json={"guardian_id": "../search"})

    assert response.status_code == 422


def test_openai_failure_returns_502(client, session):
    use_fakes(FakeOpenAIClient(error=AnalysisError("OpenAI is down")))

    response = client.post("/api/analyses", json={"guardian_id": GUARDIAN_ID})

    assert response.status_code == 502


def test_list_filters_by_sentiment_and_keyword(client, session):
    save_analysis(session, "world/good-news", "Climate deal agreed", Sentiment.POSITIVE)
    save_analysis(session, "business/bad-news", "Markets crash", Sentiment.NEGATIVE)

    everything = client.get("/api/analyses").json()
    positive = client.get("/api/analyses", params={"sentiment": "positive"}).json()
    crash = client.get("/api/analyses", params={"q": "crash"}).json()

    assert len(everything) == 2
    assert [r["article"]["headline"] for r in positive] == ["Climate deal agreed"]
    assert [r["article"]["headline"] for r in crash] == ["Markets crash"]


def test_unknown_analysis_returns_404(client, session):
    response = client.get("/api/analyses/999")

    assert response.status_code == 404
