import structlog
from prometheus_client import Counter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Metric1h, Metric1m, RawMetric
from app.models.query import DataPoint, MetricQueryRequest, MetricQueryResponse

logger = structlog.get_logger(__name__)

# Observability
QUERY_GRANULARITY_COUNT = Counter(
    "query_granularity_total", "Queries per granularity level", ["granularity"]
)

# Table Mapping Strategy
GRANULARITY_MAP = {
    "raw": (RawMetric, RawMetric.timestamp, RawMetric.value),
    "1m": (Metric1m, Metric1m.bucket, Metric1m.avg_value),
    "1h": (Metric1h, Metric1h.bucket, Metric1h.avg_value),
}


async def fetch_metrics(
    session: AsyncSession, request: MetricQueryRequest
) -> MetricQueryResponse:
    """
    Builds and executes the SQLAlchemy query based on requested granularity
    """
    # Select the correct table/columns from our map
    table_class, time_col, val_col = GRANULARITY_MAP.get(
        request.granularity, GRANULARITY_MAP["1m"]
    )

    QUERY_GRANULARITY_COUNT.labels(granularity=request.granularity).inc()

    # Build the query
    stmt = (
        select(time_col, val_col)
        .where(
            and_(
                table_class.tenant_id == request.tenant_id,
                table_class.name == request.name,
                time_col >= request.start_time,
                time_col <= request.end_time,
            )
        )
        .order_by(time_col.asc())
    )

    # Execute
    result = await session.execute(stmt)
    rows = result.all()

    # Format for Response
    data_points = [DataPoint(timestamp=row[0], value=row[1]) for row in rows]

    return MetricQueryResponse(
        tenant_id=request.tenant_id,
        name=request.name,
        granularity=request.granularity,
        data=data_points,
    )


# SELF CRITIQUE:
# - Table Mapping Strategy -> This could be handled by a factory function
# Memory Risk -> If a query returns 100.000 rows with result.all(), and 10 users
# are making requests at the same time, we could run out of memory
