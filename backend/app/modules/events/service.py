from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.errors import ApiError
from app.core.schemas import Page, utc
from app.modules.auth.schemas import AdminUserInput, UserOutput
from app.modules.auth.service import AuthService
from app.modules.events.repository import EventRepository
from app.modules.events.schemas import (
    EventCreate,
    EventInput,
    EventOutput,
    EventPatch,
    PrizeInput,
    PrizePatch,
    RoleInput,
    RoleOutput,
    RoundInput,
    RoundPatch,
    TrackInput,
    TrackPatch,
    UserBrief,
)

if TYPE_CHECKING:
    from app.modules.events.models import Event


class EventService:
    @staticmethod
    def sync_guard(session: object, event_id: UUID) -> bool:
        return EventRepository.sync_guard(session, event_id)

    @staticmethod
    def sync_events(session: object) -> list:
        return EventRepository.sync_events(session)

    @staticmethod
    def reminder_rounds(session: object, now: datetime) -> list[tuple[object, set[UUID] | None]]:
        return EventRepository.reminder_rounds(session, now)

    def __init__(
        self, repository: EventRepository, auth: AuthService, judging: object = None
    ) -> None:
        self.repository = repository
        self.auth = auth
        self.judging = judging

    async def get(self, event_id: UUID, *, lock: bool = False) -> Event:
        event = await self.repository.get(event_id, lock=lock)
        if event is None:
            raise ApiError(404, "EVENT_NOT_FOUND", "Event not found")
        return event

    async def read(self, event_id: UUID, actor: UserOutput | None) -> EventOutput:
        event = await self.get(event_id)
        if event.status == "draft" or event.archived_at is not None:
            roles = await self.auth.roles_in_event(event_id) if actor else []
            allowed = actor and (
                actor.is_admin
                or any(
                    role.user_id == actor.id
                    and (event.archived_at is not None or role.role == "organizer")
                    for role in roles
                )
            )
            if not allowed:
                raise ApiError(404, "EVENT_NOT_FOUND", "Event not found")
        return EventOutput.model_validate(event)

    async def by_slug(self, slug: str, actor: UserOutput | None) -> EventOutput:
        event = await self.repository.by_slug(slug)
        if event is None:
            raise ApiError(404, "EVENT_NOT_FOUND", "Event not found")
        return await self.read(event.id, actor)

    async def require_organizer(
        self, actor: UserOutput, event_id: UUID, *, admin_read: bool = False
    ) -> None:
        if admin_read and actor.is_admin:
            return
        await self.auth.require_event_role(actor, event_id, ("organizer",))

    async def locked(
        self,
        actor: UserOutput,
        event_id: UUID,
        *,
        admin: bool = False,
        others: tuple[UUID, ...] = (),
    ) -> tuple[Event, UserOutput]:
        actor = await self.auth.lock_actor(actor, others)
        event = await self.get(event_id, lock=True)
        if admin:
            self.auth.require_admin(actor)
        else:
            await self.require_organizer(actor, event_id)
        return event, actor

    @staticmethod
    def editable(event: Event) -> None:
        if event.status == "closed" or event.archived_at:
            raise ApiError(409, "EVENT_CLOSED", "Event is read only")

    @staticmethod
    def validate_schedule(values: dict[str, object]) -> None:
        if (
            not (
                utc(values["registration_opens_at"])
                < utc(values["registration_closes_at"])
                <= utc(values["starts_at"])
                < utc(values["ends_at"])
            )
            or values["min_team_size"] > values["max_team_size"]
        ):
            raise ApiError(422, "INVALID_SCHEDULE", "Invalid event schedule or team size")

    async def log(
        self,
        actor: UserOutput,
        action: str,
        target_id: UUID,
        data: dict[str, object],
        target_type: str = "event",
    ) -> None:
        await self.auth.write_audit_log(
            actor.id,
            action,
            target_type,
            str(target_id),
            jsonable_encoder(data, custom_encoder={Decimal: str}),
        )

    async def create(self, actor: UserOutput, data: EventCreate) -> EventOutput:
        self.auth.require_admin(actor)
        organizer = await self.auth.find_user(str(data.organizer_email))
        actor = await self.auth.lock_actor(actor, (organizer.id,))
        self.auth.require_admin(actor)
        organizer = (await self.auth.users([organizer.id]))[organizer.id]
        if organizer.is_admin or not organizer.is_active or not organizer.email_verified:
            raise ApiError(
                409, "ROLE_CONFLICT", "Organizer must be active, verified and not an administrator"
            )
        values = data.model_dump(exclude={"organizer_email"})
        values["banner_url"] = str(data.banner_url) if data.banner_url else None
        self.validate_schedule(values)
        event = await self.repository.create(values)
        role = await self.auth.grant_role(organizer.id, event.id, "organizer")
        await self.log(actor, "event.created", event.id, {"organizer_id": organizer.id})
        await self.log(
            actor,
            "role.granted",
            role.id,
            {"event_id": event.id, "user_id": organizer.id, "role": "organizer"},
            "event_role",
        )
        result = EventOutput.model_validate(event)
        await self.repository.commit()
        return result

    async def update(self, actor: UserOutput, event_id: UUID, data: EventPatch) -> EventOutput:
        event, actor = await self.locked(actor, event_id, admin=actor.is_admin)
        self.editable(event)
        values = data.model_dump(exclude_unset=True)
        if actor.is_admin and values.keys() - {"name", "description", "banner_url"}:
            raise ApiError(403, "FORBIDDEN", "Administrators may only edit event metadata")
        if "slug" in values and values["slug"] != event.slug and event.status != "draft":
            raise ApiError(409, "RESOURCE_IN_USE", "Event slug is frozen")
        protected = set(EventInput.model_fields) - {
            "name",
            "description",
            "banner_url",
            "slug",
            "sync_interval_minutes",
            "inactivity_alert_hours",
        }
        if values.keys() & protected and (
            event.status in {"ongoing", "judging"} or datetime.now(UTC) >= utc(event.starts_at)
        ):
            raise ApiError(
                409, "RESOURCE_IN_USE", "Operational settings are frozen after the event starts"
            )
        merged = {key: getattr(event, key) for key in EventInput.model_fields} | values
        self.validate_schedule(merged)
        for round_ in await self.repository.all_rounds(event_id):
            if (
                not utc(merged["starts_at"])
                <= utc(round_.starts_at)
                < utc(round_.ends_at)
                <= utc(merged["ends_at"])
            ):
                raise ApiError(422, "INVALID_SCHEDULE", "Event schedule excludes an existing round")
        if "banner_url" in values and values["banner_url"] is not None:
            values["banner_url"] = str(values["banner_url"])
        for key, value in values.items():
            setattr(event, key, value)
        await self.repository.flush()
        if values:
            await self.log(actor, "event.updated", event_id, {"after": values})
        result = EventOutput.model_validate(event)
        await self.repository.commit()
        return result

    async def archive(self, actor: UserOutput, event_id: UUID, archived: bool) -> EventOutput:
        event, actor = await self.locked(actor, event_id, admin=True)
        if event.status != "closed":
            raise ApiError(409, "EVENT_NOT_CLOSED", "Only closed events can be archived")
        event.archived_at = datetime.now(UTC) if archived else None
        await self.log(actor, "event.archived" if archived else "event.unarchived", event_id, {})
        result = EventOutput.model_validate(event)
        await self.repository.commit()
        return result

    async def child_list(
        self, actor: UserOutput | None, event_id: UUID, kind: str, limit: int, offset: int
    ) -> tuple[list[object], int]:
        await self.read(event_id, actor)
        return await self.repository.children(kind, event_id, limit, offset)

    async def change_child(
        self,
        actor: UserOutput,
        event_id: UUID,
        kind: str,
        data: RoundInput | RoundPatch | TrackInput | TrackPatch | PrizeInput | PrizePatch | None,
        child_id: UUID | None = None,
    ) -> object:
        event, actor = await self.locked(actor, event_id)
        self.editable(event)
        if datetime.now(UTC) >= utc(event.starts_at):
            raise ApiError(409, "RESOURCE_IN_USE", "Event configuration is frozen at its start")
        child = await self.repository.child(kind, event_id, child_id) if child_id else None
        if child_id and child is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Resource not found in event")
        if child and kind == "rounds" and datetime.now(UTC) >= utc(child.starts_at):
            raise ApiError(409, "RESOURCE_IN_USE", "Round has already started")
        values = data.model_dump(exclude_unset=True) if data else {}
        if kind == "rounds" and data:
            merged = (
                {key: getattr(child, key) for key in RoundInput.model_fields} | values
                if child
                else data.model_dump()
            )
            if (
                not utc(event.starts_at)
                <= utc(merged["starts_at"])
                < utc(merged["submission_deadline"])
                <= utc(merged["ends_at"])
                <= utc(event.ends_at)
            ):
                raise ApiError(422, "INVALID_SCHEDULE", "Round schedule must fit the event")
        if child and data is None:
            await self.repository.remove(child)
            await self.log(actor, f"{kind}.deleted", child.id, {"event_id": event_id}, kind[:-1])
            await self.repository.commit()
            return None
        if child:
            for key, value in values.items():
                setattr(child, key, value)
            await self.repository.flush()
        else:
            child = await self.repository.create_child(kind, event_id, data.model_dump())
        await self.log(
            actor,
            f"{kind}.updated" if child_id else f"{kind}.created",
            child.id,
            {"event_id": event_id, "after": values},
            kind[:-1],
        )
        await self.repository.commit()
        return child

    async def role_list(
        self,
        actor: UserOutput,
        event_id: UUID,
        role: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> Page[RoleOutput]:
        await self.get(event_id)
        await self.require_organizer(actor, event_id, admin_read=True)
        rows, total = await self.auth.role_page(event_id, role, q, limit, offset)
        users = await self.auth.users([row.user_id for row in rows])
        return Page(
            items=[
                RoleOutput(
                    id=row.id, user=UserBrief.model_validate(users[row.user_id]), role=row.role
                )
                for row in rows
            ],
            total=total,
        )

    async def grant(self, actor: UserOutput, event_id: UUID, data: RoleInput) -> RoleOutput:
        await self.get(event_id)
        await self.require_organizer(actor, event_id, admin_read=True)
        target = await self.auth.find_user(str(data.email))
        event, actor = await self.locked(actor, event_id, admin=actor.is_admin, others=(target.id,))
        self.editable(event)
        target = (await self.auth.users([target.id]))[target.id]
        allowed = {"organizer"} if actor.is_admin else {"judge", "mentor"}
        if data.role not in allowed:
            raise ApiError(403, "FORBIDDEN", "Role cannot be granted by this actor")
        if target.is_admin or not target.is_active or not target.email_verified:
            raise ApiError(
                409, "ROLE_CONFLICT", "Target must be active, verified and not an administrator"
            )
        existing = {
            row.role for row in await self.auth.roles_in_event(event_id) if row.user_id == target.id
        }
        if (
            data.role in existing
            or "participant" in existing
            or (data.role == "organizer" and "judge" in existing)
            or (data.role == "judge" and "organizer" in existing)
        ):
            raise ApiError(409, "ROLE_CONFLICT", "Conflicting event role")
        entry = await self.auth.grant_role(target.id, event_id, data.role)
        await self.log(
            actor,
            "role.granted",
            entry.id,
            {"event_id": event_id, "user_id": target.id, "role": data.role},
            "event_role",
        )
        await self.repository.commit()
        return RoleOutput(id=entry.id, user=UserBrief.model_validate(target), role=entry.role)

    async def revoke(self, actor: UserOutput, event_id: UUID, role_id: UUID) -> None:
        await self.get(event_id)
        await self.require_organizer(actor, event_id, admin_read=True)
        roles = await self.auth.roles_in_event(event_id)
        entry = next((row for row in roles if row.id == role_id), None)
        if entry is None:
            raise ApiError(404, "ROLE_NOT_FOUND", "Role not found")
        event, actor = await self.locked(
            actor, event_id, admin=actor.is_admin, others=(entry.user_id,)
        )
        self.editable(event)
        roles = await self.auth.roles_in_event(event_id)
        entry = next((row for row in roles if row.id == role_id), None)
        if entry is None:
            raise ApiError(404, "ROLE_NOT_FOUND", "Role not found")
        if entry.role not in ({"organizer"} if actor.is_admin else {"judge", "mentor"}):
            raise ApiError(403, "FORBIDDEN", "Role cannot be revoked by this actor")
        if entry.role == "organizer":
            await self.require_other_organizer(event_id, entry.user_id)
        elif self.judging and await self.judging.role_in_use(event_id, entry.user_id, entry.role):
            raise ApiError(409, "ROLE_IN_USE", "Resolve assignments before revoking this role")
        await self.auth.revoke_role(role_id)
        await self.log(
            actor,
            "role.revoked",
            role_id,
            {"event_id": event_id, "user_id": entry.user_id, "role": entry.role},
            "event_role",
        )
        await self.repository.commit()

    async def require_other_organizer(self, event_id: UUID, excluding: UUID) -> None:
        ids = [
            row.user_id
            for row in await self.auth.roles_in_event(event_id)
            if row.role == "organizer" and row.user_id != excluding
        ]
        users = await self.auth.users(ids)
        if not any(
            user.is_active and user.email_verified and not user.is_admin for user in users.values()
        ):
            raise ApiError(409, "LAST_ORGANIZER", "Assign another active organizer first")

    async def guard_account_change(
        self, actor: UserOutput, target_id: UUID, data: AdminUserInput
    ) -> None:
        actor = await self.auth.lock_actor(actor, (target_id,))
        self.auth.require_admin(actor)
        target = (await self.auth.users([target_id])).get(target_id)
        if target is None:
            raise ApiError(404, "USER_NOT_FOUND", "User not found")
        if not (
            (data.is_admin is True and not target.is_admin)
            or (data.is_active is False and target.is_active)
        ):
            return
        roles = await self.auth.role_records(target_id)
        for event_id in sorted({row.event_id for row in roles}):
            event = await self.get(event_id, lock=True)
            if event.status == "closed":
                continue
            if data.is_admin is True and not target.is_admin:
                raise ApiError(
                    409,
                    "EVENT_ROLES_PRESENT",
                    "Revoke active event roles before granting administrator access",
                )
            if any(row.event_id == event_id and row.role == "organizer" for row in roles):
                await self.require_other_organizer(event_id, target_id)

    async def ensure_track(self, event_id: UUID, track_id: UUID | None) -> None:
        if track_id and await self.repository.child("tracks", event_id, track_id) is None:
            raise ApiError(404, "TRACK_NOT_FOUND", "Track not found in event")

    async def query_list(
        self,
        visible_drafts: list[UUID] | None,
        archived: bool,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
        ids: list[UUID] | None = None,
    ) -> tuple[list[object], int]:
        return await self.repository.list(visible_drafts, archived, status, q, limit, offset, ids)

    async def rounds(self, event_id: UUID) -> list[object]:
        return await self.repository.all_rounds(event_id)

    async def submission_round(self, event_id: UUID, round_id: UUID) -> object:
        round_ = await self.repository.child("rounds", event_id, round_id)
        if round_ is None:
            raise ApiError(404, "ROUND_NOT_FOUND", "Round not found in event")
        return round_

    async def submission_eligible(self, round_: object, team_id: UUID) -> bool:
        rounds = await self.rounds(round_.event_id)
        if round_.id == rounds[0].id:
            return True
        source = (await self.eligibility_sources(round_.id)).get(team_id)
        return bool(source and self.judging and await self.judging.results_ready([source]))

    async def eligibility_sources(self, round_id: UUID) -> dict[UUID, UUID | None]:
        return await self.repository.eligibility_sources(round_id)

    async def replace_eligibility(
        self, round_id: UUID, source_id: UUID, team_ids: list[UUID]
    ) -> None:
        await self.repository.replace_eligibility(round_id, source_id, team_ids)

    async def has_started_dependents(self, source_id: UUID) -> bool:
        return await self.repository.has_started_dependents(source_id, datetime.now(UTC))

    async def update_account(
        self, actor: UserOutput, target_id: UUID, data: AdminUserInput
    ) -> UserOutput:
        await self.guard_account_change(actor, target_id, data)
        return await self.auth.update_user(actor, target_id, data)
