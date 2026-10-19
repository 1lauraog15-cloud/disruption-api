import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient
from kombu.exceptions import OperationalError as KombuOperationalError

from disruption_api.errors import MAX_BODY_BYTES

ROOT = Path(__file__).resolve().parents[1]


# --- uniform errors and headers --------------------------------------------------------------------


def test_unknown_route_returns_json_404(client: FlaskClient) -> None:
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_wrong_method_returns_json_405_with_allow_header(client: FlaskClient) -> None:
    resp = client.delete("/flights/1")
    assert resp.status_code == 405
    assert resp.get_json()["error"] == "method_not_allowed"
    assert "GET" in resp.headers["Allow"]


def test_oversized_body_is_rejected_with_413(client: FlaskClient) -> None:
    resp = client.post("/flights", data=b"x" * (MAX_BODY_BYTES + 1), content_type="application/json")
    assert resp.status_code == 413
    assert resp.get_json()["error"] == "request_entity_too_large"


def test_unexpected_error_is_a_generic_500_without_internals(app: Flask, client: FlaskClient) -> None:
    @app.get("/boom")
    def boom() -> str:
        raise RuntimeError("secret internal detail")

    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "internal_error", "message": "unexpected error"}
    assert b"secret internal detail" not in resp.data


def test_json_responses_are_not_cached_and_not_sniffed(client: FlaskClient) -> None:
    resp = client.get("/health")
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_docs_page_is_not_marked_no_store(anon_client: FlaskClient) -> None:
    resp = anon_client.get("/docs")
    assert "Cache-Control" not in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# --- airports are validated like everything else ---------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"iata": "BCN", "is_hub": "false"},  # a string must not count as true
        {"iata": "BCN", "name": "x" * 121},
        {"iata": "BCN", "name": ""},
        {"iata": 123},
        {},
    ],
)
def test_airport_validation(client: FlaskClient, body: dict[str, object]) -> None:
    assert client.post("/airports", json=body).status_code == 422


def test_airport_iata_is_upper_cased_and_name_defaults(client: FlaskClient) -> None:
    assert client.post("/airports", json={"iata": "lhr"}).get_json() == {"iata": "LHR"}
    assert client.post("/airports", json={"iata": "LHR"}).status_code == 409


# --- queue failure does not lose the record --------------------------------------------------------


@pytest.mark.usefixtures("airports")
def test_disruption_is_kept_when_the_queue_is_down(
    client: FlaskClient, flight_payload: dict[str, object], delay_task: MagicMock
) -> None:
    fid = client.post("/flights", json=flight_payload).get_json()["id"]
    delay_task.side_effect = KombuOperationalError("broker down")
    resp = client.post("/disruptions", json={"flight_id": fid, "kind": "delay", "delay_minutes": 60})
    assert resp.status_code == 202
    assert resp.get_json()["impact_score"] is None
    assert client.get(f"/disruptions/{resp.get_json()['id']}").status_code == 200


# --- repository hygiene ----------------------------------------------------------------------------


def _names(requirements: list[str]) -> set[str]:
    out = set()
    for line in requirements:
        name = line.strip().split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip()
        if name and not name.startswith("#"):
            out.add(name.lower())
    return out


def test_requirements_txt_matches_pyproject_dependencies() -> None:
    """The Docker image installs requirements.txt; fail if it drifts from pyproject.toml."""
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pinned = (ROOT / "requirements.txt").read_text().splitlines()
    assert _names(declared) == _names(pinned)


def test_celery_only_accepts_json() -> None:
    from disruption_api.celery_app import celery

    assert list(celery.conf.accept_content) == ["json"]


def test_no_debug_mode_in_source() -> None:
    source = "".join(p.read_text() for p in (ROOT / "disruption_api").glob("*.py"))
    assert "debug=True" not in source
    assert "app.run(" not in source
