from app.core.config import get_settings
from app.core.db import sync_session_factory
from app.modules.notifications.jobs import NotificationJobs
from worker.celery_app import celery_app


@celery_app.task(name="seal.notifications")
def notifications() -> dict[str, int]:
    with sync_session_factory() as session:
        jobs = NotificationJobs(session, get_settings())
        return {"realtime": jobs.realtime(), "deliveries": jobs.deliver(channel="in_app")}


@celery_app.task(name="seal.notification_emails", ignore_result=True)
def notification_emails() -> int:
    with sync_session_factory() as session:
        return NotificationJobs(session, get_settings()).deliver(channel="email")
