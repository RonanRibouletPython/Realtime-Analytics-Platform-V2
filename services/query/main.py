from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.endpoints import router as api_router
from app.core.cache import redis_client
from app.core.database import engine
from app.core.settings import get_settings

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

# CORS Middleware for Frontend Dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
