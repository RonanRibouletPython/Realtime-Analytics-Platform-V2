from datetime import datetime as dt
from datetime import timezone as tz
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


class MetricBase(BaseModel):
    """
    Fields shared by all metric request/response schemas.
    Used by: ingestion (validates POST body), query_service (serialises responses).
    """

    tenant_id: str = Field(default="default")
    name: str = Field(..., description="Metric name, e.g. cpu_usage")
    value: float = Field(..., description="Numeric measurement")
    timestamp: dt = Field(default_factory=lambda: dt.now(tz.utc))
    environment: str | None = Field(
        default=None, description="e.g. production, staging"
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="e.g. {host: server-1}"
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "tenant_id": "acme-corp",
                "name": "cpu_usage",
                "value": 75.32,
                "environment": "production",
                "labels": {"host": "server-1", "region": "eu-west-1"},
            }
        },
    )


class MetricCreate(MetricBase):
    """Request body for POST /metrics."""

    pass


class MetricResponse(MetricBase):
    """Response body — includes the DB-assigned id."""

    id: int


class IngestionAck(BaseModel):
    """
    Acknowledgement returned immediately by the ingestion service.
    HTTP 202 Accepted: the metric is queued in Kafka, not yet persisted to DB.
    Callers should not assume durability until the worker confirms via its own metrics.
    """

    status: str  # always "queued"
    message: str
    timestamp: dt
