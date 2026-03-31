import asyncio

import pytest
import pytest_asyncio
from app.core.cache import get_cached_query, redis_client, set_cached_query
from app.core.settings import get_settings
from redis.asyncio import ConnectionPool

settings = get_settings()


@pytest_asyncio.fixture(autouse=True)
async def clear_redis():
    """Decisively reset Redis connections for each test loop."""
    # 1. Force the global client to use a fresh pool for THIS test's event loop
    new_pool = ConnectionPool.from_url(
        str(settings.redis_url), max_connections=5, decode_responses=True
    )
    old_pool = redis_client.connection_pool
    redis_client.connection_pool = new_pool

    # 2. Cleanup
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()

    # 3. Shutdown this pool so it doesn't leak into the next test
    await new_pool.disconnect()
    await old_pool.disconnect()


@pytest.mark.asyncio
async def test_redis_set_and_get():
    """Verify we can set and retrieve complex dictionary data"""
    test_key = "test_aggregate:tenant_1:cpu_usage"
    test_data = {
        "metric": "cpu_usage",
        "average": 45.5,
        "timestamps": ["2024-01-01T00:00:00Z"],
    }

    # Set data with 10s TTL
    await set_cached_query(test_key, test_data, ttl=10)

    # Retrieve data
    cached_data = await get_cached_query(test_key)

    assert cached_data is not None
    assert cached_data["average"] == 45.5
    assert cached_data["metric"] == "cpu_usage"


@pytest.mark.asyncio
async def test_redis_cache_miss():
    """Verify a missing key safely returns None"""
    cached_data = await get_cached_query("non_existent_key")
    assert cached_data is None


@pytest.mark.asyncio
async def test_redis_ttl_expiration():
    """Verify data actually expires based on TTL"""
    test_key = "test_ttl_key"
    test_data = {"status": "ok"}

    # Set with 1 second TTL
    await set_cached_query(test_key, test_data, ttl=1)

    # Wait for TTL to expire
    await asyncio.sleep(1.1)

    # Should be a cache miss now
    cached_data = await get_cached_query(test_key)
    assert cached_data is None
