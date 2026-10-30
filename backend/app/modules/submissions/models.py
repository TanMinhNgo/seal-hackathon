from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("team_id", "round_id", "version", name="uq_submission_version"),
        UniqueConstraint(
            "submitted_by", "team_id", "round_id", "idempotency_key", name="uq_submission_receipt"
        ),
        CheckConstraint("version >= 1", name="ck_submission_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    submitted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    repo_url: Mapped[str] = mapped_column(String(2048))
    commit_sha: Mapped[str] = mapped_column(String(40))
    demo_url: Mapped[str | None] = mapped_column(String(2048))
    video_url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    files: Mapped[list[SubmissionFile]] = relationship(lazy="raise")


class SubmissionFile(Base):
    __tablename__ = "submission_files"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    key: Mapped[str] = mapped_column(String(255), unique=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))


class FileUpload(Base):
    __tablename__ = "file_uploads"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeadlineReminder(Base):
    __tablename__ = "deadline_reminders"
    __table_args__ = (
        UniqueConstraint("team_id", "round_id", "hours", name="uq_deadline_reminder"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    hours: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="claimed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
