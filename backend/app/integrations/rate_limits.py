from redis.asyncio import Redis


async def consume(redis_url: str, key: str, window: int, limit: int) -> bool:
    async with Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2) as client:
        count = await client.eval(
            "local n=redis.call('INCR',KEYS[1]); "
            "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1,
            key,
            window,
        )
    return count <= limit
