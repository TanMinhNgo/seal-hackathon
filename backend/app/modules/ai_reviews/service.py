from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import ApiError
from app.core.schemas import Page
from app.modules.ai_reviews.repository import ReviewRepository, can_retry
from app.modules.ai_reviews.schemas import (
    AiSummary,
    FlagOutput,
    JobCounts,
    LastJob,
    RetryOutput,
    ReviewOutput,
)
from app.modules.events.schemas import AiConfig, UserBrief


class ReviewService:
    def __init__(
        self,
        repository: ReviewRepository,
        commits: object,
        teams: object,
        events: object,
        judging: object,
        auth: object,
    ) -> None:
        self.repository = repository
        self.commits = commits
        self.teams = teams
        self.events = events
        self.judging = judging
        self.auth = auth

    async def scope(self, actor: object, team_id: UUID, round_id: UUID | None) -> tuple:
        team = await self.commits.access(actor, team_id)
        roles = {
            r.role for r in await self.auth.roles_in_event(team.event_id) if r.user_id == actor.id
        }
        manager = actor.is_admin or "organizer" in roles
        rounds = await self.events.rounds(team.event_id)
        if round_id and not any(r.id == round_id for r in rounds):
            raise ApiError(404, "ROUND_NOT_FOUND", "Round not found in team event")
        selected = [r for r in rounds if round_id is None or r.id == round_id]
        if manager:
            return [r.id for r in selected], True, True, selected
        mentor = "mentor" in roles and await self.judging.can_read_team(actor.id, team_id)
        assigned = (
            await self.judging.ai_assigned_rounds(actor.id, team_id) if "judge" in roles else set()
        )
        member = any(m.user_id == actor.id and m.status == "active" for m in team.members)
        published = (
            await self.judging.ai_published_rounds([r.id for r in selected]) if member else set()
        )
        allowed = []
        for round_ in selected:
            judge = round_.id in assigned
            config = AiConfig.model_validate(round_.ai_config)
            visible = member and (
                config.ai_visible_to_participants == "during"
                or (config.ai_visible_to_participants == "after_round" and round_.id in published)
            )
            if mentor or judge or visible:
                allowed.append(round_.id)
        if not allowed:
            raise ApiError(403, "FORBIDDEN", "AI reports are outside the user's scope")
        return allowed, False, "judge" in roles, selected

    async def page(
        self,
        actor: object,
        team_id: UUID,
        round_id: UUID | None,
        verdict: str | None,
        sha: str | None,
        limit: int,
        offset: int,
    ) -> Page:
        ids, _, _, _ = await self.scope(actor, team_id, round_id)
        rows, total = await self.repository.reviews(team_id, ids, verdict, sha, limit, offset)
        flags = await self.repository.flags_many([r.id for r in rows])
        items = []
        for row in rows:
            statuses = {f.status for f in flags if f.review_id == row.id}
            status = next(
                (s for s in ("open", "acknowledged", "dismissed") if s in statuses), "none"
            )
            data = {
                key: getattr(row, key)
                for key in ReviewOutput.model_fields
                if key not in {"flagged", "flag_status"}
            }
            items.append(ReviewOutput(**data, flagged=status != "none", flag_status=status))
        return Page[ReviewOutput](items=items, total=total)

    async def summary(self, actor: object, team_id: UUID, round_id: UUID | None) -> AiSummary:
        ids, manager, spike_visible, rounds = await self.scope(actor, team_id, round_id)
        rows, _ = await self.repository.reviews(team_id, ids)
        weight = sum(r.weight for r in rows)
        counts = Counter(r.verdict for r in rows)
        categories = Counter(i["category"] for r in rows for i in r.issues)
        spike = False
        if len(rows) >= 3:
            prior = sum(r.overall * r.weight for r in rows[1:]) / sum(r.weight for r in rows[1:])
            spike = rows[0].overall - prior >= 3
        values = {
            "avg_score": round(sum(r.overall * r.weight for r in rows) / weight, 2)
            if weight
            else None,
            "verdict_counts": {k: counts[k] for k in ("good", "pass", "needs_improvement")},
            "critical_count": sum(r.critical for r in rows),
            "timeline": [{"at": r.created_at, "score": r.overall} for r in reversed(rows)],
            "top_issues": [{"category": c, "count": n} for c, n in categories.most_common(10)],
            "score_spike": bool(spike and spike_visible),
        }
        if manager:
            jobs = await self.repository.jobs(team_id, ids)
            budgets = await self.repository.budgets(team_id, ids)
            configured = {
                r.id: AiConfig.model_validate(r.ai_config).ai_token_budget_per_team_round
                for r in rounds
                if AiConfig.model_validate(r.ai_config).ai_review_enabled
            }
            used = sum(b.tokens_used for b in budgets)
            job_counts = Counter(j.status for j in jobs)
            values.update(
                jobs=JobCounts(**{k: job_counts[k] for k in JobCounts.model_fields}),
                last_job=LastJob(
                    id=jobs[0].id,
                    round_id=jobs[0].round_id,
                    status=jobs[0].status,
                    error_code=jobs[0].error_code,
                    attempts=jobs[0].attempts,
                    can_retry=can_retry(jobs[0]),
                )
                if jobs
                else None,
                tokens_used=used,
                token_budget=sum(configured.values()),
                budget_exhausted=any(b.tokens_used >= b.token_budget for b in budgets)
                or any(j.error_code == "AI_BUDGET_EXHAUSTED" for j in jobs),
            )
        return AiSummary(**values)

    async def get_review(self, review_id: UUID) -> object:
        row = await self.repository.review(review_id)
        if row is None:
            raise ApiError(404, "AI_REVIEW_NOT_FOUND", "AI review not found")
        return row

    async def flag(self, actor: object, review_id: UUID, reason: str) -> None:
        review = await self.get_review(review_id)
        team = await self.teams.get(review.team_id)
        actor = await self.auth.lock_actor(actor)
        await self.events.get(team.event_id, lock=True)
        await self.auth.require_event_role(actor, team.event_id, ("judge",))
        if not await self.judging.ai_judge_assigned(actor.id, review.team_id, review.round_id):
            raise ApiError(403, "FORBIDDEN", "Judge is not assigned to this review's round")
        row = await self.repository.put_flag(review_id, actor.id, reason.strip())
        await self.events.log(
            actor, "ai_review.flagged", row.id, {"review_id": review_id}, "review_flag"
        )
        await self.repository.commit()

    async def flags(self, actor: object, review_id: UUID, limit: int, offset: int) -> Page:
        review = await self.get_review(review_id)
        team = await self.teams.get(review.team_id)
        await self.events.require_organizer(actor, team.event_id, admin_read=True)
        rows, total = await self.repository.flags(review_id, limit, offset)
        users = await self.auth.users([r.judge_id for r in rows])
        return Page[FlagOutput](
            items=[self.flag_output(r, users[r.judge_id]) for r in rows], total=total
        )

    @staticmethod
    def flag_output(row: object, judge: object) -> FlagOutput:
        return FlagOutput(
            **{k: getattr(row, k) for k in FlagOutput.model_fields if k != "judge"},
            judge=UserBrief.model_validate(judge),
        )

    async def resolve(self, actor: object, flag_id: UUID, decision: str, note: str) -> FlagOutput:
        row = await self.repository.flag(flag_id)
        if row is None:
            raise ApiError(404, "AI_FLAG_NOT_FOUND", "Review flag not found")
        review = await self.get_review(row.review_id)
        team = await self.teams.get(review.team_id)
        _, actor = await self.events.locked(actor, team.event_id)
        row = await self.repository.flag(flag_id, lock=True)
        row.status = decision
        row.resolution_note = note.strip()
        row.resolved_at = datetime.now(UTC)
        await self.events.log(
            actor,
            "ai_review.flag_resolved",
            row.id,
            {"decision": decision, "note": row.resolution_note},
            "review_flag",
        )
        users = await self.auth.users([row.judge_id])
        result = self.flag_output(row, users[row.judge_id])
        await self.repository.commit()
        return result

    async def retry(self, actor: object, team_id: UUID, job_id: UUID) -> RetryOutput:
        team = await self.teams.get(team_id)
        event, actor = await self.events.locked(actor, team.event_id)
        if event.status not in {"ongoing", "judging"} or event.archived_at:
            raise ApiError(409, "EVENT_NOT_ACTIVE", "AI retry requires an active event")
        job = await self.repository.retry(team_id, job_id)
        if job is None:
            raise ApiError(404, "AI_JOB_NOT_FOUND", "AI job not found for this team")
        if (
            not event.ai_review_enabled
            or not can_retry(job)
            or not await self.repository.queue_retry(job_id)
        ):
            raise ApiError(409, "AI_RETRY_NOT_ALLOWED", "AI job cannot be retried")
        await self.events.log(actor, "ai_review.retry_requested", job_id, {}, "ai_review_job")
        await self.repository.commit()
        return RetryOutput(job_id=job_id)
