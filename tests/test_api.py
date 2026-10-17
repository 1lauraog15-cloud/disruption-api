from unittest.mock import MagicMock

import pytest
from flask.testing import FlaskClient

pytestmark = pytest.mark.usefixtures("airports")


def make_flight(client: FlaskClient, payload: dict[str, object]) -> int:
    resp = client.post("/flights", json=payload)
    assert resp.status_code == 201
    return int(resp.get_json()["id"])


def test_health(client: FlaskClient) -> None:
    assert client.get("/health").get_json() == {"status": "ok"}


def test_create_and_get_flight(client: FlaskClient, flight_payload: dict[str, object]) -> None:
    fid = make_flight(client, flight_payload)
    got = client.get(f"/flights/{fid}").get_json()
    assert got["number"] == "XY123" and got["passengers"] == 180


@pytest.mark.parametrize(
    "change",
    [{"origin": "bcn"}, {"passengers": -1}, {"number": "A"}, {"passengers": "many"}],
)
def test_flight_validation_errors(
    client: FlaskClient, flight_payload: dict[str, object], change: dict[str, object]
) -> None:
    resp = client.post("/flights", json={**flight_payload, **change})
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "validation_error"


def test_flight_unknown_airport(client: FlaskClient, flight_payload: dict[str, object]) -> None:
    resp = client.post("/flights", json={**flight_payload, "destination": "ZZZ"})
    assert resp.status_code == 422 and resp.get_json()["error"] == "unknown_airport"


def test_missing_flight_404(client: FlaskClient) -> None:
    assert client.get("/flights/999").status_code == 404


def test_create_disruption_enqueues_task(
    client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock
) -> None:
    fid = make_flight(client, flight_payload)
    resp = client.post(
        "/disruptions", json={"flight_id": fid, "kind": "delay", "delay_minutes": 90, "reason": "weather"}
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] == "open" and body["impact_score"] is None
    delay_task.assert_called_once_with(body["id"])


def test_disruption_for_missing_flight(client: FlaskClient, delay_task: MagicMock) -> None:
    resp = client.post("/disruptions", json={"flight_id": 42, "kind": "delay"})
    assert resp.status_code == 404
    delay_task.assert_not_called()


def test_disruption_invalid_kind(client: FlaskClient, delay_task: MagicMock) -> None:
    assert client.post("/disruptions", json={"flight_id": 1, "kind": "strike"}).status_code == 422


def test_list_filter_resolve_and_actions(
    client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock
) -> None:
    fid = make_flight(client, flight_payload)
    a = client.post("/disruptions", json={"flight_id": fid, "kind": "delay", "delay_minutes": 70}).get_json()["id"]
    client.post("/disruptions", json={"flight_id": fid, "kind": "cancellation"})
    assert client.get("/disruptions").get_json()["total"] == 2
    assert client.get("/disruptions?kind=cancellation").get_json()["total"] == 1
    assert client.get("/disruptions?status=bogus").status_code == 422

    act = client.post(f"/disruptions/{a}/actions", json={"action_type": "rebook", "note": "next flight"})
    assert act.status_code == 201 and act.get_json()["disruption_id"] == a
    assert client.post("/disruptions/999/actions", json={"action_type": "rebook"}).status_code == 404

    assert client.patch(f"/disruptions/{a}/resolve").get_json()["status"] == "resolved"
    assert client.get("/disruptions?status=open").get_json()["total"] == 1


def test_stats_endpoint(client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock) -> None:
    fid = make_flight(client, flight_payload)
    for m in (10, 50, 90):
        client.post("/disruptions", json={"flight_id": fid, "kind": "delay", "delay_minutes": m})
    stats = client.get("/stats/delays").get_json()
    assert stats == [{"origin": "BCN", "count": 3, "p50": 50.0, "p90": 82.0}]


def test_airport_create_conflict_and_validation(client: FlaskClient) -> None:
    assert client.post("/airports", json={"iata": "lhr", "name": "Heathrow", "is_hub": True}).status_code == 201
    assert client.post("/airports", json={"iata": "LHR"}).status_code == 409
    assert client.post("/airports", json={"iata": "L1"}).status_code == 422


def test_resolve_and_get_missing_disruption(client: FlaskClient) -> None:
    assert client.patch("/disruptions/77/resolve").status_code == 404
    assert client.get("/disruptions/77").status_code == 404


def test_pagination_pages_and_total(
    client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock
) -> None:
    fid = make_flight(client, flight_payload)
    for m in range(5):
        client.post("/disruptions", json={"flight_id": fid, "kind": "delay", "delay_minutes": m})
    first = client.get("/disruptions?limit=2").get_json()
    assert [d["delay_minutes"] for d in first["items"]] == [0, 1]
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    last = client.get("/disruptions?limit=2&offset=4").get_json()
    assert [d["delay_minutes"] for d in last["items"]] == [4] and last["total"] == 5
    assert client.get("/disruptions?offset=10").get_json()["items"] == []


def test_pagination_total_respects_filters(
    client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock
) -> None:
    fid = make_flight(client, flight_payload)
    client.post("/disruptions", json={"flight_id": fid, "kind": "delay"})
    client.post("/disruptions", json={"flight_id": fid, "kind": "cancellation"})
    page = client.get("/disruptions?kind=delay&limit=1").get_json()
    assert page["total"] == 1 and len(page["items"]) == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=abc", "offset=-1"])
def test_pagination_rejects_bad_params(client: FlaskClient, query: str) -> None:
    assert client.get(f"/disruptions?{query}").status_code == 422
