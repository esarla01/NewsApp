import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Point the app at the test database before any app module reads settings.
load_dotenv()
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    # Rebuild the schema from the migrations, so the migrations themselves are tested.
    config = Config(str(ALEMBIC_INI))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
        session.rollback()
        session.execute(text("TRUNCATE articles, analyses RESTART IDENTITY CASCADE"))
        session.commit()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
