"""Background work: estimate the impact of a disruption after it is recorded."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .celery_app import celery
from .config import Settings
from .db import make_engine, make_session_factory
from .models import Airport, Disruption, DisruptionKind, Flight
from .services import Leg, estimate_impact, propagate_delay

log = logging.getLogger(__name__)


def apply_impact(session: Session, disruption_id: int) -> bool:
    """Compute and store the impact. Returns False if the disruption does not exist."""
    disruption = session.get(Disruption, disruption_id)
    if disruption is None:
        log.warning("disruption %s not found", disruption_id)
        return False
    flight = disruption.flight
    airport = session.get(Airport, flight.destination)
    impact = estimate_impact(
        disruption.kind,
        disruption.delay_minutes,
        flight.passengers,
        destination_is_hub=bool(airport and airport.is_hub),
    )
    disruption.affected_connections = impact.affected_connections
    disruption.impact_score = impact.score
    session.commit()
    return True


def apply_cascade(session: Session, disruption_id: int) -> list[int]:
    """Create knock-on delays for the later flights of the same aircraft.

    Only delays that were recorded directly (not knock-ons) cascade, and only once: if children already
    exist the task does nothing, so a retry cannot duplicate them. Returns the new disruption ids.
    """
    parent = session.get(Disruption, disruption_id)
    if parent is None or parent.parent_id is not None or parent.kind is not DisruptionKind.DELAY:
        return []
    flight = parent.flight
    if flight.tail_number is None or flight.scheduled_arrival is None or parent.delay_minutes <= 0:
        return []
    if session.scalar(select(Disruption.id).where(Disruption.parent_id == parent.id).limit(1)) is not None:
        return []
    later = session.scalars(
        select(Flight)
        .where(
            Flight.tail_number == flight.tail_number,
            Flight.scheduled_departure > flight.scheduled_departure,
            Flight.scheduled_arrival.is_not(None),
        )
        .order_by(Flight.scheduled_departure)
    ).all()
    legs = [Leg(f.id, f.scheduled_departure, f.scheduled_arrival) for f in later if f.scheduled_arrival is not None]
    created: list[Disruption] = []
    for flight_id, minutes in propagate_delay(parent.delay_minutes, flight.scheduled_arrival, legs):
        child = Disruption(
            flight_id=flight_id,
            kind=DisruptionKind.DELAY,
            delay_minutes=minutes,
            reason=f"Knock-on from flight {flight.number}",
            parent_id=parent.id,
        )
        session.add(child)
        created.append(child)
    session.commit()
    for child in created:
        apply_impact(session, child.id)
    return [c.id for c in created]


@celery.task(bind=True, autoretry_for=(ConnectionError,), max_retries=3)  # type: ignore[untyped-decorator]
def compute_impact(self: object, disruption_id: int) -> bool:
    factory = make_session_factory(make_engine(Settings.from_env().database_url))
    with factory() as session:
        found = apply_impact(session, disruption_id)
        if found:
            apply_cascade(session, disruption_id)
        return found
