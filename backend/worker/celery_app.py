from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "seal",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=["worker.tasks.ping", "worker.tasks.send_email", "worker.tasks.submissions"],
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
    beat_scheduler="worker.scheduler:HeartbeatScheduler",
    beat_schedule={
        "submission-reminders": {"task": "seal.submission_reminders", "schedule": 60.0},
        "cleanup-uploads": {"task": "seal.cleanup_uploads", "schedule": 3600.0},
    },
)
# Chỉ đăng ký lịch đồng bộ khi có task thật và chu kỳ theo từng cuộc thi.
