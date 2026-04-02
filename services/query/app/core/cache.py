import json
from typing import Any

import structlog
from prometheus_client import Counter
from redis.asyncio import ConnectionPool, Redis

from app.core.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Observability - with Prometheus
CACHE_HITS = Counter("cache_hits_total", "Total successful cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total cache misses")
CACHE_ERRORS = Counter(
    "cache_errors_total",
    "Total cache errors (fallback to DB triggered)",
    ["error_type"],
)

# Connection Pool Init
redis_pool = ConnectionPool.from_url(
    str(settings.redis_url),
    max_connections=50,
    decode_responses=True,  # Automatically decodes byte responses to UTF-8 strings
)

redis_client = Redis(connection_pool=redis_pool)


async def get_cached_query(key: str) -> dict[str, Any] | None:
    """
    Attempt to get data from Redis.
    Fails gracefully -> If Redis is down, returns None
    so the application falls back to querying the database
    """
    try:
        data = await redis_client.get(key)
        if data:
            CACHE_HITS.inc()
            return json.loads(data)

        CACHE_MISSES.inc()
        return None
    except Exception as e:
        CACHE_ERRORS.labels(error_type=type(e).__name__).inc()
        logger.error("redis_get_error", error=str(e), key=key)
        # Graceful degradation: pretend it's a cache miss
        return None


async def set_cached_query(key: str, data: dict[str, Any], ttl: int) -> None:
    """
    Attempt to save data to Redis
    Fails gracefully -> Never fail a user request just
    because saving to the cache failed
    """
    try:
        # setex = SET with EXpiration (TTL)
        await redis_client.setex(key, ttl, json.dumps(data))
    except Exception as e:
        CACHE_ERRORS.labels(error_type=type(e).__name__).inc()
        logger.error("redis_set_error", error=str(e), key=key)
        # Graceful degradation: ignore the error, move on
        pass


def generate_cache_key(
    tenant_id: str, metric_name: str, start: str, end: str, granularity: str
) -> str:
    """
    Generate consistent cache keys.

    Format: {version}:metrics:{tenant}:{metric}:{start}:{end}:{granularity}
    Example: v1:metrics:acme:cpu_usage:2026-03-05T14:00:2026-03-06T14:00:1h
    """
    return f"{settings.cache_version}:metrics:{tenant_id}:{metric_name}:{start}:{end}:{granularity}"
