import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# In-memory SQLite for tests: no filesystem dependency (`./data/` is gitignored
# and absent in a fresh CI checkout). None of the P0 tests need persistent
# tables — they exercise routing, auth, WS heartbeats, and the SELECT-1
# healthcheck path, all of which work against `:memory:`.
os.environ.setdefault("WORKBENCH_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WORKBENCH_LOG_LEVEL", "WARNING")
# Tests don't have (and shouldn't use) real Alpaca creds, and shouldn't touch
# the broker network. Disable the lifespan's adapter+scheduler block.
os.environ.setdefault("WORKBENCH_ALPACA_STARTUP_ENABLED", "0")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    """A per-test async session factory bound to a fresh in-memory SQLite DB.

    Schema is created via Base.metadata.create_all so service tests can write
    to real tables without depending on alembic migrations running first.
    """
    # Import inside the fixture so `app.db.models` is fully populated before
    # `Base.metadata.create_all` is called.
    from app.db import models  # noqa: F401 - register models on Base.metadata
    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
