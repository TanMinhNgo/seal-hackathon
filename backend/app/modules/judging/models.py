from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("round_id", "order", name="uq_rubric_order"),
        CheckConstraint("weight >= 0 AND max_score > 0", name="ck_rubric_numbers"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    max_score: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    order: Mapped[int]


class Conflict(Base):
    __tablename__ = "conflicts"
    __table_args__ = (UniqueConstraint("judge_id", "team_id", name="uq_conflict_pair"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    judge_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index(
            "uq_active_assignment",
            "round_id",
            "judge_id",
            "team_id",
            unique=True,
            postgresql_where=text("status != 'cancelled'"),
            sqlite_where=text("status != 'cancelled'"),
        ),
        CheckConstraint(
            "status IN ('pending','draft','submitted','cancelled')", name="ck_assignment_status"
        ),
        CheckConstraint("revision >= 0", name="ck_assignment_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    judge_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    submission_id: Mapped[UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    revision: Mapped[int] = mapped_column(default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    general_comment: Mapped[str | None] = mapped_column(Text)


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("assignment_id", "criterion_id", name="uq_score_criterion"),
        CheckConstraint("score >= 0", name="ck_score_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("assignments.id"), index=True)
    criterion_id: Mapped[UUID] = mapped_column(ForeignKey("rubric_criteria.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    comment: Mapped[str | None] = mapped_column(Text)


class RoundJudging(Base):
    __tablename__ = "round_judging"
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), primary_key=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_revision: Mapped[int] = mapped_column(default=0)
    cache_revision: Mapped[int] = mapped_column(default=0)


class PublicationSnapshot(Base):
    __tablename__ = "publication_snapshots"
    __table_args__ = (UniqueConstraint("round_id", "revision", name="uq_publication_revision"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    revision: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResultEmail(Base):
    __tablename__ = "result_emails"
    __table_args__ = (UniqueConstraint("snapshot_id", "user_id", name="uq_result_email"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("publication_snapshots.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(254))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class MentorAssignment(Base):
    __tablename__ = "mentor_assignments"
    __table_args__ = (
        Index(
            "uq_active_mentor_assignment",
            "mentor_id",
            "team_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    mentor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MentorNote(Base):
    __tablename__ = "mentor_notes"
    __table_args__ = (
        Index("ix_mentor_notes_team_commit", "team_id", "commit_sha"),
        CheckConstraint(
            "(kind = 'feedback' AND progress_status IS NULL) OR "
            "(kind = 'progress' AND progress_status IN ('on_track','at_risk','blocked'))",
            name="ck_mentor_note_kind",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    mentor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20), default="feedback")
    progress_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MentorQuestion(Base):
    __tablename__ = "mentor_questions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','answered','resolved')", name="ck_mentor_question_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    content: Mapped[str] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MentorAnswer(Base):
    __tablename__ = "mentor_answers"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("mentor_questions.id"), index=True)
    mentor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
