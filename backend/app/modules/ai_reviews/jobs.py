from datetime import datetime
from uuid import UUID, uuid4

from app.core.schemas import utc
from app.integrations.ai_diff import GitHubReview, prepare
from app.integrations.github_sync import GitHubSyncError
from app.integrations.llm_client import LlmClient, LlmError, request_body, reservation
from app.modules.ai_reviews.repository import ReviewJobRepository
from app.modules.commits.service import CommitService
from app.modules.events.schemas import AiConfig
from app.modules.events.service import EventService
from app.modules.teams.service import TeamService


class ReviewJobs:
    def __init__(self, repository: ReviewJobRepository, settings: object) -> None:
        self.repository = repository
        self.settings = settings

    @staticmethod
    def schedule(
        session: object, event: object, team: object, base: str, head: str, after: datetime
    ) -> None:
        if not event.ai_review_enabled or base == head:
            return
        candidates = CommitService.ai_candidates(session, team.id, after)
        repository = ReviewJobRepository(session)
        for round_ in EventService.ai_rounds(session, event.id, team.id):
            config = AiConfig.model_validate(round_.ai_config).model_dump()
            shas = [
                c["sha"]
                for c in candidates
                if utc(round_.starts_at) <= utc(c["first_seen_at"]) <= utc(round_.ends_at)
            ]
            if not config["ai_review_enabled"] or not shas:
                continue
            boundary = utc(after) < utc(round_.starts_at) or len(shas) != len(candidates)
            repository.add(
                {
                    "event_id": event.id,
                    "team_id": team.id,
                    "round_id": round_.id,
                    "base_sha": base,
                    "head_sha": head,
                    "commit_shas": shas,
                    "config": config,
                    "prompt_version": config["prompt_version"],
                    "repo_url": team.repo_url,
                    "status": "skipped" if boundary else "queued",
                    "error_code": "AI_ROUND_BOUNDARY" if boundary else None,
                }
            )

    def run(self, job_id: UUID, queued: str) -> bool:
        token = str(uuid4())
        job = self.repository.start(job_id, queued, token)
        if job is None:
            return False
        github = None
        llm = None
        usage = None
        try:
            event = EventService.ai_guard(self.repository.session, job.event_id)
            if not event:
                return self.repository.finish(job, token, "skipped", "AI_EVENT_STOPPED")
            if not event.ai_review_enabled:
                return self.repository.finish(job, token, "skipped", "AI_DISABLED")
            if not any(
                t.id == job.team_id
                for t in TeamService.sync_teams(self.repository.session, event.id)
            ):
                return self.repository.finish(job, token, "skipped", "AI_EVENT_STOPPED")
            llm = LlmClient(self.settings)
            github = GitHubReview(self.settings, job.repo_url)

            def heartbeat() -> None:
                self.repository.heartbeat(job, token)

            data = github.compare(job.base_sha, job.head_sha, heartbeat)
            if not data["complete"]:
                return self.repository.finish(job, token, "skipped", "AI_INCOMPLETE_COMPARE")
            shas = [sha for sha in job.commit_shas if sha in data["shas"]]
            payload, coverage, locations, weight = prepare(data)
            if not shas or weight == 0 or not payload["files"]:
                return self.repository.finish(job, token, "skipped", "AI_NO_CODE_CHANGES")
            body = request_body(job.config["model"], job.prompt_version, payload)
            heartbeat()
            event = EventService.ai_guard(self.repository.session, job.event_id)
            if not event:
                return self.repository.finish(job, token, "skipped", "AI_EVENT_STOPPED")
            if not self.repository.reserve(job, token, reservation(body)):
                return self.repository.finish(job, token, "skipped", "AI_BUDGET_EXHAUSTED")
            result, usage = llm.review(body)
            for issue in result.issues:
                if issue.file not in locations:
                    raise LlmError("AI_SCHEMA_INVALID", usage)
                if issue.line is None or issue.line not in locations[issue.file]:
                    issue.line = None
                    issue.message = (
                        issue.message[:1800] + " (Không xác minh được dòng từ patch đã cung cấp.)"
                    )
            scores = result.scores.model_dump()
            overall = round(sum(scores.values()) / len(scores), 2)
            verdict = (
                "good"
                if overall >= job.config["ai_good_threshold"]
                else "pass"
                if overall >= job.config["ai_pass_threshold"]
                else "needs_improvement"
            )
            if not EventService.ai_guard(self.repository.session, job.event_id):
                return self.repository.finish(job, token, "skipped", "AI_EVENT_STOPPED", usage)
            return self.repository.finish(
                job,
                token,
                "completed",
                usage=usage,
                review={
                    "commit_shas": shas,
                    "scores": scores,
                    "overall": overall,
                    "verdict": verdict,
                    "critical": any(i.severity == "high" for i in result.issues),
                    "summary": result.summary,
                    "issues": [i.model_dump() for i in result.issues],
                    "coverage": coverage,
                    "weight": weight,
                },
            )
        except (LlmError, GitHubSyncError) as exc:
            self.repository.session.rollback()
            return self.repository.finish(
                job, token, "failed", exc.code, exc.usage if isinstance(exc, LlmError) else None
            )
        except Exception:
            self.repository.session.rollback()
            # Không log exception chứa dữ liệu provider/diff; job vẫn có trạng thái kiểm tra được.
            return self.repository.finish(job, token, "failed", "AI_PROVIDER_UNAVAILABLE", usage)
        finally:
            if github:
                github.close()
            if llm:
                llm.close()
