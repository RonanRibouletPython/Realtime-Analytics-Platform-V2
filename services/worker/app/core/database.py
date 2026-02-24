from app.core.settings import settings
from shared.models.metric import Base  # noqa: F401 — re-exported for consumers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    settings.DB_URL,
    echo=False,  # worker is high-throughput — SQL logging is too noisy
    pool_pre_ping=True,
    pool_size=5,  # one per concurrent message batch is plenty
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
