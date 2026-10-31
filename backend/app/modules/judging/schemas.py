from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.core.schemas import Output, Page
from app.modules.auth.schemas import Input
from app.modules.events.schemas import UserBrief
from app.modules.submissions.schemas import SubmissionOutput

Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Number = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=12, decimal_places=4)]
TeamIDs = Annotated[list[UUID], Field(min_length=1, max_length=100)]
CommitSHA = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class CriterionInput(Input):
    name: Name
    description: str = Field(default="", max_length=5000)
    weight: Number = Field(ge=0, le=100)
    max_score: Number = Field(gt=0)
    order: int = Field(ge=1)


class Criterion(CriterionInput, Output):
    id: UUID


class RubricInput(Input):
    criteria: list[CriterionInput] = Field(min_length=1, max_length=100)


class Rubric(Output):
    round_id: UUID
    criteria: list[Criterion]


class ReasonInput(Input):
    reason: Content


class ConflictInput(ReasonInput):
    team_id: UUID


class ConflictOutput(Output):
    id: UUID
    judge: UserBrief
    team_id: UUID
    reason: str
    created_at: datetime


class AssignmentInput(Input):
    judge_id: UUID
    team_ids: TeamIDs


class AutoInput(Input):
    judges_per_team: int = Field(ge=1, le=100)


class TeamBrief(Output):
    id: UUID
    name: str
    track_id: UUID | None


class AssignmentOutput(Output):
    id: UUID
    round_id: UUID
    judge: UserBrief
    team: TeamBrief
    submission_id: UUID
    status: Literal["pending", "draft", "submitted", "cancelled"]
    revision: int
    submitted_at: datetime | None


class Skipped(Output):
    team_id: UUID
    code: str


class Unfilled(Output):
    team_id: UUID
    missing_judges: int


class AssignmentBatch(Output):
    items: list[AssignmentOutput]
    skipped: list[Skipped]
    unfilled: list[Unfilled]


class RevisionInput(Input):
    expected_revision: int = Field(ge=0)


class ScoreInput(Input):
    criterion_id: UUID
    score: Number
    comment: Content | None = None


class ScoresInput(RevisionInput):
    scores: list[ScoreInput] = Field(max_length=100)
    general_comment: Content | None = None


class ScoreOutput(Output):
    criterion_id: UUID
    score: Decimal
    comment: str | None


class ScoresOutput(Output):
    assignment: AssignmentOutput
    scores: list[ScoreOutput]
    general_comment: str | None


class AssignmentDetail(ScoresOutput):
    submission: SubmissionOutput
    rubric: Rubric


class MentorAssignmentInput(Input):
    mentor_id: UUID
    team_ids: TeamIDs


class MentorTeam(Output):
    id: UUID
    name: str


class MentorAssignmentOutput(Output):
    id: UUID
    event_id: UUID
    mentor: UserBrief
    team: MentorTeam
    created_at: datetime


class MentorBatch(Output):
    items: list[MentorAssignmentOutput]


class EligibilityInput(Input):
    source_round_id: UUID
    team_ids: list[UUID] = Field(max_length=100)


class RoundTeam(Output):
    team_id: UUID
    name: str
    source_round_id: UUID | None


class Progress(Output):
    team: TeamBrief
    required: int
    assigned: int
    submitted: int
    missing: int
    has_conflict: bool
    status: Literal["not_submitted", "pending", "complete"]


class JudgingProgress(Page[Progress], Output):
    locked_at: datetime | None
    published_at: datetime | None


class CriterionAverage(Output):
    criterion_id: UUID
    avg: Decimal


class LeaderboardRow(Output):
    rank: int
    team: TeamBrief
    total: Decimal
    criteria: list[CriterionAverage]
    tied: bool


class Leaderboard(Page[LeaderboardRow]):
    publication_revision: int


class ResultCriterion(Output):
    name: str
    avg: Decimal


class TeamResult(Output):
    rank: int
    total: Decimal
    criteria: list[ResultCriterion]
    comments: list[str]
    publication_revision: int


class NoteInput(Input):
    content: Content
    commit_sha: CommitSHA | None = None
    kind: Literal["feedback", "progress"] = "feedback"
    progress_status: Literal["on_track", "at_risk", "blocked"] | None = None

    @model_validator(mode="after")
    def validate_progress(self) -> Self:
        if (self.kind == "progress") != (self.progress_status is not None):
            raise ValueError("progress_status is required only for progress notes")
        return self


class NoteOutput(Output):
    id: UUID
    team_id: UUID
    mentor: UserBrief
    content: str
    commit_sha: str | None
    kind: Literal["feedback", "progress"]
    progress_status: Literal["on_track", "at_risk", "blocked"] | None
    created_at: datetime


class QuestionInput(Input):
    title: Name
    content: Content
    commit_sha: CommitSHA | None = None


class QuestionOutput(Output):
    id: UUID
    team_id: UUID
    author: UserBrief
    title: str
    content: str
    commit_sha: str | None
    status: Literal["open", "answered", "resolved"]
    created_at: datetime
    resolved_at: datetime | None


class AnswerInput(Input):
    content: Content


class AnswerOutput(Output):
    id: UUID
    question_id: UUID
    mentor: UserBrief
    content: str
    created_at: datetime
