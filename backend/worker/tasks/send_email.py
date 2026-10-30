from app.integrations.mailer import send_email as deliver_email
from worker.celery_app import celery_app


@celery_app.task(name="seal.send_email", ignore_result=True)
def send_email(recipient: str, subject: str, body: str) -> None:
    try:
        deliver_email(recipient, subject, body)
    except Exception:
        # Không tự retry khi SMTP có thể đã nhận thư; không ghi nội dung chứa token.
        raise RuntimeError(
            "SMTP delivery failed; review provider status before resending"
        ) from None
