import json
import logging
from time import time

from celery import bootsteps
from redis import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WorkerHeartbeat(bootsteps.StartStopStep):
    def start(self, consumer: object) -> None:
        def publish() -> None:
            try:
                queues = list(consumer.app.amqp.queues.consume_from)
                with Redis.from_url(
                    str(get_settings().redis_url), socket_connect_timeout=1, socket_timeout=1
                ) as redis:
                    redis.set(
                        f"seal:health:worker:{consumer.hostname}",
                        json.dumps({"at": time(), "queues": queues}),
                        ex=90,
                    )
            except Exception:
                logger.warning("Worker heartbeat unavailable")

        publish()
        self.timer = consumer.timer.call_repeatedly(30, publish)

    def stop(self, consumer: object) -> None:
        self.timer.cancel()
        try:
            with Redis.from_url(
                str(get_settings().redis_url), socket_connect_timeout=1, socket_timeout=1
            ) as redis:
                redis.delete(f"seal:health:worker:{consumer.hostname}")
        except Exception:
            logger.warning("Worker heartbeat cleanup unavailable")
