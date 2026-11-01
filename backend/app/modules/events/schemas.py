from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.schemas import Output, utc
from app.modules.auth.schemas import EmailInput, Input, Name, Role

EventStatus = Literal["draft", "open", "ongoing", "judging", "closed"]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)]


class TimedInput(Input):
    @field_validator("*")
    @classmethod
    def normalize_datetime(cls, value: object) -> object:
        return utc(value) if isinstance(value, datetime) else value


class EventInput(TimedInput):
    name: Name
    slug: Slug
    description: str = Field(default="", max_length=20000)
    rules: str = Field(default="", max_length=20000)
    banner_url: HttpUrl | None = Field(default=None, max_length=2048)
    registration_opens_at: AwareDatetime
    registration_closes_at: AwareDatetime
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    min_team_size: int = Field(default=1, ge=1, le=100)
    max_team_size: int = Field(default=5, ge=1, le=100)
    sync_interval_minutes: int = Field(default=30, ge=1, le=1440)
    inactivity_alert_hours: int = Field(default=6, ge=1, le=168)


class EventCreate(EventInput):
    organizer_email: EmailStr = Field(max_length=254)

    @field_validator("organizer_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class EventPatch(TimedInput):
    name: Name | None = None
    slug: Slug | None = None
    description: str | None = Field(default=None, max_length=20000)
    rules: str | None = Field(default=None, max_length=20000)
    banner_url: HttpUrl | None = Field(default=None, max_length=2048)
    registration_opens_at: AwareDatetime | None = None
    registration_closes_at: AwareDatetime | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    min_team_size: int | None = Field(default=None, ge=1, le=100)
    max_team_size: int | None = Field(default=None, ge=1, le=100)
    sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    inactivity_alert_hours: int | None = Field(default=None, ge=1, le=168)

    @model_validator(mode="after")
    def reject_null(self) -> "EventPatch":
        if any(
            value is None and key != "banner_url"
            for key, value in self.model_dump(exclude_unset=True).items()
        ):
            raise ValueError("Only banner_url may be null")
        return self


class EventOutput(Output):
    id: UUID
    name: str
    slug: str
    description: str
    rules: str
    banner_url: str | None
    status: EventStatus
    registration_opens_at: datetime
    registration_closes_at: datetime
    starts_at: datetime
    ends_at: datetime
    min_team_size: int
    max_team_size: int
    sync_interval_minutes: int = 30
    inactivity_alert_hours: int = 6
    archived_at: datetime | None
    created_at: datetime

    @field_validator(
        "registration_opens_at",
        "registration_closes_at",
        "starts_at",
        "ends_at",
        "archived_at",
        "created_at",
    )
    @classmethod
    def utc_dates(cls, value: datetime | None) -> datetime | None:
        return utc(value) if value else None


class EventSummary(EventOutput):
    team_count: int | None = Field(default=None, exclude_if=lambda value: value is None)
    participant_count: int | None = Field(default=None, exclude_if=lambda value: value is None)


class TransitionInput(Input):
    to_status: EventStatus


class ArchiveInput(Input):
    archived: bool = Field(strict=True)


class RoundInput(TimedInput):
    name: Name
    order: int = Field(ge=1)
    starts_at: AwareDatetime
    submission_deadline: AwareDatetime
    ends_at: AwareDatetime
    required_judges: int = Field(default=2, ge=1, le=100)


class RoundPatch(TimedInput):
    name: Name | None = None
    order: int | None = Field(default=None, ge=1)
    starts_at: AwareDatetime | None = None
    submission_deadline: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    required_judges: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def reject_null(self) -> "RoundPatch":
        if None in self.model_dump(exclude_unset=True).values():
            raise ValueError("Fields cannot be null")
        return self


class RoundOutput(Output, RoundInput):
    id: UUID
    event_id: UUID


class TrackInput(Input):
    name: Name
    description: str = Field(default="", max_length=10000)


class TrackPatch(Input):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def reject_null(self) -> "TrackPatch":
        if None in self.model_dump(exclude_unset=True).values():
            raise ValueError("Fields cannot be null")
        return self


class TrackOutput(Output, TrackInput):
    id: UUID
    event_id: UUID


class PrizeInput(TrackInput):
    rank: int = Field(ge=1)
    value: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class PrizePatch(TrackPatch):
    rank: int | None = Field(default=None, ge=1)
    value: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class PrizeOutput(Output, PrizeInput):
    id: UUID
    event_id: UUID


class UserBrief(Output):
    id: UUID
    full_name: str
    email: str
    avatar_url: str | None


class RoleInput(EmailInput):
    role: Role


class RoleOutput(Output):
    id: UUID
    user: UserBrief
    role: Role


class Registration(Output):
    user: UserBrief
    registered_at: datetime
    team_id: UUID | None
    member_status: str | None
