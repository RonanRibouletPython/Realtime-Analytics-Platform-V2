import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from rate_limit.middleware import (
    RateLimitMiddleware,
    RequestIdentifier,
    extract_request_identifier,
)


class TestRequestIdentifier:
    """Test RequestIdentifier dataclass"""

    def test_creation(self):
        """Verify creation"""
        identifier = RequestIdentifier(
            tenant_id="tenant123",
            client_id="client456",
            endpoint="/api/query",
        )
        assert identifier.tenant_id == "tenant123"
        assert identifier.client_id == "client456"
        assert identifier.endpoint == "/api/query"

    def test_frozen(self):
        """Verify frozen (immutable)"""
        identifier = RequestIdentifier(
            tenant_id="tenant123",
            client_id="client456",
            endpoint="/api/query",
        )
        with pytest.raises(AttributeError):
            identifier.tenant_id = "new_tenant"


class TestExtractRequestIdentifier:
    """Test identifier extraction from requests"""

    def test_default_tenant(self):
        """Verify default tenant when no header"""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/query"
        # Mock query_params.get to return the default "default" when key not found
        request.query_params = MagicMock()
        request.query_params.get = MagicMock(side_effect=lambda key, default: default)

        identifier = extract_request_identifier(request)

        assert identifier.tenant_id == "default"

    def test_tenant_from_header(self):
        """Verify tenant extracted from X-Tenant-ID"""
        request = MagicMock(spec=Request)
        request.headers = {"X-Tenant-ID": "acme_corp"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/query"

        identifier = extract_request_identifier(request)

        assert identifier.tenant_id == "acme_corp"

    def test_client_from_auth_header(self):
        """Verify client ID from Authorization header"""
        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer my-secret-api-key-12345"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/query"

        identifier = extract_request_identifier(request)

        assert identifier.client_id.startswith("key_")
        assert "my-secret-api-key-12345" not in identifier.client_id  # Hashed

    def test_client_from_ip(self):
        """Verify client ID falls back to IP"""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.url.path = "/api/query"

        identifier = extract_request_identifier(request)

        assert identifier.client_id == "ip_10.0.0.1"

    def test_client_from_forwarded_for(self):
        """Verify X-Forwarded-For is used"""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.url.path = "/api/query"

        identifier = extract_request_identifier(request)

        assert identifier.client_id == "ip_1.2.3.4"

    def test_endpoint_extraction(self):
        """Verify endpoint is extracted"""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/v1/metrics"

        identifier = extract_request_identifier(request)

        assert identifier.endpoint == "/api/v1/metrics"


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware"""

    @pytest.mark.asyncio
    async def test_skip_health_path(self):
        """Verify /health is skipped"""
        app = FastAPI()
        
        async def mock_call_next(request):
            return MagicMock()
        
        middleware = RateLimitMiddleware(app)
        
        request = MagicMock(spec=Request)
        request.url.path = "/health"
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response is not None

    @pytest.mark.asyncio
    async def test_skip_metrics_path(self):
        """Verify /metrics is skipped"""
        app = FastAPI()
        
        async def mock_call_next(request):
            return MagicMock()
        
        middleware = RateLimitMiddleware(app)
        
        request = MagicMock(spec=Request)
        request.url.path = "/metrics"
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response is not None

    @pytest.mark.asyncio
    async def test_custom_skip_paths(self):
        """Verify custom skip paths work"""
        app = FastAPI()
        
        async def mock_call_next(request):
            return MagicMock()
        
        middleware = RateLimitMiddleware(app, skip_paths={"/health", "/custom"})
        
        request = MagicMock(spec=Request)
        request.url.path = "/custom"
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response is not None


class TestRateLimitMiddlewareIntegration:
    """Integration tests with mocking"""

    @patch("rate_limit.middleware.get_rate_limit_config")
    @patch("rate_limit.middleware.get_rate_limit_storage")
    @pytest.mark.asyncio
    async def test_full_flow_allowed(self, mock_storage, mock_config):
        """Test full flow when allowed"""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.enabled = True
        mock_config_instance.get_redis_key.return_value = "test:key"
        mock_config_instance.get_tenant_config.return_value = MagicMock(
            bucket_size=100,
            refill_rate=10,
            refill_interval=60,
        )
        mock_config.return_value = mock_config_instance

        mock_storage_instance = MagicMock()
        mock_storage_instance.check_and_consume = AsyncMock(
            return_value=MagicMock(
                allowed=True,
                remaining=50,
                reset_time=1700000000,
                bucket_size=100,
                retry_after=None,
                to_headers=MagicMock(
                    return_value={
                        "X-RateLimit-Limit": "100",
                        "X-RateLimit-Remaining": "50",
                        "X-RateLimit-Reset": "1700000000",
                    }
                ),
            )
        )
        mock_storage.return_value = mock_storage_instance

        app = FastAPI()
        middleware = RateLimitMiddleware(app)

        async def mock_call_next(request):
            response = MagicMock()
            response.headers = {}
            return response

        request = MagicMock(spec=Request)
        request.headers = {"X-Tenant-ID": "test"}
        request.url.path = "/api/query"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        response = await middleware.dispatch(request, mock_call_next)
        
        assert response is not None
        mock_storage_instance.check_and_consume.assert_called_once()