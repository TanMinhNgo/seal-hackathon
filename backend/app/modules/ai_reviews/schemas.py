from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.schemas import Output
from app.modules.auth.schemas import Input
from app.modules.events.schemas import UserBrief

Score = Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)]
Verdict = Literal["good", "pass", "needs_improvement"]
FlagStatus = Literal["none", "open", "acknowledged", "dismissed"]


class Scores(Input):
    correctness: Score
    security: Score
    clean_code: Score
    structure: Score
    error_handling: Score
    testing: Score
    commit_hygiene: Score


class Issue(Input):
    file: str = Field(min_length=1, max_length=500)
    line: int | None = Field(ge=1)
    severity: Literal["low", "medium", "high"]
    category: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(max_length=2000)


class LlmReview(Input):
    scores: Scores
    summary: str = Field(min_length=1, max_length=4000)
    issues: list[Issue] = Field(max_length=50)


class Coverage(Output):
    reviewed_files: int
    omitted_files: int
    truncated: bool


class ReviewOutput(Output):
    id: UUID
    round_id: UUID
    commit_shas: list[str]
    model: str
    prompt_version: str
    scores: Scores
    overall: float
    verdict: Verdict
    critical: bool
    summary: str
    issues: list[Issue]
    coverage: Coverage
    tokens_used: int
    flagged: bool
    flag_status: FlagStatus
    created_at: datetime


class FlagInput(Input):
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class ResolveInput(Input):
    decision: Literal["acknowledged", "dismissed"]
    note: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class FlagOutput(Output):
    id: UUID
    review_id: UUID
    judge: UserBrief
    reason: str
    status: Literal["open", "acknowledged", "dismissed"]
    resolution_note: str | None
    resolved_at: datetime | None
    created_at: datetime


class RetryInput(Input):
    job_id: UUID


class RetryOutput(Output):
    job_id: UUID
    status: Literal["queued"] = "queued"


class JobCounts(Output):
    queued: int = 0
    running: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0


class LastJob(Output):
    id: UUID
    round_id: UUID
    status: Literal["queued", "running", "completed", "skipped", "failed"]
    error_code: str | None
    attempts: int
    can_retry: bool


class TimelinePoint(Output):
    at: datetime
    score: float


class IssueCount(Output):
    category: str
    count: int


class AiSummary(Output):
    avg_score: float | None
    verdict_counts: dict[Verdict, int]
    critical_count: int
    timeline: list[TimelinePoint]
    top_issues: list[IssueCount]
    score_spike: bool
    jobs: JobCounts | None = Field(default=None, exclude_if=lambda v: v is None)
    last_job: LastJob | None = None
    tokens_used: int | None = Field(default=None, exclude_if=lambda v: v is None)
    token_budget: int | None = Field(default=None, exclude_if=lambda v: v is None)
    budget_exhausted: bool | None = Field(default=None, exclude_if=lambda v: v is None)
