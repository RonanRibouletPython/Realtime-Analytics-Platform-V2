from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz

import pytest
from app.core.settings import get_settings
from app.models.query import MetricQueryRequest
from pydantic import ValidationError

settings = get_settings()


def test_smart_granularity_auto_routing():
    """Verify short ranges get 1m, and long ranges get 1h granularity"""
    now = dt.now(tz.utc)

    # Short range: 2 days (less than 7-day threshold)
    short_req = MetricQueryRequest(
        tenant_id="tenant_1",
        name="cpu_usage",
        start_time=now - td(days=2),
        end_time=now,
    )
    assert short_req.granularity == "1m"

    # Long range: 10 days (greater than 7-day threshold)
    long_req = MetricQueryRequest(
        tenant_id="tenant_1",
        name="cpu_usage",
        start_time=now - td(days=10),
        end_time=now,
    )
    assert long_req.granularity == "1h"


def test_naive_datetime_conversion():
    """Verify naive datetimes are forcefully converted to UTC"""
    # Note: datetime.now() without tzinfo is "naive"
    naive_start = dt.now()
    naive_end = naive_start + td(hours=1)

    req = MetricQueryRequest(
        tenant_id="tenant_1",
        name="cpu_usage",
        start_time=naive_start,
        end_time=naive_end,
    )

    # Proof that timezone was attached
    assert req.start_time.tzinfo is not None
    assert req.start_time.tzinfo == tz.utc


def test_database_protection_limits():
    """Verify users cannot request 10 years of data"""
    now = dt.now(tz.utc)

    with pytest.raises(ValidationError) as exc_info:
        MetricQueryRequest(
            tenant_id="tenant_1",
            name="cpu_usage",
            start_time=now - td(days=40),  # settings max is 30
            end_time=now,
        )

    assert "Time range cannot exceed" in str(exc_info.value)
