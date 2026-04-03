import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cached_query, set_cached_query
from app.core.database import get_db_session
from app.core.query_router import QueryRequest, create_query_plan
from app.core.query_service import fetch_metrics
from app.models.query import MetricQueryRequest

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/metrics")
async def execute_metric_query(
    request: QueryRequest = Depends(),  # Tells FastAPI to read these fields from the URL Query Parameters
    session: AsyncSession = Depends(get_db_session),
):
    """
    RESTful GET endpoint for fetching metrics
    Example: /api/v1/metrics?tenant_id=acme&name=cpu_usage&start_time=2026-03-06T00:00:00Z&end_time=2026-03-06T23:59:59Z
    """
    try:
        # Create the Execution Plan (Validates, Rounds, Estimates Cost)
        plan = create_query_plan(request)

        # Check Cache
        cached_data = await get_cached_query(plan.cache_key)
        if cached_data:
            logger.info("api_cache_hit", key=plan.cache_key)
            return cached_data

        logger.info("api_cache_miss", key=plan.cache_key)

        # Adapt QueryRequest to our Service Layer's MetricQueryRequest
        service_req = MetricQueryRequest(
            tenant_id=plan.tenant_id,
            name=plan.name,
            start_time=plan.rounded_start,  # Use ROUNDED times for DB queries!
            end_time=plan.rounded_end,
            granularity=plan.granularity,
        )

        # Fetch from Database
        response = await fetch_metrics(session, service_req)

        # Save to Cache (Background/Async)
        # We convert the Pydantic model to a dict using model_dump()
        response_dict = response.model_dump(mode="json")
        await set_cached_query(
            key=plan.cache_key, data=response_dict, ttl=plan.cache_ttl
        )

        return response_dict

    except ValueError as e:
        # Catch our business logic errors (like Cost Estimation failure)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("api_internal_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
