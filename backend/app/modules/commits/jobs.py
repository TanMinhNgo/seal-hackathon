import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.schemas import utc
from app.integrations import mailer
from app.integrations.github_sync import GitHubSync, GitHubSyncError
from app.modules.auth.service import AuthService
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

    def run(self, team_id: UUID, queued: str) -> bool:
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
            client = GitHubSync(self.settings, team.repo_url)

            def heartbeat() -> None:
                self.repository.heartbeat(team_id, token)

            branch, head = client.branch_head(state.branch)
            state.branch = branch
            self.repository.commit()
            shas, complete = client.history(head, heartbeat)
            stored = self.repository.stored(team_id)
            baseline = state.baseline_at is None
            for sha in shas:
                if sha in stored:
                    continue
                detail = client.detail(sha, heartbeat)
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
            else:
                state.sync_status = "error"
                state.sync_error = "GITHUB_INCOMPLETE_HISTORY"
            state.truncated = not complete
            self.repository.commit()
            self.repository.release(team_id, token)
            return complete
        except Exception as exc:
            self.repository.session.rollback()
            code = exc.code if isinstance(exc, GitHubSyncError) else "GITHUB_UNAVAILABLE"
            try:
                self.repository.heartbeat(team_id, token)
            except RuntimeError:
                return False
            state = self.repository.state(team_id)
            notify = code == "REPO_NOT_ACCESSIBLE" and not state.notified
            # Mark before transport: ambiguous SMTP acceptance must not cause duplicate mail.
            if notify:
                state.notified = True
            self.repository.commit()
            self.repository.release(team_id, token, code)
            if notify and self.settings.smtp_host:
                for recipient in AuthService.sync_recipients(self.repository.session, event.id):
                    try:
                        mailer.send_email(
                            recipient,
                            "SEAL - Repository sync failed",
                            f"Team {team.id}: repository is private, removed or inaccessible. "
                            "Check commit overview.",
                        )
                    except Exception:
                        logger.warning(
                            "Repository alert delivery requires review",
                            extra={"team_id": str(team_id)},
                        )
            if isinstance(exc, GitHubSyncError):
                raise
            raise GitHubSyncError(code) from None
        finally:
            if client:
                client.close()
