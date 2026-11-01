from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import TYPE_CHECKING
from uuid import UUID

from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.schemas import Page, utc
from app.integrations import github_client, rate_limits
from app.modules.auth.schemas import UserOutput
from app.modules.auth.service import AuthService
from app.modules.events.schemas import (
    EventOutput,
    EventPatch,
    EventSummary,
    Registration,
    UserBrief,
)
from app.modules.events.service import EventService
from app.modules.teams.repository import TeamRepository
from app.modules.teams.schemas import (
    MemberOutput,
    MyEvent,
    MyTeam,
    PublicTeam,
    ReviewInput,
    TeamBrief,
    TeamCreate,
    TeamOutput,
    TeamPatch,
)

if TYPE_CHECKING:
    from app.modules.teams.models import Team


class TeamService:
    @staticmethod
    def sync_teams(session: object, event_id: UUID) -> list:
        return TeamRepository.sync_teams(session, event_id)

    @staticmethod
    def reminder_teams(session: object, event_id: UUID, eligible: set[UUID] | None) -> list[object]:
        return TeamRepository.reminder_teams(session, event_id, eligible)

    def __init__(
        self,
        repository: TeamRepository,
        events: EventService,
        auth: AuthService,
        settings: Settings,
        judging: object = None,
    ) -> None:
        self.repository = repository
        self.events = events
        self.auth = auth
        self.settings = settings
        self.judging = judging

    @staticmethod
    def frozen(event: EventOutput | object) -> None:
        if event.status != "open" or event.archived_at or datetime.now(UTC) >= utc(event.starts_at):
            raise ApiError(409, "TEAM_FROZEN", "Team configuration is frozen")

    @staticmethod
    def leader(team: Team, actor: UserOutput) -> None:
        if actor.is_admin or team.leader_id != actor.id:
            raise ApiError(403, "NOT_TEAM_LEADER", "Only the team leader may perform this action")

    async def get(self, team_id: UUID, *, lock: bool = False) -> Team:
        team = await self.repository.get(team_id, lock=lock)
        if team is None or team.disbanded_at:
            raise ApiError(404, "TEAM_NOT_FOUND", "Team not found")
        return team

    async def locked(
        self,
        actor: UserOutput,
        team_id: UUID,
        others: tuple[UUID, ...] = (),
        *,
        organizer: bool = False,
    ) -> tuple[Team, object, UserOutput]:
        initial = await self.get(team_id)
        if organizer:
            others = tuple({*others, *(m.user_id for m in initial.members)})
        actor = await self.auth.lock_actor(actor, others)
        event = await self.events.get(initial.event_id, lock=True)
        team = await self.get(team_id, lock=True)
        if organizer:
            await self.events.require_organizer(actor, event.id)
        elif actor.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrators cannot modify teams")
        self.frozen(event)
        return team, event, actor

    async def render(self, teams: list[Team], actor: UserOutput) -> list[TeamOutput]:
        users = await self.auth.users(
            list({member.user_id for team in teams for member in team.members})
        )
        result = []
        for team in teams:
            member = next((m for m in team.members if m.user_id == actor.id), None)
            active = member is not None and member.status == "active" and not actor.is_admin
            pending = member is not None and member.status == "pending" and not actor.is_admin
            result.append(
                TeamOutput(
                    id=team.id,
                    event_id=team.event_id,
                    name=team.name,
                    status=team.status,
                    track_id=team.track_id,
                    leader_id=team.leader_id,
                    invite_code=team.invite_code if active else None,
                    invite_expires_at=team.invite_expires_at if active else None,
                    repo_url=None if pending else team.repo_url,
                    review_note=None if pending else team.review_note,
                    reviewed_at=team.reviewed_at,
                    disbanded_at=team.disbanded_at,
                    created_at=team.created_at,
                    members=[
                        MemberOutput(
                            user=UserBrief.model_validate(users[m.user_id]),
                            status=m.status,
                            joined_at=m.joined_at,
                        )
                        for m in team.members
                        if not pending or m.user_id == actor.id
                    ],
                )
            )
        return result

    async def view(self, actor: UserOutput, team_id: UUID) -> TeamOutput:
        team = await self.get(team_id)
        await self.events.read(team.event_id, actor)
        member = any(m.user_id == actor.id for m in team.members)
        roles = await self.auth.roles_in_event(team.event_id)
        organizer = any(r.user_id == actor.id and r.role == "organizer" for r in roles)
        assigned = self.judging and await self.judging.can_read_team(actor.id, team.id)
        if not (actor.is_admin or member or organizer or assigned):
            raise ApiError(403, "FORBIDDEN", "Team is outside the user's scope")
        return (await self.render([team], actor))[0]

    async def own(self, actor: UserOutput, event_id: UUID) -> TeamOutput:
        await self.auth.require_event_role(actor, event_id, ("participant",))
        member = await self.repository.membership(event_id, actor.id)
        if member is None:
            raise ApiError(404, "TEAM_NOT_FOUND", "User has no team")
        return await self.view(actor, member.team_id)

    async def list(
        self,
        actor: UserOutput,
        event_id: UUID,
        status: str | None,
        track_id: UUID | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> Page[TeamOutput]:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        rows, total = await self.repository.list(event_id, status, track_id, q, limit, offset)
        return Page(items=await self.render(rows, actor), total=total)

    async def public(self, actor: UserOutput | None, event_id: UUID) -> list[PublicTeam]:
        await self.events.read(event_id, actor)
        return [
            PublicTeam(
                id=team.id,
                name=team.name,
                track_id=team.track_id,
                member_count=sum(m.status == "active" for m in team.members),
                approved_at=team.reviewed_at,
            )
            for team in await self.repository.approved(event_id)
        ]

    async def directory(
        self, actor: UserOutput, event_id: UUID, q: str | None, limit: int, offset: int
    ) -> Page[TeamBrief]:
        await self.events.get(event_id)
        await self.auth.require_event_role(actor, event_id, ("judge",))
        rows, total = await self.repository.list(event_id, None, None, q, limit, offset)
        return Page(items=[TeamBrief.model_validate(team) for team in rows], total=total)

    async def list_events(
        self,
        actor: UserOutput | None,
        status: str | None,
        q: str | None,
        archived: bool,
        limit: int,
        offset: int,
    ) -> Page[EventSummary]:
        if archived and (not actor or not actor.is_admin):
            raise ApiError(403, "FORBIDDEN", "Only administrators may include archived events")
        roles = await self.auth.role_records(actor.id) if actor else []
        drafts = (
            None
            if actor and actor.is_admin
            else [r.event_id for r in roles if r.role == "organizer"]
        )
        rows, total = await self.events.query_list(drafts, archived, status, q, limit, offset)
        team_counts = (
            await self.repository.counts([row.id for row in rows])
            if actor and actor.is_admin
            else {}
        )
        participant_counts = (
            await self.auth.participant_counts([row.id for row in rows])
            if actor and actor.is_admin
            else {}
        )
        return Page(
            items=[
                EventSummary(
                    **EventOutput.model_validate(row).model_dump(),
                    team_count=team_counts.get(row.id, 0) if actor and actor.is_admin else None,
                    participant_count=participant_counts.get(row.id, 0)
                    if actor and actor.is_admin
                    else None,
                )
                for row in rows
            ],
            total=total,
        )

    async def my_events(self, actor: UserOutput, limit: int, offset: int) -> Page[MyEvent]:
        if actor.is_admin:
            raise ApiError(403, "FORBIDDEN", "Use administrator event listings")
        roles = await self.auth.role_records(actor.id)
        rows, total = await self.events.query_list(
            [r.event_id for r in roles],
            True,
            None,
            None,
            limit,
            offset,
            list({r.event_id for r in roles}),
        )
        memberships = {
            m.event_id: m
            for m in await self.repository.memberships([actor.id], [row.id for row in rows])
        }
        teams = {
            team.id: team
            for team in await self.repository.get_many([m.team_id for m in memberships.values()])
        }
        result = []
        for event in rows:
            member = memberships.get(event.id)
            team = teams.get(member.team_id) if member else None
            result.append(
                MyEvent(
                    event=EventSummary.model_validate(event),
                    roles=sorted(r.role for r in roles if r.event_id == event.id),
                    team=MyTeam(
                        id=team.id, name=team.name, status=team.status, member_status=member.status
                    )
                    if team
                    else None,
                )
            )
        return Page(items=result, total=total)

    async def register(self, actor: UserOutput, event_id: UUID, *, withdraw: bool = False) -> None:
        actor = await self.auth.lock_actor(actor)
        if actor.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrators cannot register")
        event = await self.events.get(event_id, lock=True)
        now = datetime.now(UTC)
        if (
            event.status != "open"
            or event.archived_at
            or not utc(event.registration_opens_at) <= now < utc(event.registration_closes_at)
        ):
            raise ApiError(409, "REGISTRATION_CLOSED", "Registration is closed")
        roles = [r for r in await self.auth.roles_in_event(event_id) if r.user_id == actor.id]
        if withdraw:
            if await self.repository.membership(event_id, actor.id):
                raise ApiError(
                    409, "ALREADY_IN_TEAM", "Leave the team before withdrawing registration"
                )
            for role in roles:
                if role.role == "participant":
                    await self.auth.revoke_role(role.id)
        else:
            if roles:
                raise ApiError(409, "ROLE_CONFLICT", "User already has an event role")
            await self.auth.grant_role(actor.id, event_id, "participant")
        await self.events.log(
            actor,
            "registration.withdrawn" if withdraw else "registration.created",
            event_id,
            {"user_id": actor.id},
        )
        await self.repository.commit()

    async def registrations(
        self, actor: UserOutput, event_id: UUID, q: str | None, limit: int, offset: int
    ) -> Page[Registration]:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        rows, total = await self.auth.role_page(event_id, "participant", q, limit, offset)
        users = await self.auth.users([r.user_id for r in rows])
        members = {m.user_id: m for m in await self.repository.memberships(list(users), [event_id])}
        return Page(
            items=[
                Registration(
                    user=UserBrief.model_validate(users[r.user_id]),
                    registered_at=utc(r.created_at),
                    team_id=members[r.user_id].team_id if r.user_id in members else None,
                    member_status=members[r.user_id].status if r.user_id in members else None,
                )
                for r in rows
            ],
            total=total,
        )

    async def create(self, actor: UserOutput, event_id: UUID, data: TeamCreate) -> TeamOutput:
        actor = await self.auth.lock_actor(actor)
        event = await self.events.get(event_id, lock=True)
        await self.auth.require_event_role(actor, event_id, ("participant",))
        self.frozen(event)
        if await self.repository.membership(event_id, actor.id):
            raise ApiError(409, "ALREADY_IN_TEAM", "User already belongs to a team")
        await self.events.ensure_track(event_id, data.track_id)
        team = await self.repository.create(
            event_id,
            actor.id,
            data.model_dump()
            | {"invite_code": token_urlsafe(24), "invite_expires_at": event.registration_closes_at},
        )
        await self.events.log(actor, "team.created", team.id, {"event_id": event_id}, "team")
        result = (await self.render([team], actor))[0]
        await self.repository.commit()
        return result

    @staticmethod
    def invalidate_review(team: Team) -> None:
        team.status = "pending"
        team.review_note = None
        team.reviewed_at = None

    async def save(
        self, team: Team, actor: UserOutput, action: str, data: dict[str, object] | None = None
    ) -> TeamOutput:
        await self.repository.flush()
        await self.events.log(actor, action, team.id, data or {}, "team")
        result = (await self.render([team], actor))[0]
        await self.repository.commit()
        return result

    async def update(self, actor: UserOutput, team_id: UUID, data: TeamPatch) -> TeamOutput:
        team, event, actor = await self.locked(actor, team_id)
        self.leader(team, actor)
        values = data.model_dump(exclude_unset=True)
        if "track_id" in values:
            await self.events.ensure_track(event.id, data.track_id)
        if any(getattr(team, key) != value for key, value in values.items()):
            self.invalidate_review(team)
        for key, value in values.items():
            setattr(team, key, value)
        return await self.save(team, actor, "team.updated", values)

    async def invite_code(self, actor: UserOutput, team_id: UUID) -> str:
        team, event, actor = await self.locked(actor, team_id)
        self.leader(team, actor)
        team.invite_code = token_urlsafe(24)
        team.invite_expires_at = event.registration_closes_at
        await self.save(team, actor, "team.invite_rotated")
        return team.invite_code

    async def limit(self, actor: UserOutput, kind: str, window: int, limit: int) -> None:
        try:
            allowed = await rate_limits.consume(
                str(self.settings.redis_url), f"seal:teams:{kind}:{actor.id}", window, limit
            )
        except RedisError:
            raise ApiError(503, "RATE_LIMIT_UNAVAILABLE", "Rate limiter unavailable") from None
        if not allowed:
            raise ApiError(429, "RATE_LIMITED", "Too many requests")

    async def join(self, actor: UserOutput, code: str) -> TeamOutput:
        if actor.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrators cannot join teams")
        await self.limit(actor, "join", 60, 30)
        initial = await self.repository.by_invite(code)
        if initial is None:
            raise ApiError(404, "INVALID_INVITE_CODE", "Invite code is invalid")
        team, event, actor = await self.locked(actor, initial.id)
        await self.auth.require_event_role(actor, event.id, ("participant",))
        if (
            team.invite_code != code
            or not team.invite_expires_at
            or datetime.now(UTC) >= utc(team.invite_expires_at)
        ):
            raise ApiError(404, "INVALID_INVITE_CODE", "Invite code is invalid or expired")
        if await self.repository.membership(event.id, actor.id):
            raise ApiError(409, "ALREADY_IN_TEAM", "User already belongs to a team")
        if len(team.members) >= event.max_team_size:
            raise ApiError(409, "TEAM_FULL", "Team is full")
        await self.repository.add_member(team, actor.id, "pending")
        self.invalidate_review(team)
        return await self.save(team, actor, "team.join_requested", {"user_id": actor.id})

    async def approve_member(self, actor: UserOutput, team_id: UUID, user_id: UUID) -> TeamOutput:
        team, event, actor = await self.locked(actor, team_id, (user_id,))
        self.leader(team, actor)
        member = next((m for m in team.members if m.user_id == user_id), None)
        if member is None:
            raise ApiError(404, "MEMBER_NOT_FOUND", "Member not found")
        target = (await self.auth.users([user_id])).get(user_id)
        if not target or not target.is_active or target.is_admin or not target.email_verified:
            raise ApiError(409, "ROLE_CONFLICT", "Member account is not eligible")
        if len(team.members) > event.max_team_size:
            raise ApiError(409, "TEAM_FULL", "Team is full")
        member.status = "active"
        self.invalidate_review(team)
        return await self.save(team, actor, "team.member_approved", {"user_id": user_id})

    async def remove_member(self, actor: UserOutput, team_id: UUID, user_id: UUID) -> None:
        team, _, actor = await self.locked(actor, team_id, (user_id,))
        if actor.id != user_id:
            self.leader(team, actor)
        member = next((m for m in team.members if m.user_id == user_id), None)
        if member is None:
            raise ApiError(404, "MEMBER_NOT_FOUND", "Member not found")
        if user_id == team.leader_id:
            if len(team.members) > 1:
                raise ApiError(409, "TEAM_HAS_MEMBERS", "Transfer leadership before leaving")
            team.disbanded_at = datetime.now(UTC)
            team.invite_code = None
            team.invite_expires_at = None
        await self.repository.remove_member(team, user_id)
        self.invalidate_review(team)
        await self.save(team, actor, "team.member_removed", {"user_id": user_id})

    async def transfer(self, actor: UserOutput, team_id: UUID, user_id: UUID) -> TeamOutput:
        team, _, actor = await self.locked(actor, team_id, (user_id,))
        self.leader(team, actor)
        member = next(
            (m for m in team.members if m.user_id == user_id and m.status == "active"), None
        )
        target = (await self.auth.users([user_id])).get(user_id)
        if (
            member is None
            or not target
            or not target.is_active
            or target.is_admin
            or not target.email_verified
        ):
            raise ApiError(409, "ROLE_CONFLICT", "New leader must be an active member")
        team.leader_id = user_id
        return await self.save(team, actor, "team.leader_transferred", {"user_id": user_id})

    async def repo(self, actor: UserOutput, team_id: UUID, repo_url: str) -> TeamOutput:
        team, event, actor = await self.locked(actor, team_id)
        self.leader(team, actor)
        canonical = await github_client.verify_public_repo(repo_url, self.settings)
        self.frozen(event)
        if team.repo_url != canonical:
            team.repo_url = canonical
            self.invalidate_review(team)
        return await self.save(team, actor, "team.repo_updated", {"repo_url": canonical})

    async def invitation(self, actor: UserOutput, team_id: UUID, email: str) -> None:
        await self.limit(actor, "email", 3600, 30)
        team, _, actor = await self.locked(actor, team_id)
        self.leader(team, actor)
        if (
            not team.invite_code
            or not team.invite_expires_at
            or datetime.now(UTC) >= utc(team.invite_expires_at)
        ):
            raise ApiError(409, "INVALID_INVITE_CODE", "Invite code is expired")
        link = f"{str(self.settings.frontend_url).rstrip('/')}/join?code={team.invite_code}"
        await self.repository.commit()
        await self.auth.queue_email(
            email, "SEAL - Team invitation", f"You are invited to join {team.name}: {link}"
        )

    async def review(self, actor: UserOutput, team_id: UUID, data: ReviewInput) -> TeamOutput:
        team, event, actor = await self.locked(actor, team_id, organizer=True)
        if data.status == "approved":
            if (
                not event.min_team_size <= len(team.members) <= event.max_team_size
                or any(m.status != "active" for m in team.members)
                or not team.repo_url
            ):
                raise ApiError(
                    409,
                    "TEAM_NOT_ELIGIBLE",
                    "Team requires eligible members and a public repository",
                )
            users = await self.auth.users([m.user_id for m in team.members])
            if any(
                not user.is_active or user.is_admin or not user.email_verified
                for user in users.values()
            ):
                raise ApiError(409, "TEAM_NOT_ELIGIBLE", "Team has an ineligible account")
            await github_client.verify_public_repo(team.repo_url, self.settings)
            self.frozen(event)
        changed = team.status != data.status or team.review_note != data.note
        team.status = data.status
        team.review_note = data.note
        if changed:
            team.reviewed_at = datetime.now(UTC)
        leader = (await self.auth.users([team.leader_id]))[team.leader_id]
        result = await self.save(team, actor, "team.reviewed", data.model_dump())
        if changed:
            # shortcut: queue lỗi sau commit cần BTC kiểm tra lại; Phase 7 bổ sung outbox.
            await self.auth.queue_email(
                str(leader.email),
                "SEAL - Team review",
                f"Team {team.name}: {data.status}. {data.note or ''}",
            )
        return result

    async def transition(self, actor: UserOutput, event_id: UUID, to_status: str) -> EventOutput:
        approved = await self.repository.approved(event_id)
        member_ids = tuple({m.user_id for team in approved for m in team.members})
        event, actor = await self.events.locked(actor, event_id, others=member_ids)
        self.events.editable(event)
        transitions = {
            "draft": "open",
            "open": "ongoing",
            "ongoing": "judging",
            "judging": "closed",
        }
        if transitions.get(event.status) != to_status:
            raise ApiError(
                409, "INVALID_STATUS_TRANSITION", "Status transitions must be sequential"
            )
        rounds = await self.events.rounds(event_id)
        now = datetime.now(UTC)
        if to_status == "open" and (not rounds or now >= utc(event.starts_at)):
            raise ApiError(409, "INVALID_SCHEDULE", "Configure rounds before opening registration")
        if to_status == "ongoing":
            if now < utc(event.starts_at):
                raise ApiError(409, "INVALID_STATUS_TRANSITION", "Event has not started")
            approved = await self.repository.approved(event_id)
            users = await self.auth.users(list({m.user_id for t in approved for m in t.members}))
            for team in approved:
                if (
                    not event.min_team_size <= len(team.members) <= event.max_team_size
                    or any(m.status != "active" for m in team.members)
                    or not team.repo_url
                    or any(
                        not users[m.user_id].is_active
                        or not users[m.user_id].email_verified
                        or users[m.user_id].is_admin
                        for m in team.members
                    )
                ):
                    raise ApiError(409, "TEAM_NOT_ELIGIBLE", "Approved team violates eligibility")
        if to_status == "judging" and any(now < utc(r.submission_deadline) for r in rounds):
            raise ApiError(409, "INVALID_STATUS_TRANSITION", "Rounds still accept submissions")
        if to_status == "closed" and (
            not self.judging or not await self.judging.results_ready([r.id for r in rounds])
        ):
            raise ApiError(
                409, "RESULTS_NOT_READY", "Closing requires published round results from Phase 4"
            )
        previous = event.status
        event.status = to_status
        await self.events.log(
            actor, "event.transitioned", event.id, {"before": previous, "after": to_status}
        )
        result = EventOutput.model_validate(event)
        await self.repository.commit()
        return result

    async def delete_track(self, actor: UserOutput, event_id: UUID, track_id: UUID) -> None:
        await self.events.locked(actor, event_id)
        if await self.repository.track_used(track_id):
            raise ApiError(409, "RESOURCE_IN_USE", "Track is referenced by a team")
        await self.events.change_child(actor, event_id, "tracks", None, track_id)

    async def update_event(
        self, actor: UserOutput, event_id: UUID, data: EventPatch
    ) -> EventOutput:
        event, actor = await self.events.locked(actor, event_id, admin=actor.is_admin)
        if (
            data.max_team_size is not None
            and data.max_team_size < await self.repository.largest_team(event_id)
        ):
            raise ApiError(409, "TEAM_FULL", "Existing teams exceed the requested size")
        if data.min_team_size is not None and any(
            len(t.members) < data.min_team_size for t in await self.repository.approved(event_id)
        ):
            raise ApiError(
                409, "TEAM_NOT_ELIGIBLE", "An approved team is smaller than the requested minimum"
            )
        if data.registration_closes_at is not None:
            await self.repository.invite_deadline(event_id, data.registration_closes_at)
        return await self.events.update(actor, event_id, data)

    async def approved_for_judging(self, event_id: UUID) -> list:
        return await self.repository.approved(event_id)

    async def judging_teams(self, ids: list[UUID]) -> dict:
        return {t.id: t for t in await self.repository.get_many(ids)}
