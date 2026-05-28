"""StrategyEngine: register / dispatch / error-contain / unregister.

Real session, real event bus, real APScheduler. The order router is
mocked and the bar cache is a stub returning canned bars. We never
schedule a real cron tick — strategies are registered with
``schedule="event"`` so the test runs deterministically.
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
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies import StrategyEngine
from app.strategies.loader import StrategyLoadError

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now() -> datetime:
    return datetime.now(UTC)


def _canned_bar_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "t": _now(),
                "o": 190.0,
                "h": 190.5,
                "l": 189.5,
                "c": 190.2,
                "v": 12345,
            }
        ]
    )


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1, ticker="AAPL", exchange="NASDAQ",
                asset_class="us_equity", name="Apple", active=True,
            )
        )
        await session.commit()


@pytest.fixture
async def engine(session_factory, seeded):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()

    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_canned_bar_df())
    indicator_computer = MagicMock()
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=99))

    eng = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=bus,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )
    # Yield control briefly so the engine's bus-consumer tasks register
    # their async subscriptions before the test starts publishing.
    await asyncio.sleep(0)

    yield eng, bus, order_router

    await eng.shutdown()
    scheduler.shutdown(wait=False)


async def _register_echo_strategy(session_factory) -> int:
    """Insert an echo_strategy row pointing at the fixture file.

    schedule='event' keeps the test deterministic — no cron firing.
    """
    async with session_factory() as session:
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
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def test_register_transitions_to_paper_and_opens_run(engine, session_factory):
    eng, _bus, _router = engine
    sid = await _register_echo_strategy(session_factory)

    running = await eng.register(sid)
    assert running.strategy_id == sid
    assert running.instance.init_called is True

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.PAPER
        runs = (
            await session.execute(
                select(StrategyRun).where(StrategyRun.strategy_id == sid)
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].ended_at is None


async def test_register_is_idempotent(engine, session_factory):
    eng, _, _ = engine
    sid = await _register_echo_strategy(session_factory)
    first = await eng.register(sid)
    second = await eng.register(sid)
    assert first is second


async def test_unregister_calls_on_shutdown_and_closes_run(engine, session_factory):
    eng, _, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await eng.unregister(sid, reason="test_done")

    assert instance.shutdown_called is True
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.IDLE
        runs = (
            await session.execute(
                select(StrategyRun).where(StrategyRun.strategy_id == sid)
            )
        ).scalars().all()
        assert runs[0].ended_at is not None


async def test_unregister_unknown_strategy_is_noop(engine, session_factory):
    eng, _, _ = engine
    # No registration, no row — must not raise.
    await eng.unregister(99999, reason="never_registered")


async def test_fill_event_routes_to_correct_strategy(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await bus.publish(
        "fill.created",
        {
            "source_type": "strategy",
            "source_id": str(sid),
            "fill_id": 1,
            "order_id": 100,
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "price": "190.50",
            "filled_at": _now(),
        },
    )
    # Yield to the consumer task so it can drain the queue.
    await asyncio.sleep(0.05)

    assert len(instance.fills_seen) == 1
    assert instance.fills_seen[0].symbol == "AAPL"
    assert str(instance.fills_seen[0].price) == "190.50"


async def test_fill_for_other_source_ignored(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await bus.publish(
        "fill.created",
        {
            "source_type": "manual",
            "order_id": 999,
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "price": "190.50",
        },
    )
    await asyncio.sleep(0.05)

    assert len(instance.fills_seen) == 0


async def test_user_exception_marks_error_and_unregisters(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)

    async def boom(_fill):
        raise RuntimeError("synthetic failure")

    running.instance.on_fill = boom  # type: ignore[method-assign]

    await bus.publish(
        "fill.created",
        {
            "source_type": "strategy",
            "source_id": str(sid),
            "fill_id": 1,
            "order_id": 100,
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "price": "190.50",
        },
    )
    await asyncio.sleep(0.05)

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.ERROR
        assert row.error_text is not None
        assert "synthetic failure" in row.error_text

    # The engine should have unregistered the broken strategy.
    assert sid not in eng._running


async def test_register_pine_strategy_is_rejected_in_p2(engine, session_factory):
    """PINE enum exists in the DB but the engine refuses to dispatch."""
    eng, _, _ = engine
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1,
            name="pine-not-yet",
            version="0.0.1",
            type=StrategyType.PINE,
            status=StrategyStatus.IDLE,
            code_path=None,
            params_json={},
            symbols_json=["AAPL"],
            schedule="event",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        pine_sid = row.id

    with pytest.raises(StrategyLoadError, match="only PYTHON is dispatched"):
        await eng.register(pine_sid)


# ---------- P4 §8: dispatch_event_bar + start/stop_event_fallback ----------


async def _register_cron_echo_strategy(session_factory) -> int:
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1,
            name="echo-cron",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"],
            schedule="*/5 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


def _streamed_bar(symbol: str = "AAPL"):
    from decimal import Decimal

    from app.services.bar_stream import StreamedBar

    return StreamedBar(
        symbol=symbol,
        ts=_now(),
        open=Decimal("190"),
        high=Decimal("191"),
        low=Decimal("189"),
        close=Decimal("190.5"),
        volume=Decimal("12345"),
    )


async def test_dispatch_event_bar_fires_event_strategy(engine, session_factory):
    """An event-scheduled strategy with the matching symbol receives on_bar."""
    eng, _, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await eng.dispatch_event_bar(symbol="AAPL", bar=_streamed_bar("AAPL"))
    assert len(instance.bars_seen) == 1
    assert instance.bars_seen[0].symbol == "AAPL"
    assert instance.bars_seen[0].c == 190.5


async def test_dispatch_event_bar_ignores_cron_strategy(engine, session_factory):
    """A cron strategy on the same symbol must NOT receive the event bar."""
    eng, _, _ = engine
    sid = await _register_cron_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await eng.dispatch_event_bar(symbol="AAPL", bar=_streamed_bar("AAPL"))
    assert instance.bars_seen == []


async def test_dispatch_event_bar_ignores_unmatched_symbol(engine, session_factory):
    """Bar for a symbol the strategy doesn't list is a no-op."""
    eng, _, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await eng.dispatch_event_bar(symbol="ZZZZ", bar=_streamed_bar("ZZZZ"))
    assert instance.bars_seen == []


async def test_start_and_stop_event_fallback_registers_with_scheduler(engine):
    """The fallback API schedules / removes a job on the engine's scheduler."""
    eng, _, _ = engine

    job_id = await eng.start_event_fallback(interval_seconds=60)
    assert job_id.startswith("event_fallback_")
    assert eng._scheduler.get_job(job_id) is not None

    await eng.stop_event_fallback(job_id)
    assert eng._scheduler.get_job(job_id) is None


async def test_register_notifies_bar_stream_service(engine, session_factory):
    """register() calls on_strategies_changed() if a service is wired."""
    eng, _, _ = engine
    notify_calls = []

    class FakeService:
        async def on_strategies_changed(self):
            notify_calls.append(True)

    eng.set_bar_stream_service(FakeService())
    sid = await _register_echo_strategy(session_factory)
    await eng.register(sid)
    assert notify_calls == [True]

    await eng.unregister(sid, reason="test_done")
    assert notify_calls == [True, True]
