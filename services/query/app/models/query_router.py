from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Literal

import structlog
from app.core.settings import get_settings
from pydantic import BaseModel, Field, field_validator

# Type alias for granularity options
Granularity = Literal["raw", "1m", "1h", "auto"]

logger = structlog.get_logger(__name__)
settings = get_settings()


class QueryRequest(BaseModel):
    """
    Validated query request from API endpoint

    Pydantic enforces:
    - Required fields (tenant_id, name)
    - Valid datetime formats
    - Time range constraints
    """

    tenant_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    start_time: dt
    end_time: dt
    granularity: Granularity | None = Field(
        default=None, description="Override auto-selection (raw, 1m, 1h)"
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def ensure_timezone_aware(cls, v: dt) -> dt:
        """Ensure all timestamps are timezone-aware (UTC)"""
        if v.tzinfo is None:
            # Assume UTC if no timezone provided
            return v.replace(tzinfo=tz.utc)
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, v: dt, info) -> dt:
        """Validate time range constraints"""
        start = info.data.get("start_time")
        if not start:
            return v

        # Ensure end > start
        if v <= start:
            raise ValueError("end_time must be after start_time")

        # Ensure range doesn't exceed maximum
        time_range = v - start
        max_range = td(days=settings.max_time_range_days)
        if time_range > max_range:
            raise ValueError(
                f"Time range exceeds maximum of {settings.max_time_range_days} days. "
                f"Requested: {time_range.days} days"
            )

        # Ensure range meets minimum (prevents point queries)
        min_range = td(seconds=settings.min_time_range_seconds)
        if time_range < min_range:
            raise ValueError(
                f"Time range too small. Minimum: {settings.min_time_range_seconds} seconds"
            )

        return v


class QueryPlan(BaseModel):
    """
    Execution plan for a query

    Contains all information needed to execute the query:
    - Which table to query
    - Rounded timestamps (for caching)
    - Cache key
    - Estimated cost
    """

    tenant_id: str
    name: str
    start_time: dt
    end_time: dt
    granularity: Granularity
    rounded_start: dt
    rounded_end: dt
    cache_key: str
    estimated_rows: int
    cache_ttl: int
