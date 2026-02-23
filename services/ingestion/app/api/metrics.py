import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from shared.models.metric import Metric
from shared.schemas.metric import IngestionAck, MetricCreate, MetricResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.kafka_producer import SchemaVersion, produce_metric

router = APIRouter(prefix="/metrics", tags=["metrics"])
logger = structlog.get_logger()


@router.post("", response_model=IngestionAck, status_code=status.HTTP_202_ACCEPTED)
async def ingest_metric(metric_in: MetricCreate) -> IngestionAck:
    """
    Accept a metric and queue it to Kafka.

    Returns 202 immediately — the metric is buffered, not yet in the DB.
    The worker picks it up asynchronously and writes to TimescaleDB.
    """
    try:
        await produce_metric(metric_in.model_dump(), version=SchemaVersion.V3)

        logger.info(
            "metric_queued",
            name=metric_in.name,
            tenant_id=metric_in.tenant_id,
            value=metric_in.value,
        )

        return IngestionAck(
            status="queued",
            message="Metric accepted for processing",
            timestamp=metric_in.timestamp,
        )

    except ValueError as e:
        # ValueError = bad data from the caller, not a server problem.
        # 422 here prevents DLQ alerts from firing on client-side mistakes.
        logger.warning("metric_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    except Exception as e:
        logger.error("metric_ingest_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue metric",
        )


@router.get("", response_model=list[MetricResponse])
async def list_metrics(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[MetricResponse]:
    """
    Return the most recent metrics from the DB.
    This is a convenience endpoint for development/debugging.
    Production time-series queries belong in query_service.

    Query params:
        limit: 1–100 (default 10)
    """
    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )

    try:
        result = await db.execute(
            select(Metric).order_by(Metric.timestamp.desc()).limit(limit)
        )
        return result.scalars().all()

    except Exception as e:
        logger.error("metrics_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics",
        )
