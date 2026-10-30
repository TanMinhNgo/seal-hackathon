from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.schemas import Output
from app.modules.auth.schemas import Input, Name
from app.modules.events.schemas import EventSummary, UserBrief


class TeamCreate(Input):
    name: Name
    track_id: UUID | None = None


class TeamPatch(Input):
    name: Name | None = None
    track_id: UUID | None = None

    @model_validator(mode="after")
    def reject_null_name(self) -> "TeamPatch":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class MemberOutput(Output):
    user: UserBrief
    status: Literal["pending", "active"]
    joined_at: datetime


class TeamOutput(Output):
    id: UUID
    event_id: UUID
    name: str
    status: Literal["pending", "approved", "rejected"]
    track_id: UUID | None
    leader_id: UUID
    invite_code: str | None = Field(default=None, exclude_if=lambda value: value is None)
    invite_expires_at: datetime | None = Field(default=None, exclude_if=lambda value: value is None)
    repo_url: str | None
    review_note: str | None
    reviewed_at: datetime | None
    disbanded_at: datetime | None
    members: list[MemberOutput]
    created_at: datetime


class TeamBrief(Output):
    id: UUID
    name: str
    track_id: UUID | None


class PublicTeam(TeamBrief):
    member_count: int
    approved_at: datetime


class MyTeam(Output):
    id: UUID
    name: str
    status: str
    member_status: str


class MyEvent(Output):
    event: EventSummary
    roles: list[str]
    team: MyTeam | None


class InviteInput(Input):
    invite_code: str = Field(min_length=20, max_length=64)


class InviteOutput(Output):
    invite_code: str


class QueueOutput(Output):
    status: Literal["queued"] = "queued"


class TransferInput(Input):
    user_id: UUID


class RepoInput(Input):
    repo_url: str = Field(min_length=1, max_length=2048)


class ReviewInput(Input):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def rejection_reason(self) -> "ReviewInput":
        if self.status == "rejected" and (not self.note or not self.note.strip()):
            raise ValueError("Rejection requires a reason")
        return self
