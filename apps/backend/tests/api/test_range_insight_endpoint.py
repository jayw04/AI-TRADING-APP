"""P8 §5 — GET /api/v1/range-insight/{symbol} (shape + 503)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _bars() -> pd.DataFrame:
    end = pd.Timestamp(2026, 6, 5, 13, tz="UTC")
    dates = [end - pd.Timedelta(days=24 - i) for i in range(25)]
    return pd.DataFrame(
        {
            "t": dates,
            "o": [100.0] * 25,
            "h": [103.0] * 25,
            "l": [98.0] * 25,
            "c": [100.0] * 25,
            "v": [1_000_000] * 25,
        }
    )


class _FakeBarCache:
    async def get_bars(self, symbol: str, tf: str, start: Any, end: Any) -> pd.DataFrame:
        return _bars()


@pytest_asyncio.fixture
async def ri_app() -> AsyncIterator[tuple[AsyncClient, Any]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, app

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_range_insight_shape(ri_app) -> None:
    client, app = ri_app
    app.state.bar_cache = _FakeBarCache()
    r = await client.get("/api/v1/range-insight/aapl")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["status"] == "ok"
    assert body["support"] == 98.0
    assert body["resistance"] == 103.0
    assert body["classification"] == "range_bound"
    assert body["disclaimer"]


async def test_range_insight_503_without_bar_cache(ri_app) -> None:
    client, app = ri_app
    app.state.bar_cache = None
    r = await client.get("/api/v1/range-insight/AAPL")
    assert r.status_code == 503
