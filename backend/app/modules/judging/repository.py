from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.judging.models import (
    Assignment,
    Conflict,
    MentorAssignment,
    PublicationSnapshot,
    ResultEmail,
    RoundJudging,
    RubricCriterion,
    Score,
)


class JudgingRepository:
    async def ai_assigned_rounds(self, user_id: UUID, team_id: UUID) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(Assignment.round_id).where(
                    Assignment.judge_id == user_id,
                    Assignment.team_id == team_id,
                    Assignment.status != "cancelled",
                )
            )
        )

    async def ai_published_rounds(self, round_ids: list[UUID]) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(RoundJudging.round_id)
                .join(
                    PublicationSnapshot,
                    (PublicationSnapshot.round_id == RoundJudging.round_id)
                    & (PublicationSnapshot.revision == RoundJudging.publication_revision),
                )
                .where(
                    RoundJudging.round_id.in_(round_ids),
                    RoundJudging.locked_at.is_not(None),
                    RoundJudging.published_at.is_not(None),
                )
            )
        )

    @staticmethod
    def sync_round_published(session: object, round_id: UUID) -> bool:
        state = session.get(RoundJudging, round_id, populate_existing=True)
        return bool(
            state
            and state.locked_at
            and state.published_at
            and session.scalar(
                select(PublicationSnapshot.id).where(
                    PublicationSnapshot.round_id == round_id,
                    PublicationSnapshot.revision == state.publication_revision,
                )
            )
        )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rows(self, model: type, **filters: object) -> list:
        return list(
            await self.session.scalars(select(model).filter_by(**filters).order_by(model.id))
        )

    async def get(self, model: type, key: UUID) -> object | None:
        return await self.session.get(model, key, populate_existing=True)

    async def page(
        self, model: type, limit: int, offset: int, **filters: object
    ) -> tuple[list, int]:
        query = select(model).filter_by(**filters)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        order = (model.created_at.desc(), model.id) if hasattr(model, "created_at") else (model.id,)
        rows = await self.session.scalars(query.order_by(*order).limit(limit).offset(offset))
        return list(rows), total or 0

    async def add(self, model: type, **values: object) -> object:
        row = model(**values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def remove(self, row: object) -> None:
        await self.session.delete(row)
        await self.session.flush()

    async def state(self, round_id: UUID, *, create: bool = False) -> RoundJudging | None:
        row = await self.get(RoundJudging, round_id)
        if row is None and create:
            row = await self.add(RoundJudging, round_id=round_id)
        return row

    async def active_assignments(self, round_id: UUID) -> list[Assignment]:
        return list(
            await self.session.scalars(
                select(Assignment)
                .where(Assignment.round_id == round_id, Assignment.status != "cancelled")
                .order_by(Assignment.id)
            )
        )

    async def blocked_pairs(self, event_id: UUID) -> set[tuple[UUID, UUID]]:
        conflicts = await self.session.execute(
            select(Conflict.judge_id, Conflict.team_id).where(Conflict.event_id == event_id)
        )
        mentors = await self.session.execute(
            select(MentorAssignment.mentor_id, MentorAssignment.team_id).where(
                MentorAssignment.event_id == event_id
            )
        )
        return set(conflicts.all()) | set(mentors.all())

    async def mentor_assigned(self, user_id: UUID, team_id: UUID, *, history: bool = False) -> bool:
        query = select(MentorAssignment.id).where(
            MentorAssignment.mentor_id == user_id, MentorAssignment.team_id == team_id
        )
        if not history:
            query = query.where(MentorAssignment.revoked_at.is_(None))
        return await self.session.scalar(query.limit(1)) is not None

    async def judge_assigned(self, user_id: UUID, team_id: UUID, round_id: UUID | None) -> bool:
        query = select(Assignment.id).where(
            Assignment.judge_id == user_id,
            Assignment.team_id == team_id,
            Assignment.status != "cancelled",
        )
        if round_id:
            query = query.where(Assignment.round_id == round_id)
        return await self.session.scalar(query.limit(1)) is not None

    async def role_in_use(self, event_id: UUID, user_id: UUID, role: str) -> bool:
        model = Assignment if role == "judge" else MentorAssignment
        query = select(model.id).where(model.event_id == event_id)
        query = (
            query.where(Assignment.judge_id == user_id, Assignment.status != "cancelled")
            if role == "judge"
            else query.where(
                MentorAssignment.mentor_id == user_id, MentorAssignment.revoked_at.is_(None)
            )
        )
        return await self.session.scalar(query.limit(1)) is not None

    async def rubric(self, round_id: UUID) -> list[RubricCriterion]:
        return list(
            await self.session.scalars(
                select(RubricCriterion)
                .where(RubricCriterion.round_id == round_id)
                .order_by(RubricCriterion.order)
            )
        )

    async def scores(self, assignment_ids: list[UUID]) -> list[Score]:
        return list(
            await self.session.scalars(
                select(Score)
                .where(Score.assignment_id.in_(assignment_ids))
                .order_by(Score.criterion_id)
            )
        )

    async def snapshot(self, round_id: UUID, revision: int) -> PublicationSnapshot | None:
        return await self.session.scalar(
            select(PublicationSnapshot).where(
                PublicationSnapshot.round_id == round_id, PublicationSnapshot.revision == revision
            )
        )

    async def commit(self) -> None:
        await self.session.commit()


class ResultEmailRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    def claim(self) -> ResultEmail | None:
        row = self.session.scalar(
            select(ResultEmail)
            .join(PublicationSnapshot, PublicationSnapshot.id == ResultEmail.snapshot_id)
            .join(RoundJudging, RoundJudging.round_id == PublicationSnapshot.round_id)
            .where(
                ResultEmail.status == "pending",
                RoundJudging.published_at.is_not(None),
                RoundJudging.publication_revision == PublicationSnapshot.revision,
            )
            .order_by(ResultEmail.id)
            .limit(1)
            .with_for_update(of=ResultEmail, skip_locked=True)
        )
        if row:
            row.status = "sending"
            self.session.commit()
        return row

    def finish(self, row: ResultEmail, status: str) -> None:
        row.status = status
        self.session.commit()
