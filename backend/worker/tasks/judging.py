from app.core.db import sync_session_factory
from app.modules.judging.jobs import ResultEmailJobs
from app.modules.judging.repository import ResultEmailRepository
from worker.celery_app import celery_app


@celery_app.task(name="seal.result_emails", ignore_result=True)
def result_emails() -> int:
    with sync_session_factory() as session:
        return ResultEmailJobs(ResultEmailRepository(session)).deliver()
