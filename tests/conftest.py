from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from disruption_api import create_app
from disruption_api.config import Settings
from disruption_api.models import Airport, Base


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def app(engine) -> Flask:  # type: ignore[no-untyped-def]
    settings = Settings("sqlite://", "memory://", "cache+memory://")
    return create_app(settings, engine=engine)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
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
