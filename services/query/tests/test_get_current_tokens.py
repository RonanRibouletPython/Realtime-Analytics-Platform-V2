"""
Unit tests for RedisStorage.get_current_tokens()

The method retrieves the current token count from a bucket without consuming.
Used for monitoring and debugging purposes.
"""

from unittest.mock import AsyncMock

import pytest
from rate_limit.storage import RedisStorage
from redis.exceptions import RedisError


class TestGetCurrentTokens:
    """Test suite for get_current_tokens method."""

    @pytest.fixture
    def storage(self):
        """Create RedisStorage instance with mocked Redis."""
        mock_redis = AsyncMock()
        return RedisStorage(redis=mock_redis)

    @pytest.mark.asyncio
    async def test_returns_token_count_as_float(self, storage):
        """Happy path: bucket exists, returns token count as float."""
        # Mock Redis hget to return a token value
        storage._redis.hget = AsyncMock(return_value=b"75.5")

        result = await storage.get_current_tokens("tenant1:/api")

        assert result == 75.5
        assert isinstance(result, float)
        storage._redis.hget.assert_called_once_with("tenant1:/api", "tokens")

    @pytest.mark.asyncio
    async def test_returns_none_when_bucket_not_found(self, storage):
        """Bucket doesn't exist, returns None."""
        # Mock Redis hget to return None (key doesn't exist)
        storage._redis.hget = AsyncMock(return_value=None)

        result = await storage.get_current_tokens("nonexistent:/api")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self, storage):
        """RedisError is caught and returns None (fail open)."""
        # Mock Redis hget to raise RedisError
        storage._redis.hget = AsyncMock(
            side_effect=RedisError("Connection lost")
        )

        result = await storage.get_current_tokens("tenant1:/api")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self, storage):
        """ConnectionError is caught and returns None (fail open)."""
        from redis.exceptions import ConnectionError

        storage._redis.hget = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )

        result = await storage.get_current_tokens("tenant1:/api")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout_error(self, storage):
        """TimeoutError is caught and returns None (fail open)."""
        from redis.exceptions import TimeoutError

        storage._redis.hget = AsyncMock(
            side_effect=TimeoutError("Connection timed out")
        )

        result = await storage.get_current_tokens("tenant1:/api")

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_integer_token_value(self, storage):
        """Redis returns integer bytes, should convert to float."""
        storage._redis.hget = AsyncMock(return_value=b"50")

        result = await storage.get_current_tokens("tenant1:/api")

        assert result == 50.0

    @pytest.mark.asyncio
    async def test_handles_zero_tokens(self, storage):
        """Bucket at zero tokens returns 0.0."""
        storage._redis.hget = AsyncMock(return_value=b"0")

        result = await storage.get_current_tokens("tenant1:/api")

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_key_passed_correctly(self, storage):
        """Verify the correct key is used in Redis call."""
        storage._redis.hget = AsyncMock(return_value=b"100")

        await storage.get_current_tokens("my_tenant:/api/endpoint")

        # Verify hget was called with correct arguments
        storage._redis.hget.assert_called_once_with("my_tenant:/api/endpoint", "tokens")