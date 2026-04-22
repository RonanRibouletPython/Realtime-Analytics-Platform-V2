"""
Redis-backed rate limit storage implementing the Token Bucket algorithm.

This module provides:
- RateLimitStorage protocol for testability (swap implementations)
- RedisStorage implementation using Lua scripts for atomic operations
- Multi-tenant support via key namespacing

Token Bucket Algorithm:
    - Tracks tokens + last_refill_time per tenant/endpoint
    - Allows bursts up to bucket_size, then enforces refill_rate
    - Atomic check+consume via Lua script prevents race conditions

Usage:
    storage = RedisStorage()
    result = await storage.check_and_consume(
        key="tenant123:api",
        bucket_size=100,
        refill_rate=10,
        refill_interval=60
    )
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from datetime import datetime, timezone
import time

import structlog
from prometheus_client import Counter, Gauge, Histogram
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.cache import redis_client

logger = structlog.get_logger(__name__)

# =============================================================================
# Observability Metrics
# =============================================================================

RATE_LIMIT_CHECKS = Counter(
    "rate_limit_checks_total",
    "Total rate limit checks",
    ["tenant_id", "result"],
)

RATE_LIMIT_TOKENS = Gauge(
    "rate_limit_tokens_available",
    "Current tokens in bucket",
    ["tenant_id"],
)

RATE_LIMIT_ERRORS = Counter(
    "rate_limit_errors_total",
    "Total rate limit errors",
    ["error_type"],
)

RATE_LIMIT_LATENCY = Histogram(
    "rate_limit_check_duration_seconds",
    "Rate limit check latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)


# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """
    Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed (True) or rate limited (False)
        remaining: Number of tokens remaining after this check
        reset_time: Unix timestamp when the bucket will be full again
        bucket_size: The configured bucket size (for header response)
        retry_after: Seconds until a token is available (only if denied)
    """

    allowed: bool
    remaining: int
    reset_time: int  # Unix timestamp
    bucket_size: int
    retry_after: int | None = None  # None if allowed

    def to_headers(self) -> dict[str, str]:
        """Convert to HTTP response headers."""
        headers = {
            "X-RateLimit-Limit": str(self.bucket_size),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_time),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


# =============================================================================
# Protocol Interface (for testability and swap implementations)
# =============================================================================


@runtime_checkable
class RateLimitStorage(Protocol):
    """
    Protocol for rate limit storage backends.

    Implement this protocol to create custom rate limiters:
    - RedisStorage (production)
    - InMemoryStorage (development/testing)
    - MockStorage (unit tests)

    The storage MUST be atomic to prevent race conditions in distributed systems.
    """

    async def check_and_consume(
        self,
        key: str,
        bucket_size: int,
        refill_rate: float,
        refill_interval: int,
    ) -> RateLimitResult:
        """
        Check and consume a token from the rate limit bucket.

        This operation is atomic - check and consume happen together.

        Args:
            key: Unique identifier for the bucket (e.g., "tenant123:api")
            bucket_size: Maximum tokens in the bucket
            refill_rate: Tokens added per refill_interval
            refill_interval: Refill interval in seconds

        Returns:
            RateLimitResult with allowed/denied and metadata
        """
        ...


# =============================================================================
# Lua Script for Atomic Token Bucket
# =============================================================================

# Token Bucket Lua Script - Atomic check and consume
# Runs atomically in Redis (single-threaded execution)
#
# KEYS[1] = bucket key
# ARGV[1] = bucket_size (max tokens)
# ARGV[2] = refill_rate (tokens per interval)
# ARGV[3] = refill_interval (seconds)
# ARGV[4] = now (current Unix timestamp in milliseconds)
# ARGV[5] = ttl (key TTL in seconds)
#
# Returns: [allowed (0/1), remaining_tokens, reset_timestamp_ms]

TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local bucket_size = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local refill_interval = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

-- Get current bucket state
local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

-- Initialize bucket if it doesn't exist
if tokens == nil then
    tokens = bucket_size
    last_refill = now
end

-- Calculate token refill based on elapsed time
local elapsed = (now - last_refill) / 1000  -- convert ms to seconds
local tokens_to_add = (elapsed / refill_interval) * refill_rate
tokens = math.min(bucket_size, tokens + tokens_to_add)

-- Check if we can consume a token
if tokens >= 1 then
    -- Consume one token
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, ttl)
    -- Calculate reset time (when bucket will be full)
    local tokens_needed = bucket_size - tokens
    local reset_in_seconds = (tokens_needed / refill_rate) * refill_interval
    local reset_time = math.ceil(now / 1000 + reset_in_seconds)
    return {1, math.floor(tokens), reset_time}
else
    -- No tokens available
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, ttl)
    -- Calculate when next token will be available
    local reset_in_seconds = ((1 - tokens) / refill_rate) * refill_interval
    local reset_time = math.ceil(now / 1000 + reset_in_seconds)
    return {0, 0, reset_time}
end
"""


# =============================================================================
# Redis Storage Implementation
# =============================================================================


class RedisStorage:
    """
    Redis-backed rate limit storage using Token Bucket algorithm.

    Features:
    - Atomic operations via Lua script (no race conditions)
    - Multi-tenant support via key namespacing
    - Automatic TTL management (prevents memory leaks)
    - Graceful degradation (fails open if Redis unavailable)

    Example:
        storage = RedisStorage()
        result = await storage.check_and_consume(
            key="tenant123:/api/metrics",
            bucket_size=100,
            refill_rate=10,
            refill_interval=60
        )
        if not result.allowed:
            raise HTTPException(429, headers=result.to_headers())
    """

    def __init__(
        self,
        redis: Redis | None = None,
        lua_script: str | None = None,
    ) -> None:
        """
        Initialize Redis storage.

        Args:
            redis: Redis client instance (defaults to shared client)
            lua_script: Lua script for atomic operations (defaults to TOKEN_BUCKET_SCRIPT)
        """
        self._redis = redis or redis_client
        self._script = lua_script or TOKEN_BUCKET_SCRIPT
        self._script_sha: str | None = None

    async def _get_script_sha(self) -> str:
        """
        Get cached script SHA or load new script into Redis.

        Uses SCRIPT LOAD for efficiency (avoids sending script on every call).
        """
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(self._script)
        return self._script_sha

    def _calculate_ttl(
        self,
        bucket_size: int,
        refill_rate: float,
        refill_interval: int,
    ) -> int:
        """
        Calculate TTL for Redis key.

        TTL = time until bucket naturally empties + buffer
        This ensures abandoned buckets auto-cleanup.

        Args:
            bucket_size: Maximum tokens in bucket
            refill_rate: Tokens per interval
            refill_interval: Interval in seconds

        Returns:
            TTL in seconds (minimum 60, maximum 86400)
        """
        if refill_rate <= 0:
            return 300  # Default 5 minutes

        # Time to fill empty bucket: tokens_needed / tokens_per_second
        # tokens_needed = bucket_size, tokens_per_second = refill_rate / refill_interval
        seconds_to_fill = (bucket_size / refill_rate) * refill_interval

        # Add 50% buffer for safety
        ttl = int(seconds_to_fill * 1.5)

        # Clamp to reasonable bounds
        return max(60, min(ttl, 86400))  # 1 minute to 24 hours

    async def check_and_consume(
        self,
        key: str,
        bucket_size: int,
        refill_rate: float,
        refill_interval: int,
    ) -> RateLimitResult:
        """
        Atomically check and consume a token from the bucket.

        This is the main entry point for rate limiting. It:
        1. Refills tokens based on elapsed time
        2. Checks if a token is available
        3. Consumes the token if allowed
        4. Returns detailed result with headers info

        Args:
            key: Unique bucket identifier (include tenant_id for multi-tenant)
            bucket_size: Maximum burst capacity
            refill_rate: Tokens added per interval
            refill_interval: Refill interval in seconds

        Returns:
            RateLimitResult with allowed/denied status and metadata
        """
        start_time = time.monotonic()
        tenant_id = key.split(":")[0] if ":" in key else "default"

        # Validate inputs to prevent Lua division by zero
        if refill_interval <= 0 or refill_rate <= 0 or bucket_size <= 0:
            logger.warning("rate_limit_invalid_params", key=key, bucket_size=bucket_size, refill_rate=refill_rate, refill_interval=refill_interval)
            return RateLimitResult(
                allowed=True,
                remaining=bucket_size,
                reset_time=int(time.time()) + 60,
                bucket_size=bucket_size,
                retry_after=None,
            )

        try:
            # Load script if needed
            script_sha = await self._get_script_sha()

            # Calculate TTL for key
            ttl = self._calculate_ttl(bucket_size, refill_rate, refill_interval)

            # Current time in milliseconds for Lua script
            now_ms = int(time.time() * 1000)

            # Execute atomic Lua script
            result = await self._redis.evalsha(
                script_sha,
                1,  # number of keys
                key,  # KEYS[1]
                bucket_size,  # ARGV[1]
                refill_rate,  # ARGV[2]
                refill_interval,  # ARGV[3]
                now_ms,  # ARGV[4]
                ttl,  # ARGV[5]
            )

            # Parse Lua script result
            allowed = bool(result[0])
            remaining = int(result[1])
            reset_time = int(result[2])

            # Calculate retry_after if denied
            retry_after = None
            if not allowed:
                retry_after = max(0, reset_time - int(time.time()))

            # Update metrics
            duration = time.monotonic() - start_time
            RATE_LIMIT_LATENCY.observe(duration)
            RATE_LIMIT_CHECKS.labels(tenant_id=tenant_id, result="allowed" if allowed else "denied").inc()
            RATE_LIMIT_TOKENS.labels(tenant_id=tenant_id).set(remaining)

            logger.debug(
                "rate_limit_check",
                key=key,
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                duration_ms=round(duration * 1000, 2),
            )

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                bucket_size=bucket_size,
                retry_after=retry_after,
            )

        except RedisError as e:
            # Graceful degradation: fail open on Redis errors
            RATE_LIMIT_ERRORS.labels(error_type=type(e).__name__).inc()
            logger.warning(
                "rate_limit_redis_error_falling_back",
                key=key,
                error=str(e),
            )

            # Return allowed result to not block traffic
            # This allows the system to operate even if Redis is temporarily unavailable
            return RateLimitResult(
                allowed=True,
                remaining=bucket_size,
                reset_time=int(time.time()) + refill_interval,
                bucket_size=bucket_size,
                retry_after=None,
            )

        except Exception as e:
            # Unexpected error - fail closed for safety
            RATE_LIMIT_ERRORS.labels(error_type=type(e).__name__).inc()
            logger.error(
                "rate_limit_unexpected_error",
                key=key,
                error=str(e),
            )

            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=int(time.time()) + refill_interval,
                bucket_size=bucket_size,
                retry_after=refill_interval,
            )

    async def get_current_tokens(self, key: str) -> float | None:
        """
        Get current token count without consuming.

        Useful for monitoring and debugging.

        Args:
            key: Bucket key

        Returns:
            Current token count or None if bucket doesn't exist
        """
        try:
            tokens = await self._redis.hget(key, "tokens")
            if tokens is None:
                return None
            return float(tokens)
        except RedisError as e:
            logger.warning("rate_limit_get_tokens_error", key=key, error=str(e))
            return None

    async def reset_bucket(self, key: str) -> bool:
        """
        Reset a bucket to full capacity.

        Useful for admin operations or testing.

        Args:
            key: Bucket key to reset

        Returns:
            True if reset successful
        """
        try:
            now_ms = int(time.time() * 1000)
            await self._redis.hset(key, mapping={"tokens": "0", "last_refill": str(now_ms)})
            logger.info("rate_limit_bucket_reset", key=key)
            return True
        except RedisError as e:
            logger.error("rate_limit_reset_error", key=key, error=str(e))
            return False


# =============================================================================
# In-Memory Storage (for testing/development without Redis)
# =============================================================================


@dataclass
class _BucketState:
    """In-memory bucket state for non-Redis storage."""

    tokens: float
    last_refill: float
    bucket_size: int
    refill_rate: float
    refill_interval: int


class InMemoryStorage:
    """
    In-memory rate limit storage for testing/development.

    WARNING: Not suitable for multi-process or distributed deployments.
    Use RedisStorage for production.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _BucketState] = {}

    def _refill_bucket(self, bucket: _BucketState) -> float:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_refill
        tokens_to_add = (elapsed / bucket.refill_interval) * bucket.refill_rate
        bucket.tokens = min(bucket.bucket_size, bucket.tokens + tokens_to_add)
        bucket.last_refill = now
        return bucket.tokens

    async def check_and_consume(
        self,
        key: str,
        bucket_size: int,
        refill_rate: float,
        refill_interval: int,
    ) -> RateLimitResult:
        """Non-atomic in-memory implementation for testing."""
        now = time.time()

        if key not in self._buckets:
            self._buckets[key] = _BucketState(
                tokens=bucket_size,
                last_refill=now,
                bucket_size=bucket_size,
                refill_rate=refill_rate,
                refill_interval=refill_interval,
            )

        bucket = self._buckets[key]
        bucket.tokens = self._refill_bucket(bucket)

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return RateLimitResult(
                allowed=True,
                remaining=int(bucket.tokens),
                reset_time=int(now + (1 / refill_rate) * refill_interval),
                bucket_size=bucket_size,
            )
        else:
            reset_time = int(now + ((1 - bucket.tokens) / refill_rate) * refill_interval)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                bucket_size=bucket_size,
                retry_after=reset_time - int(now),
            )


# =============================================================================
# Factory Functions
# =============================================================================


def get_rate_limit_storage() -> RateLimitStorage:
    """
    Get the appropriate rate limit storage backend.

    Returns:
        RedisStorage for production, InMemoryStorage if Redis unavailable
    """
    return RedisStorage()


__all__ = [
    "RateLimitStorage",
    "RateLimitResult",
    "RedisStorage",
    "InMemoryStorage",
    "get_rate_limit_storage",
    # Exported for testing
    "TOKEN_BUCKET_SCRIPT",
]