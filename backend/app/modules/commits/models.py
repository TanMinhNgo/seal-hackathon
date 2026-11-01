from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CommitSyncState(Base):
    __tablename__ = "commit_sync_states"
    __table_args__ = (
        CheckConstraint("sync_status IN ('pending','ok','error')", name="ck_commit_sync_status"),
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    branch: Mapped[str | None] = mapped_column(String(255))
    head_sha: Mapped[str | None] = mapped_column(String(40))
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(10), default="pending")
    sync_error: Mapped[str | None] = mapped_column(String(100))
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("team_id", "sha", name="uq_commits_team_sha"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    sha: Mapped[str] = mapped_column(String(40))
    author: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    branch: Mapped[str] = mapped_column(String(255))
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    additions: Mapped[int] = mapped_column(Integer)
    deletions: Mapped[int] = mapped_column(Integer)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline: Mapped[bool] = mapped_column(Boolean)
    in_event_window: Mapped[bool] = mapped_column(Boolean)
    url: Mapped[str] = mapped_column(String(2048))
    files: Mapped[list[dict]] = mapped_column(JSON)
    diff_truncated: Mapped[bool] = mapped_column(Boolean)
