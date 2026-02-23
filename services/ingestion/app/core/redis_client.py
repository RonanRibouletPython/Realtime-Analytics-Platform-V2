import redis.asyncio as redis

from app.core.settings import settings

# Module-level singleton — one connection pool shared across all requests.
# Not closing per-request is intentional: we reuse the pool.
_client = redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> redis.Redis:
    """FastAPI dependency — yields the shared Redis client."""
    yield _client


async def check_redis_health() -> None:
    """Raises if Redis is unreachable. Used by the /health endpoint."""
    await _client.ping()
