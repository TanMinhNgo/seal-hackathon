import logging
from time import monotonic

from celery.beat import PersistentScheduler
from redis.exceptions import RedisError

from app.integrations.system_monitor import publish_beat_heartbeat

logger = logging.getLogger(__name__)


class HeartbeatScheduler(PersistentScheduler):
    def tick(self, *args: object, **kwargs: object) -> float:
        now = monotonic()
        if now - getattr(self, "_last_health_at", float("-inf")) >= 30:
            self._last_health_at = now
            try:
                publish_beat_heartbeat(self.app.conf.broker_url)
            except (RedisError, OSError) as exc:
                logger.warning("Beat heartbeat unavailable: %s", type(exc).__name__)
        return min(super().tick(*args, **kwargs), 30)
