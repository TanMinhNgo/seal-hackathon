from worker.celery_app import celery_app


@celery_app.task(name="seal.ping")
def ping() -> str:
    return "pong"
