import json
import re

from flask import Flask
from flask.testing import FlaskClient

from disruption_api.openapi import build_spec

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
NOT_DOCUMENTED = {"/openapi.json", "/docs", "/static/<path:filename>"}


def flask_operations(app: Flask) -> set[tuple[str, str]]:
    ops = set()
    for rule in app.url_map.iter_rules():
        if rule.rule in NOT_DOCUMENTED:
            continue
        path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
        ops.update((path, m.lower()) for m in (rule.methods or set()) if m.lower() in HTTP_METHODS)
    return ops


def spec_operations() -> set[tuple[str, str]]:
    return {(path, m) for path, item in build_spec()["paths"].items() for m in item if m in HTTP_METHODS}


def test_spec_matches_the_routes_exactly(app: Flask) -> None:
    """Fails whenever someone adds, removes or renames a route without updating the docs."""
    assert flask_operations(app) == spec_operations()


def test_every_schema_reference_resolves() -> None:
    spec = build_spec()
    refs = set(re.findall(r'"#/components/schemas/(\w+)"', json.dumps(spec)))
    assert refs <= set(spec["components"]["schemas"])


def test_health_endpoints_are_the_only_public_paths() -> None:
    paths = build_spec()["paths"]
    public = {p for p, item in paths.items() if any(op.get("security") == [] for op in item.values())}
    assert public == {"/health", "/health/ready"}


def test_openapi_json_is_public(anon_client: FlaskClient) -> None:
    resp = anon_client.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["openapi"].startswith("3.0") and "DisruptionPage" in body["components"]["schemas"]
    assert body["components"]["securitySchemes"]["ApiKeyAuth"]["name"] == "X-API-Key"


def test_docs_page_is_public_and_points_to_spec(anon_client: FlaskClient) -> None:
    resp = anon_client.get("/docs")
    assert resp.status_code == 200 and b"/openapi.json" in resp.data
