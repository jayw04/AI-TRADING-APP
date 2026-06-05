"""P6b §4.5 (ADR 0015) — the engine resolves the dispatch account by STATUS:
LIVE → live account (and stays LIVE), PAPER → paper, LIVE-without-live-account
→ ERROR.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies.engine import StrategyEngine
from app.strategies.loader import StrategyLoadError

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now() -> datetime:
    return datetime.now(UTC)


def _canned_bar_df() -> pd.DataFrame:
    idx = pd.date_range("2026-06-01 09:30", periods=3, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {"open": [1.0, 1, 1], "high": [1.0, 1, 1], "low": [1.0, 1, 1],
         "close": [1.0, 1, 1], "volume": [10, 10, 10]},
        index=idx,
    )


@pytest.fixture
async def eng(session_factory):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_canned_bar_df())
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=99))
    engine = StrategyEngine(
        scheduler=scheduler, session_factory=session_factory, bus=bus,
        bar_cache=bar_cache, indicator_computer=MagicMock(),
        order_router=order_router, strategies_root=FIXTURES_ROOT,
    )
    await asyncio.sleep(0)
    yield engine
    await engine.shutdown()
    scheduler.shutdown(wait=False)


async def _seed(session_factory, *, status: StrategyStatus, with_live: bool) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        if with_live:
            s.add(Account(id=2, user_id=1, broker="alpaca", mode=AccountMode.live, label="L"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                     asset_class="us_equity", name="Apple", active=True))
        row = StrategyRow(
            user_id=1, name="echo-test", version="0.0.1", type=StrategyType.PYTHON,
            status=status, code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"}, symbols_json=["AAPL"],
            schedule="event", created_at=_now(), updated_at=_now(),
        )
        s.add(row)
        await s.commit()
        return row.id


async def test_paper_strategy_binds_paper_account(eng, session_factory):
    sid = await _seed(session_factory, status=StrategyStatus.IDLE, with_live=True)
    running = await eng.register(sid)
    assert running.instance.ctx.account_id == 1  # paper


async def test_live_strategy_binds_live_account_and_stays_live(eng, session_factory):
    sid = await _seed(session_factory, status=StrategyStatus.LIVE, with_live=True)
    running = await eng.register(sid)
    assert running.instance.ctx.account_id == 2  # live
    async with session_factory() as s:
        row = await s.get(StrategyRow, sid)
    assert row.status == StrategyStatus.LIVE  # not flipped to PAPER


async def test_live_strategy_without_live_account_errors(eng, session_factory):
    sid = await _seed(session_factory, status=StrategyStatus.LIVE, with_live=False)
    with pytest.raises(StrategyLoadError, match="no live account"):
        await eng.register(sid)
    async with session_factory() as s:
        row = await s.get(StrategyRow, sid)
    assert row.status == StrategyStatus.ERROR
