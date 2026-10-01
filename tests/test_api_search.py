from datetime import UTC, datetime

import pytest

from app.clients.guardian import GuardianArticle, GuardianError, GuardianRateLimitError
from app.dependencies import get_guardian_client
from app.main import app
from app.models import Analysis, Article, Sentiment
from app.services import search


class FakeGuardianClient:
    """Returns fixed articles, or raises an error, instead of calling the Guardian."""

    def __init__(self, articles=(), error=None):
        self.articles = list(articles)
        self.error = error

    def search(self, query, section=None, from_date=None, to_date=None, order_by="newest"):
        if self.error:
            raise self.error
        return self.articles


def guardian_article(guardian_id: str) -> GuardianArticle:
    return GuardianArticle(
        guardian_id=guardian_id,
        web_url=f"https://www.theguardian.com/{guardian_id}",
        headline=f"Headline for {guardian_id}",
        section_name="World news",
        published_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )


def use_fake_guardian(fake: FakeGuardianClient) -> None:
    app.dependency_overrides[get_guardian_client] = lambda: fake


@pytest.fixture(autouse=True)
def reset_app():
    search._cache.clear()
    yield
    app.dependency_overrides.clear()


def test_search_attaches_stored_analysis(client, session):
    article = Article(
        guardian_id="world/analysed",
        web_url="https://www.theguardian.com/world/analysed",
        headline="Analysed",
        section_name="World news",
        published_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )
    session.add(
        Analysis(
            article=article,
            summary="A summary.",
            sentiment=Sentiment.POSITIVE,
            rationale="Upbeat.",
            model="gpt-4.1-nano",
        )
    )
    session.commit()
    use_fake_guardian(
        FakeGuardianClient([guardian_article("world/analysed"), guardian_article("world/new")])
    )

    response = client.get("/api/articles/search", params={"q": "climate"})

    assert response.status_code == 200
    analysed, new = response.json()
    assert analysed["analysis"]["sentiment"] == "positive"
    assert analysed["analysis"]["summary"] == "A summary."
    assert new["analysis"] is None


def test_empty_query_is_rejected(client):
    response = client.get("/api/articles/search", params={"q": ""})

    assert response.status_code == 422


def test_guardian_rate_limit_returns_429(client):
    use_fake_guardian(FakeGuardianClient(error=GuardianRateLimitError("slow down")))

    response = client.get("/api/articles/search", params={"q": "climate"})

    assert response.status_code == 429


def test_guardian_failure_returns_502(client):
    use_fake_guardian(FakeGuardianClient(error=GuardianError("Guardian is down")))

    response = client.get("/api/articles/search", params={"q": "climate"})

    assert response.status_code == 502


def test_from_date_after_to_date_returns_422(client):
    response = client.get(
        "/api/articles/search",
        params={"q": "climate", "from_date": "2026-09-30", "to_date": "2026-09-01"},
    )

    assert response.status_code == 422
