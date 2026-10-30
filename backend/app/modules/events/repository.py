from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.events.models import Event, Prize, Round, RoundEligibility, Track

Child = Round | Track | Prize
CHILDREN = {"rounds": Round, "tracks": Track, "prizes": Prize}


class EventRepository:
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

    async def eligible(self, round_id: UUID, team_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(RoundEligibility.id).where(
                    RoundEligibility.round_id == round_id, RoundEligibility.team_id == team_id
                )
            )
            is not None
        )

    async def commit(self) -> None:
        await self.session.commit()
