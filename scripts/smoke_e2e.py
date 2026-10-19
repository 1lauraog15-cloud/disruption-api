"""End-to-end check against a running stack (API + Postgres + Redis + Celery worker).

Usage: API_KEY=... python scripts/smoke_e2e.py [base_url]

Records a delay on a flight whose aircraft flies a later leg, then waits for the Celery worker to
fill in the impact and create the knock-on disruption. Exits non-zero on any failure.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
if not BASE.startswith(("http://", "https://")):
    sys.exit("base URL must start with http:// or https://")
KEY = os.environ["API_KEY"]
TIMEOUT_S = 90


def call(method: str, path: str, body: dict[str, Any] | None = None, key: str | None = KEY) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310 (scheme checked at the top)
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"null")


def wait_until(description: str, check: Any) -> Any:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            result = check()
        except (urllib.error.URLError, ConnectionError):
            result = None
        if result:
            print(f"ok: {description}")
            return result
        time.sleep(2)
    sys.exit(f"FAILED: timed out waiting for {description}")


def expect(description: str, got: int, want: int) -> None:
    if got != want:
        sys.exit(f"FAILED: {description}: expected HTTP {want}, got {got}")
    print(f"ok: {description}")


def main() -> None:
    wait_until("database readiness", lambda: call("GET", "/health/ready", key=None)[0] == 200)
    expect("protected endpoint rejects a request without a key", call("GET", "/disruptions", key=None)[0], 401)

    expect("create airport BCN", call("POST", "/airports", {"iata": "BCN", "name": "Barcelona"})[0], 201)
    expect("create hub MAD", call("POST", "/airports", {"iata": "MAD", "name": "Madrid", "is_hub": True})[0], 201)

    legs = [("XY1", "08:00", "09:00"), ("XY2", "10:00", "11:00")]
    flight_ids = []
    for number, dep, arr in legs:
        status, flight = call(
            "POST",
            "/flights",
            {
                "number": number,
                "origin": "BCN",
                "destination": "MAD",
                "scheduled_departure": f"2026-11-01T{dep}:00+00:00",
                "scheduled_arrival": f"2026-11-01T{arr}:00+00:00",
                "passengers": 180,
                "tail_number": "EC-AAA",
            },
        )
        expect(f"create flight {number}", status, 201)
        flight_ids.append(flight["id"])

    status, disruption = call(
        "POST", "/disruptions", {"flight_id": flight_ids[0], "kind": "delay", "delay_minutes": 60, "reason": "smoke"}
    )
    expect("record a 60-minute delay (accepted for background processing)", status, 202)
    did = disruption["id"]

    impact = wait_until(
        "worker filled in the impact",
        lambda: (d := call("GET", f"/disruptions/{did}")[1])["impact_score"] is not None and d,
    )
    print(f"    impact_score={impact['impact_score']} affected_connections={impact['affected_connections']}")

    cascade = wait_until(
        "worker created the knock-on delay",
        lambda: (c := call("GET", f"/disruptions/{did}/cascade")[1])["total"] >= 1 and c,
    )
    knock_on = cascade["affected_flights"][0]
    if (knock_on["flight_number"], knock_on["delay_minutes"]) != ("XY2", 45):
        sys.exit(f"FAILED: unexpected knock-on {knock_on}")
    print(f"ok: knock-on is {knock_on['flight_number']} late by {knock_on['delay_minutes']} min")

    status, page = call("GET", "/disruptions?status=open")
    expect("list open disruptions", status, 200)
    if page["total"] != 2:
        sys.exit(f"FAILED: expected 2 open disruptions (original + knock-on), got {page['total']}")
    print("ok: end-to-end flow works")


if __name__ == "__main__":
    main()
