from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from disruption_api.models import Airport, Base, Disruption, DisruptionKind, Flight
from disruption_api.tasks import apply_impact, compute_impact


def test_apply_impact_fills_columns(session: Session, airports: None) -> None:
    flight = Flight(
        number="XY1", origin="BCN", destination="MAD", scheduled_departure=datetime(2026, 11, 1), passengers=200
    )
    session.add(flight)
    session.flush()
    d = Disruption(flight_id=flight.id, kind=DisruptionKind.CANCELLATION)
    session.add(d)
    session.commit()

    assert apply_impact(session, d.id) is True
    session.refresh(d)
    assert d.affected_connections == 70
    assert d.impact_score == 200.0


def test_apply_impact_missing_disruption(session: Session) -> None:
    assert apply_impact(session, 12345) is False


def test_celery_task_runs_end_to_end_with_its_own_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the real task entry point (eagerly) against a SQLite file it opens itself."""
    url = f"sqlite:///{tmp_path / 'task.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        s.add(Airport(iata="BCN", name="Barcelona", is_hub=False))
        s.add(Airport(iata="MAD", name="Madrid", is_hub=True))
        flight = Flight(
            number="XY1", origin="BCN", destination="MAD", scheduled_departure=datetime(2026, 11, 1), passengers=200
        )
        s.add(flight)
        s.flush()
        d = Disruption(flight_id=flight.id, kind=DisruptionKind.CANCELLATION)
        s.add(d)
        s.commit()
        disruption_id = d.id
    monkeypatch.setenv("DATABASE_URL", url)

    assert compute_impact.apply(args=[disruption_id]).get() is True
    assert compute_impact.apply(args=[999]).get() is False
    with sessionmaker(bind=engine)() as s:
        assert s.get(Disruption, disruption_id).impact_score == 200.0  # type: ignore[union-attr]
