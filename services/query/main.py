from contextlib import asynccontextmanager

import structlog
from app.api.endpoints import router as api_router
from app.core.cache import redis_client
from app.core.database import engine
from app.core.settings import get_settings
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from pydantic import ValidationError
from rate_limit.middleware import RateLimitMiddleware

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage startup and shutdown events cleanly
    Crucial for preventing memory leaks and 'Event loop is closed' errors
    """
    logger.info("service_starting", version=settings.cache_version)
    await redis_client.initialize()

    yield  # Application is running

    logger.info("service_shutting_down")
    # Clean up DB pool and Redis connections
    await engine.dispose()
    await redis_client.aclose()


app = FastAPI(
    title=settings.service_name,
    lifespan=lifespan,
)


# Glogbal Exception Handler
@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """
    Catches pure Pydantic ValidationErrors (often raised inside Depends())
    and translates them into standard HTTP 422 responses instead of 500s
    """
    errors = exc.errors()
    logger.warning("api_validation_error", errors=exc.errors(), url=str(request.url))
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors)},
    )


# CORS Middleware for Frontend Dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting Middleware
app.add_middleware(RateLimitMiddleware)

# Expose Prometheus Metrics (Hits, Errors, Query Durations)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Mount our API Router
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check():
    """Simple Liveness Probe"""
    return {"status": "healthy"}


# SELF CRITIQUE
# - Thundering Herd Risk -> If 500 users request a dashboard simultaneously on a cache miss, all 500 requests will currently pass through the endpoint and hit the DB at the exact same time
# We would need to implement query coalescing: where requests wait for an in-flight DB query to finish instead of launching their own
