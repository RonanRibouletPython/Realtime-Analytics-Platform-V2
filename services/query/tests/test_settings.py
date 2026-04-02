from app.core.settings import get_settings


def test_settings_loads():
    """Verify settings load with defaults"""
    settings = get_settings()

    assert settings.service_name == "query-service"
    assert settings.environment == "development"
    assert settings.database_pool_size == 5
    assert settings.max_time_range_days == 30
    assert settings.max_data_points == 1000
    assert settings.query_rounding_minutes == 5


def test_connection_pool_math():
    """Verify connection pool calculations are correct"""
    settings = get_settings()

    max_connections = settings.database_pool_size + settings.database_max_overflow
    assert max_connections == 15


def test_cache_ttl_logic():
    """Verify cache TTL matches aggregate refresh intervals"""
    settings = get_settings()

    # 1-min aggregate refreshes every 60s → cache for 120s (2x safety margin)
    assert settings.cache_ttl_1min == 120

    # 1-hour aggregate refreshes every 900s (15min) → cache for 1200s (20min)
    assert settings.cache_ttl_1hour == 1200

    # Historical data (>24h old) is immutable → cache for 1 hour
    assert settings.cache_ttl_historical == 3600


def test_granularity_thresholds():
    """Verify auto-granularity selection makes sense"""
    settings = get_settings()

    # Use 1-min aggregate for queries under 7 days (168 hours)
    assert settings.granularity_threshold_1min_hours == 168

    # For 7 days at 1-min granularity:
    # 7 days × 24 hours × 60 minutes = 10,080 points
    # This is above our max_data_points (1000), so downsampling kicks in
    max_points_at_threshold = settings.granularity_threshold_1min_hours * 60
    assert max_points_at_threshold > settings.max_data_points
