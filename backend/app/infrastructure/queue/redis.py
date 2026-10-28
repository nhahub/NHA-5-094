from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Returns the shared asynchronous Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.redis_uri,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis_client() -> None:
    """Closes the Redis connection pool."""
    global redis_client
    if redis_client is not None:
        if hasattr(redis_client, "aclose"):
            await redis_client.aclose()
        else:
            await redis_client.close()
        redis_client = None


async def check_redis_health() -> bool:
    """Verifies Redis connectivity with a ping."""
    try:
        client = await get_redis_client()
        pong = await client.ping()
        return pong is True
    except Exception:
        return False
