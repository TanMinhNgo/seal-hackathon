from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select

from app.core.db import Base


class ReportRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    async def dashboard(self, event_id: UUID) -> dict:
        # Read model báo cáo: aggregate cố định, không nạp model/secret liên module.
        t, _, r, e, s, a, c, v, j, q, n, sync, roles = (
            Base.metadata.tables[key]
            for key in (
                "teams",
                "team_members",
                "rounds",
                "round_eligibilities",
                "submissions",
                "assignments",
                "commits",
                "commit_reviews",
                "ai_review_jobs",
                "mentor_questions",
                "mentor_notes",
                "commit_sync_states",
                "event_roles",
            )
        )
        team_ids = select(t.c.id).where(t.c.event_id == event_id)
        active_teams = select(t.c.id).where(t.c.event_id == event_id, t.c.disbanded_at.is_(None))
        committed_at = c.c.committed_at
        if self.session.bind.dialect.name == "postgresql":
            committed_at = func.timezone("UTC", committed_at)
        result = {
            "registrations": await self.session.scalar(
                select(func.count(func.distinct(roles.c.user_id))).where(
                    roles.c.event_id == event_id, roles.c.role == "participant"
                )
            )
        }
        for key, table, column, condition in (
            (
                "teams_by_status",
                t,
                t.c.status,
                and_(t.c.event_id == event_id, t.c.disbanded_at.is_(None)),
            ),
            ("submissions_by_round", s, s.c.round_id, s.c.team_id.in_(team_ids)),
            ("judging_progress", a, a.c.status, a.c.event_id == event_id),
            (
                "commits_per_day",
                c,
                func.date(committed_at),
                and_(c.c.team_id.in_(team_ids), c.c.removed.is_(False)),
            ),
            ("ai_verdict_counts", v, v.c.verdict, v.c.team_id.in_(team_ids)),
            ("ai_job_counts", j, j.c.status, j.c.event_id == event_id),
        ):
            result[key] = {
                str(k): count
                for k, count in (
                    await self.session.execute(
                        select(column, func.count())
                        .select_from(table)
                        .where(condition)
                        .group_by(column)
                        .order_by(column)
                    )
                ).all()
            }
        first = select(func.min(r.c.order)).where(r.c.event_id == event_id).scalar_subquery()
        eligible = or_(
            r.c.order == first,
            exists(select(e.c.id).where(e.c.round_id == r.c.id, e.c.team_id == t.c.id)),
        )
        for key, table, condition in (
            ("unassigned_teams", a, a.c.status != "cancelled"),
            ("unsubmitted_teams", s, True),
        ):
            missing = exists(
                select(r.c.id).where(
                    r.c.event_id == event_id,
                    eligible,
                    ~exists(
                        select(table.c.id).where(
                            table.c.team_id == t.c.id, table.c.round_id == r.c.id, condition
                        )
                    ),
                )
            )
            result[key] = await self.session.scalar(
                select(func.count())
                .select_from(t)
                .where(
                    t.c.event_id == event_id,
                    t.c.status == "approved",
                    t.c.disbanded_at.is_(None),
                    missing,
                )
            )
        result["unresolved_questions"] = await self.session.scalar(
            select(func.count())
            .select_from(q)
            .where(q.c.team_id.in_(active_teams), q.c.status != "resolved")
        )
        result["sync_errors"] = await self.session.scalar(
            select(func.count())
            .select_from(sync)
            .where(sync.c.team_id.in_(active_teams), sync.c.sync_status == "error")
        )
        latest = (
            select(
                n.c.progress_status,
                func.row_number()
                .over(partition_by=n.c.team_id, order_by=(n.c.created_at.desc(), n.c.id))
                .label("position"),
            )
            .where(n.c.team_id.in_(active_teams), n.c.kind == "progress")
            .subquery()
        )
        result["mentor_progress"] = dict(
            (
                await self.session.execute(
                    select(latest.c.progress_status, func.count())
                    .where(latest.c.position == 1)
                    .group_by(latest.c.progress_status)
                )
            ).all()
        )
        return result

    async def rows(
        self, event_id: UUID, kind: str, round_id: UUID | None, track_id: UUID | None
    ) -> list[dict]:
        teams, members, submissions = (
            Base.metadata.tables[k] for k in ("teams", "team_members", "submissions")
        )
        if kind == "teams":
            counts = (
                select(members.c.team_id, func.count().label("active_members"))
                .where(members.c.status == "active")
                .group_by(members.c.team_id)
                .subquery()
            )
            query = (
                select(
                    teams.c.id,
                    teams.c.name,
                    teams.c.status,
                    teams.c.track_id,
                    teams.c.repo_url,
                    func.coalesce(counts.c.active_members, 0).label("active_members"),
                )
                .outerjoin(counts, counts.c.team_id == teams.c.id)
                .where(teams.c.event_id == event_id)
            )
            if round_id:
                rounds, eligible = (
                    Base.metadata.tables[k] for k in ("rounds", "round_eligibilities")
                )
                first = (
                    select(rounds.c.id)
                    .where(rounds.c.event_id == event_id)
                    .order_by(rounds.c.order)
                    .limit(1)
                    .scalar_subquery()
                )
                query = query.where(
                    or_(
                        first == round_id,
                        teams.c.id.in_(
                            select(eligible.c.team_id).where(eligible.c.round_id == round_id)
                        ),
                    )
                )
            query = query.order_by(teams.c.id)
        else:
            query = (
                select(
                    submissions.c.id,
                    teams.c.name.label("team"),
                    submissions.c.round_id,
                    submissions.c.version,
                    submissions.c.repo_url,
                    submissions.c.commit_sha,
                    submissions.c.description,
                    submissions.c.submitted_at,
                )
                .join(teams, teams.c.id == submissions.c.team_id)
                .where(teams.c.event_id == event_id)
            )
            if round_id:
                query = query.where(submissions.c.round_id == round_id)
            query = query.order_by(submissions.c.submitted_at, submissions.c.id)
        if track_id:
            query = query.where(teams.c.track_id == track_id)
        return [dict(row) for row in (await self.session.execute(query.limit(10001))).mappings()]
