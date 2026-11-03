from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import EventServiceDependency, Limit, Offset, SessionDependency, no_store
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser, OptionalUser, ServiceDependency, check_origin
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    AnnouncementInput,
    AnnouncementOutput,
    DeliveryOutput,
    DeliveryStatus,
    NotificationPage,
)
from app.modules.notifications.service import NotificationService


def get_notification_service(
    session: SessionDependency, events: EventServiceDependency, auth: ServiceDependency
) -> NotificationService:
    return NotificationService(NotificationRepository(session), events, auth)


Service = Annotated[NotificationService, Depends(get_notification_service)]
router = APIRouter(
    prefix="/api/v1",
    tags=["notifications"],
    dependencies=[Depends(no_store), Depends(check_origin)],
)


@router.get("/me/notifications", response_model=NotificationPage)
async def inbox(
    service: Service,
    user: CurrentUser,
    unread: bool | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> NotificationPage:
    return await service.inbox(user, unread, limit, offset)


@router.post("/me/notifications/read-all", status_code=204)
async def read_all(service: Service, user: CurrentUser) -> Response:
    await service.read(user)
    return Response(status_code=204)


@router.post("/me/notifications/{notification_id}/read", status_code=204)
async def read(notification_id: UUID, service: Service, user: CurrentUser) -> Response:
    await service.read(user, notification_id)
    return Response(status_code=204)


@router.get("/events/{event_id}/announcements", response_model=Page[AnnouncementOutput])
async def announcements(
    event_id: UUID, service: Service, user: OptionalUser, limit: Limit = 20, offset: Offset = 0
) -> Page:
    return await service.announcements(user, event_id, limit, offset)


@router.post("/events/{event_id}/announcements", status_code=201, response_model=AnnouncementOutput)
async def announce(
    event_id: UUID, data: AnnouncementInput, service: Service, user: CurrentUser
) -> AnnouncementOutput:
    return await service.announce(user, event_id, data)


@router.get("/events/{event_id}/notification-deliveries", response_model=Page[DeliveryOutput])
async def deliveries(
    event_id: UUID,
    service: Service,
    user: CurrentUser,
    status: DeliveryStatus | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page:
    return await service.deliveries(user, event_id, status, limit, offset)
