from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.db import sync_session_factory
from app.modules.ai_reviews.jobs import ReviewJobs
from app.modules.ai_reviews.repository import ReviewJobRepository
from worker.celery_app import celery_app


@celery_app.task(name="seal.dispatch_ai_reviews", ignore_result=True)
def dispatch_ai_reviews() -> int:
    count = 0
    with sync_session_factory() as session:
        repository = ReviewJobRepository(session)
        for job_id in repository.pending():
            token = str(uuid4())
            if not repository.claim(job_id, token):
                continue
            try:
                review_commit.apply_async(args=[str(job_id), token], task_id=token)
                count += 1
            except Exception:
                # Enqueue mơ hồ: giữ lease, token cũ không chạy được sau lần claim kế tiếp.
                continue
    return count


@celery_app.task(
    name="seal.review_commit",
    queue="ai-review",
    ignore_result=True,
    soft_time_limit=240,
    time_limit=270,
    rate_limit="10/m",
)
def review_commit(job_id: str, token: str) -> bool:
    with sync_session_factory() as session:
        return ReviewJobs(ReviewJobRepository(session), get_settings()).run(UUID(job_id), token)
