from app.core.config import get_settings
from app.core.db import sync_session_factory
from app.modules.submissions.jobs import SubmissionJobs
from app.modules.submissions.repository import SubmissionJobRepository
from worker.celery_app import celery_app


@celery_app.task(name="seal.submission_reminders", ignore_result=True)
def submission_reminders() -> int:
    with sync_session_factory() as session:
        return SubmissionJobs(SubmissionJobRepository(session), get_settings()).remind()


@celery_app.task(name="seal.cleanup_uploads", ignore_result=True)
def cleanup_uploads() -> int:
    settings = get_settings()
    if not (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    ):
        return 0
    with sync_session_factory() as session:
        return SubmissionJobs(SubmissionJobRepository(session), settings).cleanup()
