import pytest
from app.core.database import engine, get_db_session
from sqlalchemy import text


@pytest.mark.asyncio
async def test_database_connection():
    """
    Verify that the async engine can successfully connect,
    execute a simple query, and return the connection to the pool
    """
    # Grab the generator
    session_generator = get_db_session()

    # Get the session from the generator
    session = await anext(session_generator)

    try:
        # Execute a raw SQL query
        result = await session.execute(text("SELECT 1 as is_alive"))
        row = result.fetchone()

        assert row is not None
        assert row.is_alive == 1
    finally:
        # Safely close the generator to return the connection to the pool
        try:
            await anext(session_generator)
        except StopAsyncIteration:
            pass


@pytest.mark.asyncio
async def test_engine_pool_settings():
    """Ensure the engine was created with our exact settings"""
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 10
    assert engine.pool._timeout == 30.0
