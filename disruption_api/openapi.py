"""OpenAPI 3.0 description of the API, built from the Pydantic models, plus a Swagger UI page."""

from typing import Any

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel

from .schemas import (
    ActionIn,
    ActionOut,
    DisruptionIn,
    DisruptionOut,
    DisruptionPage,
    FlightIn,
    FlightOut,
)

docs = Blueprint("docs", __name__)

MODELS: list[type[BaseModel]] = [FlightIn, FlightOut, DisruptionIn, DisruptionOut, DisruptionPage, ActionIn, ActionOut]

SWAGGER_UI_VERSION = "5.17.14"


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json(schema: dict[str, Any]) -> dict[str, Any]:
    return {"application/json": {"schema": schema}}


def _responses(ok: str, schema: dict[str, Any] | None, *errors: str) -> dict[str, Any]:
    out: dict[str, Any] = {ok: {"description": "Success"}}
    if schema is not None:
        out[ok]["content"] = _json(schema)
    descriptions = {
        "401": "Missing or invalid API key",
        "404": "Resource not found",
        "409": "Conflict",
        "422": "Invalid input",
        "503": "Database unavailable",
    }
    for code in errors:
        out[code] = {"description": descriptions[code], "content": _json(_ref("Error"))}
    return out


def _id_param(name: str) -> dict[str, Any]:
    return {"name": name, "in": "path", "required": True, "schema": {"type": "integer"}}


def _components() -> dict[str, Any]:
    schemas: dict[str, Any] = {
        "Error": {
            "type": "object",
            "properties": {"error": {"type": "string"}, "message": {"type": "string"}},
            "required": ["error"],
        },
        "AirportIn": {
            "type": "object",
            "properties": {
                "iata": {"type": "string", "pattern": "^[A-Za-z]{3}$"},
                "name": {"type": "string"},
                "is_hub": {"type": "boolean", "default": False},
            },
            "required": ["iata"],
        },
        "DelayStat": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "count": {"type": "integer"},
                "p50": {"type": "number"},
                "p90": {"type": "number"},
            },
        },
    }
    for model in MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    return {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        "schemas": schemas,
    }


def build_spec() -> dict[str, Any]:
    list_params = [
        {"name": "status", "in": "query", "schema": {"type": "string", "enum": ["open", "resolved"]}},
        {"name": "kind", "in": "query", "schema": {"type": "string", "enum": ["delay", "cancellation", "diversion"]}},
        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}},
        {"name": "offset", "in": "query", "schema": {"type": "integer", "minimum": 0, "default": 0}},
    ]
    public: list[dict[str, Any]] = []
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Disruption API",
            "version": "0.1.0",
            "description": "Track flight disruptions (delays, cancellations, diversions). Synthetic data only.",
        },
        "security": [{"ApiKeyAuth": []}],
        "paths": {
            "/health": {
                "get": {"summary": "Liveness", "security": public, "responses": _responses("200", None)},
            },
            "/health/ready": {
                "get": {
                    "summary": "Readiness (checks the database)",
                    "security": public,
                    "responses": _responses("200", None, "503"),
                },
            },
            "/airports": {
                "post": {
                    "summary": "Register an airport",
                    "requestBody": {"required": True, "content": _json(_ref("AirportIn"))},
                    "responses": _responses("201", None, "401", "409", "422"),
                },
            },
            "/flights": {
                "post": {
                    "summary": "Create a flight",
                    "requestBody": {"required": True, "content": _json(_ref("FlightIn"))},
                    "responses": _responses("201", _ref("FlightOut"), "401", "422"),
                },
            },
            "/flights/{flight_id}": {
                "get": {
                    "summary": "Get a flight",
                    "parameters": [_id_param("flight_id")],
                    "responses": _responses("200", _ref("FlightOut"), "401", "404"),
                },
            },
            "/disruptions": {
                "get": {
                    "summary": "List disruptions (paginated, filterable)",
                    "parameters": list_params,
                    "responses": _responses("200", _ref("DisruptionPage"), "401", "422"),
                },
                "post": {
                    "summary": "Record a disruption; impact is computed in the background",
                    "requestBody": {"required": True, "content": _json(_ref("DisruptionIn"))},
                    "responses": _responses("202", _ref("DisruptionOut"), "401", "404", "422"),
                },
            },
            "/disruptions/{disruption_id}": {
                "get": {
                    "summary": "Get a disruption",
                    "parameters": [_id_param("disruption_id")],
                    "responses": _responses("200", _ref("DisruptionOut"), "401", "404"),
                },
            },
            "/disruptions/{disruption_id}/resolve": {
                "patch": {
                    "summary": "Mark a disruption as resolved",
                    "parameters": [_id_param("disruption_id")],
                    "responses": _responses("200", _ref("DisruptionOut"), "401", "404"),
                },
            },
            "/disruptions/{disruption_id}/actions": {
                "post": {
                    "summary": "Log a recovery action",
                    "parameters": [_id_param("disruption_id")],
                    "requestBody": {"required": True, "content": _json(_ref("ActionIn"))},
                    "responses": _responses("201", _ref("ActionOut"), "401", "404", "422"),
                },
            },
            "/stats/delays": {
                "get": {
                    "summary": "Median and p90 delay per origin airport",
                    "responses": _responses("200", {"type": "array", "items": _ref("DelayStat")}, "401"),
                },
            },
        },
        "components": _components(),
    }


@docs.get("/openapi.json")
def openapi_json() -> Response:
    return jsonify(build_spec())


@docs.get("/docs")
def swagger_ui() -> Response:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Disruption API docs</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui-bundle.js"></script>
  <script>SwaggerUIBundle({{url: "/openapi.json", dom_id: "#swagger-ui"}});</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
