from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_serializer,
    field_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterInput(EmailInput):
    password: Password
    full_name: Name


class LoginInput(EmailInput):
    password: Annotated[str, Field(min_length=1, max_length=128)]


class VerifyEmailInput(Input):
    token: str = Field(min_length=1, max_length=256)


class ProfileInput(Input):
    full_name: Name | None = None
    student_id: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None
    ) = None
    phone: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)] | None
    ) = None
    avatar_url: HttpUrl | None = Field(default=None, max_length=2048)

    @field_validator("full_name")
    @classmethod
    def name_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("full_name cannot be null")
        return value


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    student_id: str | None
    phone: str | None
    avatar_url: str | None
    is_admin: bool
    is_active: bool
    email_verified: bool
    created_at: datetime

    @field_serializer("created_at")
    def utc_created_at(self, value: datetime) -> str:
        # SQLite trong test không giữ timezone; PostgreSQL lưu timestamptz.
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")


class TokenOutput(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class ErrorOutput(BaseModel):
    detail: str
    code: str


Role = Literal["organizer", "judge", "mentor", "participant"]


class ResetPasswordInput(VerifyEmailInput):
    new_password: Password


class AdminUserInput(Input):
    is_active: bool | None = Field(default=None, strict=True)
    is_admin: bool | None = Field(default=None, strict=True)

    @field_validator("is_active", "is_admin")
    @classmethod
    def flags_cannot_be_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Flag cannot be null")
        return value


class EventRoleOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: UUID
    role: Role


class RoleRecord(EventRoleOutput):
    id: UUID
    user_id: UUID
    created_at: datetime


class UserPage(BaseModel):
    items: list[UserOutput]
    total: int


class AuditLogOutput(BaseModel):
    id: UUID
    actor_id: UUID
    actor_email: EmailStr
    action: str
    target_type: str
    target_id: str
    data: dict[str, object]
    created_at: datetime

    @field_serializer("created_at")
    def utc_created_at(self, value: datetime) -> str:
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")


class AuditLogPage(BaseModel):
    items: list[AuditLogOutput]
    total: int


class ServiceStatus(BaseModel):
    name: Literal["database", "redis", "worker", "beat", "email_queue", "storage"]
    status: Literal["ok", "degraded", "down", "not_configured"]
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class DataCounts(BaseModel):
    users: int = 0
    active_users: int = 0
    admins: int = 0
    events: int = 0
    teams: int = 0
    submissions: int = 0
    commits: int = 0
    ai_reviews: int = 0
    audit_logs: int = 0
    database_bytes: int | None = None
    storage_bytes: int | None = None


class SystemOverview(BaseModel):
    server_time: datetime
    services: list[ServiceStatus]
    data: DataCounts
