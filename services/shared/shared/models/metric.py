"""
SQLAlchemy model for metrics table.

Note: The 'id' column is marked as primary_key in SQLAlchemy for ORM
compatibility, but the database does NOT enforce a PRIMARY KEY constraint.
This is intentional for TimescaleDB compatibility.

In time-series databases, primary keys are unnecessary because:
1. Data is append-only (no updates)
2. Queries are time-range based (not id-based)
3. TimescaleDB partitioning requires timestamp in any unique constraint

The 'id' is just a sequence number for reference, not a true unique identifier.
"""

from sqlalchemy import Column, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Metric(Base):
    __tablename__ = "metrics"

    # Fake primary key for ORM compatibility
    # Database doesn't enforce uniqueness - this is just an auto-incrementing sequence
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Sequential ID (not enforced as unique in DB)",
    )

    name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        doc="Partition column for TimescaleDB",
    )
    labels = Column(JSONB, nullable=False, default={})
    environment = Column(String)
    tenant_id = Column(String(64), nullable=False, default="default", index=True)

    # Composite index matching the one in V2 migration
    __table_args__ = (
        Index("idx_metrics_tenant_name_time", "tenant_id", "name", "timestamp"),
    )

    def __repr__(self):
        return f"<Metric(id={self.id}, tenant={self.tenant_id}, name={self.name}, value={self.value}, timestamp={self.timestamp})>"
