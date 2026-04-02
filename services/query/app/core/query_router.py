from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Literal

import structlog

from app.core.settings import get_settings
from app.models.query_router import QueryPlan, QueryRequest

# Type alias for granularity options
Granularity = Literal["raw", "1min", "1hour"]

logger = structlog.get_logger(__name__)
settings = get_settings()


def round_timestamp(dt: dt, minutes: int) -> dt:
    """
    Round timestamp down to nearest N-minute boundary

    Examples:
        round_timestamp(14:37, 5) → 14:35
        round_timestamp(14:37, 15) → 14:30
        round_timestamp(14:03, 5) → 14:00

    Why?
    - Increases cache hit rate
    - Queries at 14:37, 14:38, 14:39 all use cache key "14:35"
    """
    # Round down to nearest minute boundary
    minutes_since_epoch = int(dt.timestamp() / 60)
    rounded_minutes = (minutes_since_epoch // minutes) * minutes
    return dt.fromtimestamp(rounded_minutes * 60, tz=tz.utc)


def select_granularity(
    time_range: td, override: Granularity | None = None
) -> Granularity:
    """
    Auto-select optimal granularity based on time range

    Strategy:
    - 0-7 days: 1-minute aggregate (good detail, manageable size)
    - 7+ days: 1-hour aggregate (fast queries, less detail)
    - Override: User can force specific granularity

    Trade-offs:
    - 1-min: More accurate, more rows, slower queries
    - 1-hour: Less accurate, fewer rows, faster queries
    """
    if override:
        logger.info(
            "granularity_override",
            override=override,
            time_range_hours=time_range.total_seconds() / 3600,
        )
        return override

    # Convert time range to hours for threshold comparison
    time_range_hours = time_range.total_seconds() / 3600

    if time_range_hours <= settings.granularity_threshold_1min_hours:
        selected = "1min"
    else:
        selected = "1hour"

    logger.info(
        "granularity_auto_selected",
        selected=selected,
        time_range_hours=time_range_hours,
        threshold_hours=settings.granularity_threshold_1min_hours,
    )

    return selected


def estimate_query_cost(time_range: td, granularity: Granularity) -> int:
    """
    Estimate number of rows the query will scan

    Used to reject expensive queries before execution

    Assumptions:
    - Raw: ~1 row per second (aggressive, assumes high write rate)
    - 1-min: 1 row per minute
    - 1-hour: 1 row per hour

    Reality check:
    - At 10 events/sec, 1 day = 864,000 raw rows
    - With 1-min aggregates, 1 day = 1,440 rows (600x smaller)
    - With 1-hour aggregates, 1 day = 24 rows (36,000x smaller)
    """
    total_seconds = int(time_range.total_seconds())

    if granularity == "raw":
        # Pessimistic: assume 1 event per second
        estimated = total_seconds
    elif granularity == "1min":
        # 1 row per minute
        estimated = total_seconds // 60
    else:  # 1hour
        # 1 row per hour
        estimated = total_seconds // 3600

    return max(estimated, 1)  # At least 1 row


def get_cache_ttl(granularity: Granularity, end_time: dt) -> int:
    """
    Determine cache TTL based on granularity and data age.

    Strategy:
    - Recent data (last hour): Short TTL (2 minutes)
    - Medium-age data (1-24 hours): Medium TTL (20 minutes)
    - Historical data (>24 hours): Long TTL (1 hour)

    Why?
    - Recent data changes frequently (new metrics arriving)
    - Historical data is immutable (won't change)
    """
    now = dt.now(tz=tz.utc)
    age = now - end_time

    # Historical data (older than 24 hours) → long TTL
    if age > td(hours=24):
        return settings.cache_ttl_historical

    # Medium-age data → granularity-based TTL
    if granularity == "1hour":
        return settings.cache_ttl_1hour
    else:
        return settings.cache_ttl_1min


def generate_cache_key(
    tenant_id: str,
    metric_name: str,
    start: dt,
    end: dt,
    granularity: Granularity,
) -> str:
    """
    Generate consistent cache key

    Format: {version}:metrics:{tenant}:{metric}:{start_iso}:{end_iso}:{granularity}

    Example:
        v1:metrics:acme:cpu_usage:2026-03-05T14:00:00Z:2026-03-06T14:00:00Z:1hour

    Why ISO format?
    - Sortable
    - URL-safe
    - Timezone-aware
    """
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"{settings.cache_version}:metrics:{tenant_id}:{metric_name}:{start_iso}:{end_iso}:{granularity}"


def create_query_plan(request: QueryRequest) -> QueryPlan:
    """
    Create optimized execution plan for a query.

    This is the main entry point that orchestrates:
    1. Granularity selection
    2. Timestamp rounding (for cache optimization)
    3. Cost estimation
    4. Cache key generation
    5. TTL calculation

    Raises:
        ValueError: If query is too expensive (estimated rows > threshold)
    """
    # Calculate time range
    time_range = request.end_time - request.start_time

    # Auto-select granularity (or use override)
    granularity = select_granularity(time_range, request.granularity)

    # Round timestamps for cache optimization
    # This is YOUR insight from the design question!
    rounded_start = round_timestamp(request.start_time, settings.query_rounding_minutes)
    rounded_end = round_timestamp(request.end_time, settings.query_rounding_minutes)

    # Estimate query cost
    estimated_rows = estimate_query_cost(time_range, granularity)

    # Reject expensive queries
    if estimated_rows > settings.max_estimated_rows:
        raise ValueError(
            f"Query too expensive. Estimated rows: {estimated_rows:,} "
            f"(max: {settings.max_estimated_rows:,}). "
            f"Try a smaller time range or use 'granularity=1hour'"
        )

    # Generate cache key
    cache_key = generate_cache_key(
        request.tenant_id, request.metric_name, rounded_start, rounded_end, granularity
    )

    # Determine cache TTL
    cache_ttl = get_cache_ttl(granularity, request.end_time)

    logger.info(
        "query_plan_created",
        tenant_id=request.tenant_id,
        metric_name=request.metric_name,
        granularity=granularity,
        estimated_rows=estimated_rows,
        cache_ttl=cache_ttl,
        time_range_hours=time_range.total_seconds() / 3600,
    )

    return QueryPlan(
        tenant_id=request.tenant_id,
        metric_name=request.metric_name,
        start_time=request.start_time,
        end_time=request.end_time,
        granularity=granularity,
        rounded_start=rounded_start,
        rounded_end=rounded_end,
        cache_key=cache_key,
        estimated_rows=estimated_rows,
        cache_ttl=cache_ttl,
    )
