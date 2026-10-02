from datetime import date

import pytest

from app.clients.guardian import GuardianError
from app.clients.openai_client import AnalysisError, SearchQuestion
from app.services import search
from app.services.search import interpret_question, search_articles


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


TODAY = date(2026, 10, 2)


class FakeOpenAIClient:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error

    def interpret_question(self, question):
        if self.error:
            raise self.error
        return self.answer


def test_time_period_becomes_a_from_date():
    answer = SearchQuestion(
        keywords="renewable energy",
        section="environment",
        time_period="this_week",
        order_by="newest",
    )

    interpreted = interpret_question(FakeOpenAIClient(answer), "renewables this week", TODAY)

    assert interpreted.keywords == "renewable energy"
    assert interpreted.section == "environment"
    assert interpreted.from_date == date(2026, 9, 25)


def test_unknown_section_is_dropped():
    answer = SearchQuestion(keywords="cats", section="pets", time_period="any", order_by="newest")

    interpreted = interpret_question(FakeOpenAIClient(answer), "cat news", TODAY)

    assert interpreted.section is None
    assert interpreted.from_date is None


def test_openai_failure_falls_back_to_keyword_search():
    openai = FakeOpenAIClient(error=AnalysisError("OpenAI is down"))

    interpreted = interpret_question(openai, "good news about renewables", TODAY)

    assert interpreted.keywords == "good news about renewables"
    assert interpreted.section is None
