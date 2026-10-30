from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','open','ongoing','judging','closed')", name="ck_events_status"
        ),
        CheckConstraint(
            "min_team_size >= 1 AND max_team_size >= min_team_size", name="ck_events_team_size"
        ),
        CheckConstraint(
            "registration_opens_at < registration_closes_at "
            "AND registration_closes_at <= starts_at AND starts_at < ends_at",
            name="ck_events_schedule",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[str] = mapped_column(Text, default="")
    banner_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    registration_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    min_team_size: Mapped[int] = mapped_column(Integer, default=1)
    max_team_size: Mapped[int] = mapped_column(Integer, default=5)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Round(Base):
    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("event_id", "order", name="uq_rounds_event_order"),
        CheckConstraint('"order" >= 1 AND required_judges >= 1', name="ck_rounds_numbers"),
        CheckConstraint(
            "starts_at < submission_deadline AND submission_deadline <= ends_at",
            name="ck_rounds_schedule",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submission_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    required_judges: Mapped[int] = mapped_column(Integer, default=2)


class Track(Base):
    __tablename__ = "tracks"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")


class Prize(Base):
    __tablename__ = "prizes"
    __table_args__ = (CheckConstraint("rank >= 1 AND value >= 0", name="ck_prizes_numbers"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    rank: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class RoundEligibility(Base):
    __tablename__ = "round_eligibilities"
    __table_args__ = (UniqueConstraint("round_id", "team_id", name="uq_round_eligibility"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    source_round_id: Mapped[UUID | None] = mapped_column(ForeignKey("rounds.id"), index=True)
