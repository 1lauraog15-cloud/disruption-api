"""REST endpoints."""

import json
from typing import Any, TypeVar

from flask import Blueprint, Response, current_app, g, jsonify, request
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Airport,
    Disruption,
    DisruptionKind,
    DisruptionStatus,
    Flight,
    RecoveryAction,
)
from .schemas import (
    ActionIn,
    ActionOut,
    DisruptionIn,
    DisruptionOut,
    DisruptionPage,
    FlightIn,
    FlightOut,
    PageParams,
)
from .services import delay_stats
from .tasks import compute_impact

bp = Blueprint("api", __name__)


def db() -> Session:
    if "db" not in g:
        g.db = current_app.extensions["session_factory"]()
    return g.db  # type: ignore[no-any-return]


@bp.teardown_app_request
def close_db(_exc: BaseException | None) -> None:
    session = g.pop("db", None)
    if session is not None:
        session.close()


T = TypeVar("T", bound=BaseModel)


def parse(model: type[T]) -> T:
    """Validate the JSON body; raises ValidationError on bad input."""
    return model.model_validate(request.get_json(silent=True) or {})


@bp.errorhandler(ValidationError)
def handle_validation(exc: ValidationError) -> tuple[Response, int]:
    return jsonify(
        {
            "error": "validation_error",
            "details": json.loads(exc.json(include_url=False, include_context=False, include_input=False)),
        }
    ), 422


def not_found(what: str) -> tuple[Response, int]:
    return jsonify({"error": "not_found", "message": f"{what} not found"}), 404


@bp.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@bp.post("/airports")
def create_airport() -> tuple[Response, int]:
    data: dict[str, Any] = request.get_json(silent=True) or {}
    iata = str(data.get("iata", "")).upper()
    if len(iata) != 3 or not iata.isalpha():
        return jsonify({"error": "validation_error", "message": "iata must be 3 letters"}), 422
    if db().get(Airport, iata):
        return jsonify({"error": "conflict", "message": "airport exists"}), 409
    db().add(Airport(iata=iata, name=str(data.get("name", iata)), is_hub=bool(data.get("is_hub", False))))
    db().commit()
    return jsonify({"iata": iata}), 201


@bp.post("/flights")
def create_flight() -> tuple[Response, int]:
    body = parse(FlightIn)
    for code in (body.origin, body.destination):
        if db().get(Airport, code) is None:
            return jsonify({"error": "unknown_airport", "message": f"airport {code} not found"}), 422
    flight = Flight(**body.model_dump())
    db().add(flight)
    db().commit()
    return jsonify(FlightOut.model_validate(flight).model_dump(mode="json")), 201


@bp.get("/flights/<int:flight_id>")
def get_flight(flight_id: int) -> Response | tuple[Response, int]:
    flight = db().get(Flight, flight_id)
    if flight is None:
        return not_found("flight")
    return jsonify(FlightOut.model_validate(flight).model_dump(mode="json"))


@bp.post("/disruptions")
def create_disruption() -> tuple[Response, int]:
    body = parse(DisruptionIn)
    if db().get(Flight, body.flight_id) is None:
        return not_found("flight")
    disruption = Disruption(**body.model_dump())
    db().add(disruption)
    db().commit()
    compute_impact.delay(disruption.id)  # impact is filled in asynchronously
    return jsonify(DisruptionOut.model_validate(disruption).model_dump(mode="json")), 202


@bp.get("/disruptions")
def list_disruptions() -> Response | tuple[Response, int]:
    try:
        page = PageParams.model_validate(request.args.to_dict())
        conditions = []
        if page.status:
            conditions.append(Disruption.status == DisruptionStatus(page.status))
        if page.kind:
            conditions.append(Disruption.kind == DisruptionKind(page.kind))
    except (ValidationError, ValueError):
        return jsonify({"error": "validation_error", "message": "invalid status, kind, limit or offset"}), 422
    total = db().scalar(select(func.count()).select_from(Disruption).where(*conditions)) or 0
    rows = (
        db()
        .scalars(select(Disruption).where(*conditions).order_by(Disruption.id).limit(page.limit).offset(page.offset))
        .all()
    )
    body = DisruptionPage(
        items=[DisruptionOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )
    return jsonify(body.model_dump(mode="json"))


@bp.get("/disruptions/<int:disruption_id>")
def get_disruption(disruption_id: int) -> Response | tuple[Response, int]:
    d = db().get(Disruption, disruption_id)
    if d is None:
        return not_found("disruption")
    return jsonify(DisruptionOut.model_validate(d).model_dump(mode="json"))


@bp.patch("/disruptions/<int:disruption_id>/resolve")
def resolve_disruption(disruption_id: int) -> Response | tuple[Response, int]:
    d = db().get(Disruption, disruption_id)
    if d is None:
        return not_found("disruption")
    d.status = DisruptionStatus.RESOLVED
    db().commit()
    return jsonify(DisruptionOut.model_validate(d).model_dump(mode="json"))


@bp.post("/disruptions/<int:disruption_id>/actions")
def add_action(disruption_id: int) -> tuple[Response, int]:
    body = parse(ActionIn)
    if db().get(Disruption, disruption_id) is None:
        return not_found("disruption")
    action = RecoveryAction(disruption_id=disruption_id, **body.model_dump())
    db().add(action)
    db().commit()
    return jsonify(ActionOut.model_validate(action).model_dump(mode="json")), 201


@bp.get("/stats/delays")
def stats_delays() -> Response:
    rows = (
        db()
        .execute(
            select(Flight.origin, Disruption.delay_minutes)
            .join(Flight, Disruption.flight_id == Flight.id)
            .where(Disruption.kind == DisruptionKind.DELAY)
        )
        .all()
    )
    return jsonify(delay_stats([(o, m) for o, m in rows]))
