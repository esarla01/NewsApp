from datetime import UTC, datetime

import httpx
import pytest

from app.clients.guardian import (
    GuardianClient,
    GuardianError,
    GuardianNotFoundError,
    GuardianRateLimitError,
)

ARTICLE = {
    "id": "world/2026/oct/01/example",
    "webUrl": "https://www.theguardian.com/world/2026/oct/01/example",
    "webTitle": "Example headline",
    "sectionName": "World news",
    "webPublicationDate": "2026-10-01T09:00:00Z",
    "fields": {
        "standfirst": "<p>Example standfirst</p>",
        "byline": "A Reporter",
        "thumbnail": "https://media.guim.co.uk/example.jpg",
    },
}

EMPTY_SEARCH = {"response": {"results": []}}


class FakeGuardian:
    """Stands in for the Guardian API: returns a canned response and records the request."""

    def __init__(self, status=200, body=EMPTY_SEARCH):
        self.status = status
        self.body = body
        self.last_request = None

    def handle(self, request):
        self.last_request = request
        return httpx.Response(self.status, json=self.body)

    def client(self):
        return GuardianClient("test-key", transport=httpx.MockTransport(self.handle))


def test_search_sends_expected_params():
    fake = FakeGuardian()

    fake.client().search("climate", section="environment")

    params = fake.last_request.url.params
    assert params["q"] == "climate"
    assert params["section"] == "environment"
    assert params["type"] == "article"
    assert params["order-by"] == "newest"
    assert params["api-key"] == "test-key"


def test_search_parses_articles():
    client = FakeGuardian(body={"response": {"results": [ARTICLE]}}).client()

    [article] = client.search("climate")

    assert article.guardian_id == "world/2026/oct/01/example"
    assert article.headline == "Example headline"
    assert article.standfirst == "<p>Example standfirst</p>"
    assert article.byline == "A Reporter"
    assert article.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def test_missing_optional_fields_become_none():
    article_without_fields = {**ARTICLE, "fields": {}}
    client = FakeGuardian(body={"response": {"results": [article_without_fields]}}).client()

    [article] = client.search("climate")

    assert article.standfirst is None
    assert article.byline is None
    assert article.thumbnail_url is None


def test_rate_limit_raises_rate_limit_error():
    client = FakeGuardian(status=429).client()

    with pytest.raises(GuardianRateLimitError):
        client.search("climate")


def test_server_error_raises_guardian_error():
    client = FakeGuardian(status=500).client()

    with pytest.raises(GuardianError):
        client.search("climate")


def test_timeout_raises_guardian_error():
    def time_out(request):
        raise httpx.ConnectTimeout("timed out")

    client = GuardianClient("test-key", transport=httpx.MockTransport(time_out))

    with pytest.raises(GuardianError):
        client.search("climate")


def test_get_article_requests_body_and_parses_it():
    article_with_body = {**ARTICLE, "fields": {**ARTICLE["fields"], "bodyText": "Full text."}}
    fake = FakeGuardian(body={"response": {"content": article_with_body}})

    article = fake.client().get_article("world/2026/oct/01/example")

    assert fake.last_request.url.path == "/world/2026/oct/01/example"
    assert "bodyText" in fake.last_request.url.params["show-fields"]
    assert article.body_text == "Full text."


def test_get_unknown_article_raises_not_found():
    client = FakeGuardian(status=404).client()

    with pytest.raises(GuardianNotFoundError):
        client.get_article("world/does-not-exist")
