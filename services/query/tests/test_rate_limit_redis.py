"""
Tests for RedisStorage - production backend with graceful degradation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rate_limit.storage import RateLimitResult, RedisStorage
from redis.exceptions import ConnectionError, RedisError, TimeoutError


class TestRedisStorageGracefulDegradation:
    """Test graceful degradation behavior - critical for production.

    When Redis is unavailable (partition, timeout, etc.), the rate limiter
    should fail OPEN to prevent cascading outages. Traffic is allowed through
    instead of blocking all tenants.
    """

    @pytest.mark.asyncio
    async def test_connection_error_fails_open(self):
        """ConnectionError from Redis causes fail-open behavior.

        When Redis has a partition fault, the rate limiter fails gracefully
        and does NOT block access to the API for all tenants (even if they
        are supposed to be blocked because of the rate limiter).
        """
        # Create RedisStorage with mocked Redis client
        mock_redis = AsyncMock()
        storage = RedisStorage(redis=mock_redis)

        # Mock evalsha to raise ConnectionError (simulating Redis partition)
        mock_redis.evalsha = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )
        mock_redis.script_load = AsyncMock(return_value="fake_sha")

        # Call check_and_consume - should fail open
        result = await storage.check_and_consume(
            key="test_key",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )

        # Assert: fail open means allowed=True (traffic allowed through)
        assert result.allowed is True, "Should allow traffic when Redis is down"

        # Assert: remaining equals full bucket size
        assert result.remaining == 100, "Should report full bucket when failing open"

    @pytest.mark.asyncio
    async def test_timeout_error_fails_open(self):
        """TimeoutError from Redis causes fail-open behavior.

        When Redis times out (slow response due to network issues or partition),
        we should fail gracefully and all endpoints should be reachable.
        """
        # Create RedisStorage with mocked Redis client
        mock_redis = AsyncMock()
        storage = RedisStorage(redis=mock_redis)

        # Mock evalsha to raise TimeoutError (simulating slow Redis)
        mock_redis.evalsha = AsyncMock(side_effect=TimeoutError("Connection timed out"))
        mock_redis.script_load = AsyncMock(return_value="fake_sha")

        # Call check_and_consume - should fail open
        result = await storage.check_and_consume(
            key="test_key",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )

        # Assert: fail open means allowed=True (traffic allowed through)
        assert result.allowed is True, "Should allow traffic when Redis times out"

        # Assert: remaining equals full bucket size
        assert result.remaining == 100, "Should report full bucket when failing open"

    @pytest.mark.asyncio
    async def test_generic_redis_error_fails_open(self):
        """
        Any Redis Exception should be handled with gracefully fail open
        """

        # Moched Redis Storage
        mock_redis = AsyncMock()
        storage = RedisStorage(redis=mock_redis)

        # Make evalsha raise a RedisError
        mock_redis.evalsha = AsyncMock(
            side_effect=RedisError("Redis generic Exception")
        )
        mock_redis.script_load = AsyncMock(return_value="fake_sha")

        # Fail open check
        result = await storage.check_and_consume(
            key="test_key",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )

        # Fail gracefully assertions
        assert result.allowed is True, "Should allow traffic when Redis times out"

        assert result.remaining == 100, "Should report full bucket when failing open"

    @pytest.mark.asyncio
    async def test_unexpected_error_fails_closed(self):
        """
        When any other Exception (not Redis) we should fail close
        """

        mock_redis = AsyncMock()
        storage = RedisStorage(redis=mock_redis)

        mock_redis.evalsha = AsyncMock(
            side_effect=ValueError("Non Redis generic Exception")
        )
        mock_redis.script_load = AsyncMock(return_value="fake_sha")

        # Fail close check
        result = await storage.check_and_consume(
            key="test_key",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )

        assert result.allowed is False, "Should allow traffic when Redis times out"

        assert result.remaining == 0, "Should report full bucket when failing open"

        assert result.retry_after == 60, "Should have a value"
