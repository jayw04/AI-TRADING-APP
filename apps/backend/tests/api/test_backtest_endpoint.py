"""End-to-end tests for ``POST /api/v1/strategies/{id}/backtest``.

The happy-path test runs the real Backtester + reference RSI strategy
against the committed AAPL fixture parquets. If those fixtures aren't
present (e.g. local environment that couldn't reach Alpaca for
generation), the happy-path test skips; the range-validation tests run
unconditionally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"
FIXTURE_DAYS = ["2025-11-03", "2025-11-04", "2025-11-05"]


def _now() -> datetime:
    return datetime.now(UTC)


def _load_fixture_bars_or_skip() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for d in FIXTURE_DAYS:
        path = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not path.exists():
            pytest.skip(
                f"Fixture not present: {path}. "
                "Run apps/backend/scripts/generate_fixture_bars.py AAPL <DATE>."
            )
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


async def _seed(factory: async_sessionmaker) -> int:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
            )
        )
        row = StrategyRow(
            user_id=1,
            name="rsi-bt",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest_asyncio.fixture
async def client_and_state() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker, int]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.events.bus import get_event_bus
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    sid = await _seed(factory)

    app = create_app()
    # Test patches: bar_cache + indicator_computer go on app.state; the bus
    # is the singleton (replace .publish with an AsyncMock).
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    )
    app.state.bar_cache = bar_cache

    from app.indicators import IndicatorComputer

    app.state.indicator_computer = IndicatorComputer()

    bus = get_event_bus()
    bus.publish = AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory, sid

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


async def test_backtest_rejects_inverted_range(client_and_state) -> None:
    client, _, sid = client_and_state
    resp = await client.post(
        f"/api/v1/strategies/{sid}/backtest",
        json={
            "start": "2025-11-06T00:00:00+00:00",
            "end": "2025-11-03T00:00:00+00:00",
            "label": "backwards",
        },
    )
    assert resp.status_code == 400


async def test_backtest_rejects_long_range(client_and_state) -> None:
    client, _, sid = client_and_state
    resp = await client.post(
        f"/api/v1/strategies/{sid}/backtest",
        json={
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2026-01-01T00:00:00+00:00",
            "label": "too-long",
        },
    )
    assert resp.status_code == 400
    assert "exceeds 1 year" in resp.json()["detail"]


async def test_backtest_rejects_extra_field(client_and_state) -> None:
    client, _, sid = client_and_state
    resp = await client.post(
        f"/api/v1/strategies/{sid}/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-06T00:00:00+00:00",
            "fnord": "extra",
        },
    )
    assert resp.status_code == 422


async def test_backtest_runs_and_persists(client_and_state) -> None:
    """Happy path: real Backtester against committed AAPL fixtures."""
    bars = _load_fixture_bars_or_skip()
    client, factory, sid = client_and_state
    client._transport.app.state.bar_cache.get_bars = AsyncMock(return_value=bars)

    body = {
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-06T00:00:00+00:00",
        "label": "smoke",
        "initial_equity": "100000",
        "slippage_bps": 5.0,
        "timeframe": "1Min",
    }
    resp = await client.post(f"/api/v1/strategies/{sid}/backtest", json=body)
    assert resp.status_code == 200, resp.text
    response_body = resp.json()
    assert response_body["strategy_id"] == sid
    assert response_body["label"] == "smoke"
    assert "trade_count" in response_body["metrics"]
    assert "total_return" in response_body["metrics"]

    # Persisted row exists
    async with factory() as session:
        rows = (
            await session.execute(
                select(BacktestResult).where(BacktestResult.strategy_id == sid)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].label == "smoke"

    # backtest.completed published on the bus
    from app.events.bus import get_event_bus

    bus = get_event_bus()
    bus.publish.assert_called()
    topics = [c.args[0] for c in bus.publish.call_args_list]
    assert "backtest.completed" in topics
