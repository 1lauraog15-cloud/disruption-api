"""Pydantic models: validate what comes in and shape what goes out."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import DisruptionKind, DisruptionStatus

Iata = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class FlightIn(BaseModel):
    number: Annotated[str, Field(min_length=3, max_length=8)]
    origin: Iata
    destination: Iata
    scheduled_departure: datetime
    passengers: Annotated[int, Field(ge=0, le=900)]

    @field_validator("scheduled_departure")
    @classmethod
    def to_naive_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC).replace(tzinfo=None) if v.tzinfo else v


class FlightOut(FlightIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DisruptionIn(BaseModel):
    flight_id: int
    kind: DisruptionKind
    delay_minutes: Annotated[int, Field(ge=0, le=2880)] = 0
    reason: Annotated[str, Field(max_length=500)] = ""


class DisruptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    flight_id: int
    kind: DisruptionKind
    status: DisruptionStatus
    delay_minutes: int
    reason: str
    affected_connections: int | None
    impact_score: float | None


class ActionIn(BaseModel):
    action_type: Annotated[str, Field(min_length=2, max_length=40)]
    note: Annotated[str, Field(max_length=500)] = ""


class ActionOut(ActionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    disruption_id: int


class PageParams(BaseModel):
    """Query string for GET /disruptions."""

    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0
    status: str | None = None
    kind: str | None = None


class DisruptionPage(BaseModel):
    items: list[DisruptionOut]
    total: int
    limit: int
    offset: int
