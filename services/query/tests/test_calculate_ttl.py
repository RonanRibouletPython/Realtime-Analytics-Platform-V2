"""
Unit tests for RedisStorage._calculate_ttl()

The TTL calculation ensures abandoned buckets auto-cleanup while keeping
active buckets alive. TTL = time to fill empty bucket + 50% buffer,
clamped to [60s, 86400s].

If refill_rate <= 0, returns default 300s (5 minutes).
"""

import pytest
from rate_limit.storage import RedisStorage


class TestCalculateTtl:
    """Test suite for _calculate_ttl method."""

    @pytest.fixture
    def storage(self):
        """Create RedisStorage instance for testing."""
        return RedisStorage()

    # =========================================================================
    # Boundary Tests - verify clamping to [60, 86400] seconds
    # =========================================================================

    def test_ttl_clamped_to_minimum_60_seconds(self, storage):
        """TTL should never be less than 60 seconds (1 minute)."""
        # Very small bucket with high refill rate = very short fill time
        # (10 / 100) * 60 * 1.5 = 9 seconds → clamped to 60
        ttl = storage._calculate_ttl(
            bucket_size=10,
            refill_rate=100,  # 100 tokens per 60s = ~1.67 tokens/sec
            refill_interval=60,
        )
        assert ttl == 60

    def test_ttl_clamped_to_maximum_86400_seconds(self, storage):
        """TTL should never exceed 86400 seconds (24 hours)."""
        # Large bucket with low refill rate = very long fill time
        # (10000 / 1) * 3600 * 1.5 = 54,000,000 seconds → clamped to 86400
        ttl = storage._calculate_ttl(
            bucket_size=10000,
            refill_rate=1,  # 1 token per 3600s = very slow
            refill_interval=3600,
        )
        assert ttl == 86400

    # =========================================================================
    # Normal Cases - realistic configurations
    # =========================================================================

    def test_ttl_standard_api_rate_limit(self, storage):
        """Standard rate limit: 100 requests/min, refill 10/sec.

        100 tokens, 10 per 60s = 600 seconds to fill
        600 * 1.5 = 900 seconds = 15 minutes
        """
        ttl = storage._calculate_ttl(
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )
        assert ttl == 900  # 15 minutes

    def test_ttl_strict_api_rate_limit(self, storage):
        """Strict rate limit: 10 requests/min.

        10 tokens, 1 per 6s = 60 seconds to fill
        60 * 1.5 = 90 seconds
        """
        ttl = storage._calculate_ttl(
            bucket_size=10,
            refill_rate=1,
            refill_interval=6,
        )
        assert ttl == 90

    def test_ttl_generous_rate_limit(self, storage):
        """Generous rate limit: 1000 requests/min.

        1000 tokens, 100 per 60s = 600 seconds to fill
        600 * 1.5 = 900 seconds = 15 minutes
        """
        ttl = storage._calculate_ttl(
            bucket_size=1000,
            refill_rate=100,
            refill_interval=60,
        )
        assert ttl == 900

    # =========================================================================
    # Edge Cases - extreme values
    # =========================================================================

    def test_ttl_zero_refill_rate_returns_default(self, storage):
        """Zero refill rate returns default 300 seconds (5 min)."""
        ttl = storage._calculate_ttl(
            bucket_size=100,
            refill_rate=0,
            refill_interval=60,
        )
        assert ttl == 300

    def test_ttl_negative_refill_rate_returns_default(self, storage):
        """Negative refill rate returns default 300 seconds (5 min)."""
        ttl = storage._calculate_ttl(
            bucket_size=100,
            refill_rate=-10,
            refill_interval=60,
        )
        assert ttl == 300

    def test_ttl_bucket_size_one(self, storage):
        """Single token bucket with fast refill."""
        # 1 token, 10 per 60s = 0.1 seconds to fill
        # 0.1 * 1.5 = 0.15 → clamped to minimum 60
        ttl = storage._calculate_ttl(
            bucket_size=1,
            refill_rate=10,
            refill_interval=60,
        )
        assert ttl == 60

    def test_ttl_refill_rate_equals_bucket_size(self, storage):
        """Refill rate equals bucket size = fill time equals interval."""
        # 100 tokens, 100 per 60s = 60 seconds to fill
        # 60 * 1.5 = 90 seconds
        ttl = storage._calculate_ttl(
            bucket_size=100,
            refill_rate=100,
            refill_interval=60,
        )
        assert ttl == 90

    # =========================================================================
    # Formula Verification - ensure the math is correct
    # =========================================================================

    def test_ttl_formula_exact_calculation(self, storage):
        """Verify the formula: (bucket_size / refill_rate) * interval * 1.5"""
        # 50 tokens, 25 per 30s = 60 seconds to fill
        # 60 * 1.5 = 90 seconds
        ttl = storage._calculate_ttl(
            bucket_size=50,
            refill_rate=25,
            refill_interval=30,
        )
        assert ttl == 90

    def test_ttl_fractional_refill_rate(self, storage):
        """Handle fractional refill rates correctly."""
        # 10 tokens, 0.5 per 60s = 1200 seconds to fill
        # 1200 * 1.5 = 1800 seconds
        ttl = storage._calculate_ttl(
            bucket_size=10,
            refill_rate=0.5,  # 1 token per 2 minutes
            refill_interval=60,
        )
        assert ttl == 1800  # 30 minutes

    # =========================================================================
    # Intent Tests - verify the formula serves operational purpose
    # =========================================================================

    def test_ttl_active_bucket_stays_alive(self, storage):
        """Active buckets (frequently accessed) stay alive.

        With normal API usage, buckets are accessed before TTL expires,
        so they stay alive. The TTL is a safety net for abandoned buckets.
        """
        # Standard API: 100 tokens, 10/min → 15 min TTL
        ttl = storage._calculate_ttl(
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )
        # 15 minutes should be enough for active usage
        assert ttl >= 300  # At least 5 minutes

    def test_ttl_abandoned_bucket_gets_cleaned_up(self, storage):
        """Abandoned buckets eventually get cleaned up.

        Even with large buckets, TTL is capped at 24 hours to prevent
        unbounded Redis memory growth from abandoned keys.
        """
        # Extreme case: huge bucket would have huge TTL
        ttl = storage._calculate_ttl(
            bucket_size=1_000_000,
            refill_rate=1,
            refill_interval=1,
        )
        # Must be capped at 24 hours
        assert ttl == 86400