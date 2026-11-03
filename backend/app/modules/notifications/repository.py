from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select, update

from app.core.db import Base
from app.modules.notifications.models import (
    Announcement,
    Notification,
    NotificationDelivery,
    RealtimeOutbox,
)


class NotificationRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    async def announce(self, event_id: UUID, row: Announcement) -> None:
        self.session.add(row)
        recipients = list(
            (await self.session.execute(self.recipients(event_id, row.audience))).all()
        )
        self.enqueue(
            event_id,
            f"announcement:{row.id}:{row.audience}",
            "announcement",
            recipients,
            row.title,
            row.body,
            f"/events/{event_id}",
            row.send_email,
        )

    async def commit_announcement(self, row: Announcement) -> None:
        await self.session.commit()
        await self.session.refresh(row)

    async def inbox(self, user_id: UUID, unread: bool | None, limit: int, offset: int) -> tuple:
        query = select(Notification).where(Notification.user_id == user_id, self.visible(user_id))
        unread_count = await self.session.scalar(
            select(func.count()).select_from(query.where(Notification.read_at.is_(None)).subquery())
        )
        if unread is not None:
            query = query.where(
                Notification.read_at.is_(None) if unread else Notification.read_at.is_not(None)
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            await self.session.scalars(
                query.order_by(Notification.created_at.desc(), Notification.id)
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total, unread_count

    async def can_receive(self, user_id: UUID, notification_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.id == notification_id,
                    self.visible(user_id),
                )
            )
        )

    @staticmethod
    def visible(user_id: UUID) -> object:
        roles = Base.metadata.tables["event_roles"]
        member = exists(
            select(roles.c.id).where(
                roles.c.user_id == user_id, roles.c.event_id == Notification.event_id
            )
        )
        audiences = []
        for name, role in (
            ("participants", "participant"),
            ("judges", "judge"),
            ("mentors", "mentor"),
        ):
            audiences.append(
                ~Notification.source.endswith(f":{name}")
                | exists(
                    select(roles.c.id).where(
                        roles.c.user_id == user_id,
                        roles.c.event_id == Notification.event_id,
                        roles.c.role == role,
                    )
                )
            )
        return or_(
            Notification.type == "team.invitation",
            Notification.source.endswith(":public"),
            member & and_(*audiences),
        )

    def delivery_allowed(self, row: NotificationDelivery) -> bool:
        if row.recipient_id is None:
            return row.notification_type == "team.invitation"
        users = Base.metadata.tables["users"]
        query = select(users.c.id).where(
            users.c.id == row.recipient_id,
            users.c.is_active.is_(True),
            users.c.email_verified.is_(True),
            users.c.is_admin.is_(False),
        )
        # SMTP giữ khóa để serialize thu hồi quyền; in-app được kiểm quyền lại ngay trước emit.
        user = self.session.scalar(query.with_for_update() if row.channel == "email" else query)
        return bool(
            user
            and self.session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user,
                    Notification.source == row.source,
                    self.visible(user),
                )
            )
        )

    async def read(self, user_id: UUID, notification_id: UUID | None) -> bool:
        query = update(Notification).where(Notification.user_id == user_id)
        if notification_id:
            query = query.where(Notification.id == notification_id)
        result = await self.session.execute(
            query.values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def announcements(
        self, event_id: UUID, audiences: set[str], limit: int, offset: int
    ) -> tuple:
        query = select(Announcement).where(
            Announcement.event_id == event_id, Announcement.audience.in_(audiences)
        )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        return list(
            await self.session.scalars(
                query.order_by(Announcement.created_at.desc(), Announcement.id)
                .limit(limit)
                .offset(offset)
            )
        ), total

    async def deliveries(
        self, event_id: UUID, status: str | None, limit: int, offset: int
    ) -> tuple:
        query = select(NotificationDelivery).where(NotificationDelivery.event_id == event_id)
        if status:
            query = query.where(NotificationDelivery.status == status)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        return list(
            await self.session.scalars(
                query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id)
                .limit(limit)
                .offset(offset)
            )
        ), total

    def recipients(self, event_id: UUID, audience: str = "all") -> object:
        # Read model liên module chỉ chọn ID/email; không nạp model hoặc secret xác thực.
        users, roles = (Base.metadata.tables[t] for t in ("users", "event_roles"))
        query = (
            select(users.c.id, users.c.email)
            .join(roles, roles.c.user_id == users.c.id)
            .where(
                roles.c.event_id == event_id,
                users.c.is_active.is_(True),
                users.c.email_verified.is_(True),
                users.c.is_admin.is_(False),
            )
        )
        role = {"participants": "participant", "judges": "judge", "mentors": "mentor"}.get(audience)
        return query.where(roles.c.role == role).distinct() if role else query.distinct()

    def enqueue(
        self,
        event_id: UUID,
        source: str,
        kind: str,
        recipients: list,
        title: str,
        body: str,
        link: str,
        email: bool = True,
    ) -> None:
        if (
            not link.startswith("/")
            or link.startswith("//")
            or "\\" in link
            or any(ord(c) < 32 for c in link)
        ):
            raise ValueError("Notification link must be an internal route")
        for user_id, address in set(recipients):
            recipient_key = (
                str(user_id) if user_id else sha256(address.lower().encode()).hexdigest()
            )
            if user_id:
                notification = Notification(
                    event_id=event_id,
                    user_id=user_id,
                    source=source,
                    type=kind,
                    title=title,
                    body=body,
                    link=link,
                )
                self.session.add(notification)
            for channel in (
                ["in_app", "email"] if email and user_id else ["in_app"] if user_id else ["email"]
            ):
                self.session.add(
                    NotificationDelivery(
                        event_id=event_id,
                        recipient_id=user_id,
                        recipient_key=recipient_key,
                        source=source,
                        notification_type=kind,
                        channel=channel,
                        payload={
                            "address": address,
                            "title": title,
                            "body": body,
                            "link": link,
                            "source": source,
                        },
                    )
                )

    def realtime(self, event: str, room: str, payload: dict) -> None:
        self.session.add(RealtimeOutbox(event=event, room=room, payload=payload))

    def sync_failure(self, event_id: UUID, team_id: UUID, source: str) -> None:
        roles = Base.metadata.tables["event_roles"]
        recipients = list(
            self.session.execute(self.recipients(event_id).where(roles.c.role == "organizer")).all()
        )
        self.enqueue(
            event_id,
            f"sync:{source}",
            "sync.failed",
            recipients,
            "SEAL - Repository sync failed",
            f"Team {team_id}: check repository access in commit overview.",
            f"/events/{event_id}",
        )


async def invitation_recipient(
    session: object, event_id: UUID, team: object, email: str, link: str
) -> None:
    users = Base.metadata.tables["users"]
    user = (
        await session.execute(
            select(users.c.id, users.c.email).where(
                func.lower(users.c.email) == email.lower(),
                users.c.is_active.is_(True),
                users.c.email_verified.is_(True),
                users.c.is_admin.is_(False),
            )
        )
    ).first()
    repository = NotificationRepository(session)
    key = sha256(f"{team.id}:{team.invite_code}:{email.lower()}".encode()).hexdigest()
    if await session.scalar(
        select(NotificationDelivery.id)
        .where(NotificationDelivery.source == f"invitation:{key}")
        .limit(1)
    ):
        return
    repository.enqueue(
        event_id,
        f"invitation:{key}",
        "team.invitation",
        [user or (None, email)],
        "SEAL - Team invitation",
        f"You are invited to join {team.name}",
        link,
    )


async def capture_audit(
    session: object, source: UUID, action: str, target: str, data: dict
) -> None:
    tables = Base.metadata.tables
    repo = NotificationRepository(session)
    event_id = data.get("event_id")
    team_id = data.get("team_id")
    round_id = None
    recipient_ids = None
    audience = "all"
    if action == "team.reviewed":
        team_id = UUID(target)
        team = (
            await session.execute(select(tables["teams"]).where(tables["teams"].c.id == team_id))
        ).first()
        event_id = team.event_id
        recipient_ids = [team.leader_id]
        if data.get("status") == "approved":
            repo.realtime("team:approved", f"event:{event_id}", {"team_id": target})
    elif (
        action
        in {
            "round.lock",
            "round.unlock",
            "round.publish",
            "round.unpublish",
            "round.eligibility_updated",
        }
        or action == "rounds.updated"
    ):
        round_id = UUID(target)
        round_ = (
            await session.execute(select(tables["rounds"]).where(tables["rounds"].c.id == round_id))
        ).first()
        event_id = round_.event_id
        if action in {"round.publish", "round.unpublish"}:
            repo.realtime(
                "leaderboard:updated" if action == "round.publish" else "leaderboard:unpublished",
                f"event:{event_id}",
                {"round_id": target},
            )
            members, teams = tables["team_members"], tables["teams"]
            recipient_ids = list(
                await session.scalars(
                    select(members.c.user_id)
                    .join(teams, teams.c.id == members.c.team_id)
                    .where(
                        teams.c.event_id == event_id,
                        teams.c.status == "approved",
                        teams.c.disbanded_at.is_(None),
                        members.c.status == "active",
                    )
                )
            )
        if action in {"round.lock", "round.unlock"}:
            return
    elif action == "assignments.created":
        round_id = UUID(target)
        round_ = (
            await session.execute(select(tables["rounds"]).where(tables["rounds"].c.id == round_id))
        ).first()
        event_id = round_.event_id
        recipient_ids = [UUID(item["judge"]["id"]) for item in data["items"]]
    elif action == "mentors.assigned":
        event_id = UUID(target)
        recipient_ids = [UUID(data["mentor_id"])]
    elif action in {"mentor.question_created", "mentor.note_created", "mentor.answer_created"}:
        if action == "mentor.answer_created":
            question = (
                await session.execute(
                    select(tables["mentor_questions"]).where(
                        tables["mentor_questions"].c.id == UUID(data["question_id"])
                    )
                )
            ).first()
            team_id = question.team_id
        else:
            team_id = UUID(str(team_id))
        team = (
            await session.execute(select(tables["teams"]).where(tables["teams"].c.id == team_id))
        ).first()
        event_id = team.event_id
        if action == "mentor.question_created":
            assignments = tables["mentor_assignments"]
            recipient_ids = list(
                await session.scalars(
                    select(assignments.c.mentor_id).where(
                        assignments.c.team_id == team_id, assignments.c.revoked_at.is_(None)
                    )
                )
            )
        else:
            members = tables["team_members"]
            recipient_ids = list(
                await session.scalars(
                    select(members.c.user_id).where(
                        members.c.team_id == team_id, members.c.status == "active"
                    )
                )
            )
    elif action == "event.updated":
        event_id = UUID(target)
        changed = data.get("after", {})
        if not any(key.endswith("_at") for key in changed):
            return
    else:
        return
    event_id = UUID(str(event_id))
    query = repo.recipients(event_id, audience)
    if recipient_ids is not None:
        query = query.where(tables["users"].c.id.in_(recipient_ids))
    recipients = list((await session.execute(query)).all())
    title = {
        "team.reviewed": "SEAL - Team review",
        "round.publish": "SEAL - Results published",
        "round.unpublish": "SEAL - Results withdrawn",
    }.get(action, "SEAL - Event update")
    body = f"{title}. Open the event to view the current information."
    repo.enqueue(
        event_id, f"audit:{source}", action, recipients, title, body, f"/events/{event_id}"
    )
