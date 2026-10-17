"""Business logic kept apart from HTTP: impact estimate and delay statistics."""

from dataclasses import dataclass

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
