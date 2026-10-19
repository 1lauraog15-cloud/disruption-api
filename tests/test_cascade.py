from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from disruption_api.models import Disruption, DisruptionKind, Flight
from disruption_api.services import MIN_TURNAROUND, Leg, propagate_delay
from disruption_api.tasks import apply_cascade

T0 = datetime(2026, 11, 1, 8, 0)


def leg(flight_id: int, departs_after_prev_arrival_min: int, prev_arrival: datetime, block_min: int = 60) -> Leg:
    departure = prev_arrival + timedelta(minutes=departs_after_prev_arrival_min)
    return Leg(flight_id, departure, departure + timedelta(minutes=block_min))


# --- pure propagation ------------------------------------------------------------------------------


def test_no_later_legs_means_no_knock_on() -> None:
    assert propagate_delay(90, T0, []) == []


@pytest.mark.parametrize(
    ("ground_min", "expected"),
    [
        (30, 90),  # tighter than the minimum turnaround: no slack, and no extra delay either
        (45, 90),  # exactly the minimum turnaround: nothing is absorbed
        (75, 60),  # 30 min of slack absorbed
        (135, 0),  # slack covers the whole delay
        (60, 75),
    ],
)
def test_slack_absorbs_delay(ground_min: int, expected: int) -> None:
    result = propagate_delay(90, T0, [leg(2, ground_min, T0)])
    assert (result[0][1] if result else 0) == expected


def test_delay_decays_along_the_rotation_and_stops() -> None:
    first = leg(2, 60, T0)  # 15 min slack
    second = leg(3, 60, first.arrival)  # 15 min slack
    third = leg(4, 200, second.arrival)  # 155 min slack: absorbs everything left
    fourth = leg(5, 45, third.arrival)  # never reached
    result = propagate_delay(50, T0, [first, second, third, fourth])
    assert result == [(2, 35), (3, 20)]


def test_minimum_turnaround_is_45_minutes() -> None:
    assert timedelta(minutes=45) == MIN_TURNAROUND


# --- task ------------------------------------------------------------------------------------------


def add_flight(session: Session, number: str, tail: str | None, dep: datetime, block_min: int = 60) -> Flight:
    f = Flight(
        number=number,
        origin="BCN",
        destination="MAD",
        scheduled_departure=dep,
        scheduled_arrival=dep + timedelta(minutes=block_min) if tail else None,
        passengers=100,
        tail_number=tail,
    )
    session.add(f)
    session.flush()
    return f


@pytest.fixture
def rotation(session: Session, airports: None) -> dict[str, Flight]:
    """EC-AAA flies XY1 08:00-09:00, XY2 10:00-11:00, XY3 12:00-13:00 (60 min on the ground, 15 min of slack)."""
    flights = {
        "XY1": add_flight(session, "XY1", "EC-AAA", T0),
        "XY2": add_flight(session, "XY2", "EC-AAA", T0 + timedelta(minutes=120)),
        "XY3": add_flight(session, "XY3", "EC-AAA", T0 + timedelta(minutes=240)),
        "XY9": add_flight(session, "XY9", "EC-BBB", T0 + timedelta(minutes=120)),
        "NOTAIL": add_flight(session, "NT1", None, T0 + timedelta(minutes=100)),
    }
    session.commit()
    return flights


def record(session: Session, flight: Flight, minutes: int, kind: DisruptionKind = DisruptionKind.DELAY) -> Disruption:
    d = Disruption(flight_id=flight.id, kind=kind, delay_minutes=minutes)
    session.add(d)
    session.commit()
    return d


def test_cascade_creates_knock_on_disruptions(session: Session, rotation: dict[str, Flight]) -> None:
    parent = record(session, rotation["XY1"], 60)
    ids = apply_cascade(session, parent.id)
    children = [session.get(Disruption, i) for i in ids]
    # 60 min late; each leg has 15 min of slack, so the delay shrinks 60 -> 45 -> 30
    assert [c.flight_id for c in children if c] == [rotation["XY2"].id, rotation["XY3"].id]
    assert [c.delay_minutes for c in children if c] == [45, 30]
    assert all(c and c.parent_id == parent.id and c.kind is DisruptionKind.DELAY for c in children)
    assert all(c and c.impact_score is not None for c in children)  # impact computed for each


def test_other_aircraft_and_untailed_flights_are_untouched(session: Session, rotation: dict[str, Flight]) -> None:
    parent = record(session, rotation["XY1"], 60)
    apply_cascade(session, parent.id)
    touched = {d.flight_id for d in session.query(Disruption).filter(Disruption.parent_id == parent.id)}
    assert rotation["XY9"].id not in touched and rotation["NOTAIL"].id not in touched


def test_cascade_is_idempotent(session: Session, rotation: dict[str, Flight]) -> None:
    parent = record(session, rotation["XY1"], 60)
    assert len(apply_cascade(session, parent.id)) == 2
    assert apply_cascade(session, parent.id) == []
    assert session.query(Disruption).filter(Disruption.parent_id == parent.id).count() == 2


def test_knock_on_disruptions_do_not_cascade_again(session: Session, rotation: dict[str, Flight]) -> None:
    parent = record(session, rotation["XY1"], 60)
    child_id = apply_cascade(session, parent.id)[0]
    assert apply_cascade(session, child_id) == []


@pytest.mark.parametrize("kind", [DisruptionKind.CANCELLATION, DisruptionKind.DIVERSION])
def test_only_delays_cascade(session: Session, rotation: dict[str, Flight], kind: DisruptionKind) -> None:
    assert apply_cascade(session, record(session, rotation["XY1"], 60, kind).id) == []


def test_flight_without_tail_number_does_not_cascade(session: Session, rotation: dict[str, Flight]) -> None:
    assert apply_cascade(session, record(session, rotation["NOTAIL"], 60).id) == []


def test_missing_disruption(session: Session) -> None:
    assert apply_cascade(session, 999) == []


# --- API -------------------------------------------------------------------------------------------


def flight_body(number: str, dep: str, arr: str | None, tail: str | None) -> dict[str, object]:
    return {
        "number": number,
        "origin": "BCN",
        "destination": "MAD",
        "scheduled_departure": dep,
        "scheduled_arrival": arr,
        "passengers": 120,
        "tail_number": tail,
    }


@pytest.mark.usefixtures("airports")
def test_flight_tail_number_requires_arrival(client: FlaskClient) -> None:
    resp = client.post("/flights", json=flight_body("XY1", "2026-11-01T08:00:00+00:00", None, "EC-AAA"))
    assert resp.status_code == 422


@pytest.mark.usefixtures("airports")
@pytest.mark.parametrize("tail", ["ec-aaa", "E", "EC AAA"])
def test_invalid_tail_number(client: FlaskClient, tail: str) -> None:
    body = flight_body("XY1", "2026-11-01T08:00:00+00:00", "2026-11-01T09:00:00+00:00", tail)
    assert client.post("/flights", json=body).status_code == 422


@pytest.mark.usefixtures("airports")
def test_arrival_must_be_after_departure(client: FlaskClient) -> None:
    body = flight_body("XY1", "2026-11-01T09:00:00+00:00", "2026-11-01T08:00:00+00:00", None)
    assert client.post("/flights", json=body).status_code == 422


@pytest.mark.usefixtures("airports")
def test_cascade_endpoint_lists_knock_on_flights(client: FlaskClient, session: Session, delay_task: MagicMock) -> None:
    ids = []
    for number, dep, arr in [
        ("XY1", "2026-11-01T08:00:00+00:00", "2026-11-01T09:00:00+00:00"),
        ("XY2", "2026-11-01T10:00:00+00:00", "2026-11-01T11:00:00+00:00"),
    ]:
        resp = client.post("/flights", json=flight_body(number, dep, arr, "EC-AAA"))
        assert resp.status_code == 201
        ids.append(resp.get_json()["id"])
    d = client.post("/disruptions", json={"flight_id": ids[0], "kind": "delay", "delay_minutes": 60}).get_json()
    assert apply_cascade(session, d["id"])  # the task body, run in-process
    body = client.get(f"/disruptions/{d['id']}/cascade").get_json()
    assert body["total"] == 1 and body["affected_flights"][0]["flight_number"] == "XY2"
    assert body["affected_flights"][0]["delay_minutes"] == 45
    assert body["affected_flights"][0]["tail_number"] == "EC-AAA"
    assert client.get(f"/disruptions/{body['affected_flights'][0]['disruption_id']}").get_json()["parent_id"] == d["id"]


def test_cascade_endpoint_404(client: FlaskClient) -> None:
    assert client.get("/disruptions/999/cascade").status_code == 404
