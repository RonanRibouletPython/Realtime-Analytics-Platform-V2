from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Prometheus metrics
# Defined at module level → registered once on import → process-global singletons
DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds", "Time spent executing database queries", ["operation"]
)
DB_ERRORS = Counter(
    "db_errors_total", "Total database errors encountered", ["error_type"]
)

# Connection Pool Init
engine = create_async_engine(
    str(settings.database_url),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    pool_pre_ping=True,  # Checks if connection is alive before using it
    echo=settings.log_level == "DEBUG",
)

# Session factory with context manager
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency for providing an async database session
    Ensures the session is cleanly closed (returned to the pool) after the request
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception as e:
            # Observability: Track exactly what type of DB error occurred
            DB_ERRORS.labels(error_type=type(e).__name__).inc()
            logger.error(
                "database_session_error", error=str(e), error_type=type(e).__name__
            )
            raise


@asynccontextmanager
async def get_db_connection():
    """
    Context manager for background tasks/workers outside of FastAPI requests
    """
    async with AsyncSessionFactory() as session:
        yield session
