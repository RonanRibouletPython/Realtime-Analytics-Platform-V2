"""
FastAPI middleware for rate limiting using Token Bucket algorithm.

This middleware:
- Extracts tenant/client identifier from request
- Checks rate limit using Redis storage
- Returns 429 Too Many Requests when limit exceeded
- Injects rate limit headers into all responses

Usage:
    from rate_limit import RateLimitMiddleware
    
    app.add_middleware(RateLimitMiddleware)

Or with custom config:
    app.add_middleware(RateLimitMiddleware, app_config=config)
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from rate_limit.config import get_rate_limit_config
from rate_limit.storage import (
    RateLimitResult,
    get_rate_limit_storage,
)

# =============================================================================
# Request Identifier Extraction
# =============================================================================


@dataclass(frozen=True)
class RequestIdentifier:
    """Extracted identifier for rate limiting a request."""

    tenant_id: str
    client_id: str
    endpoint: str


def extract_request_identifier(request: Request) -> RequestIdentifier:
    """
    Extract tenant and client identifiers from request.

    Priority:
    1. X-Tenant-ID header
    2. tenant_id query parameter
    3. Client IP fallback

    Args:
        request: FastAPI request object

    Returns:
        RequestIdentifier with tenant_id, client_id, endpoint
    """
    # Extract tenant ID: header → query param → default
    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id", "default")

    # Extract client ID (priority: API key, then IP)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]  # Extract token without "Bearer "
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        client_id = f"key_{key_hash}"
    else:
        # Fallback to client IP
        client_ip = request.client.host if request.client else "unknown"
        # Normalize for common proxies
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        client_id = f"ip_{client_ip}"

    # Extract endpoint path
    endpoint = request.url.path

    return RequestIdentifier(
        tenant_id=tenant_id,
        client_id=client_id,
        endpoint=endpoint,
    )


# =============================================================================
# Middleware Class
# =============================================================================


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies Token Bucket algorithm per tenant/endpoint using Redis.
    Returns 429 with Retry-After when limit exceeded.

    Example:
        app.add_middleware(RateLimitMiddleware)
    """

    def __init__(
        self,
        app: FastAPI,
        skip_paths: set[str] | None = None,
    ) -> None:
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            skip_paths: Paths to skip rate limiting (e.g., {"/health", "/metrics"})
        """
        super().__init__(app)
        self._skip_paths = skip_paths or {"/health", "/metrics", "/ready"}
        self._config = get_rate_limit_config()
        self._storage = get_rate_limit_storage()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """
        Process request through rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response with rate limit headers (or 429 error)
        """
        # Skip rate limiting for excluded paths
        if request.url.path in self._skip_paths:
            return await call_next(request)

        # Skip if rate limiting is disabled
        if not self._config.enabled:
            return await call_next(request)

        # Extract identifier for rate limiting
        identifier = extract_request_identifier(request)
        key = self._config.get_redis_key(identifier.tenant_id, identifier.endpoint)

        # Get tenant-specific config
        tenant_config = self._config.get_tenant_config(identifier.tenant_id)

        # Check and consume token
        result: RateLimitResult = await self._storage.check_and_consume(
            key=key,
            bucket_size=tenant_config.bucket_size,
            refill_rate=tenant_config.refill_rate,
            refill_interval=tenant_config.refill_interval,
        )

        # Handle rate limit exceeded
        if not result.allowed:
            return self._rate_limit_exceeded(request, result)

        # Process request
        response = await call_next(request)

        # Inject rate limit headers into response
        self._inject_headers(response, result)

        return response

    def _rate_limit_exceeded(
        self,
        request: Request,
        result: RateLimitResult,
    ) -> JSONResponse:
        """
        Return 429 Too Many Requests response.

        Args:
            request: Original request
            result: Rate limit check result

        Returns:
            JSON response with error and retry info
        """
        headers = result.to_headers()

        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "message": "Rate limit exceeded. Please retry later.",
                "retry_after": result.retry_after,
            },
            headers=headers,
        )

    def _inject_headers(
        self,
        response: Response,
        result: RateLimitResult,
    ) -> None:
        """
        Inject rate limit headers into response.

        Args:
            response: Response to modify
            result: Rate limit check result
        """
        headers = result.to_headers()
        for key, value in headers.items():
            response.headers[key] = value


# =============================================================================
# Dependency Injection Helper
# =============================================================================


async def get_rate_limit_result(request: Request) -> RateLimitResult | None:
    """
    FastAPI dependency to get rate limit result for the current request.

    Useful for endpoints that want to inspect their rate limit status.

    Example:
        @app.get("/api/data")
        async def get_data(rate_result: RateLimitResult = Depends(get_rate_limit_result)):
            if rate_result:
                log.info(f"Rate limit remaining: {rate_result.remaining}")
    """
    # This extracts the same identifier as the middleware
    identifier = extract_request_identifier(request)
    config = get_rate_limit_config()

    if not config.enabled:
        return None

    key = config.get_redis_key(identifier.tenant_id, identifier.endpoint)
    tenant_config = config.get_tenant_config(identifier.tenant_id)

    storage = get_rate_limit_storage()
    result = await storage.check_and_consume(
        key=key,
        bucket_size=tenant_config.bucket_size,
        refill_rate=tenant_config.refill_rate,
        refill_interval=tenant_config.refill_interval,
    )

    return result


__all__ = [
    "RateLimitMiddleware",
    "RequestIdentifier",
    "extract_request_identifier",
    "get_rate_limit_result",
]