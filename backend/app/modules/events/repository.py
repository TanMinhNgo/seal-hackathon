from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.events.models import Event, Prize, Round, RoundEligibility, Track

Child = Round | Track | Prize
CHILDREN = {"rounds": Round, "tracks": Track, "prizes": Prize}


class EventRepository:
    @staticmethod
    def reminder_rounds(session: object, now: datetime) -> list[tuple[object, set[UUID] | None]]:
        events = list(
            session.scalars(
                select(Event).where(Event.status == "ongoing", Event.archived_at.is_(None))
            )
        )
        rounds = list(
            session.scalars(
                select(Round)
                .where(Round.event_id.in_([e.id for e in events]), Round.submission_deadline > now)
                .order_by(Round.event_id, Round.order)
            )
        )
        eligibilities = list(
            session.scalars(
                select(RoundEligibility).where(
                    RoundEligibility.round_id.in_([r.id for r in rounds])
                )
            )
        )
        first = dict(
            session.execute(
                select(Round.event_id, func.min(Round.order)).group_by(Round.event_id)
            ).all()
        )
        return [
            (
                r,
                None
                if r.order == first[r.event_id]
                else {e.team_id for e in eligibilities if e.round_id == r.id},
            )
            for r in rounds
        ]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, event_id: UUID, *, lock: bool = False) -> Event | None:
        query = select(Event).where(Event.id == event_id).execution_options(populate_existing=True)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def by_slug(self, slug: str) -> Event | None:
        return await self.session.scalar(select(Event).where(Event.slug == slug))

    async def list(
        self,
        visible_drafts: list[UUID] | None,
        archived: bool,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
        ids: list[UUID] | None = None,
    ) -> tuple[list[Event], int]:
        query = select(Event)
        if visible_drafts is not None:
            query = query.where(or_(Event.status != "draft", Event.id.in_(visible_drafts)))
        if not archived:
            query = query.where(Event.archived_at.is_(None))
        if ids is not None:
            query = query.where(Event.id.in_(ids))
        if status:
            query = query.where(Event.status == status)
        if q:
            query = query.where(func.lower(Event.name).contains(q.lower(), autoescape=True))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(Event.created_at.desc(), Event.id).limit(limit).offset(offset)
        )
        return list(rows), total

    async def flush(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ApiError(409, "RESOURCE_CONFLICT", "Duplicate or referenced resource") from None

    async def create(self, values: dict[str, object]) -> Event:
        event = Event(**values)
        self.session.add(event)
        await self.flush()
        return event

    async def child(self, kind: str, event_id: UUID, child_id: UUID) -> Child | None:
        model = CHILDREN[kind]
        return await self.session.scalar(
            select(model).where(model.id == child_id, model.event_id == event_id)
        )

    async def children(
        self, kind: str, event_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[list[Child], int]:
        model = CHILDREN[kind]
        query = select(model).where(model.event_id == event_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        order = model.order if kind == "rounds" else model.rank if kind == "prizes" else model.name
        rows = await self.session.scalars(
            query.order_by(order, model.id).limit(limit).offset(offset)
        )
        return list(rows), total

    async def all_rounds(self, event_id: UUID) -> list[Round]:
        return list(
            await self.session.scalars(
                select(Round).where(Round.event_id == event_id).order_by(Round.order)
            )
        )

    async def create_child(self, kind: str, event_id: UUID, values: dict[str, object]) -> Child:
        child = CHILDREN[kind](event_id=event_id, **values)
        self.session.add(child)
        await self.flush()
        return child

    async def remove(self, child: Child) -> None:
        await self.session.delete(child)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ApiError(409, "RESOURCE_IN_USE", "Resource is still referenced") from None

    async def commit(self) -> None:
        await self.session.commit()

    async def eligibility_sources(self, round_id: UUID) -> dict[UUID, UUID | None]:
        return dict(
            (
                await self.session.execute(
                    select(RoundEligibility.team_id, RoundEligibility.source_round_id).where(
                        RoundEligibility.round_id == round_id
                    )
                )
            ).all()
        )

    async def replace_eligibility(
        self, round_id: UUID, source_id: UUID, team_ids: list[UUID]
    ) -> None:
        await self.session.execute(
            delete(RoundEligibility).where(RoundEligibility.round_id == round_id)
        )
        self.session.add_all(
            [
                RoundEligibility(round_id=round_id, source_round_id=source_id, team_id=t)
                for t in team_ids
            ]
        )
        await self.session.flush()

    async def has_started_dependents(self, source_id: UUID, now: datetime) -> bool:
        return (
            await self.session.scalar(
                select(RoundEligibility.id)
                .join(Round, Round.id == RoundEligibility.round_id)
                .where(RoundEligibility.source_round_id == source_id, Round.starts_at <= now)
                .limit(1)
            )
            is not None
        )
