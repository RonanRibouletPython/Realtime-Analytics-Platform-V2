from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
import uvicorn
from app.api.metrics import router as metrics_router
from app.core.database import Base, engine, get_db
from app.core.kafka_producer import check_kafka_health, flush_producer
from app.core.logging import setup_logging
from app.core.redis_client import check_redis_health, get_redis
from app.core.settings import settings
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    setup_logging()
    logger.info("ingestion_service_starting", env=settings.ENV)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db_tables_ready")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("ingestion_service_stopping")
    flush_producer()  # drain Kafka buffer before exit
    await engine.dispose()  # return DB connections to pool


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    openapi_url=f"/{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"/{settings.API_V1_PREFIX}/docs",
)

app.include_router(metrics_router, prefix=f"/{settings.API_V1_PREFIX}")


# ── Health endpoints ──────────────────────────────────────────────────────────
# Each component gets its own endpoint so k8s / load balancers can probe
# individual dependencies without getting a false-positive from a combined check.


@app.get("/health", tags=["health"])
async def health():
    """Basic liveness probe — is the process alive?"""
    return {"status": "healthy", "service": "ingestion", "env": settings.ENV}


@app.get("/health/db", tags=["health"])
async def health_db(db: AsyncSession = Depends(get_db)):
    """Readiness probe — can we reach the database?"""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "component": "database"}
    except Exception as e:
        logger.error("health_db_failed", error=str(e))
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "component": "database"}
        )


@app.get("/health/redis", tags=["health"])
async def health_redis(redis_client: redis.Redis = Depends(get_redis)):
    """Readiness probe — can we reach Redis?"""
    try:
        await check_redis_health()
        return {"status": "healthy", "component": "redis"}
    except Exception as e:
        logger.error("health_redis_failed", error=str(e))
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "component": "redis"}
        )


@app.get("/health/kafka", tags=["health"])
async def health_kafka():
    """Readiness probe — can we reach the Kafka broker?"""
    try:
        await check_kafka_health()
        return {"status": "healthy", "component": "kafka"}
    except Exception as e:
        logger.error("health_kafka_failed", error=str(e))
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "component": "kafka"}
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
