"""Smoke tests for ``GET /api/v1/indicators/{symbol}``.

BarCache is mocked; we exercise the endpoint's request parsing, response
shape, and the multi-output indicator expansion (MACD → 3 series, BB → 3
series). IndicatorComputer is the real thing — keeping it real catches
contract drift between the endpoint and the computer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.indicators import IndicatorComputer


def _bars(n: int = 250) -> pd.DataFrame:
    start = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    return pd.DataFrame(
        [
            {
                "t": start + timedelta(minutes=i),
                "o": 100 + i * 0.01,
                "h": 100.5 + i * 0.01,
                "l": 99.5 + i * 0.01,
                "c": 100 + i * 0.01,
                "v": 1000 + i,
            }
            for i in range(n)
        ]
    )


@pytest_asyncio.fixture
async def client_with_indicators():
    """Test client with a mocked BarCache + real IndicatorComputer."""
    from app.config import get_settings
    from app.db import models  # noqa: F401 — register models on Base.metadata
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
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(return_value=_bars())
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, app

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_endpoint_returns_core_set_with_multi_output_expansion(
    client_with_indicators,
):
    ac, _ = client_with_indicators
    resp = await ac.get("/api/v1/indicators/AAPL?timeframe=1Min")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["timeframe"] == "1Min"

    names = [s["name"] for s in body["indicators"]]
    # Single-output indicators present
    assert "RSI14" in names
    assert "SMA20" in names
    assert "ATR14" in names
    # Multi-output expanded
    assert "MACD.macd" in names
    assert "MACD.signal" in names
    assert "MACD.hist" in names
    assert "BB.bb_lower" in names
    assert "BB.bb_mid" in names
    assert "BB.bb_upper" in names


async def test_endpoint_filters_by_names(client_with_indicators):
    ac, _ = client_with_indicators
    resp = await ac.get("/api/v1/indicators/AAPL?names=RSI14,SMA20")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["indicators"]}
    assert names == {"RSI14", "SMA20"}


async def test_endpoint_rejects_unknown_indicator(client_with_indicators):
    ac, _ = client_with_indicators
    resp = await ac.get("/api/v1/indicators/AAPL?names=FNORD,RSI14")
    assert resp.status_code == 400
    assert "FNORD" in resp.text


async def test_endpoint_returns_503_when_not_wired():
    """If the lifespan didn't wire the bar_cache (e.g. alpaca_startup_enabled=0
    in tests), the endpoint 503s rather than crashing on app.state access."""
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
    # Deliberately do NOT set app.state.bar_cache / indicator_computer.
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/indicators/AAPL")
        assert resp.status_code == 503
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


async def test_endpoint_handles_empty_bars():
    """When BarCache returns an empty frame (e.g. all requested days are
    empty markers), the endpoint returns 200 with no indicators rather than
    crashing on ``iloc[-1]``."""
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
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    )
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/indicators/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_bar_ts"] is None
        assert body["indicators"] == []
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()
