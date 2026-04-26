"""
Unit tests for RedisStorage.reset_bucket()

The method resets a bucket to initial state (tokens=0, last_refill=now).
Useful for admin operations or testing.

Note: The method sets tokens to 0 (not bucket_size), meaning the bucket
starts empty and will refill over time based on refill_rate.
"""

from unittest.mock import AsyncMock, ANY, patch
import time as time_module

import pytest
from rate_limit.storage import RedisStorage
from redis.exceptions import ConnectionError, RedisError, TimeoutError


class TestResetBucket:
    """Test suite for reset_bucket method."""

    @pytest.fixture
    def storage(self):
        """Create RedisStorage instance with mocked Redis."""
        mock_redis = AsyncMock()
        return RedisStorage(redis=mock_redis)

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self, storage):
        """Happy path: reset successful, returns True."""
        storage._redis.hset = AsyncMock(return_value=1)

        result = await storage.reset_bucket("tenant1:/api")

        assert result is True

    @pytest.mark.asyncio
    async def test_calls_hset_with_correct_mapping(self, storage):
        """Verify hset is called with tokens=0 and last_refill timestamp."""
        # Mock time to have predictable timestamp (1700000000.5 seconds = 1700000000500 ms)
        with patch.object(time_module, 'time', return_value=1700000000.5):
            storage._redis.hset = AsyncMock(return_value=1)

            await storage.reset_bucket("tenant1:/api")

            # Verify hset was called with the correct mapping
            storage._redis.hset.assert_called_once()
            call_args = storage._redis.hset.call_args
            assert call_args[1]["mapping"]["tokens"] == "0"
            assert call_args[1]["mapping"]["last_refill"] == "1700000000500"  # ms (with fractional seconds)

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_error(self, storage):
        """RedisError returns False (fail silently for admin ops)."""
        storage._redis.hset = AsyncMock(
            side_effect=RedisError("Connection lost")
        )

        result = await storage.reset_bucket("tenant1:/api")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self, storage):
        """ConnectionError returns False."""
        storage._redis.hset = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )

        result = await storage.reset_bucket("tenant1:/api")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout_error(self, storage):
        """TimeoutError returns False."""
        storage._redis.hset = AsyncMock(
            side_effect=TimeoutError("Connection timed out")
        )

        result = await storage.reset_bucket("tenant1:/api")

        assert result is False

    @pytest.mark.asyncio
    async def test_key_passed_correctly(self, storage):
        """Verify the correct key is used in Redis call."""
        storage._redis.hset = AsyncMock(return_value=1)

        await storage.reset_bucket("my_tenant:/api/endpoint")

        # Verify hset was called with correct key
        storage._redis.hset.assert_called_once_with(
            "my_tenant:/api/endpoint",
            mapping={"tokens": "0", "last_refill": ANY}
        )