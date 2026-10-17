"""Background work: estimate the impact of a disruption after it is recorded."""

import logging

from sqlalchemy.orm import Session

from .celery_app import celery
from .config import Settings
from .db import make_engine, make_session_factory
from .models import Airport, Disruption
from .services import estimate_impact

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


@celery.task(bind=True, autoretry_for=(ConnectionError,), max_retries=3)  # type: ignore[untyped-decorator]
def compute_impact(self: object, disruption_id: int) -> bool:
    factory = make_session_factory(make_engine(Settings.from_env().database_url))
    with factory() as session:
        return apply_impact(session, disruption_id)
