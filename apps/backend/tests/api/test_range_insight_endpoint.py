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


async def _seed_range_backtest(symbol: str, *, win_rate: float, sharpe: float, n: int) -> None:
    """Insert an IDLE range strategy on ``symbol`` plus a BacktestResult carrying the metrics."""
    from datetime import UTC, datetime

    from app.db.enums import StrategyStatus, StrategyType
    from app.db.models.backtest_result import BacktestResult
    from app.db.models.strategy import Strategy as StrategyRow
    from app.db.session import get_sessionmaker

    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        strat = StrategyRow(
            user_id=1,
            name=f"Range Trader {symbol}",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="templates/range_trader.py",
            params_json={},
            symbols_json=[symbol],
            schedule="*/5 * * * *",
            created_at=now,
            updated_at=now,
        )
        session.add(strat)
        await session.flush()
        session.add(
            BacktestResult(
                strategy_id=strat.id,
                label="default",
                params_json={},
                metrics_json={"win_rate": win_rate, "sharpe_ratio": sharpe, "trade_count": n},
                equity_curve_json=[],
                trades_json=[],
                range_start=now,
                range_end=now,
                created_at=now,
            )
        )
        await session.commit()


async def test_candidates_rank_by_backtest_win_rate(ri_app) -> None:
    """AAPL (62% / +0.46) outranks NVDA (25% / -1.12) even though both look structurally
    identical to the fake bar cache — realized win rate leads the ranking (design §8.4)."""
    client, app = ri_app
    app.state.bar_cache = _FakeBarCache()
    await _seed_range_backtest("AAPL", win_rate=0.62, sharpe=0.46, n=24)
    await _seed_range_backtest("NVDA", win_rate=0.25, sharpe=-1.12, n=20)

    r = await client.get("/api/v1/range-insight/candidates?symbols=NVDA,AAPL")
    assert r.status_code == 200
    cands = r.json()["candidates"]
    by_symbol = {c["symbol"]: c for c in cands}
    assert by_symbol["AAPL"]["rank"] < by_symbol["NVDA"]["rank"]
    assert [c["symbol"] for c in cands][:2] == ["AAPL", "NVDA"]
    aapl = by_symbol["AAPL"]
    assert aapl["backtested"] is True
    assert aapl["win_rate"] == 0.62 and aapl["sharpe"] == 0.46 and aapl["n_trades"] == 24
