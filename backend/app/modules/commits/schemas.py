from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.schemas import Output, Page


class CommitOutput(Output):
    id: UUID
    sha: str
    author: str
    message: str
    branch: str
    committed_at: datetime
    first_seen_at: datetime
    additions: int
    deletions: int
    removed: bool
    baseline: bool
    in_event_window: bool
    url: str


class DiffFile(Output):
    path: str
    previous_path: str | None
    status: str
    additions: int
    deletions: int
    patch: str | None
    binary: bool | None
    truncated: bool


class DiffPage(Page[DiffFile]):
    truncated: bool


class CommitStats(Output):
    total: int
    last_commit_at: datetime | None
    last_synced_at: datetime | None = None
    sync_status: Literal["ok", "error", "pending"] = "pending"
    sync_error: str | None = None
    branch: str | None = None
    last_attempt_at: datetime | None = None
    running: bool = False
    truncated: bool = False


class CommitTeam(Output):
    id: UUID
    name: str


class CommitOverview(CommitStats):
    team: CommitTeam
    inactive: bool


class SyncQueued(Output):
    task_id: str
    status: Literal["queued"] = "queued"
