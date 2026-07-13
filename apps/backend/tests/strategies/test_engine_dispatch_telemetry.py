"""Every dispatch writes a ``strategy_dispatch_runs`` row — the record that separates
"ran and correctly traded nothing" from "never ran".

Those two are IDENTICAL in the ``orders`` table (a no-op leaves no orders to derive a run
window from), which is precisely how a zero-order momentum rebalance became undiagnosable on
2026-07-13. The engine therefore records the DISPATCH, not just its output.

The load-bearing test in this file is the LAST one: telemetry must never be able to break a
trading dispatch. If persisting a row fails, on_bar must still have run.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.ops_health import (
    DISPATCH_COMPLETED,
    DISPATCH_NOT_RUNNING,
    DISPATCH_SKIPPED_OUT_OF_SESSION,
    StrategyDispatchRun,
)
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.market.session import MarketSessionType, SessionInfo
from app.strategies.engine import StrategyEngine

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now() -> datetime:
    return datetime.now(UTC)


def _canned_bar_df() -> pd.DataFrame:
    """The shape ``StrategyContext.get_recent_bars`` actually returns: t/o/h/l/c/v columns.

    (Not open/high/low/close/volume — the engine reads ``last["t"]`` etc., so the long names
    raise KeyError inside the per-symbol guard and on_bar is never called. Getting this wrong
    makes a telemetry test pass while the trade path silently does nothing.)
    """
    ts = pd.date_range("2026-06-01 09:30", periods=3, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {
            "t": ts,
            "o": [1.0, 1.0, 1.0],
            "h": [1.0, 1.0, 1.0],
            "l": [1.0, 1.0, 1.0],
            "c": [1.0, 1.0, 1.0],
            "v": [10, 10, 10],
        }
    )


@pytest.fixture
async def eng(session_factory):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_canned_bar_df())
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=99))
    engine = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=EventBus(),
        bar_cache=bar_cache,
        indicator_computer=MagicMock(),
        order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )
    await asyncio.sleep(0)
    yield engine
    await engine.shutdown()
    scheduler.shutdown(wait=False)


async def _seed(session_factory) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(
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
            name="echo-test",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"],
            schedule="event",
            created_at=_now(),
            updated_at=_now(),
        )
        s.add(row)
        await s.commit()
        return row.id


async def _rows(session_factory) -> list[StrategyDispatchRun]:
    async with session_factory() as s:
        return list(
            (
                await s.execute(
                    select(StrategyDispatchRun).order_by(StrategyDispatchRun.id)
                )
            )
            .scalars()
            .all()
        )


async def test_successful_dispatch_records_a_row(eng, session_factory):
    sid = await _seed(session_factory)
    await eng.register(sid)

    await eng._dispatch_bar_tick(strategy_id=sid)

    rows = await _rows(session_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row.strategy_id == sid
    assert row.outcome == DISPATCH_COMPLETED
    assert row.account_id == 1
    assert row.symbols_total == 1
    assert row.symbols_with_bars == 1
    assert row.finished_at is not None
    assert row.duration_ms is not None and row.duration_ms >= 0


async def test_zero_order_dispatch_still_records_a_row(eng, session_factory):
    """THE POINT OF THE TABLE. The echo fixture submits nothing, so `orders` stays empty —
    yet the dispatch is still on the record, distinguishable from a fire that never happened.
    """
    sid = await _seed(session_factory)
    await eng.register(sid)

    await eng._dispatch_bar_tick(strategy_id=sid)

    rows = await _rows(session_factory)
    assert len(rows) == 1
    assert rows[0].outcome == DISPATCH_COMPLETED
    assert rows[0].orders_submitted == 0  # traded nothing — and we can PROVE it ran


async def test_missed_fire_leaves_no_row(eng, session_factory):
    """The converse: if the scheduler never fires, nothing is written. The ABSENCE of a row
    in an expected window is the alarm the report trips on."""
    await _seed(session_factory)
    assert await _rows(session_factory) == []


async def test_unregistered_strategy_records_not_running(eng, session_factory):
    sid = await _seed(session_factory)  # never registered → not in engine._running

    await eng._dispatch_bar_tick(strategy_id=sid)

    rows = await _rows(session_factory)
    assert len(rows) == 1
    assert rows[0].outcome == DISPATCH_NOT_RUNNING


async def test_out_of_session_dispatch_records_skip(eng, session_factory, monkeypatch):
    """A tick that the §9A market-session gate rejects is a SKIP, not a silent nothing —
    otherwise it is indistinguishable from a missed fire."""
    sid = await _seed(session_factory)
    await eng.register(sid)

    closed = SessionInfo(
        session=MarketSessionType.CLOSED,
        as_of=_now(),
        is_trading_day=False,
        is_half_day=False,
        regular_open=None,
        regular_close=None,
    )
    monkeypatch.setattr(eng._market_session, "classify", lambda *a, **k: closed)

    await eng._dispatch_bar_tick(strategy_id=sid)

    rows = await _rows(session_factory)
    assert len(rows) == 1
    assert rows[0].outcome == DISPATCH_SKIPPED_OUT_OF_SESSION


async def test_telemetry_failure_cannot_break_the_dispatch(eng, session_factory, monkeypatch):
    """LOAD-BEARING. Telemetry is an observer, never a gate.

    If recording the row raises, the strategy must STILL have received its bar. A monitoring
    feature that can halt trading is worse than no monitoring feature.
    """
    sid = await _seed(session_factory)
    running = await eng.register(sid)

    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)
    monkeypatch.setattr(
        eng,
        "_session_factory",
        MagicMock(side_effect=RuntimeError("database is locked")),
    )

    await eng._dispatch_bar_tick(strategy_id=sid)  # must not raise

    on_bar.assert_awaited_once()  # the trade path ran regardless
