from datetime import date

import pytest

from app.clients.guardian import GuardianError
from app.services import search
from app.services.search import search_articles


class FakeGuardianClient:
    """Records each search instead of calling the Guardian."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def search(self, query, section=None, from_date=None, to_date=None, order_by="newest"):
        self.calls.append((query, section))
        if self.error:
            raise self.error
        return []


@pytest.fixture(autouse=True)
def empty_cache():
    search._cache.clear()


def test_repeated_search_uses_cache():
    client = FakeGuardianClient()

    search_articles(client, "climate")
    search_articles(client, "climate")

    assert client.calls == [("climate", None)]


def test_extra_whitespace_uses_same_cache_entry():
    client = FakeGuardianClient()

    search_articles(client, "  climate   change ")
    search_articles(client, "climate change")

    assert client.calls == [("climate change", None)]


def test_different_section_is_a_new_search():
    client = FakeGuardianClient()

    search_articles(client, "climate", "environment")
    search_articles(client, "climate", "world")

    assert client.calls == [("climate", "environment"), ("climate", "world")]


def test_expired_cache_searches_again(monkeypatch):
    monkeypatch.setattr(search, "CACHE_TTL_SECONDS", 0)
    client = FakeGuardianClient()

    search_articles(client, "climate")
    search_articles(client, "climate")

    assert len(client.calls) == 2


def test_failed_search_is_not_cached():
    client = FakeGuardianClient(error=GuardianError("Guardian is down"))

    with pytest.raises(GuardianError):
        search_articles(client, "climate")
    with pytest.raises(GuardianError):
        search_articles(client, "climate")

    assert len(client.calls) == 2


def test_different_dates_are_a_new_search():
    client = FakeGuardianClient()

    search_articles(client, "climate", from_date=date(2026, 9, 1))
    search_articles(client, "climate", from_date=date(2026, 9, 15))

    assert len(client.calls) == 2
