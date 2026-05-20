import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("WORKBENCH_DB_URL", "sqlite+aiosqlite:///./data/workbench.test.sqlite")
os.environ.setdefault("WORKBENCH_LOG_LEVEL", "WARNING")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
