import json
import logging
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


async def read(url: str, round_id: UUID, revision: int) -> dict | None:
    try:
        async with Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2) as redis:
            value = await redis.get(f"seal:ranking:{round_id}:{revision}")
            return json.loads(value) if value else None
    except (RedisError, ValueError):
        logger.warning("Ranking cache unavailable; computing from database")
        return None


async def write(url: str, round_id: UUID, revision: int, data: dict) -> None:
    try:
        async with Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2) as redis:
            await redis.set(f"seal:ranking:{round_id}:{revision}", json.dumps(data), ex=300)
    except RedisError:
        logger.warning("Ranking cache write unavailable")
