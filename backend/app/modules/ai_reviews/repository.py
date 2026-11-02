from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Text, cast, func, select, update
from sqlalchemy.exc import IntegrityError

from app.modules.ai_reviews.models import AiBudget, CommitReview, ReviewFlag, ReviewJob

RETRYABLE = {
    "AI_SCHEMA_INVALID",
    "AI_PROVIDER_UNAVAILABLE",
    "AI_RATE_LIMITED",
    "AI_PROVIDER_TIMEOUT",
    "AI_WORKER_TIMEOUT",
    "GITHUB_UNAVAILABLE",
    "GITHUB_RATE_LIMITED",
    "SYNC_COORDINATION_UNAVAILABLE",
}
AUTO_RETRY = {
    "AI_SCHEMA_INVALID",
    "AI_PROVIDER_UNAVAILABLE",
    "AI_RATE_LIMITED",
    "GITHUB_UNAVAILABLE",
    "GITHUB_RATE_LIMITED",
    "SYNC_COORDINATION_UNAVAILABLE",
}
LEASE_SECONDS = 300


def can_retry(job: ReviewJob) -> bool:
    return job.status == "failed" and job.attempts < 4 and job.error_code in RETRYABLE


class ReviewRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    async def review(self, review_id: UUID) -> CommitReview | None:
        return await self.session.get(CommitReview, review_id)

    async def reviews(
        self,
        team_id: UUID,
        round_ids: list[UUID],
        verdict: str | None = None,
        sha: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple:
        query = select(CommitReview).where(
            CommitReview.team_id == team_id, CommitReview.round_id.in_(round_ids)
        )
        if verdict:
            query = query.where(CommitReview.verdict == verdict)
        if sha:
            # SHA cố định 40 hex; tìm phần tử JSON theo chuỗi có quote chạy trên cả hai DB.
            query = query.where(cast(CommitReview.commit_shas, Text).contains('"' + sha + '"'))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        query = query.order_by(CommitReview.created_at.desc(), CommitReview.id)
        if limit is not None:
            query = query.limit(limit).offset(offset)
        return list(await self.session.scalars(query)), total

    async def flags_many(self, review_ids: list[UUID]) -> list[ReviewFlag]:
        return list(
            await self.session.scalars(
                select(ReviewFlag)
                .where(ReviewFlag.review_id.in_(review_ids))
                .order_by(ReviewFlag.created_at, ReviewFlag.id)
            )
        )

    async def flags(self, review_id: UUID, limit: int, offset: int) -> tuple:
        query = select(ReviewFlag).where(ReviewFlag.review_id == review_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            await self.session.scalars(
                query.order_by(ReviewFlag.created_at, ReviewFlag.id).limit(limit).offset(offset)
            )
        )
        return rows, total

    async def flag(self, flag_id: UUID, *, lock: bool = False) -> ReviewFlag | None:
        query = (
            select(ReviewFlag)
            .where(ReviewFlag.id == flag_id)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def put_flag(self, review_id: UUID, judge_id: UUID, reason: str) -> ReviewFlag:
        row = await self.session.scalar(
            select(ReviewFlag)
            .where(ReviewFlag.review_id == review_id, ReviewFlag.judge_id == judge_id)
            .with_for_update()
        )
        if row is None:
            try:
                async with self.session.begin_nested():
                    row = ReviewFlag(review_id=review_id, judge_id=judge_id, reason=reason)
                    self.session.add(row)
                    await self.session.flush()
            except IntegrityError:
                row = await self.session.scalar(
                    select(ReviewFlag)
                    .where(ReviewFlag.review_id == review_id, ReviewFlag.judge_id == judge_id)
                    .with_for_update()
                )
        row.reason = reason
        row.status = "open"
        row.resolution_note = None
        row.resolved_at = None
        await self.session.flush()
        return row

    async def jobs(self, team_id: UUID, round_ids: list[UUID]) -> list[ReviewJob]:
        return list(
            await self.session.scalars(
                select(ReviewJob)
                .where(ReviewJob.team_id == team_id, ReviewJob.round_id.in_(round_ids))
                .order_by(ReviewJob.created_at.desc(), ReviewJob.id)
            )
        )

    async def budgets(self, team_id: UUID, round_ids: list[UUID]) -> list[AiBudget]:
        return list(
            await self.session.scalars(
                select(AiBudget).where(
                    AiBudget.team_id == team_id, AiBudget.round_id.in_(round_ids)
                )
            )
        )

    async def retry(self, team_id: UUID, job_id: UUID) -> ReviewJob | None:
        row = await self.session.scalar(
            select(ReviewJob)
            .where(ReviewJob.team_id == team_id, ReviewJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return row

    async def queue_retry(self, job_id: UUID) -> bool:
        result = await self.session.execute(
            update(ReviewJob)
            .execution_options(synchronize_session="fetch")
            .where(
                ReviewJob.id == job_id,
                ReviewJob.status == "failed",
                ReviewJob.attempts < 4,
                ReviewJob.error_code.in_(RETRYABLE),
            )
            .values(
                status="queued",
                available_at=datetime.now(UTC),
                lease_token=None,
                lease_until=None,
                error_code=None,
            )
        )
        return bool(result.rowcount)

    async def commit(self) -> None:
        await self.session.commit()


class ReviewJobRepository:
    def __init__(self, session: object) -> None:
        self.session = session

    def add(self, values: dict) -> None:
        key = {
            k: values[k] for k in ("team_id", "round_id", "base_sha", "head_sha", "prompt_version")
        }
        if self.session.scalar(select(ReviewJob.id).filter_by(**key)):
            return
        try:
            with self.session.begin_nested():
                self.session.add(ReviewJob(**values))
                self.session.flush()
        except IntegrityError:
            return
        if not self.session.get(AiBudget, (values["team_id"], values["round_id"])):
            try:
                with self.session.begin_nested():
                    self.session.add(
                        AiBudget(
                            team_id=values["team_id"],
                            round_id=values["round_id"],
                            token_budget=values["config"]["ai_token_budget_per_team_round"],
                        )
                    )
                    self.session.flush()
            except IntegrityError:
                pass

    def pending(self) -> list[UUID]:
        now = datetime.now(UTC)
        self.session.execute(
            update(ReviewJob)
            .execution_options(synchronize_session="fetch")
            .where(ReviewJob.status == "running", ReviewJob.lease_until <= now)
            .values(
                status="failed",
                error_code="AI_WORKER_TIMEOUT",
                lease_token=None,
                lease_until=None,
                reserved_tokens=0,
            )
        )
        self.session.commit()
        return list(
            self.session.scalars(
                select(ReviewJob.id)
                .where(
                    ReviewJob.status == "queued",
                    ReviewJob.available_at <= now,
                    (ReviewJob.lease_until.is_(None)) | (ReviewJob.lease_until <= now),
                )
                .order_by(ReviewJob.created_at, ReviewJob.id)
                .limit(100)
            )
        )

    def claim(self, job_id: UUID, token: str) -> bool:
        now = datetime.now(UTC)
        result = self.session.execute(
            update(ReviewJob)
            .execution_options(synchronize_session="fetch")
            .where(
                ReviewJob.id == job_id,
                ReviewJob.status == "queued",
                ReviewJob.available_at <= now,
                (ReviewJob.lease_until.is_(None)) | (ReviewJob.lease_until <= now),
            )
            .values(lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS))
        )
        self.session.commit()
        return bool(result.rowcount)

    def start(self, job_id: UUID, queued: str, token: str) -> ReviewJob | None:
        result = self.session.execute(
            update(ReviewJob)
            .execution_options(synchronize_session="fetch")
            .where(
                ReviewJob.id == job_id,
                ReviewJob.status == "queued",
                ReviewJob.attempts < 4,
                ReviewJob.lease_token == queued,
                ReviewJob.lease_until > datetime.now(UTC),
            )
            .values(
                status="running",
                lease_token=token,
                attempts=ReviewJob.attempts + 1,
                lease_until=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS),
            )
        )
        self.session.commit()
        return self.session.get(ReviewJob, job_id) if result.rowcount else None

    def owned(self, job: ReviewJob, token: str) -> object:
        return (
            update(ReviewJob)
            .execution_options(synchronize_session="fetch")
            .where(
                ReviewJob.id == job.id,
                ReviewJob.status == "running",
                ReviewJob.lease_token == token,
                ReviewJob.lease_until > datetime.now(UTC),
            )
        )

    def heartbeat(self, job: ReviewJob, token: str) -> None:
        result = self.session.execute(
            self.owned(job, token).values(
                lease_until=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
            )
        )
        self.session.commit()
        if not result.rowcount:
            raise RuntimeError("AI_LEASE_LOST")

    def reserve(self, job: ReviewJob, token: str, amount: int) -> bool:
        result = self.session.execute(
            self.owned(job, token).values(
                reserved_tokens=amount, tokens_used=ReviewJob.tokens_used + amount
            )
        )
        if not result.rowcount:
            self.session.rollback()
            raise RuntimeError("AI_LEASE_LOST")
        charged = self.session.execute(
            update(AiBudget)
            .where(
                AiBudget.team_id == job.team_id,
                AiBudget.round_id == job.round_id,
                AiBudget.tokens_used <= AiBudget.token_budget - amount,
            )
            .values(tokens_used=AiBudget.tokens_used + amount)
        )
        if not charged.rowcount:
            self.session.rollback()
            return False
        self.session.commit()
        return True

    def finish(
        self,
        job: ReviewJob,
        token: str,
        status: str,
        error: str | None = None,
        usage: int | None = None,
        review: dict | None = None,
    ) -> bool:
        reserve = job.reserved_tokens
        refund = reserve - usage if usage is not None and 0 <= usage <= reserve else 0
        retry = status == "failed" and error in AUTO_RETRY and job.attempts < 4
        result = self.session.execute(
            self.owned(job, token).values(
                status="queued" if retry else status,
                error_code=error,
                available_at=datetime.now(UTC) + timedelta(seconds=60 * 2 ** (job.attempts - 1)),
                lease_token=None,
                lease_until=None,
                reserved_tokens=0,
                tokens_used=ReviewJob.tokens_used - refund,
            )
        )
        if not result.rowcount:
            self.session.rollback()
            return False
        if refund:
            self.session.execute(
                update(AiBudget)
                .where(AiBudget.team_id == job.team_id, AiBudget.round_id == job.round_id)
                .values(tokens_used=AiBudget.tokens_used - refund)
            )
        if review is not None:
            self.session.add(
                CommitReview(
                    **(
                        {
                            "job_id": job.id,
                            "team_id": job.team_id,
                            "round_id": job.round_id,
                            "commit_shas": job.commit_shas,
                            "model": job.config["model"],
                            "prompt_version": job.prompt_version,
                            "tokens_used": job.tokens_used,
                        }
                        | review
                    )
                )
            )
        self.session.commit()
        return True
