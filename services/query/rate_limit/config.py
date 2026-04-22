"""
Rate limiting configuration using the Token Bucket algorithm.

Design:
- Token Bucket: A classic algorithm for rate limiting that allows bursty traffic
  while enforcing a sustained rate over time.
- bucket_size: Maximum number of tokens (requests) allowed in the bucket at once.
- refill_rate: Number of tokens added per refill_interval.
- refill_interval: Time period for token replenishment (in seconds).

Example:
  bucket_size=100, refill_rate=10, refill_interval=60
  -> Tenant can burst up to 100 requests
  -> Then sustains 10 requests per minute (600/hour)
"""

from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Note: This module uses Pydantic BaseSettings with env_prefix for environment
# variable configuration. All settings can be overridden with RATE_LIMIT_* prefix.
#
# Example environment variables:
#   RATE_LIMIT_ENABLED=true
#   RATE_LIMIT_BUCKET_SIZE=200
#   RATE_LIMIT_REFILL_RATE=20
#   RATE_LIMIT_ALGORITHM=token_bucket
#   RATE_LIMIT_TENANT_OVERRIDES='{"tenant123": {"bucket_size": 500}}'


class RateLimitConfig(BaseSettings):
    """
    Rate limiting configuration for the Query Service.

    Uses Token Bucket algorithm with support for:
    - Global default limits
    - Per-tenant override limits (via tenant_id mapping)
    - Enable/disable flag for easy toggling
    - Redis key prefix for namespacing
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="RATE_LIMIT_",
        extra="forbid",
    )

    # Enable/Disable
    enabled: bool = Field(
        default=True,
        description="Enable or disable rate limiting globally",
    )

    # Token Bucket Algorithm Parameters
    bucket_size: int = Field(
        default=100,
        description="Maximum number of tokens in the bucket (burst capacity)",
    )

    refill_rate: int = Field(
        default=10,
        description="Number of tokens added per refill interval",
    )

    refill_interval: int = Field(
        default=60,
        description="Token refill interval in seconds",
    )

    # Alternative: requests per window (simpler but less flexible)
    # Window-based: requests_per_window = 100, window_seconds = 60
    requests_per_window: int = Field(
        default=100,
        description="Max requests allowed per window (simpler mode)",
    )

    window_seconds: int = Field(
        default=60,
        description="Window duration in seconds for requests_per_window mode",
    )

    # Algorithm selection (only token_bucket implemented)
    # Note: sliding_window pending future implementation
    algorithm: Literal["token_bucket"] = Field(
        default="token_bucket",
        description="Rate limiting algorithm (token_bucket only for now)",
    )

    # HTTP Headers
    # These headers inform clients about their rate limit status
    header_limit: str = Field(
        default="X-RateLimit-Limit",
        description="Header name for current limit (tokens/requests allowed)",
    )

    header_remaining: str = Field(
        default="X-RateLimit-Remaining",
        description="Header name for remaining tokens/requests",
    )

    header_reset: str = Field(
        default="X-RateLimit-Reset",
        description="Header name for when the limit resets (Unix timestamp)",
    )

    header_retry_after: str = Field(
        default="Retry-After",
        description="Header name for retry-after duration when rate limited",
    )

    # Redis Key Configuration
    redis_key_prefix: str = Field(
        default="rate_limit:",
        description="Redis key prefix for rate limit counters",
    )

    redis_ttl_buffer: int = Field(
        default=300,
        description="Additional TTL buffer for Redis keys (seconds)",
    )

    # Per-Tenant Overrides
    # Format: {"tenant_id": {"bucket_size": 200, "refill_rate": 20, ...}}
    # Can be configured via environment variable as JSON
    tenant_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-tenant rate limit overrides (JSON string or dict)",
    )

    # Default limits for specific tenant tiers
    # Useful for tiered access (free vs premium tenants)
    tier_limits: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "free": {
                "bucket_size": 50,
                "refill_rate": 5,
                "refill_interval": 60,
            },
            "premium": {
                "bucket_size": 500,
                "refill_rate": 50,
                "refill_interval": 60,
            },
            "enterprise": {
                "bucket_size": 2000,
                "refill_rate": 200,
                "refill_interval": 60,
            },
        },
        description="Rate limit tiers for different tenant levels",
    )

    # Error handling
    # When rate limited, return 429 (Too Many Requests) by default
    return_429_on_limit: bool = Field(
        default=True,
        description="Return 429 status when rate limit exceeded",
    )

    include_retry_header: bool = Field(
        default=True,
        description="Include Retry-After header in 429 responses",
    )

    # Performance tuning
    lua_script_caching: bool = Field(
        default=True,
        description="Cache the Lua script for atomic rate limit operations",
    )

    @field_validator("bucket_size", "refill_rate", "requests_per_window", mode="before")
    @classmethod
    def validate_positive_values(cls, v: int, info: Any) -> int:
        """Ensure rate limit values are positive."""
        if v <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {v}")
        return v

    @field_validator("refill_interval", "window_seconds", mode="before")
    @classmethod
    def validate_interval_positive(cls, v: int, info: Any) -> int:
        """Ensure interval values are positive."""
        if v <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {v}")
        return v

    def get_tenant_config(self, tenant_id: str) -> Self:
        """
        Get effective rate limit config for a specific tenant.

        Priority:
        1. Tenant-specific override (if exists in tenant_overrides)
        2. Tenant tier (if tenant has tier attribute)
        3. Default global config

        Args:
            tenant_id: Unique identifier for the tenant

        Returns:
            RateLimitConfig customized for the tenant
        """
        # Check for direct tenant override
        if tenant_id in self.tenant_overrides:
            override = self.tenant_overrides[tenant_id]
            return self.model_copy(update=override)

        # Return default config (could be extended to check tenant tier)
        return self.model_copy()

    def get_redis_key(self, tenant_id: str, endpoint: str = "*") -> str:
        """
        Generate Redis key for rate limiting.

        Format: {prefix}{tenant_id}:{endpoint}

        Args:
            tenant_id: Unique identifier for the tenant
            endpoint: API endpoint path (default: "*" for all endpoints)

        Returns:
            Redis key string
        """
        # Sanitize tenant_id and endpoint to prevent Redis key injection
        # Whitelist: only allow alphanumeric, hyphen, and underscore
        safe_tenant = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
        safe_endpoint = "".join(c if c.isalnum() or c in "-_/" else "_" for c in endpoint)

        return f"{self.redis_key_prefix}{safe_tenant}:{safe_endpoint}"


@lru_cache
def get_rate_limit_config() -> RateLimitConfig:
    """
    Get cached rate limit configuration instance.

    Uses lru_cache to ensure configuration is loaded only once
    and reused across requests.

    Returns:
        Singleton RateLimitConfig instance
    """
    return RateLimitConfig()