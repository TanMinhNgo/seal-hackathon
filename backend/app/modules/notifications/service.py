from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.core.schemas import Page
from app.modules.notifications.models import Announcement
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    AnnouncementOutput,
    DeliveryOutput,
    NotificationOutput,
    NotificationPage,
)


class NotificationService:
    @staticmethod
    def sync_failure(session: object, event_id: UUID, team_id: UUID, source: str) -> None:
        NotificationRepository(session).sync_failure(event_id, team_id, source)

    @staticmethod
    def realtime(session: object, event: str, room: str, payload: dict) -> None:
        NotificationRepository(session).realtime(event, room, payload)

    @staticmethod
    def enqueue(
        session: object,
        event_id: UUID,
        source: str,
        kind: str,
        recipients: list,
        title: str,
        body: str,
        link: str,
        email: bool = True,
    ) -> None:
        NotificationRepository(session).enqueue(
            event_id, source, kind, recipients, title, body, link, email
        )

    def __init__(self, repository: NotificationRepository, events: object, auth: object) -> None:
        self.repository = repository
        self.events = events
        self.auth = auth

    async def inbox(
        self, actor: object, unread: bool | None, limit: int, offset: int
    ) -> NotificationPage:
        rows, total, count = await self.repository.inbox(actor.id, unread, limit, offset)
        return NotificationPage(
            items=[NotificationOutput.model_validate(r) for r in rows],
            total=total,
            unread_count=count,
        )

    async def read(self, actor: object, notification_id: UUID | None = None) -> None:
        if not await self.repository.read(actor.id, notification_id) and notification_id:
            raise ApiError(404, "NOTIFICATION_NOT_FOUND", "Notification not found")

    async def announcements(self, actor: object, event_id: UUID, limit: int, offset: int) -> Page:
        await self.events.read(event_id, actor)
        own = {
            r.role
            for r in await self.auth.roles_in_event(event_id)
            if actor and r.user_id == actor.id
        }
        audiences = {"public"}
        if actor and (actor.is_admin or "organizer" in own):
            audiences |= {"all", "participants", "judges", "mentors"}
        elif own:
            audiences.add("all")
            audiences |= {
                a
                for a, role in (
                    ("participants", "participant"),
                    ("judges", "judge"),
                    ("mentors", "mentor"),
                )
                if role in own
            }
        rows, total = await self.repository.announcements(event_id, audiences, limit, offset)
        return Page[AnnouncementOutput](
            items=[AnnouncementOutput.model_validate(r) for r in rows], total=total
        )

    async def announce(self, actor: object, event_id: UUID, data: object) -> AnnouncementOutput:
        event, actor = await self.events.locked(actor, event_id)
        self.events.editable(event)
        row = Announcement(id=uuid4(), event_id=event_id, **data.model_dump())
        await self.repository.announce(event_id, row)
        await self.events.log(
            actor, "announcement.created", row.id, {"event_id": event_id}, "announcement"
        )
        await self.repository.commit_announcement(row)
        return AnnouncementOutput.model_validate(row)

    async def deliveries(
        self, actor: object, event_id: UUID, status: str | None, limit: int, offset: int
    ) -> Page:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        rows, total = await self.repository.deliveries(event_id, status, limit, offset)
        return Page[DeliveryOutput](
            items=[DeliveryOutput.model_validate(r) for r in rows], total=total
        )

    @staticmethod
    async def invitation(
        session: object, event_id: UUID, team: object, email: str, link: str
    ) -> None:
        from app.modules.notifications.repository import invitation_recipient

        await invitation_recipient(session, event_id, team, email, link)

    @staticmethod
    async def audit(session: object, source: UUID, action: str, target: str, data: dict) -> None:
        from app.modules.notifications.repository import capture_audit

        await capture_audit(session, source, action, target, data)
