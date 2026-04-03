from sqlalchemy import Column, DateTime, Float, MetaData, String
from sqlalchemy.orm import DeclarativeBase

# MetaData allows us to point to tables that already exist (created by migrations)
metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class RawMetric(Base):
    __tablename__ = "metrics"  # The raw hypertable
    timestamp = Column(DateTime(timezone=True), primary_key=True)
    tenant_id = Column(String, primary_key=True)
    name = Column(String, primary_key=True)
    value = Column(Float)


class Metric1m(Base):
    __tablename__ = "metrics_1min"  # The 1-minute aggregate view
    bucket = Column(DateTime(timezone=True), primary_key=True)
    tenant_id = Column(String, primary_key=True)
    name = Column(String, primary_key=True)
    avg_value = Column(Float)


class Metric1h(Base):
    __tablename__ = "metrics_1hour"  # The 1-hour aggregate view
    bucket = Column(DateTime(timezone=True), primary_key=True)
    tenant_id = Column(String, primary_key=True)
    name = Column(String, primary_key=True)
    avg_value = Column(Float)
