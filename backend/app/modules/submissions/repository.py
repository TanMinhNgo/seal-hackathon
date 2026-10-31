from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.submissions.models import DeadlineReminder, FileUpload, Submission, SubmissionFile


class SubmissionJobRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    def claim(
        self, team_id: UUID, round_id: UUID, hours: int, now: datetime
    ) -> DeadlineReminder | None:
        existing = self.session.scalar(
            select(DeadlineReminder.id).where(
                DeadlineReminder.team_id == team_id,
                DeadlineReminder.round_id == round_id,
                DeadlineReminder.hours == hours,
            )
        )
        if existing:
            return None
        row = DeadlineReminder(team_id=team_id, round_id=round_id, hours=hours, created_at=now)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return None
        return row

    def finish(self, reminder: DeadlineReminder, status: str) -> None:
        reminder.status = status
        self.session.commit()

    def cleanup(self, before: datetime, storage: object) -> int:
        rows = list(
            self.session.scalars(
                select(FileUpload)
                .where(FileUpload.created_at < before)
                .order_by(FileUpload.key)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            storage.delete_temporary(row.key)
            self.session.delete(row)
        self.session.commit()
        return len(rows)


class SubmissionRepository:
    async def get_many(self, ids: list[UUID]) -> list[Submission]:
        return list(
            await self.session.scalars(
                select(Submission)
                .options(selectinload(Submission.files))
                .where(Submission.id.in_(ids))
            )
        )

    async def finals(self, team_ids: list[UUID], round_id: UUID) -> list[Submission]:
        latest = (
            select(Submission.team_id, func.max(Submission.version).label("version"))
            .where(Submission.round_id == round_id)
            .group_by(Submission.team_id)
            .subquery()
        )
        return list(
            await self.session.scalars(
                select(Submission)
                .options(selectinload(Submission.files))
                .join(
                    latest,
                    (Submission.team_id == latest.c.team_id)
                    & (Submission.version == latest.c.version),
                )
                .where(Submission.round_id == round_id, Submission.team_id.in_(team_ids))
            )
        )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def receipt(
        self, user_id: UUID, team_id: UUID, round_id: UUID, key: str
    ) -> Submission | None:
        return await self.session.scalar(
            select(Submission)
            .options(selectinload(Submission.files))
            .where(
                Submission.submitted_by == user_id,
                Submission.team_id == team_id,
                Submission.round_id == round_id,
                Submission.idempotency_key == key,
            )
        )

    async def get(self, submission_id: UUID) -> Submission | None:
        return await self.session.scalar(
            select(Submission)
            .options(selectinload(Submission.files))
            .where(Submission.id == submission_id)
        )

    async def latest(self, team_ids: list[UUID], round_id: UUID) -> dict[UUID, int]:
        rows = await self.session.execute(
            select(Submission.team_id, func.max(Submission.version))
            .where(Submission.team_id.in_(team_ids), Submission.round_id == round_id)
            .group_by(Submission.team_id)
        )
        return dict(rows.all())

    async def list(
        self, team_ids: list[UUID], round_id: UUID, limit: int, offset: int, *, final: bool = False
    ) -> tuple[list[Submission], int]:
        query = select(Submission).where(
            Submission.team_id.in_(team_ids), Submission.round_id == round_id
        )
        if final:
            latest = (
                select(Submission.team_id, func.max(Submission.version).label("version"))
                .where(Submission.round_id == round_id)
                .group_by(Submission.team_id)
                .subquery()
            )
            query = query.join(
                latest,
                (Submission.team_id == latest.c.team_id) & (Submission.version == latest.c.version),
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.options(selectinload(Submission.files))
            .order_by(Submission.version.desc(), Submission.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def uploads(self, keys: list[str]) -> list[FileUpload]:
        return list(
            await self.session.scalars(
                select(FileUpload)
                .where(FileUpload.key.in_(keys))
                .order_by(FileUpload.key)
                .with_for_update()
            )
        )

    async def add_upload(self, **values: object) -> None:
        self.session.add(FileUpload(**values))
        await self.session.flush()

    async def create(self, values: dict[str, object], files: list[dict[str, object]]) -> Submission:
        row = Submission(**values, files=[SubmissionFile(**f) for f in files])
        self.session.add(row)
        await self.session.flush()
        return row

    async def commit(self) -> None:
        await self.session.commit()
