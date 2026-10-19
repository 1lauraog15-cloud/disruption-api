import os
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from disruption_api import create_app
from disruption_api.auth import hash_key
from disruption_api.config import Settings
from disruption_api.models import Airport, Base

TEST_API_KEY = "test-key-not-a-secret"


@pytest.fixture
def engine() -> Iterator[Engine]:
    """In-memory SQLite by default; a real PostgreSQL when TEST_DATABASE_URL is set (used in CI)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        eng = create_engine(url)
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    if url:
        cleanup = create_engine(url)
        Base.metadata.drop_all(cleanup)
        cleanup.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def app(engine: Engine) -> Flask:
    settings = Settings("sqlite://", "memory://", "cache+memory://", frozenset({hash_key(TEST_API_KEY)}))
    return create_app(settings, engine=engine)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """A client that already sends a valid API key."""
    test_client = app.test_client()
    test_client.environ_base["HTTP_X_API_KEY"] = TEST_API_KEY
    return test_client


@pytest.fixture
def anon_client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def delay_task(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the Celery task's .delay so tests never need a broker."""
    mock = MagicMock()
    monkeypatch.setattr("disruption_api.routes.compute_impact.delay", mock)
    return mock


@pytest.fixture
def airports(session: Session) -> None:
    session.add_all(
        [Airport(iata="BCN", name="Barcelona", is_hub=False), Airport(iata="MAD", name="Madrid", is_hub=True)]
    )
    session.commit()


@pytest.fixture
def flight_payload() -> dict[str, object]:
    return {
        "number": "XY123",
        "origin": "BCN",
        "destination": "MAD",
        "scheduled_departure": "2026-11-01T08:30:00+00:00",
        "passengers": 180,
    }
