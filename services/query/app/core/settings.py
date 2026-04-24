from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Query Service Configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    #########################
    # Service configuration #
    #########################

    service_name: str = "query-service"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    #############
    # DB config #
    #############

    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://analytics:analytics@localhost:5432/analytics",
        description="PostgreSQL connection URL with asyncpg driver",
    )

    # Connection Pool Settings
    database_pool_size: int = Field(
        default=5, description="Base connection pool size"
    )  # Minimum connections always ready
    database_max_overflow: int = Field(
        default=10, description="Max connections beyond pool_size"
    )  # Burst capacity (5 + 10 = 15 max concurrent queries)
    database_pool_timeout: int = Field(
        default=30, description="Seconds to wait for available connection"
    )  # Wait up to 30s for available connection
    database_pool_recycle: int = Field(
        default=3600, description="Seconds before recycling connection"
    )  # Recycle connections every hour to prevent stale connections

    ################
    # Redis config #
    ################

    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # Cache TTL Settings
    cache_ttl_1min: int = Field(
        default=120, description="Cache TTL for 1-minute aggregates (seconds)"
    )
    cache_ttl_1hour: int = Field(
        default=1200, description="Cache TTL for 1-hour aggregates (seconds)"
    )
    cache_ttl_historical: int = Field(
        default=3600, description="Cache TTL for historical data >24h old (seconds)"
    )

    # Cache key versioning (increment when aggregate logic changes)
    cache_version: str = Field(default="v1", description="Cache key version prefix")

    #######################
    # Query Configuration #
    #######################

    # Time Range Limits
    max_time_range_days: int = Field(
        default=30, description="Maximum allowed time range in days"
    )
    min_time_range_seconds: int = Field(
        default=60, description="Minimum time range (prevents point queries)"
    )

    # Pagination & Response Limits
    max_data_points: int = Field(
        default=1000, description="Maximum data points per response"
    )  # Forces downsampling for large time ranges
    default_page_size: int = Field(default=100, description="Default pagination size")

    # Granularity Selection Thresholds
    granularity_threshold_1min_hours: int = Field(
        default=168,  # 7 days
        description="Use 1-min aggregate below this threshold (hours)",
    )

    # Query Rounding (for cache hit rate optimization)
    # Round query timestamps to nearest N minutes
    # Higher = better cache hit rate, slightly less precision
    query_rounding_minutes: int = Field(
        default=5, description="Round query timestamps to N-minute boundaries"
    )

    # Cost Estimation (prevent expensive queries)
    # Estimated rows = time_range_minutes * metric_count * tenant_count
    max_estimated_rows: int = Field(
        default=100_000, description="Reject queries estimated to scan >N rows"
    )

    ##############
    # API Config #
    ##############
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )

    ##############
    # Prometheus #
    ##############
    metrics_port: int = Field(
        default=8002, description="Port for Prometheus metrics endpoint"
    )


# Cache
@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once
    and reused across requests.
    """
    return Settings()
