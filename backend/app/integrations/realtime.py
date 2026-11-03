import socketio
from redis import Redis

from app.core.config import get_settings


class OutboxRedisManager(socketio.RedisManager):
    def _publish(self, data: dict) -> int:
        with Redis.from_url(
            str(get_settings().redis_url), socket_timeout=2, socket_connect_timeout=2
        ) as redis:
            return redis.publish(self.channel, self.json.dumps(data))


def publish(event: str, room: str, payload: dict) -> None:
    manager = OutboxRedisManager(str(get_settings().redis_url), write_only=True)
    manager.emit(event, payload, room=room)
