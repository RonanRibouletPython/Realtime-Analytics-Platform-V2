import pytest
from rate_limit.config import RateLimitConfig, get_rate_limit_config


class TestRateLimitConfigDefaults:
    """Test RateLimitConfig default values"""

    def test_default_bucket_size(self):
        """Verify default bucket_size is 100"""
        config = get_rate_limit_config()
        assert config.bucket_size == 100

    def test_default_refill_rate(self):
        """Verify default refill_rate is 10"""
        config = get_rate_limit_config()
        assert config.refill_rate == 10

    def test_default_refill_interval(self):
        """Verify default refill_interval is 60 seconds"""
        config = get_rate_limit_config()
        assert config.refill_interval == 60

    def test_default_enabled(self):
        """Verify rate limiting is enabled by default"""
        config = get_rate_limit_config()
        assert config.enabled is True

    def test_algorithm_is_token_bucket(self):
        """Verify algorithm is token_bucket"""
        config = get_rate_limit_config()
        assert config.algorithm == "token_bucket"


class TestRateLimitRedisKeyGeneration:
    """Test Redis key generation"""

    def test_basic_key(self):
        """Verify basic key generation"""
        config = get_rate_limit_config()
        key = config.get_redis_key("tenant123", "/api/query")
        assert key.startswith("rate_limit:")
        assert "tenant123" in key
        assert "/api/query" in key

    def test_key_sanitization(self):
        """Verify special characters are sanitized"""
        config = get_rate_limit_config()
        key = config.get_redis_key("tenant:id:with:colons", "/api/path")
        # Colon in tenant is replaced with underscore
        assert "tenant_id_with_colons" in key

    def test_endpoint_with_slash(self):
        """Verify slashes are preserved in endpoint"""
        config = get_rate_limit_config()
        key = config.get_redis_key("tenant123", "/api/v1/metrics")
        assert "/api/v1/metrics" in key


class TestRateLimitTenantOverrides:
    """Test tenant override functionality"""

    def test_default_config(self):
        """Verify default config is returned when no override"""
        config = get_rate_limit_config()
        tenant_config = config.get_tenant_config("nonexistent")
        assert tenant_config.bucket_size == config.bucket_size

    def test_none_returns_copy(self):
        """Verify get_tenant_config returns a copy, not self"""
        config = get_rate_limit_config()
        tenant_config = config.get_tenant_config("default")
        assert tenant_config is not config


class TestRateLimitConfigValidation:
    """Test config validation"""

    def test_negative_bucket_size_raises(self):
        """Verify negative bucket_size raises"""
        with pytest.raises(ValueError):
            RateLimitConfig(bucket_size=-1)

    def test_zero_refill_rate_raises(self):
        """Verify zero refill_rate raises"""
        with pytest.raises(ValueError):
            RateLimitConfig(refill_rate=0)

    def test_negative_interval_raises(self):
        """Verify negative refill_interval raises"""
        with pytest.raises(ValueError):
            RateLimitConfig(refill_interval=-1)