import pytest

from app.clients.openai_client import AnalysisError
from app.dependencies import get_guardian_client, get_openai_client
from app.main import app
from app.services import search
from tests.fakes import FakeGuardianClient, FakeOpenAIClient

GUARDIAN_ID = "world/2026/oct/01/example"


def use_fakes(openai: FakeOpenAIClient) -> None:
    app.dependency_overrides[get_guardian_client] = lambda: FakeGuardianClient()
    app.dependency_overrides[get_openai_client] = lambda: openai


@pytest.fixture(autouse=True)
def reset_app():
    search._cache.clear()
    yield
    app.dependency_overrides.clear()


def test_search_page_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'hx-get="/partials/search"' in response.text


def test_history_page_loads(client, session):
    response = client.get("/history")

    assert response.status_code == 200
    assert 'hx-get="/partials/history"' in response.text


def test_search_shows_cards_with_analyse_button(client, session):
    use_fakes(FakeOpenAIClient())

    response = client.get("/partials/search", params={"q": "climate"})

    assert "Example headline" in response.text
    assert 'hx-post="/partials/analyse"' in response.text


def test_analyse_shows_summary(client, session):
    use_fakes(FakeOpenAIClient())

    response = client.post("/partials/analyse", data={"guardian_id": GUARDIAN_ID})

    assert "A summary." in response.text


def test_analyse_failure_shows_error_and_keeps_button(client, session):
    use_fakes(FakeOpenAIClient(error=AnalysisError("OpenAI is down")))

    response = client.post("/partials/analyse", data={"guardian_id": GUARDIAN_ID})

    assert response.status_code == 200
    assert "analyse this article. Try again." in response.text
    assert "Analyse" in response.text


def test_search_with_dates_the_wrong_way_round_shows_error(client):
    response = client.get(
        "/partials/search",
        params={"q": "climate", "from_date": "2026-09-30", "to_date": "2026-09-01"},
    )

    assert "must be before the To date" in response.text
