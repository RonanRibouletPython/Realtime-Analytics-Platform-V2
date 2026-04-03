from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from app.core.settings import get_settings
from pydantic import BaseModel, Field, model_validator

settings = get_settings()


class MetricQueryRequest(BaseModel):
    """
    Schema for incoming metric queries.
    Acts as the strict data contract between the frontend and our query service.
    """

    tenant_id: str = Field(..., description="Tenant ID for data isolation")
    name: str = Field(..., description="Name of the metric to query")
    start_time: datetime = Field(..., description="Start of time range")
    end_time: datetime = Field(..., description="End of time range")

    # "auto" means the backend decides the best table to query
    granularity: Literal["1m", "1h", "raw", "auto"] = Field(default="auto")

    @model_validator(mode="after")
    def enforce_business_rules(self) -> "MetricQueryRequest":
        # Enforce strict UTC Timezone awareness
        if self.start_time.tzinfo is None:
            self.start_time = self.start_time.replace(tzinfo=timezone.utc)
        if self.end_time.tzinfo is None:
            self.end_time = self.end_time.replace(tzinfo=timezone.utc)

        # Prevent time-travel and zero-duration queries
        delta = self.end_time - self.start_time
        if delta.total_seconds() < settings.min_time_range_seconds:
            raise ValueError(
                f"Time range must be at least {settings.min_time_range_seconds} seconds"
            )

        # Protect Database: Enforce maximum time range
        if delta.days > settings.max_time_range_days:
            raise ValueError(
                f"Time range cannot exceed {settings.max_time_range_days} days to prevent database overload."
            )

        # Smart Granularity Routing
        if self.granularity == "auto":
            hours_requested = delta.total_seconds() / 3600
            if hours_requested >= settings.granularity_threshold_1min_hours:
                # Large time range -> route to hourly aggregates table
                self.granularity = "1h"
            else:
                # Small time range -> route to minute aggregates table
                self.granularity = "1m"

        return self


class DataPoint(BaseModel):
    """A single point of time-series data"""

    timestamp: datetime
    value: Decimal


class MetricQueryResponse(BaseModel):
    """Standardized response schema for the API"""

    tenant_id: str
    name: str
    granularity: str
    data: list[DataPoint]
