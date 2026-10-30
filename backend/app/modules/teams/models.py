from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("id", "event_id", name="uq_teams_id_event"),
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_teams_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    track_id: Mapped[UUID | None] = mapped_column(ForeignKey("tracks.id"), index=True)
    leader_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    invite_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repo_url: Mapped[str | None] = mapped_column(String(2048))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disbanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    members: Mapped[list["TeamMember"]] = relationship(lazy="raise", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_team_members_event_user"),
        ForeignKeyConstraint(
            ["team_id", "event_id"],
            ["teams.id", "teams.event_id"],
            name="fk_team_members_team_event",
        ),
        CheckConstraint("status IN ('pending','active')", name="ck_team_members_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
