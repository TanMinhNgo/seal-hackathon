from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AiBudget(Base):
    __tablename__ = "ai_budgets"
    __table_args__ = (
        CheckConstraint("tokens_used >= 0 AND token_budget > 0", name="ck_ai_budget"),
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), primary_key=True, index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), primary_key=True, index=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    token_budget: Mapped[int] = mapped_column(Integer)


class ReviewJob(Base):
    __tablename__ = "ai_review_jobs"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "round_id", "base_sha", "head_sha", "prompt_version", name="uq_ai_job_window"
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','skipped','failed')", name="ck_ai_job_status"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 4 AND tokens_used >= 0", name="ck_ai_job_attempts"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    base_sha: Mapped[str] = mapped_column(String(40))
    head_sha: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(40))
    config: Mapped[dict] = mapped_column(JSON)
    commit_shas: Mapped[list] = mapped_column(JSON)
    repo_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class CommitReview(Base):
    __tablename__ = "commit_reviews"
    __table_args__ = (
        CheckConstraint("overall BETWEEN 0 AND 10 AND weight > 0", name="ck_commit_review_score"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ai_review_jobs.id"), unique=True, index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    commit_shas: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    scores: Mapped[dict] = mapped_column(JSON)
    overall: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(20))
    critical: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[str] = mapped_column(Text)
    issues: Mapped[list] = mapped_column(JSON)
    coverage: Mapped[dict] = mapped_column(JSON)
    weight: Mapped[int] = mapped_column(Integer)
    tokens_used: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class ReviewFlag(Base):
    __tablename__ = "review_flags"
    __table_args__ = (
        UniqueConstraint("review_id", "judge_id", name="uq_review_flag_judge"),
        CheckConstraint(
            "status IN ('open','acknowledged','dismissed')", name="ck_review_flag_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("commit_reviews.id"), index=True)
    judge_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
