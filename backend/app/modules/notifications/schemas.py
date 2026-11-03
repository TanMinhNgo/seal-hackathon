from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.schemas import Output, Page

Audience = Literal["public", "all", "participants", "judges", "mentors"]
DeliveryStatus = Literal["queued", "sent", "failed", "unknown"]


class AnnouncementInput(Output):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=150, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=5000, pattern=r"\S")
    audience: Audience
    send_email: bool = False


class AnnouncementOutput(AnnouncementInput):
    id: UUID
    event_id: UUID
    created_at: datetime


class NotificationOutput(Output):
    id: UUID
    type: str
    title: str
    body: str
    link: str
    read_at: datetime | None
    created_at: datetime


class NotificationPage(Page[NotificationOutput]):
    unread_count: int


class DeliveryOutput(Output):
    id: UUID
    notification_type: str
    recipient_id: UUID | None
    channel: Literal["in_app", "email"]
    status: DeliveryStatus
    error_code: str | None
    created_at: datetime
    updated_at: datetime
