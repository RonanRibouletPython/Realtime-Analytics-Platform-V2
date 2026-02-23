# Re-export Base from shared so main.py can call Base.metadata.create_all
# without importing from two different places.
from shared.models.metric import Base  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import settings

engine = create_async_engine(
    settings.DB_URL,
    echo=(settings.ENV == "development"),
    pool_pre_ping=True,  # drops stale connections before using them
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields a session per request.
    Commits on success, rolls back on any exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
