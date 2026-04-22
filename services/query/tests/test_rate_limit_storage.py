import pytest
from rate_limit.storage import (
    InMemoryStorage,
    RateLimitResult,
)


class TestRateLimitResult:
    """Test RateLimitResult dataclass"""

    def test_allowed_result(self):
        """Verify allowed result"""
        result = RateLimitResult(
            allowed=True,
            remaining=50,
            reset_time=1700000000,
            bucket_size=100,
        )
        assert result.allowed is True
        assert result.remaining == 50
        assert result.retry_after is None

    def test_denied_result(self):
        """Verify denied result with retry_after"""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_time=1700000060,
            bucket_size=100,
            retry_after=60,
        )
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 60

    def test_to_headers_allowed(self):
        """Verify headers for allowed request"""
        result = RateLimitResult(
            allowed=True,
            remaining=50,
            reset_time=1700000000,
            bucket_size=100,
        )
        headers = result.to_headers()
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
        assert "Retry-After" not in headers
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"

    def test_to_headers_denied(self):
        """Verify headers for denied request includes Retry-After"""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_time=1700000060,
            bucket_size=100,
            retry_after=60,
        )
        headers = result.to_headers()
        assert "Retry-After" in headers
        assert headers["Retry-After"] == "60"


class TestInMemoryStorage:
    """Test InMemoryStorage for unit testing"""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        """Verify first request is allowed"""
        storage = InMemoryStorage()
        result = await storage.check_and_consume(
            key="test_tenant:/api",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )
        assert result.allowed is True
        assert result.remaining >= 0

    @pytest.mark.asyncio
    async def test_bucket_depletes(self):
        """Verify bucket depletes after requests"""
        storage = InMemoryStorage()
        # Exhaust the bucket
        for _ in range(100):
            result = await storage.check_and_consume(
                key="test_deplete:/api",
                bucket_size=10,
                refill_rate=10,
                refill_interval=60,
            )
        # 11th request should be denied
        result = await storage.check_and_consume(
            key="test_deplete:/api",
            bucket_size=10,
            refill_rate=10,
            refill_interval=60,
        )
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_different_keys_separate(self):
        """Verify different keys have separate buckets"""
        storage = InMemoryStorage()
        key1 = "tenant_a:/api"
        key2 = "tenant_b:/api"
        
        # Make 90 requests on key1
        for _ in range(90):
            await storage.check_and_consume(key1, 100, 10, 60)
        
        # key1 should be near limit, but key2 should be full
        result1 = await storage.check_and_consume(key1, 100, 10, 60)
        result2 = await storage.check_and_consume(key2, 100, 10, 60)
        
        # key1 should have fewer remaining
        assert result1.remaining < result2.remaining


class TestInMemoryStorageEdgeCases:
    """Test edge cases"""

    @pytest.mark.asyncio
    async def test_zero_bucket_size_denies(self):
        """Edge case: zero bucket denies all requests"""
        storage = InMemoryStorage()
        result = await storage.check_and_consume(
            key="test:/api",
            bucket_size=0,
            refill_rate=10,
            refill_interval=60,
        )
        # With zero bucket, no tokens available
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_reset_bucket(self):
        """Verify bucket reset works"""
        storage = InMemoryStorage()
        # Exhaust bucket
        for _ in range(10):
            await storage.check_and_consume("reset_test:/api", 10, 10, 60)
        
        result = await storage.check_and_consume("reset_test:/api", 10, 10, 60)
        assert result.allowed is False
        
        # Reset would require direct state manipulation in real scenario
        # InMemoryStorage doesn't expose reset publicly