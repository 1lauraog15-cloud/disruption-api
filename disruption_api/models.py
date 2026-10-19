"""SQLAlchemy 2.0 models: airports, flights, disruptions and recovery actions."""

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DisruptionKind(enum.StrEnum):
    DELAY = "delay"
    CANCELLATION = "cancellation"
    DIVERSION = "diversion"


class DisruptionStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Airport(Base):
    __tablename__ = "airports"

    iata: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    is_hub: Mapped[bool] = mapped_column(default=False)


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (
        CheckConstraint("passengers >= 0", name="ck_flights_passengers_nonneg"),
        CheckConstraint("origin <> destination", name="ck_flights_origin_ne_dest"),
        CheckConstraint(
            "scheduled_arrival IS NULL OR scheduled_arrival > scheduled_departure",
            name="ck_flights_arrival_after_departure",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(8), index=True)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.iata"))
    destination: Mapped[str] = mapped_column(ForeignKey("airports.iata"))
    scheduled_departure: Mapped[datetime] = mapped_column(DateTime)
    passengers: Mapped[int] = mapped_column(Integer, default=0)
    # The aircraft flying this leg; flights sharing a tail number form its rotation.
    tail_number: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    scheduled_arrival: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    disruptions: Mapped[list["Disruption"]] = relationship(back_populates="flight")


class Disruption(Base):
    __tablename__ = "disruptions"
    __table_args__ = (
        CheckConstraint("delay_minutes >= 0", name="ck_disruptions_delay_nonneg"),
        Index("ix_disruptions_status_kind", "status", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"))
    kind: Mapped[DisruptionKind] = mapped_column(Enum(DisruptionKind, native_enum=False, length=20))
    status: Mapped[DisruptionStatus] = mapped_column(
        Enum(DisruptionStatus, native_enum=False, length=20), default=DisruptionStatus.OPEN
    )
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Filled in by the background task after the disruption is created.
    affected_connections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact_score: Mapped[float | None] = mapped_column(nullable=True)
    # Set on knock-on disruptions: the disruption that caused this one.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("disruptions.id"), index=True, nullable=True)

    flight: Mapped[Flight] = relationship(back_populates="disruptions")
    actions: Mapped[list["RecoveryAction"]] = relationship(back_populates="disruption")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    disruption_id: Mapped[int] = mapped_column(ForeignKey("disruptions.id"))
    action_type: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    disruption: Mapped[Disruption] = relationship(back_populates="actions")
