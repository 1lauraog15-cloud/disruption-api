from datetime import datetime

from sqlalchemy.orm import Session

from disruption_api.models import Disruption, DisruptionKind, Flight
from disruption_api.tasks import apply_impact


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
    assert d.affected_connections == 70 and d.impact_score == 200.0


def test_apply_impact_missing_disruption(session: Session) -> None:
    assert apply_impact(session, 12345) is False
