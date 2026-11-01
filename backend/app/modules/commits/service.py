from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.concurrency import run_in_threadpool

from app.core.errors import ApiError
from app.core.schemas import Page, utc
from app.modules.commits.repository import LEASE_SECONDS, CommitRepository
from app.modules.commits.schemas import (
    CommitOutput,
    CommitOverview,
    CommitStats,
    DiffPage,
    SyncQueued,
)


class CommitService:
    def __init__(
        self, repository: CommitRepository, teams: object = None, events: object = None
    ) -> None:
        self.repository = repository
        self.teams = teams
        self.events = events

    async def exists(self, team_id: UUID, sha: str) -> bool:
        return await self.repository.get(team_id, sha) is not None

    async def access(self, actor: object, team_id: UUID) -> object:
        team = await self.teams.get(team_id)
        await self.events.read(team.event_id, actor)
        roles = await self.teams.auth.roles_in_event(team.event_id)
        if not (
            actor.is_admin
            or any(m.user_id == actor.id and m.status == "active" for m in team.members)
            or any(r.user_id == actor.id and r.role == "organizer" for r in roles)
            or await self.teams.judging.can_read_team(actor.id, team_id)
        ):
            raise ApiError(403, "FORBIDDEN", "Team is outside the user's scope")
        return team

    async def page(
        self, actor: object, team_id: UUID, limit: int, offset: int
    ) -> Page[CommitOutput]:
        await self.access(actor, team_id)
        rows, total = await self.repository.page(team_id, limit, offset)
        return Page(items=[CommitOutput.model_validate(row) for row in rows], total=total)

    async def get(self, actor: object, team_id: UUID, sha: str) -> object:
        await self.access(actor, team_id)
        row = await self.repository.get(team_id, sha)
        if row is None:
            raise ApiError(404, "COMMIT_NOT_FOUND", "Commit not found for this team")
        return row

    async def detail(self, actor: object, team_id: UUID, sha: str) -> CommitOutput:
        return CommitOutput.model_validate(await self.get(actor, team_id, sha))

    async def diff(
        self, actor: object, team_id: UUID, sha: str, limit: int, offset: int
    ) -> DiffPage:
        row = await self.get(actor, team_id, sha)
        return DiffPage(
            items=row.files[offset : offset + limit],
            total=len(row.files),
            truncated=row.diff_truncated,
        )

    async def stats(self, actor: object, team_id: UUID) -> CommitStats:
        await self.access(actor, team_id)
        return (await self.repository.stats_many([team_id]))[team_id]

    async def overview(
        self, actor: object, event_id: UUID, limit: int, offset: int
    ) -> Page[CommitOverview]:
        event = await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id)
        page = await self.teams.list(actor, event_id, None, None, None, limit, offset)
        values = await self.repository.stats_many([t.id for t in page.items])
        started_at = await self.teams.auth.event_started_at(event_id) or event.starts_at
        now = datetime.now(UTC)
        return Page(
            items=[
                CommitOverview(
                    team={"id": t.id, "name": t.name},
                    inactive=bool(
                        values[t.id].sync_status == "ok"
                        and now - utc(values[t.id].last_commit_at or started_at)
                        >= timedelta(hours=event.inactivity_alert_hours)
                    ),
                    **values[t.id].model_dump(),
                )
                for t in page.items
            ],
            total=page.total,
        )

    async def sync(self, actor: object, team_id: UUID) -> SyncQueued:
        from worker.tasks.commits import sync_team

        team = await self.teams.get(team_id)
        event, actor = await self.events.locked(actor, team.event_id)
        team = await self.teams.get(team_id, lock=True)
        if event.status != "ongoing" or event.archived_at:
            raise ApiError(409, "EVENT_NOT_ONGOING", "Sync requires an ongoing event")
        if team.status != "approved" or not team.repo_url:
            raise ApiError(409, "TEAM_NOT_ELIGIBLE", "Approved team with a repository required")
        state = await self.repository.state(team_id)
        now = datetime.now(UTC)
        if state.lease_until and utc(state.lease_until) > now:
            raise ApiError(409, "SYNC_IN_PROGRESS", "A sync is already queued or running")
        if state.last_attempt_at and now - utc(state.last_attempt_at) < timedelta(seconds=60):
            raise ApiError(429, "RATE_LIMITED", "Wait 60 seconds between sync attempts")
        token = str(uuid4())
        state.lease_token = token
        state.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        state.last_attempt_at = now
        await self.events.log(actor, "commits.sync_requested", team_id, {}, "team")
        await self.repository.commit()
        try:
            await run_in_threadpool(
                sync_team.apply_async, args=[str(team_id), token], task_id=token
            )
        except Exception:
            # Keep lease on ambiguous enqueue; a delivered task may already own it.
            await self.repository.queue_failed(team_id, token)
            raise ApiError(
                503, "SYNC_QUEUE_UNAVAILABLE", "Sync queue unavailable; check status before retry"
            ) from None
        return SyncQueued(task_id=token)
