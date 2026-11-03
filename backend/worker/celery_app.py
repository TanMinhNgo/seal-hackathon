from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "seal",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=[
        "worker.tasks.ping",
        "worker.tasks.send_email",
        "worker.tasks.submissions",
        "worker.tasks.judging",
        "worker.tasks.commits",
        "worker.tasks.ai_reviews",
    ],
)
celery_app.conf.update(
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    broker_connection_timeout=3,
    task_publish_retry=False,
    task_routes={"seal.review_commit": {"queue": "ai-review"}},
    beat_scheduler="worker.scheduler:HeartbeatScheduler",
    beat_schedule={
        "ai-reviews": {"task": "seal.dispatch_ai_reviews", "schedule": 60.0},
        "sync-commits": {"task": "seal.sync_commits", "schedule": 60.0},
        "result-emails": {"task": "seal.result_emails", "schedule": 60.0},
        "submission-reminders": {"task": "seal.submission_reminders", "schedule": 60.0},
        "cleanup-uploads": {"task": "seal.cleanup_uploads", "schedule": 3600.0},
    },
)
