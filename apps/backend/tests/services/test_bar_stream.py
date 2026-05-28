"""BarStreamService — unit tests with a fake adapter (P4 §8).

Covers symbol-set computation, diff-based subscribe/unsubscribe,
on_bar dispatch, status publishing, and the reconnect/fallback path.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import update

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.services.bar_stream import BarStreamService, StreamedBar


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            StrategyRow(
                id=1,
                user_id=1,
                name="event-strat-1",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/rsi.py",
                params_json={},
                symbols_json=["AAPL", "MSFT"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            StrategyRow(
                id=2,
                user_id=1,
                name="cron-strat",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/rsi.py",
                params_json={},
                symbols_json=["NVDA"],
                schedule="*/5 * * * *",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            StrategyRow(
                id=3,
                user_id=1,
                name="event-strat-idle",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.IDLE,
                code_path="examples/rsi.py",
                params_json={},
                symbols_json=["GOOGL"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()


@pytest.fixture
def fake_adapter() -> MagicMock:
    a = MagicMock()
    a.connect = AsyncMock()
    a.disconnect = AsyncMock()
    a.subscribe = AsyncMock()
    a.unsubscribe = AsyncMock()
    a.run_until_disconnected = AsyncMock()
    return a


@pytest.fixture
def service(session_factory, fake_adapter):
    bus = MagicMock()
    bus.publish = AsyncMock()
    engine = MagicMock()
    engine.dispatch_event_bar = AsyncMock()
    engine.start_event_fallback = AsyncMock(return_value="fallback-job-id")
    engine.stop_event_fallback = AsyncMock()
    bar_cache = MagicMock()
    bar_cache.append_streamed_bar = AsyncMock()
    return BarStreamService(
        session_factory=session_factory,
        engine=engine,
        bar_cache=bar_cache,
        bus=bus,
        adapter=fake_adapter,
    )


def _bar(symbol: str = "AAPL") -> StreamedBar:
    return StreamedBar(
        symbol=symbol,
        ts=_now(),
        open=Decimal("190"),
        high=Decimal("191"),
        low=Decimal("189"),
        close=Decimal("190.5"),
        volume=Decimal("12345"),
    )


async def test_desired_symbols_union_of_event_active_strategies(service, seeded):
    """Only event-scheduled, active strategies contribute. Cron and idle excluded."""
    desired = await service._compute_desired_symbols()
    assert desired == {"AAPL", "MSFT"}


async def test_on_strategies_changed_subscribes_when_connected(
    service, seeded, fake_adapter
):
    service._connected = True
    await service.on_strategies_changed()
    fake_adapter.subscribe.assert_called_once()
    subscribed = set(fake_adapter.subscribe.call_args.args[0])
    assert subscribed == {"AAPL", "MSFT"}


async def test_on_strategies_changed_only_diffs(
    service, seeded, fake_adapter, session_factory
):
    """Adding one new event strategy with a new symbol should only
    subscribe to the new symbol — no churn on existing subs."""
    service._connected = True
    service._subscribed_symbols = {"AAPL", "MSFT"}

    async with session_factory() as session:
        session.add(
            StrategyRow(
                id=4,
                user_id=1,
                name="event-strat-tsla",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="examples/rsi.py",
                params_json={},
                symbols_json=["TSLA"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()

    await service.on_strategies_changed()
    fake_adapter.subscribe.assert_called()
    new_subs = set(fake_adapter.subscribe.call_args.args[0])
    assert new_subs == {"TSLA"}
    fake_adapter.unsubscribe.assert_not_called()


async def test_on_strategies_changed_unsubscribes_when_strategy_stops(
    service, seeded, fake_adapter, session_factory
):
    """When the last event strategy referencing a symbol stops, the
    symbol is unsubscribed."""
    service._connected = True
    service._subscribed_symbols = {"AAPL", "MSFT"}

    async with session_factory() as session:
        await session.execute(
            update(StrategyRow)
            .where(StrategyRow.id == 1)
            .values(status=StrategyStatus.IDLE)
        )
        await session.commit()

    await service.on_strategies_changed()
    fake_adapter.unsubscribe.assert_called()
    unsubscribed = set(fake_adapter.unsubscribe.call_args.args[0])
    assert unsubscribed == {"AAPL", "MSFT"}


async def test_on_strategies_changed_disconnected_just_remembers(
    service, seeded, fake_adapter
):
    """While disconnected, on_strategies_changed updates the in-memory set
    but doesn't call the adapter."""
    service._connected = False
    await service.on_strategies_changed()
    assert service._subscribed_symbols == {"AAPL", "MSFT"}
    fake_adapter.subscribe.assert_not_called()
    fake_adapter.unsubscribe.assert_not_called()


async def test_on_bar_async_updates_cache_and_dispatches(service):
    bar = _bar()
    await service._on_bar_async(bar)
    service._bar_cache.append_streamed_bar.assert_called_once_with("AAPL", bar)
    service._engine.dispatch_event_bar.assert_called_once()
    args = service._engine.dispatch_event_bar.call_args.kwargs
    assert args["symbol"] == "AAPL"
    assert args["bar"] is bar
    # Publishes a bar.received bus event (not WS-routed by gateway).
    topics = [c.args[0] for c in service._bus.publish.call_args_list]
    assert "bar.received" in topics


async def test_on_bar_async_continues_on_dispatch_failure(service):
    """A dispatch failure must not stop cache-append from running first."""
    service._engine.dispatch_event_bar.side_effect = RuntimeError("downstream blew up")
    await service._on_bar_async(_bar())
    service._bar_cache.append_streamed_bar.assert_called_once()


async def test_publish_status_emits_system_event(service):
    await service._publish_status(True, reason="connected")
    service._bus.publish.assert_called()
    args = service._bus.publish.call_args.args
    assert args[0] == "system.bar_stream_status"
    assert args[1]["connected"] is True
    assert args[1]["reason"] == "connected"


async def test_disconnect_kicks_off_fallback(service, fake_adapter):
    """When _connect_and_run raises, status publishes False and the
    fallback job activates."""
    fake_adapter.connect = AsyncMock()
    fake_adapter.run_until_disconnected = AsyncMock(
        side_effect=RuntimeError("ws closed")
    )

    async def trip():
        await asyncio.sleep(0.05)
        service._stop_event.set()

    asyncio.create_task(trip())
    await service._run()

    service._engine.start_event_fallback.assert_called()
    publish_topics = [c.args[0] for c in service._bus.publish.call_args_list]
    assert "system.bar_stream_status" in publish_topics
    # One of the status publishes carries connected=False
    statuses = [
        c.args[1]
        for c in service._bus.publish.call_args_list
        if c.args[0] == "system.bar_stream_status"
    ]
    assert any(s["connected"] is False for s in statuses)


async def test_start_stop_lifecycle(service, fake_adapter):
    """Start spawns the loop; stop tears it down and disconnects."""

    async def _wait_for_stop(*, stop_event: asyncio.Event) -> None:
        await stop_event.wait()

    fake_adapter.run_until_disconnected = AsyncMock(side_effect=_wait_for_stop)
    await service.start()
    assert service._task is not None
    # Yield so the loop reaches run_until_disconnected.
    await asyncio.sleep(0.05)
    await service.stop()
    assert service._task is None
    fake_adapter.disconnect.assert_called()
    # A final disconnected status must have been published.
    topics = [c.args[0] for c in service._bus.publish.call_args_list]
    assert "system.bar_stream_status" in topics
