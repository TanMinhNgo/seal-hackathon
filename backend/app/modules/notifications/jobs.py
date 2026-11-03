import logging
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.config import Settings
from app.integrations import mailer
from app.integrations.realtime import publish
from app.modules.notifications.models import Notification, NotificationDelivery, RealtimeOutbox
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationOutput

logger = logging.getLogger(__name__)


class NotificationJobs:
    def __init__(self, session: object, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def deliver(self, limit: int = 100, *, channel: str | None = None) -> int:
        count = 0
        for _ in range(limit):
            query = select(NotificationDelivery).where(NotificationDelivery.status == "queued")
            if channel:
                query = query.where(NotificationDelivery.channel == channel)
            row = self.session.scalar(
                query.order_by(NotificationDelivery.created_at, NotificationDelivery.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                self.session.rollback()
                break
            # Claim bền trước SMTP: crash hoặc mất receipt không được tự gửi lần hai.
            claimed = self.session.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.id == row.id, NotificationDelivery.status == "queued")
                .values(status="unknown", updated_at=datetime.now(UTC))
            )
            if not claimed.rowcount:
                self.session.rollback()
                continue
            self.session.commit()
            try:
                if not NotificationRepository(self.session).delivery_allowed(row):
                    row.status, row.error_code = "failed", "RECIPIENT_NO_LONGER_ELIGIBLE"
                    self.session.commit()
                    continue
                if row.channel == "email" and not self.settings.smtp_host:
                    row.status, row.error_code = "failed", "SMTP_NOT_CONFIGURED"
                    self.session.commit()
                    continue
                if row.channel == "email":
                    payload = row.payload
                    mailer.send_email(
                        payload["address"],
                        payload["title"],
                        payload["body"]
                        + "\n"
                        + str(self.settings.frontend_url).rstrip("/")
                        + payload["link"],
                    )
                else:
                    notification = self.session.scalar(
                        select(Notification).where(
                            Notification.user_id == row.recipient_id,
                            Notification.source == row.source,
                        )
                    )
                    publish(
                        "notification:new",
                        f"user:{row.recipient_id}",
                        NotificationOutput.model_validate(notification).model_dump(mode="json"),
                    )
            except Exception:
                row.status = "unknown" if row.channel == "email" else "queued"
                row.error_code = (
                    "SMTP_RECEIPT_UNKNOWN" if row.channel == "email" else "REALTIME_UNAVAILABLE"
                )
                logger.warning(
                    "Notification delivery requires review", extra={"delivery_id": str(row.id)}
                )
            else:
                row.status, row.error_code = "sent", None
                count += 1
            row.updated_at = datetime.now(UTC)
            self.session.commit()
            if row.status == "queued":
                break
        return count

    def realtime(self, limit: int = 100) -> int:
        count = 0
        for _ in range(limit):
            row = self.session.scalar(
                select(RealtimeOutbox)
                .where(RealtimeOutbox.sent_at.is_(None))
                .order_by(RealtimeOutbox.created_at, RealtimeOutbox.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                self.session.rollback()
                break
            try:
                publish(row.event, row.room, row.payload)
            except Exception:
                self.session.rollback()
                break
            row.sent_at = datetime.now(UTC)
            self.session.commit()
            count += 1
        return count
