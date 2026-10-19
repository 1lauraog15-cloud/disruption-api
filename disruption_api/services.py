"""Business logic kept apart from HTTP: impact estimate and delay statistics."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from .models import DisruptionKind

# Share of passengers assumed to connect, by airport type (synthetic assumption).
CONNECTING_SHARE_HUB = 0.35
CONNECTING_SHARE_OTHER = 0.10


@dataclass(frozen=True)
class Impact:
    affected_connections: int
    score: float


def estimate_impact(kind: DisruptionKind, delay_minutes: int, passengers: int, destination_is_hub: bool) -> Impact:
    """Rough impact of a disruption. Cancellations hit everyone; delays only past 45 min."""
    share = CONNECTING_SHARE_HUB if destination_is_hub else CONNECTING_SHARE_OTHER
    connecting = round(passengers * share)
    if kind is DisruptionKind.CANCELLATION:
        severity = 1.0
    elif kind is DisruptionKind.DIVERSION:
        severity = 0.8
    else:
        severity = 0.0 if delay_minutes <= 45 else min(delay_minutes / 240, 1.0)
    return Impact(affected_connections=round(connecting * severity), score=round(severity * passengers, 1))


def delay_stats(rows: list[tuple[str, int]]) -> list[dict[str, float | int | str]]:
    """Median, 90th percentile and count of delay minutes per origin airport."""
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=["origin", "delay_minutes"])
    grouped = df.groupby("origin")["delay_minutes"]
    out = pd.DataFrame(
        {"count": grouped.size(), "p50": grouped.quantile(0.5), "p90": grouped.quantile(0.9)}
    ).reset_index()
    return [
        {"origin": str(r.origin), "count": int(r["count"]), "p50": float(r.p50), "p90": float(r.p90)}
        for _, r in out.iterrows()
    ]


MIN_TURNAROUND = timedelta(minutes=45)


@dataclass(frozen=True)
class Leg:
    """One later flight of the same aircraft."""

    flight_id: int
    departure: datetime
    arrival: datetime


def propagate_delay(delay_minutes: int, arrival: datetime, later_legs: list[Leg]) -> list[tuple[int, int]]:
    """Knock-on delays along an aircraft's rotation.

    `arrival` is the scheduled arrival of the delayed flight and `later_legs` its following legs in
    departure order. The slack before each leg (ground time beyond the minimum turnaround) absorbs
    delay; whatever remains is passed on. Stops as soon as a leg absorbs all of it.
    Returns (flight_id, delay_minutes) for each leg that ends up late.
    """
    result: list[tuple[int, int]] = []
    delay = delay_minutes
    previous_arrival = arrival
    for leg in later_legs:
        # A schedule tighter than the minimum turnaround has no slack, but it never adds delay by itself.
        slack = max(0.0, (leg.departure - previous_arrival - MIN_TURNAROUND).total_seconds() / 60)
        delay = max(0, round(delay - slack))
        if delay == 0:
            break
        result.append((leg.flight_id, delay))
        previous_arrival = leg.arrival
    return result
