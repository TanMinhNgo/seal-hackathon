import logging

from app.integrations import mailer
from app.modules.judging.repository import ResultEmailRepository

logger = logging.getLogger(__name__)


class ResultEmailJobs:
    def __init__(self, repository: ResultEmailRepository) -> None:
        self.repository = repository

    def deliver(self) -> int:
        count = 0
        for _ in range(100):
            row = self.repository.claim()
            if row is None:
                break
            try:
                mailer.send_email(row.recipient, "SEAL - Round results", row.body)
            except Exception:
                # Không retry tự động vì SMTP có thể đã nhận thư trước khi mất kết nối.
                self.repository.finish(row, "failed")
                logger.warning(
                    "Result email requires provider review", extra={"receipt_id": str(row.id)}
                )
            else:
                self.repository.finish(row, "accepted")
                count += 1
        return count
