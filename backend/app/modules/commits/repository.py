from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.schemas import utc
from app.modules.commits.models import Commit, CommitSyncState
from app.modules.commits.schemas import CommitStats

LEASE_SECONDS = 300


def stats(state: CommitSyncState | None, total: int, last: datetime | None) -> CommitStats:
    values = (
        {
            key: getattr(state, key)
            for key in (
                "last_synced_at",
                "sync_status",
                "sync_error",
                "branch",
                "last_attempt_at",
                "truncated",
            )
        }
        if state
        else {}
    )
    if (
        state
        and state.lease_token
        and state.lease_until
        and utc(state.lease_until) <= datetime.now(UTC)
    ):
        values.update(sync_status="error", sync_error="SYNC_WORKER_TIMEOUT")
    return CommitStats(
        total=total,
        last_commit_at=last,
        running=bool(state and state.lease_until and utc(state.lease_until) > datetime.now(UTC)),
        **values,
    )


class CommitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, team_id: UUID, sha: str) -> Commit | None:
        return await self.session.scalar(
            select(Commit).where(Commit.team_id == team_id, Commit.sha == sha)
        )

    async def page(self, team_id: UUID, limit: int, offset: int) -> tuple[list[Commit], int]:
        query = select(Commit).options(defer(Commit.files)).where(Commit.team_id == team_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(Commit.first_seen_at.desc(), Commit.id).limit(limit).offset(offset)
        )
        return list(rows), total

    async def stats_many(self, ids: list[UUID]) -> dict[UUID, CommitStats]:
        states = {
            s.team_id: s
            for s in await self.session.scalars(
                select(CommitSyncState).where(CommitSyncState.team_id.in_(ids))
            )
        }
        rows = (
            await self.session.execute(
                select(Commit.team_id, func.count(), func.max(Commit.first_seen_at))
                .where(
                    Commit.team_id.in_(ids),
                    Commit.in_event_window.is_(True),
                    Commit.removed.is_(False),
                )
                .group_by(Commit.team_id)
            )
        ).all()
        counts = {tid: (count, last) for tid, count, last in rows}
        return {tid: stats(states.get(tid), *counts.get(tid, (0, None))) for tid in ids}

    async def state(self, team_id: UUID) -> CommitSyncState:
        row = await self.session.scalar(
            select(CommitSyncState)
            .where(CommitSyncState.team_id == team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            try:
                async with self.session.begin_nested():
                    self.session.add(CommitSyncState(team_id=team_id))
                    await self.session.flush()
            except IntegrityError:
                pass
            row = await self.session.scalar(
                select(CommitSyncState)
                .where(CommitSyncState.team_id == team_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        return row

    async def commit(self) -> None:
        await self.session.commit()

    async def queue_failed(self, team_id: UUID, token: str) -> None:
        await self.session.execute(
            update(CommitSyncState)
            .where(CommitSyncState.team_id == team_id, CommitSyncState.lease_token == token)
            .values(sync_status="error", sync_error="SYNC_QUEUE_UNAVAILABLE")
        )
        await self.session.commit()


class CommitJobRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    def state(self, team_id: UUID) -> CommitSyncState:
        row = self.session.get(CommitSyncState, team_id)
        if row is None:
            try:
                with self.session.begin_nested():
                    self.session.add(CommitSyncState(team_id=team_id))
                    self.session.flush()
            except IntegrityError:
                pass
            row = self.session.get(CommitSyncState, team_id)
        return row

    def claim(self, team_id: UUID, token: str, interval: int) -> bool:
        self.state(team_id)
        now = datetime.now(UTC)
        result = self.session.execute(
            update(CommitSyncState)
            .execution_options(synchronize_session="fetch")
            .where(
                CommitSyncState.team_id == team_id,
                (CommitSyncState.lease_until.is_(None)) | (CommitSyncState.lease_until <= now),
                (CommitSyncState.last_attempt_at.is_(None))
                | (CommitSyncState.last_attempt_at <= now - timedelta(minutes=interval))
                | (
                    (CommitSyncState.lease_token.is_not(None))
                    & (CommitSyncState.lease_until <= now)
                ),
            )
            .values(
                lease_token=token,
                lease_until=now + timedelta(seconds=LEASE_SECONDS),
                last_attempt_at=now,
            )
        )
        self.session.commit()
        return bool(result.rowcount)

    def heartbeat(self, team_id: UUID, token: str) -> None:
        result = self.session.execute(
            update(CommitSyncState)
            .execution_options(synchronize_session="fetch")
            .where(
                CommitSyncState.team_id == team_id,
                CommitSyncState.lease_token == token,
                CommitSyncState.lease_until > datetime.now(UTC),
            )
            .values(lease_until=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS))
        )
        self.session.commit()
        if not result.rowcount:
            raise RuntimeError("SYNC_LEASE_LOST")

    def fence(self, team_id: UUID, token: str) -> None:
        row = self.session.scalar(
            select(CommitSyncState)
            .where(CommitSyncState.team_id == team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not row
            or row.lease_token != token
            or not row.lease_until
            or utc(row.lease_until) <= datetime.now(UTC)
        ):
            raise RuntimeError("SYNC_LEASE_LOST")

    def start(self, team_id: UUID, queued: str, running: str) -> bool:
        result = self.session.execute(
            update(CommitSyncState)
            .execution_options(synchronize_session="fetch")
            .where(
                CommitSyncState.team_id == team_id,
                CommitSyncState.lease_token == queued,
                CommitSyncState.lease_until > datetime.now(UTC),
            )
            .values(lease_token=running)
        )
        self.session.commit()
        return bool(result.rowcount)

    def release(self, team_id: UUID, token: str, error: str | None = None) -> None:
        self.session.execute(
            update(CommitSyncState)
            .execution_options(synchronize_session="fetch")
            .where(CommitSyncState.team_id == team_id, CommitSyncState.lease_token == token)
            .values(
                lease_token=None,
                lease_until=None,
                **({"sync_status": "error", "sync_error": error} if error else {}),
            )
        )
        self.session.commit()

    def stored(self, team_id: UUID) -> dict[str, Commit]:
        return {
            c.sha: c
            for c in self.session.scalars(
                select(Commit).options(defer(Commit.files)).where(Commit.team_id == team_id)
            )
        }

    def save_commit(self, team_id: UUID, values: dict) -> None:
        self.session.add(Commit(team_id=team_id, **values))

    def commit(self) -> None:
        self.session.commit()
