from time import time

from celery import Celery
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

BEAT_HEARTBEAT_KEY = "seal:health:beat"


async def ping_redis(redis_url: str) -> None:
    async with AsyncRedis.from_url(
        redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
    ) as client:
        await client.ping()


async def beat_heartbeat(redis_url: str) -> float | None:
    async with AsyncRedis.from_url(
        redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
    ) as client:
        value = await client.get(BEAT_HEARTBEAT_KEY)
    return float(value) if value is not None else None


def publish_beat_heartbeat(redis_url: str) -> None:
    with Redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5) as client:
        client.set(BEAT_HEARTBEAT_KEY, str(time()), ex=120)


def worker_queues(redis_url: str) -> set[str] | None:
    with Celery("seal-monitor", broker=redis_url, set_as_current=False) as app:
        app.conf.update(
            broker_connection_timeout=0.5,
            broker_transport_options={
                "socket_connect_timeout": 0.5,
                "socket_timeout": 0.5,
                "retry_on_timeout": False,
            },
            task_publish_retry=False,
        )
        with app.connection_for_write(connect_timeout=0.5) as connection:
            connection.ensure_connection(max_retries=0, timeout=0.5)
            replies = app.control.inspect(timeout=0.8, connection=connection).active_queues()
        if not replies:
            return None
        return {queue["name"] for queues in replies.values() for queue in queues}
