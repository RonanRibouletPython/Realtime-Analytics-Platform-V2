from datetime import datetime, timedelta, timezone

import pytest
from app.core.query_router import (
    QueryRequest,
    create_query_plan,
    estimate_query_cost,
    round_timestamp,
    select_granularity,
)


def test_round_timestamp():
    """Verify timestamp rounding logic"""
    dt = datetime(2026, 3, 6, 14, 37, 0, tzinfo=timezone.utc)

    # Round to 5-minute boundaries
    rounded_5 = round_timestamp(dt, 5)
    assert rounded_5 == datetime(2026, 3, 6, 14, 35, 0, tzinfo=timezone.utc)

    # Round to 15-minute boundaries
    rounded_15 = round_timestamp(dt, 15)
    assert rounded_15 == datetime(2026, 3, 6, 14, 30, 0, tzinfo=timezone.utc)


def test_granularity_selection():
    """Verify auto-granularity selection based on time range"""
    # 6 hours → should use 1-min aggregate
    short_range = timedelta(hours=6)
    assert select_granularity(short_range) == "1m"

    # 3 days → should use 1-min aggregate (under 7-day threshold)
    medium_range = timedelta(days=3)
    assert select_granularity(medium_range) == "1m"

    # 10 days → should use 1-hour aggregate (over 7-day threshold)
    long_range = timedelta(days=10)
    assert select_granularity(long_range) == "1h"

    # Override: force 1-hour even for short range
    override = select_granularity(short_range, override="1h")
    assert override == "1h"


def test_cost_estimation():
    """Verify query cost estimation"""
    # 1 hour of 1-min data = 60 rows
    cost_1min = estimate_query_cost(timedelta(hours=1), "1m")
    assert cost_1min == 60

    # 24 hours of 1-hour data = 24 rows
    cost_1hour = estimate_query_cost(timedelta(hours=24), "1h")
    assert cost_1hour == 24

    # 1 hour of raw data = 3600 rows (pessimistic: 1 event/sec)
    cost_raw = estimate_query_cost(timedelta(hours=1), "raw")
    assert cost_raw == 3600


def test_query_validation_rejects_invalid_ranges():
    """Verify query validation catches bad inputs"""
    now = datetime.now(tz=timezone.utc)

    # Test: end_time before start_time
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        QueryRequest(
            tenant_id="test",
            name="cpu",
            start_time=now,
            end_time=now - timedelta(hours=1),  # End before start!
        )

    # Test: time range too large (> 30 days default)
    with pytest.raises(ValueError, match="Time range exceeds maximum"):
        QueryRequest(
            tenant_id="test",
            name="cpu",
            start_time=now - timedelta(days=31),
            end_time=now,
        )

    # Test: time range too small (< 60 seconds default)
    with pytest.raises(ValueError, match="Time range too small"):
        QueryRequest(
            tenant_id="test",
            name="cpu",
            start_time=now - timedelta(seconds=30),
            end_time=now,
        )


def test_query_plan_creation():
    """Verify complete query plan creation"""
    now = datetime(2026, 3, 6, 14, 37, 0, tzinfo=timezone.utc)
    start = now - timedelta(hours=24)

    request = QueryRequest(
        tenant_id="acme", name="cpu_usage", start_time=start, end_time=now
    )

    plan = create_query_plan(request)

    # Should auto-select 1-min (24 hours < 7 days)
    assert plan.granularity == "1m"

    # Should round timestamps to 5-minute boundaries
    assert plan.rounded_start.minute % 5 == 0
    assert plan.rounded_end.minute % 5 == 0

    # Should generate cache key
    assert "acme" in plan.cache_key
    assert "cpu_usage" in plan.cache_key
    assert "1m" in plan.cache_key

    # Should estimate ~1440 rows (24 hours × 60 minutes)
    assert plan.estimated_rows == 1440


def test_expensive_query_rejected():
    """Verify that prohibitively expensive queries are rejected"""
    now = datetime.now(tz=timezone.utc)

    # Create request that would scan >100K rows
    # 30 days of raw data = 30 × 86400 = 2,592,000 rows
    request = QueryRequest(
        tenant_id="test",
        name="cpu",
        start_time=now - timedelta(days=30),
        end_time=now,
        granularity="raw",  # Force raw (expensive!)
    )

    with pytest.raises(ValueError, match="Query too expensive"):
        create_query_plan(request)
