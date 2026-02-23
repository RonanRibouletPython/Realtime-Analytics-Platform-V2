from sqlalchemy import Column, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.
    Owned here so every service that talks to the DB imports from one place.
    Never re-declare Base in a service — always import this one.
    """

    pass


class Metric(Base):
    """
    Core time-series table.

    Becomes a TimescaleDB hypertable in migration V3
    (partitioned by timestamp, space-partitioned by tenant_id).

    Columns:
        tenant_id   — Phase 5 multi-tenancy. Default 'default' keeps V1/V2 data valid.
        name        — Metric identifier, e.g. 'cpu_usage', 'request_latency_ms'
        value       — The numeric measurement
        timestamp   — When the measurement was taken (timezone-aware)
        labels      — Arbitrary key/value tags, e.g. {host: server-1, region: eu-west}
        environment — Deployment context, e.g. 'production', 'staging'
    """

    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", index=True)
    name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    labels = Column(JSONB, nullable=False, server_default="{}")
    environment = Column(String, nullable=True)

    __table_args__ = (
        # Composite index covering the most common query pattern:
        # WHERE tenant_id = X AND name = Y AND timestamp BETWEEN A AND B
        Index("idx_metrics_tenant_name_time", "tenant_id", "name", "timestamp"),
    )
