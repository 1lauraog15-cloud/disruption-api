import pytest

from disruption_api.models import DisruptionKind as K
from disruption_api.services import delay_stats, estimate_impact


def test_short_delay_has_no_impact() -> None:
    impact = estimate_impact(K.DELAY, 30, 200, destination_is_hub=True)
    assert impact.affected_connections == 0 and impact.score == 0.0


def test_cancellation_hits_all_connections_at_hub() -> None:
    assert estimate_impact(K.CANCELLATION, 0, 200, destination_is_hub=True).affected_connections == 70


@pytest.mark.parametrize(("minutes", "expected"), [(60, 18), (120, 35), (240, 70), (900, 70)])
def test_delay_severity_grows_and_caps(minutes: int, expected: int) -> None:
    assert estimate_impact(K.DELAY, minutes, 200, destination_is_hub=True).affected_connections == expected


def test_non_hub_has_fewer_connections() -> None:
    hub = estimate_impact(K.DIVERSION, 0, 200, destination_is_hub=True)
    other = estimate_impact(K.DIVERSION, 0, 200, destination_is_hub=False)
    assert other.affected_connections < hub.affected_connections


def test_delay_stats_percentiles() -> None:
    stats = delay_stats([("BCN", m) for m in (10, 20, 30, 40, 100)] + [("MAD", 15)])
    bcn = next(s for s in stats if s["origin"] == "BCN")
    assert bcn["count"] == 5 and bcn["p50"] == 30.0 and bcn["p90"] == 76.0


def test_delay_stats_empty() -> None:
    assert delay_stats([]) == []
