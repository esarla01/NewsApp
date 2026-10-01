import os

import pytest
from dotenv import load_dotenv

# Point the app at the test database before any app module reads settings.
load_dotenv()
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
