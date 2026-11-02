from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.db import sync_session_factory
from app.core.schemas import utc
from app.integrations.github_sync import GitHubSyncError, budget_pause
from app.modules.commits.jobs import CommitJobs
from app.modules.commits.repository import CommitJobRepository
from worker.celery_app import celery_app


@celery_app.task(name="seal.sync_commits", ignore_result=True)
def sync_commits() -> int:
    count = 0
    if budget_pause(get_settings()):
        return 0
    with sync_session_factory() as session:
        repository = CommitJobRepository(session)
        for event, team in CommitJobs(repository, get_settings()).contexts():
            token = str(uuid4())
            if not repository.claim(team.id, token, event.sync_interval_minutes):
                continue
            try:
                sync_team.apply_async(args=[str(team.id), token], task_id=token)
            except Exception:
                repository.release(team.id, token, "SYNC_QUEUE_UNAVAILABLE")
            else:
                count += 1
    return count


@celery_app.task(
    bind=True,
    name="seal.sync_team",
    rate_limit="30/m",
    max_retries=3,
    ignore_result=True,
    soft_time_limit=240,
    time_limit=270,
)
def sync_team(self: object, team_id: str, token: str) -> bool:
    with sync_session_factory() as session:
        repository = CommitJobRepository(session)
        retry_token = str(uuid4()) if self.request.retries < self.max_retries else None
        try:
            return CommitJobs(repository, get_settings()).run(
                UUID(team_id), token, retry_token, 60 * 2**self.request.retries
            )
        except GitHubSyncError as exc:
            if retry_token is None:
                return False
            state = repository.state(UUID(team_id))
            if state.lease_token != retry_token or state.next_retry_at is None:
                return False
            raise self.retry(args=[team_id, retry_token], eta=utc(state.next_retry_at), exc=exc)
