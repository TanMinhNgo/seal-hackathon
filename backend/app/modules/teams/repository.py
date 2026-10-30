from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ApiError
from app.modules.teams.models import Team, TeamMember


class TeamRepository:
    @staticmethod
    def reminder_teams(session: object, event_id: UUID, eligible: set[UUID] | None) -> list[object]:
        query = (
            select(Team)
            .join(
                TeamMember, (TeamMember.team_id == Team.id) & (TeamMember.user_id == Team.leader_id)
            )
            .where(
                Team.event_id == event_id,
                Team.status == "approved",
                Team.disbanded_at.is_(None),
                TeamMember.status == "active",
            )
        )
        if eligible is not None:
            query = query.where(Team.id.in_(eligible))
        return list(session.scalars(query))

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, team_id: UUID, *, lock: bool = False) -> Team | None:
        query = (
            select(Team)
            .options(selectinload(Team.members))
            .where(Team.id == team_id)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def membership(self, event_id: UUID, user_id: UUID) -> TeamMember | None:
        return await self.session.scalar(
            select(TeamMember).where(TeamMember.event_id == event_id, TeamMember.user_id == user_id)
        )

    async def get_many(self, ids: list[UUID]) -> list[Team]:
        return list(
            await self.session.scalars(
                select(Team).where(Team.id.in_(ids), Team.disbanded_at.is_(None))
            )
        )

    async def memberships(self, user_ids: list[UUID], event_ids: list[UUID]) -> list[TeamMember]:
        return list(
            await self.session.scalars(
                select(TeamMember).where(
                    TeamMember.user_id.in_(user_ids), TeamMember.event_id.in_(event_ids)
                )
            )
        )

    async def by_invite(self, code: str) -> Team | None:
        return await self.session.scalar(
            select(Team).where(Team.invite_code == code, Team.disbanded_at.is_(None))
        )

    async def list(
        self,
        event_id: UUID,
        status: str | None,
        track_id: UUID | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Team], int]:
        query = select(Team).where(Team.event_id == event_id, Team.disbanded_at.is_(None))
        if status:
            query = query.where(Team.status == status)
        if track_id:
            query = query.where(Team.track_id == track_id)
        if q:
            query = query.where(func.lower(Team.name).contains(q.lower(), autoescape=True))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.options(selectinload(Team.members))
            .order_by(Team.created_at, Team.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total

    async def approved(self, event_id: UUID) -> list[Team]:
        return list(
            await self.session.scalars(
                select(Team)
                .options(selectinload(Team.members))
                .where(
                    Team.event_id == event_id,
                    Team.status == "approved",
                    Team.disbanded_at.is_(None),
                )
                .order_by(Team.reviewed_at, Team.id)
            )
        )

    async def counts(self, event_ids: list[UUID]) -> dict[UUID, int]:
        rows = await self.session.execute(
            select(Team.event_id, func.count())
            .where(Team.event_id.in_(event_ids), Team.disbanded_at.is_(None))
            .group_by(Team.event_id)
        )
        return dict(rows.all())

    async def track_used(self, track_id: UUID) -> bool:
        return (
            await self.session.scalar(select(Team.id).where(Team.track_id == track_id).limit(1))
            is not None
        )

    async def create(self, event_id: UUID, leader_id: UUID, values: dict[str, object]) -> Team:
        team = Team(event_id=event_id, leader_id=leader_id, members=[], **values)
        self.session.add(team)
        await self.flush()
        await self.add_member(team, leader_id, "active")
        return team

    async def add_member(self, team: Team, user_id: UUID, status: str) -> None:
        team.members.append(
            TeamMember(team_id=team.id, event_id=team.event_id, user_id=user_id, status=status)
        )
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ApiError(
                409, "ALREADY_IN_TEAM", "User already belongs to a team in this event"
            ) from None

    async def remove_member(self, team: Team, user_id: UUID) -> None:
        for member in list(team.members):
            if member.user_id == user_id:
                team.members.remove(member)
        await self.flush()

    async def flush(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ApiError(409, "RESOURCE_CONFLICT", "Conflicting team resource") from None

    async def commit(self) -> None:
        await self.session.commit()

    async def largest_team(self, event_id: UUID) -> int:
        counts = (
            select(func.count().label("size"))
            .where(TeamMember.event_id == event_id)
            .group_by(TeamMember.team_id)
            .subquery()
        )
        return await self.session.scalar(select(func.max(counts.c.size))) or 0

    async def invite_deadline(self, event_id: UUID, deadline: object) -> None:
        await self.session.execute(
            update(Team)
            .where(Team.event_id == event_id, Team.disbanded_at.is_(None))
            .values(invite_expires_at=deadline)
        )
