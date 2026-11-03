import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.schemas import utc
from app.integrations.github_sync import GitHubSync, GitHubSyncError
from app.modules.commits.repository import CommitJobRepository
from app.modules.events.service import EventService
from app.modules.teams.service import TeamService

logger = logging.getLogger(__name__)


class CommitJobs:
    def __init__(self, repository: CommitJobRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def contexts(self) -> list[tuple]:
        session = self.repository.session
        return [
            (event, team)
            for event in EventService.sync_events(session)
            for team in TeamService.sync_teams(session, event.id)
        ]

    def run(
        self, team_id: UUID, queued: str, retry_token: str | None = None, retry_delay: int = 60
    ) -> bool:
        token = str(uuid4())
        if not self.repository.start(team_id, queued, token):
            return False
        context = next(((e, t) for e, t in self.contexts() if t.id == team_id), None)
        if context is None:
            self.repository.release(team_id, token)
            return False
        event, team = context
        client = None
        try:
            state = self.repository.state(team_id)
            previous_head = state.head_sha
            previous_sync = state.last_synced_at
            client = GitHubSync(self.settings, team.repo_url)

            def heartbeat() -> None:
                self.repository.heartbeat(team_id, token)

            branch, head = client.branch_head(state.branch)
            state.branch = branch
            self.repository.commit()
            stored = self.repository.stored(team_id)
            baseline = state.baseline_at is None
            if (
                head == previous_head
                and state.sync_status == "ok"
                and not state.truncated
                and not baseline
            ):
                shas, complete = [sha for sha, row in stored.items() if not row.removed], True
            else:
                shas, complete = client.history(head, heartbeat)
            missing = [sha for sha in shas if sha not in stored]
            details = (
                client.baseline(missing, heartbeat)
                if baseline
                else (client.detail(sha, heartbeat) for sha in missing)
            )
            for detail in details:
                heartbeat()
                if not EventService.sync_guard(self.repository.session, event.id):
                    self.repository.release(team_id, token)
                    return False
                self.repository.fence(team_id, token)
                now = datetime.now(UTC)
                self.repository.save_commit(
                    team_id,
                    detail
                    | {
                        "branch": branch,
                        "first_seen_at": now,
                        "removed": False,
                        "baseline": baseline,
                        "in_event_window": not baseline
                        and utc(event.starts_at) <= now <= utc(event.ends_at),
                    },
                )
                self.repository.commit()
            heartbeat()
            if not EventService.sync_guard(self.repository.session, event.id):
                self.repository.release(team_id, token)
                return False
            self.repository.fence(team_id, token)
            state = self.repository.state(team_id)
            if complete:
                reachable = set(shas)
                for sha, row in stored.items():
                    row.removed = sha not in reachable
                state.head_sha = head
                state.baseline_at = state.baseline_at or datetime.now(UTC)
                state.last_synced_at = datetime.now(UTC)
                state.sync_status = "ok"
                state.sync_error = None
                state.notified = False
                if previous_head and previous_sync and event.ai_review_enabled:
                    from app.modules.ai_reviews.jobs import ReviewJobs

                    ReviewJobs.schedule(
                        self.repository.session, event, team, previous_head, head, previous_sync
                    )
            else:
                state.sync_status = "error"
                state.sync_error = "GITHUB_INCOMPLETE_HISTORY"
            state.truncated = not complete
            self.repository.realtime(event.id, team_id, state)
            self.repository.commit()
            self.repository.release(team_id, token)
            return complete
        except Exception as exc:
            self.repository.session.rollback()
            error = (
                exc if isinstance(exc, GitHubSyncError) else GitHubSyncError("GITHUB_UNAVAILABLE")
            )
            delay = min(240, max(error.retry_after, retry_delay))
            try:
                self.repository.fail(team_id, token, error.code, retry_token, delay, event.id)
            except RuntimeError:
                self.repository.session.rollback()
                return False
            raise GitHubSyncError(error.code, delay) from None
        finally:
            if client:
                client.close()
