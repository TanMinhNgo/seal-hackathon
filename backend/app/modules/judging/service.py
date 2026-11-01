from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.errors import ApiError
from app.core.schemas import Page, utc
from app.integrations import ranking_cache
from app.modules.commits.service import CommitService
from app.modules.events.schemas import UserBrief
from app.modules.judging.models import (
    Assignment,
    Conflict,
    MentorAnswer,
    MentorAssignment,
    MentorNote,
    MentorQuestion,
    PublicationSnapshot,
    ResultEmail,
    RubricCriterion,
    Score,
)
from app.modules.judging.repository import JudgingRepository
from app.modules.judging.schemas import (
    AnswerOutput,
    AssignmentBatch,
    AssignmentOutput,
    ConflictOutput,
    Criterion,
    JudgingProgress,
    Leaderboard,
    MentorAssignmentOutput,
    NoteOutput,
    Progress,
    QuestionOutput,
    RoundTeam,
    Rubric,
    ScoreOutput,
    ScoresOutput,
    TeamResult,
)
from app.modules.ranking.service import calculate

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.modules.auth.schemas import UserOutput
    from app.modules.auth.service import AuthService
    from app.modules.events.service import EventService
    from app.modules.submissions.service import SubmissionService
    from app.modules.teams.service import TeamService


class JudgingService:
    # Hook quyền của Phase 2–3 chỉ dùng repository để tránh vòng dependency giữa service.
    def __init__(
        self,
        repository: JudgingRepository,
        teams: TeamService | None = None,
        events: EventService | None = None,
        auth: AuthService | None = None,
        settings: Settings | None = None,
        submissions: SubmissionService | None = None,
        commits: CommitService | None = None,
    ) -> None:
        self.repository = repository
        self.commits = commits
        self.teams = teams
        self.events = events
        self.auth = auth
        self.settings = settings
        self.submissions = submissions

    async def can_read_submission(self, user_id: UUID, team_id: UUID, round_id: UUID) -> bool:
        return await self.repository.mentor_assigned(
            user_id, team_id
        ) or await self.repository.judge_assigned(user_id, team_id, round_id)

    async def can_read_team(self, user_id: UUID, team_id: UUID) -> bool:
        return await self.repository.mentor_assigned(
            user_id, team_id
        ) or await self.repository.judge_assigned(user_id, team_id, None)

    async def role_in_use(self, event_id: UUID, user_id: UUID, role: str) -> bool:
        return await self.repository.role_in_use(event_id, user_id, role)

    async def results_ready(self, round_ids: list[UUID]) -> bool:
        for round_id in round_ids:
            state = await self.repository.state(round_id)
            if not state or not state.locked_at or not state.published_at:
                return False
            if not await self.repository.snapshot(round_id, state.publication_revision):
                return False
            assignments = await self.repository.active_assignments(round_id)
            if not assignments:
                return False
            blocked = await self.repository.blocked_pairs(assignments[0].event_id)
            if any((a.judge_id, a.team_id) in blocked for a in assignments):
                return False
        return bool(round_ids)

    async def submissions_frozen(self, round_id: UUID) -> bool:
        return bool(await self.repository.rows(Assignment, round_id=round_id))

    async def context(
        self,
        actor: UserOutput | None,
        event_id: UUID,
        round_id: UUID | None = None,
        *,
        mutate: bool = False,
        organizer: bool = False,
        others: tuple[UUID, ...] = (),
    ) -> tuple:
        if mutate:
            actor = await self.auth.lock_actor(actor, others)
        event = await self.events.get(event_id, lock=mutate)
        if organizer:
            await self.events.require_organizer(actor, event_id)
        if mutate:
            self.events.editable(event)
        round_ = await self.events.submission_round(event_id, round_id) if round_id else None
        return event, round_, actor

    async def save(self, actor: UserOutput, action: str, target_id: UUID, data: dict) -> None:
        await self.events.log(actor, action, target_id, data, "judging")
        await self.repository.commit()

    @staticmethod
    def unlocked(state: object) -> None:
        if state and state.published_at:
            raise ApiError(409, "RESULTS_PUBLISHED", "Unpublish results before editing")
        if state and state.locked_at:
            raise ApiError(409, "SCORES_LOCKED", "Scores are locked")

    async def rubric(self, actor: UserOutput | None, event_id: UUID, round_id: UUID) -> Rubric:
        await self.events.read(event_id, actor)
        await self.events.submission_round(event_id, round_id)
        return Rubric(
            round_id=round_id,
            criteria=[Criterion.model_validate(c) for c in await self.repository.rubric(round_id)],
        )

    async def put_rubric(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, data: object
    ) -> Rubric:
        _, round_, actor = await self.context(
            actor, event_id, round_id, mutate=True, organizer=True
        )
        if datetime.now(UTC) >= utc(round_.starts_at):
            raise ApiError(409, "ROUND_ALREADY_STARTED", "Rubric is frozen at round start")
        if await self.submissions_frozen(round_id):
            raise ApiError(409, "RESOURCE_IN_USE", "Rubric is already in use")
        if sum((c.weight for c in data.criteria), Decimal(0)) != 100:
            raise ApiError(422, "RUBRIC_WEIGHT_INVALID", "Weights must sum to 100")
        if len({c.order for c in data.criteria}) != len(data.criteria):
            raise ApiError(422, "RUBRIC_ORDER_INVALID", "Criterion orders must be unique")
        for c in await self.repository.rubric(round_id):
            await self.repository.remove(c)
        for c in data.criteria:
            await self.repository.add(RubricCriterion, round_id=round_id, **c.model_dump())
        result = await self.rubric(actor, event_id, round_id)
        await self.save(actor, "rubric.updated", round_id, data.model_dump())
        return result

    async def eligible(self, round_: object) -> list:
        teams = await self.teams.approved_for_judging(round_.event_id)
        rounds = await self.events.rounds(round_.event_id)
        sources = await self.events.eligibility_sources(round_.id)
        if round_.id == rounds[0].id:
            return teams
        published = {s for s in set(sources.values()) if s and await self.results_ready([s])}
        return [t for t in teams if sources.get(t.id) in published]

    async def eligible_page(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, limit: int, offset: int
    ) -> Page[RoundTeam]:
        await self.events.require_organizer(actor, event_id, admin_read=True)
        round_ = await self.events.submission_round(event_id, round_id)
        sources = await self.events.eligibility_sources(round_id)
        rounds = await self.events.rounds(event_id)
        rows = [
            RoundTeam(team_id=t.id, name=t.name, source_round_id=sources.get(t.id))
            for t in await self.teams.approved_for_judging(event_id)
            if round_.id == rounds[0].id or t.id in sources
        ]
        return Page(items=rows[offset : offset + limit], total=len(rows))

    async def put_eligible(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, data: object
    ) -> Page[RoundTeam]:
        _, round_, actor = await self.context(
            actor, event_id, round_id, mutate=True, organizer=True
        )
        source = await self.events.submission_round(event_id, data.source_round_id)
        if datetime.now(UTC) >= utc(round_.starts_at):
            raise ApiError(409, "ROUND_ALREADY_STARTED", "Eligibility is frozen at round start")
        if source.order >= round_.order:
            raise ApiError(409, "ROUND_NOT_ELIGIBLE", "Source must be an earlier round")
        state = await self.repository.state(source.id)
        if not state or not state.published_at:
            raise ApiError(409, "NOT_PUBLISHED", "Source results must be published")
        snapshot = await self.repository.snapshot(source.id, state.publication_revision)
        selected = list(dict.fromkeys(data.team_ids))
        for team_id in selected:
            team = await self.teams.get(team_id)
            if (
                team.event_id != event_id
                or team.status != "approved"
                or str(team_id) not in snapshot.data["results"]
            ):
                raise ApiError(409, "ROUND_NOT_ELIGIBLE", "Team has no published result in source")
        previous = await self.events.eligibility_sources(round_id)
        await self.events.replace_eligibility(round_id, source.id, selected)
        await self.save(actor, "round.eligibility_updated", round_id, data.model_dump())
        teams = await self.teams.judging_teams(list(set(previous) | set(selected)))
        users = await self.auth.users([t.leader_id for t in teams.values()])
        for user in users.values():
            # shortcut: email sau commit dùng queue sẵn có; Phase 7 bổ sung outbox thông báo.
            await self.auth.queue_email(
                str(user.email),
                "SEAL - Round eligibility",
                f"Eligibility updated for {round_.name}",
            )
        return await self.eligible_page(actor, event_id, round_id, 100, 0)

    async def conflicts(
        self, actor: UserOutput, event_id: UUID, limit: int, offset: int
    ) -> Page[ConflictOutput]:
        await self.events.get(event_id)
        await self.auth.require_event_role(actor, event_id, ("organizer", "judge"))
        roles = await self.auth.roles_in_event(event_id)
        filters = {"event_id": event_id}
        if not any(r.user_id == actor.id and r.role == "organizer" for r in roles):
            filters["judge_id"] = actor.id
        rows, total = await self.repository.page(Conflict, limit, offset, **filters)
        users = await self.auth.users([c.judge_id for c in rows])
        return Page(
            items=[
                ConflictOutput(
                    id=c.id,
                    judge=UserBrief.model_validate(users[c.judge_id]),
                    team_id=c.team_id,
                    reason=c.reason,
                    created_at=c.created_at,
                )
                for c in rows
            ],
            total=total,
        )

    async def declare_conflict(
        self, actor: UserOutput, event_id: UUID, data: object
    ) -> ConflictOutput:
        _, _, actor = await self.context(actor, event_id, mutate=True)
        await self.auth.require_event_role(actor, event_id, ("judge",))
        team = await self.teams.get(data.team_id)
        if team.event_id != event_id:
            raise ApiError(404, "TEAM_NOT_FOUND", "Team not found in event")
        rows = await self.repository.rows(Conflict, judge_id=actor.id, team_id=team.id)
        row = (
            rows[0]
            if rows
            else await self.repository.add(
                Conflict, event_id=event_id, judge_id=actor.id, team_id=team.id, reason=data.reason
            )
        )
        await self.save(actor, "conflict.declared", row.id, data.model_dump())
        return ConflictOutput(
            id=row.id,
            judge=UserBrief.model_validate(actor),
            team_id=team.id,
            reason=row.reason,
            created_at=row.created_at,
        )

    async def pair_conflict(self, judge_id: UUID, team_id: UUID) -> bool:
        return bool(
            await self.repository.rows(Conflict, judge_id=judge_id, team_id=team_id)
            or await self.repository.mentor_assigned(judge_id, team_id, history=True)
        )

    async def valid_role(self, event_id: UUID, user_id: UUID, role: str) -> bool:
        users = await self.auth.users([user_id])
        user = users.get(user_id)
        return bool(
            user
            and user.is_active
            and user.email_verified
            and not user.is_admin
            and any(
                r.user_id == user_id and r.role == role
                for r in await self.auth.roles_in_event(event_id)
            )
        )

    async def valid_judges(self, event_id: UUID) -> set[UUID]:
        ids = {r.user_id for r in await self.auth.roles_in_event(event_id) if r.role == "judge"}
        users = await self.auth.users(list(ids))
        return {u.id for u in users.values() if u.is_active and u.email_verified and not u.is_admin}

    async def render_assignments(self, rows: list) -> list[AssignmentOutput]:
        users = await self.auth.users([a.judge_id for a in rows])
        teams = await self.teams.judging_teams([a.team_id for a in rows])
        return [
            AssignmentOutput(
                id=a.id,
                round_id=a.round_id,
                judge=UserBrief.model_validate(users[a.judge_id]),
                team=teams[a.team_id],
                submission_id=a.submission_id,
                status=a.status,
                revision=a.revision,
                submitted_at=a.submitted_at,
            )
            for a in rows
        ]

    async def assignments(
        self,
        actor: UserOutput,
        event_id: UUID | None,
        round_id: UUID | None,
        limit: int,
        offset: int,
        *,
        mine: bool = False,
    ) -> Page[AssignmentOutput]:
        if mine:
            if actor.is_admin:
                raise ApiError(403, "FORBIDDEN", "Administrators cannot judge")
            roles = await self.auth.role_records(actor.id)
            events = {r.event_id for r in roles if r.role == "judge"}
            if not events or (event_id and event_id not in events):
                raise ApiError(403, "FORBIDDEN", "Judge role required")
            rows = [
                a
                for a in await self.repository.rows(Assignment, judge_id=actor.id)
                if a.event_id in events
                and (not event_id or a.event_id == event_id)
                and (not round_id or a.round_id == round_id)
            ]
            rows.sort(key=lambda a: str(a.id))
            return Page(
                items=await self.render_assignments(rows[offset : offset + limit]), total=len(rows)
            )
        await self.context(actor, event_id, round_id, organizer=True)
        rows, total = await self.repository.page(
            Assignment, limit, offset, event_id=event_id, round_id=round_id
        )
        return Page(items=await self.render_assignments(rows), total=total)

    async def assign(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, data: object, *, auto: bool = False
    ) -> AssignmentBatch:
        others = () if auto else (data.judge_id,)
        _, round_, actor = await self.context(
            actor, event_id, round_id, mutate=True, organizer=True, others=others
        )
        state = await self.repository.state(round_id, create=True)
        self.unlocked(state)
        if datetime.now(UTC) < utc(round_.submission_deadline):
            raise ApiError(409, "DEADLINE_NOT_PASSED", "Wait until submission deadline")
        if not await self.repository.rubric(round_id):
            raise ApiError(409, "RUBRIC_REQUIRED", "Configure a rubric first")
        teams = await self.eligible(round_)
        latest = await self.submissions.final_for_judging([t.id for t in teams], round_)
        existing = await self.repository.active_assignments(round_id)
        if auto:
            if data.judges_per_team != round_.required_judges:
                raise ApiError(422, "JUDGE_COUNT_MISMATCH", "Use configured required_judges")
            candidates = sorted(await self.valid_judges(event_id), key=str)
        else:
            candidates = [data.judge_id]
        valid = await self.valid_judges(event_id)
        candidates = [j for j in candidates if j in valid]
        blocked = await self.repository.blocked_pairs(event_id)
        if not auto and not candidates:
            raise ApiError(409, "ROLE_CONFLICT", "Judge is not eligible")
        ids = [t.id for t in teams] if auto else list(dict.fromkeys(data.team_ids))
        created, skipped = [], []
        for team_id in ids:
            if team_id not in {t.id for t in teams}:
                skipped.append({"team_id": team_id, "code": "ROUND_NOT_ELIGIBLE"})
                continue
            if team_id not in latest:
                skipped.append({"team_id": team_id, "code": "NOT_SUBMITTED"})
                continue
            ordered = sorted(
                candidates, key=lambda j: (sum(a.judge_id == j for a in existing), str(j))
            )
            for judge_id in ordered:
                if sum(a.team_id == team_id for a in existing) >= round_.required_judges:
                    if not auto:
                        skipped.append({"team_id": team_id, "code": "JUDGES_FULL"})
                    break
                if any(a.team_id == team_id and a.judge_id == judge_id for a in existing):
                    if not auto:
                        skipped.append({"team_id": team_id, "code": "ALREADY_ASSIGNED"})
                    continue
                if (judge_id, team_id) in blocked:
                    skipped.append({"team_id": team_id, "code": "CONFLICT_OF_INTEREST"})
                    continue
                row = await self.repository.add(
                    Assignment,
                    event_id=event_id,
                    round_id=round_id,
                    judge_id=judge_id,
                    team_id=team_id,
                    submission_id=latest[team_id].id,
                )
                existing.append(row)
                created.append(row)
        missing = [
            {
                "team_id": t.id,
                "missing_judges": round_.required_judges - sum(a.team_id == t.id for a in existing),
            }
            for t in teams
            if t.id in latest and sum(a.team_id == t.id for a in existing) < round_.required_judges
        ]
        state.cache_revision += 1
        result = AssignmentBatch(
            items=await self.render_assignments(created), skipped=skipped, unfilled=missing
        )
        await self.save(actor, "assignments.created", round_id, result.model_dump())
        return result

    async def assignment_context(
        self,
        actor: UserOutput,
        assignment_id: UUID,
        *,
        mutate: bool = False,
        organizer: bool = False,
    ) -> tuple:
        row = await self.repository.get(Assignment, assignment_id)
        if row is None:
            raise ApiError(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found")
        event_id, round_id = row.event_id, row.round_id
        _, round_, actor = await self.context(
            actor, event_id, round_id, mutate=mutate, organizer=organizer
        )
        row = await self.repository.get(Assignment, assignment_id)
        if row is None:
            raise ApiError(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found")
        state = await self.repository.state(round_id, create=mutate)
        if not organizer:
            if actor.is_admin:
                if mutate or not state or not state.locked_at:
                    raise ApiError(403, "FORBIDDEN", "Administrators read scores only after lock")
            elif actor.id == row.judge_id:
                await self.auth.require_event_role(actor, event_id, ("judge",))
            else:
                if mutate:
                    raise ApiError(403, "FORBIDDEN", "Assignment belongs to another judge")
                await self.events.require_organizer(actor, event_id)
        return row, round_, state, actor

    async def score_output(self, row: object) -> ScoresOutput:
        return ScoresOutput(
            assignment=(await self.render_assignments([row]))[0],
            scores=[ScoreOutput.model_validate(s) for s in await self.repository.scores([row.id])],
            general_comment=row.general_comment,
        )

    async def detail(self, actor: UserOutput, assignment_id: UUID) -> dict:
        row, _, _, actor = await self.assignment_context(actor, assignment_id)
        result = (await self.score_output(row)).model_dump()
        result.update(
            submission=await self.submissions.get(actor, row.submission_id),
            rubric=await self.rubric(actor, row.event_id, row.round_id),
        )
        return result

    async def write_scores(
        self, actor: UserOutput, assignment_id: UUID, data: object, *, submit: bool = False
    ) -> object:
        row, _, state, actor = await self.assignment_context(actor, assignment_id, mutate=True)
        self.unlocked(state)
        if row.status == "submitted":
            raise ApiError(409, "ASSIGNMENT_SUBMITTED", "Assignment is already submitted")
        if row.status == "cancelled":
            raise ApiError(409, "ASSIGNMENT_CANCELLED", "Assignment is cancelled")
        if await self.pair_conflict(actor.id, row.team_id):
            raise ApiError(409, "CONFLICT_OF_INTEREST", "Resolve conflicts before scoring")
        if row.revision != data.expected_revision:
            raise ApiError(
                409, "SCORE_VERSION_CONFLICT", "Score draft changed; reload before saving"
            )
        criteria = {c.id: c for c in await self.repository.rubric(row.round_id)}
        values = await self.repository.scores([row.id]) if submit else data.scores
        if len({s.criterion_id for s in values}) != len(values) or any(
            s.criterion_id not in criteria for s in values
        ):
            raise ApiError(422, "SCORING_INCOMPLETE", "Duplicate or unknown criteria")
        if any(
            not s.score.is_finite() or not 0 <= s.score <= criteria[s.criterion_id].max_score
            for s in values
        ):
            raise ApiError(422, "SCORE_OUT_OF_RANGE", "Score must fit the criterion")
        if submit:
            if not criteria or {s.criterion_id for s in values} != set(criteria):
                raise ApiError(
                    409, "SCORING_INCOMPLETE", "Complete every criterion before submitting"
                )
            row.status = "submitted"
            row.submitted_at = datetime.now(UTC)
        else:
            for s in await self.repository.scores([row.id]):
                await self.repository.remove(s)
            for s in values:
                await self.repository.add(Score, assignment_id=row.id, **s.model_dump())
            row.general_comment = data.general_comment
            row.status = "draft"
        row.revision += 1
        state.cache_revision += 1
        result = (
            (await self.render_assignments([row]))[0] if submit else await self.score_output(row)
        )
        await self.save(
            actor,
            "scores.submitted" if submit else "scores.saved",
            row.id,
            {"revision": row.revision, "input": data.model_dump()},
        )
        return result

    async def change_assignment(
        self, actor: UserOutput, assignment_id: UUID, action: str, reason: str | None = None
    ) -> object:
        row, _, state, actor = await self.assignment_context(
            actor, assignment_id, mutate=True, organizer=True
        )
        self.unlocked(state)
        if action == "delete":
            if row.status != "pending" or await self.repository.scores([row.id]):
                raise ApiError(
                    409, "RESOURCE_IN_USE", "Only unscored pending assignments may be deleted"
                )
            await self.repository.remove(row)
            result = None
        else:
            if action == "reopen" and row.status != "submitted":
                raise ApiError(
                    409, "INVALID_STATUS_TRANSITION", "Only submitted assignments can be reopened"
                )
            row.status = "draft" if action == "reopen" else "cancelled"
            row.revision += 1
            if action == "reopen":
                row.submitted_at = None
            result = (await self.render_assignments([row]))[0]
        state.cache_revision += 1
        await self.save(actor, f"assignment.{action}", assignment_id, {"reason": reason})
        return result

    async def progress_rows(self, round_: object) -> list[Progress]:
        teams = await self.eligible(round_)
        latest = await self.submissions.final_for_judging([t.id for t in teams], round_)
        assignments = await self.repository.active_assignments(round_.id)
        blocked = await self.repository.blocked_pairs(round_.event_id)
        valid = await self.valid_judges(round_.event_id)
        result = []
        for team in teams:
            rows = [a for a in assignments if a.team_id == team.id]
            conflict = any(
                (a.judge_id, team.id) in blocked or a.judge_id not in valid for a in rows
            )
            submitted = sum(a.status == "submitted" for a in rows)
            complete = (
                submitted >= round_.required_judges and submitted == len(rows) and not conflict
            )
            result.append(
                Progress(
                    team=team,
                    required=round_.required_judges,
                    assigned=len(rows),
                    submitted=submitted,
                    missing=max(0, round_.required_judges - submitted),
                    has_conflict=conflict,
                    status="not_submitted"
                    if team.id not in latest
                    else "complete"
                    if complete
                    else "pending",
                )
            )
        return result

    async def progress(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, limit: int, offset: int
    ) -> JudgingProgress:
        _, round_, _ = await self.context(actor, event_id, round_id, organizer=True)
        rows = await self.progress_rows(round_)
        state = await self.repository.state(round_id)
        return JudgingProgress(
            items=rows[offset : offset + limit],
            total=len(rows),
            locked_at=state.locked_at if state else None,
            published_at=state.published_at if state else None,
        )

    async def ranking_data(self, round_: object, state: object) -> dict:
        if state and state.published_at:
            snapshot = await self.repository.snapshot(round_.id, state.publication_revision)
            return snapshot.data
        revision = state.cache_revision if state else 0
        cached = await ranking_cache.read(str(self.settings.redis_url), round_.id, revision)
        if cached is not None:
            return cached
        teams = await self.eligible(round_)
        assignments = await self.repository.active_assignments(round_.id)
        submissions = await self.submissions.judging_snapshots(assignments)
        data = calculate(
            teams,
            submissions,
            assignments,
            await self.repository.scores([a.id for a in assignments]),
            await self.repository.rubric(round_.id),
        )
        await ranking_cache.write(str(self.settings.redis_url), round_.id, revision, data)
        return data

    async def leaderboard(
        self,
        actor: UserOutput | None,
        event_id: UUID,
        round_id: UUID,
        track_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Leaderboard:
        await self.events.read(event_id, actor)
        round_ = await self.events.submission_round(event_id, round_id)
        await self.events.ensure_track(event_id, track_id)
        state = await self.repository.state(round_id)
        if not state or not state.published_at:
            if not actor:
                raise ApiError(409, "NOT_PUBLISHED", "Results are not published")
            if actor.is_admin:
                if not state or not state.locked_at:
                    raise ApiError(403, "FORBIDDEN", "Scores are private until locked")
            else:
                await self.events.require_organizer(actor, event_id)
        data = await self.ranking_data(round_, state)
        rows = data["boards"].get(str(track_id) if track_id else "all", [])
        return Leaderboard(
            items=rows[offset : offset + limit],
            total=len(rows),
            publication_revision=state.publication_revision if state else 0,
        )

    async def result(self, actor: UserOutput, team_id: UUID, round_id: UUID) -> TeamResult:
        team = await self.teams.get(team_id)
        round_ = await self.events.submission_round(team.event_id, round_id)
        state = await self.repository.state(round_id)
        roles = await self.auth.roles_in_event(team.event_id)
        organizer = not actor.is_admin and any(
            r.user_id == actor.id and r.role == "organizer" for r in roles
        )
        if actor.is_admin or organizer:
            if not state or not state.locked_at:
                raise ApiError(403, "FORBIDDEN", "Scores are private until locked")
        else:
            self.active_member(actor, team)
            if not state or not state.published_at:
                raise ApiError(409, "NOT_PUBLISHED", "Results are not published")
        data = await self.ranking_data(round_, state)
        row = data["results"].get(str(team_id))
        if row is None:
            raise ApiError(404, "RESULT_NOT_FOUND", "Team has no scored submission")
        return TeamResult(**row, publication_revision=state.publication_revision)

    async def change_round(
        self,
        actor: UserOutput,
        event_id: UUID,
        round_id: UUID,
        action: str,
        reason: str | None = None,
    ) -> None:
        _, round_, actor = await self.context(
            actor, event_id, round_id, mutate=True, organizer=True
        )
        state = await self.repository.state(round_id, create=True)
        if action in {"lock", "publish"}:
            progress = await self.progress_rows(round_)
            valid = [p for p in progress if p.status != "not_submitted"]
            if not valid or any(p.status != "complete" for p in valid):
                raise ApiError(
                    409,
                    "SCORING_INCOMPLETE",
                    "Every submitted team needs complete conflict-free judging",
                )
        if action == "lock":
            if state.locked_at:
                return
            state.locked_at = datetime.now(UTC)
        elif action == "unlock":
            if state.published_at:
                raise ApiError(409, "RESULTS_PUBLISHED", "Unpublish before unlocking")
            state.locked_at = None
        elif action == "publish":
            if not state.locked_at:
                raise ApiError(409, "SCORES_NOT_LOCKED", "Lock scores before publishing")
            if state.published_at:
                return
            data = await self.ranking_data(round_, state)
            state.publication_revision += 1
            snapshot = await self.repository.add(
                PublicationSnapshot,
                round_id=round_id,
                revision=state.publication_revision,
                data=data,
            )
            teams = [t for t in await self.eligible(round_) if str(t.id) in data["results"]]
            users = await self.auth.users(
                [m.user_id for t in teams for m in t.members if m.status == "active"]
            )
            for team in teams:
                result = data["results"][str(team.id)]
                for member in team.members:
                    user = users.get(member.user_id) if member.status == "active" else None
                    if user and user.is_active and not user.is_admin:
                        await self.repository.add(
                            ResultEmail,
                            snapshot_id=snapshot.id,
                            user_id=user.id,
                            recipient=str(user.email),
                            body=(
                                f"{round_.name}: {team.name}, rank {result['rank']}, "
                                f"score {result['total']}. Revision {state.publication_revision}"
                            ),
                        )
            state.published_at = datetime.now(UTC)
        elif action == "unpublish":
            if await self.events.has_started_dependents(round_id):
                raise ApiError(409, "RESOURCE_IN_USE", "A dependent round has started")
            state.published_at = None
        state.cache_revision += 1
        await self.save(
            actor,
            f"round.{action}",
            round_id,
            {"reason": reason, "publication_revision": state.publication_revision},
        )

    @staticmethod
    def active_member(actor: UserOutput, team: object) -> None:
        if actor.is_admin or not any(
            m.user_id == actor.id and m.status == "active" for m in team.members
        ):
            raise ApiError(403, "FORBIDDEN", "Active team membership required")

    async def mentor_access(self, actor: UserOutput, team: object, *, write: bool = False) -> None:
        roles = await self.auth.roles_in_event(team.event_id)
        own = {r.role for r in roles if r.user_id == actor.id}
        if not write and (actor.is_admin or "organizer" in own):
            return
        if (
            not actor.is_admin
            and "mentor" in own
            and await self.repository.mentor_assigned(actor.id, team.id)
        ):
            return
        if not write:
            self.active_member(actor, team)
            return
        raise ApiError(403, "FORBIDDEN", "Current mentor assignment required")

    async def render_mentor_assignments(self, rows: list) -> list[MentorAssignmentOutput]:
        users = await self.auth.users([a.mentor_id for a in rows])
        teams = await self.teams.judging_teams([a.team_id for a in rows])
        return [
            MentorAssignmentOutput(
                id=a.id,
                event_id=a.event_id,
                mentor=UserBrief.model_validate(users[a.mentor_id]),
                team=teams[a.team_id],
                created_at=a.created_at,
            )
            for a in rows
        ]

    async def mentor_assignments(
        self, actor: UserOutput, event_id: UUID, limit: int, offset: int
    ) -> Page[MentorAssignmentOutput]:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        rows, total = await self.repository.page(
            MentorAssignment, limit, offset, event_id=event_id, revoked_at=None
        )
        return Page(items=await self.render_mentor_assignments(rows), total=total)

    async def assign_mentor(self, actor: UserOutput, event_id: UUID, data: object) -> dict:
        _, _, actor = await self.context(
            actor, event_id, mutate=True, organizer=True, others=(data.mentor_id,)
        )
        if not await self.valid_role(event_id, data.mentor_id, "mentor"):
            raise ApiError(409, "ROLE_CONFLICT", "Mentor is not eligible")
        created = []
        for team_id in dict.fromkeys(data.team_ids):
            team = await self.teams.get(team_id)
            if team.event_id != event_id:
                raise ApiError(404, "TEAM_NOT_FOUND", "Team not found in event")
            if await self.repository.judge_assigned(data.mentor_id, team_id, None):
                raise ApiError(409, "CONFLICT_OF_INTEREST", "Mentor cannot judge the same team")
            if not await self.repository.mentor_assigned(data.mentor_id, team_id):
                created.append(
                    await self.repository.add(
                        MentorAssignment,
                        event_id=event_id,
                        mentor_id=data.mentor_id,
                        team_id=team_id,
                    )
                )
        result = {"items": await self.render_mentor_assignments(created)}
        await self.save(actor, "mentors.assigned", event_id, data.model_dump())
        return result

    async def revoke_mentor(self, actor: UserOutput, assignment_id: UUID) -> None:
        row = await self.repository.get(MentorAssignment, assignment_id)
        if not row:
            raise ApiError(404, "ASSIGNMENT_NOT_FOUND", "Mentor assignment not found")
        _, _, actor = await self.context(actor, row.event_id, mutate=True, organizer=True)
        row = await self.repository.get(MentorAssignment, assignment_id)
        row.revoked_at = datetime.now(UTC)
        await self.save(actor, "mentor.revoked", row.id, {})

    async def mentoring(
        self, actor: UserOutput, event_id: UUID | None, limit: int, offset: int
    ) -> Page:
        if actor.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrators cannot mentor")
        roles = await self.auth.role_records(actor.id)
        events = {r.event_id for r in roles if r.role == "mentor"}
        if not events or (event_id and event_id not in events):
            raise ApiError(403, "FORBIDDEN", "Mentor role required")
        rows = await self.repository.rows(MentorAssignment, mentor_id=actor.id, revoked_at=None)
        ids = list(
            dict.fromkeys(
                a.team_id
                for a in rows
                if a.event_id in events and (not event_id or a.event_id == event_id)
            )
        )
        teams = await self.teams.judging_teams(ids[offset : offset + limit])
        return Page(items=await self.teams.render(list(teams.values()), actor), total=len(ids))

    async def validate_commit(self, team_id: UUID, commit_sha: str | None) -> None:
        if commit_sha is not None and (
            not self.commits or not await self.commits.exists(team_id, commit_sha)
        ):
            raise ApiError(
                422,
                "COMMIT_NOT_FOUND",
                "Commit must be stored for this team",
            )

    async def discussion_context(
        self, actor: UserOutput, team_id: UUID, *, mutate: bool = False
    ) -> tuple:
        team = await self.teams.get(team_id)
        event, _, actor = await self.context(actor, team.event_id, mutate=mutate)
        if mutate and event.status not in {"open", "ongoing"}:
            raise ApiError(409, "EVENT_NOT_OPEN", "Mentoring is open only during open/ongoing")
        return team, event, actor

    async def notes(
        self, actor: UserOutput, team_id: UUID, commit_sha: str | None, limit: int, offset: int
    ) -> Page[NoteOutput]:
        team, _, actor = await self.discussion_context(actor, team_id)
        await self.mentor_access(actor, team)
        filters = {"team_id": team_id}
        if commit_sha:
            filters["commit_sha"] = commit_sha
        rows, total = await self.repository.page(MentorNote, limit, offset, **filters)
        users = await self.auth.users([n.mentor_id for n in rows])
        return Page(
            items=[
                NoteOutput(
                    **{k: getattr(n, k) for k in NoteOutput.model_fields if k != "mentor"},
                    mentor=UserBrief.model_validate(users[n.mentor_id]),
                )
                for n in rows
            ],
            total=total,
        )

    async def add_note(self, actor: UserOutput, team_id: UUID, data: object) -> NoteOutput:
        team = await self.teams.get(team_id)
        _, _, actor = await self.context(actor, team.event_id, mutate=True)
        await self.mentor_access(actor, team, write=True)
        await self.validate_commit(team_id, data.commit_sha)
        row = await self.repository.add(
            MentorNote, team_id=team_id, mentor_id=actor.id, **data.model_dump()
        )
        result = NoteOutput(
            **{k: getattr(row, k) for k in NoteOutput.model_fields if k != "mentor"},
            mentor=UserBrief.model_validate(actor),
        )
        await self.save(actor, "mentor.note_created", row.id, {"team_id": team_id})
        return result

    async def questions(
        self, actor: UserOutput, team_id: UUID, status: str | None, limit: int, offset: int
    ) -> Page[QuestionOutput]:
        team, _, actor = await self.discussion_context(actor, team_id)
        await self.mentor_access(actor, team)
        filters = {"team_id": team_id}
        if status:
            filters["status"] = status
        rows, total = await self.repository.page(MentorQuestion, limit, offset, **filters)
        users = await self.auth.users([q.author_id for q in rows])
        return Page(
            items=[
                QuestionOutput(
                    **{k: getattr(q, k) for k in QuestionOutput.model_fields if k != "author"},
                    author=UserBrief.model_validate(users[q.author_id]),
                )
                for q in rows
            ],
            total=total,
        )

    async def ask(self, actor: UserOutput, team_id: UUID, data: object) -> QuestionOutput:
        team, _, actor = await self.discussion_context(actor, team_id, mutate=True)
        self.active_member(actor, team)
        await self.teams.limit(actor, "mentor-discussion", 60, 30)
        await self.validate_commit(team_id, data.commit_sha)
        row = await self.repository.add(
            MentorQuestion, team_id=team_id, author_id=actor.id, **data.model_dump()
        )
        result = QuestionOutput(
            **{k: getattr(row, k) for k in QuestionOutput.model_fields if k != "author"},
            author=UserBrief.model_validate(actor),
        )
        await self.save(actor, "mentor.question_created", row.id, {"team_id": team_id})
        return result

    async def question_context(
        self, actor: UserOutput, question_id: UUID, *, mutate: bool = False
    ) -> tuple:
        row = await self.repository.get(MentorQuestion, question_id)
        if not row:
            raise ApiError(404, "QUESTION_NOT_FOUND", "Question not found")
        team, _, actor = await self.discussion_context(actor, row.team_id, mutate=mutate)
        row = await self.repository.get(MentorQuestion, question_id)
        return row, team, actor

    async def answers(
        self, actor: UserOutput, question_id: UUID, limit: int, offset: int
    ) -> Page[AnswerOutput]:
        row, team, actor = await self.question_context(actor, question_id)
        await self.mentor_access(actor, team)
        rows, total = await self.repository.page(MentorAnswer, limit, offset, question_id=row.id)
        users = await self.auth.users([a.mentor_id for a in rows])
        return Page(
            items=[
                AnswerOutput(
                    id=a.id,
                    question_id=a.question_id,
                    content=a.content,
                    created_at=a.created_at,
                    mentor=UserBrief.model_validate(users[a.mentor_id]),
                )
                for a in rows
            ],
            total=total,
        )

    async def answer(self, actor: UserOutput, question_id: UUID, data: object) -> AnswerOutput:
        row, team, actor = await self.question_context(actor, question_id, mutate=True)
        await self.mentor_access(actor, team, write=True)
        if row.status == "resolved":
            raise ApiError(409, "QUESTION_RESOLVED", "Question is resolved")
        await self.teams.limit(actor, "mentor-discussion", 60, 30)
        answer = await self.repository.add(
            MentorAnswer, question_id=row.id, mentor_id=actor.id, content=data.content
        )
        row.status = "answered"
        result = AnswerOutput(
            id=answer.id,
            question_id=row.id,
            content=answer.content,
            created_at=answer.created_at,
            mentor=UserBrief.model_validate(actor),
        )
        await self.save(actor, "mentor.answer_created", answer.id, {"question_id": row.id})
        return result

    async def resolve(self, actor: UserOutput, question_id: UUID) -> None:
        row, team, actor = await self.question_context(actor, question_id, mutate=True)
        self.active_member(actor, team)
        if actor.id not in {row.author_id, team.leader_id}:
            raise ApiError(403, "FORBIDDEN", "Only author or active leader may resolve")
        if row.status == "resolved":
            return
        row.status = "resolved"
        row.resolved_at = datetime.now(UTC)
        await self.save(actor, "mentor.question_resolved", row.id, {})
