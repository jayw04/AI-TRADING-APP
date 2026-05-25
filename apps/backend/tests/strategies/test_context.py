"""StrategyContext tests with a mocked OrderRouter callable."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    SignalType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk import OrderRequest
from app.strategies.context import StrategyContext


def _now() -> datetime:
    return datetime.now(UTC)


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
        session.add(
            Symbol(
                id=2, ticker="MSFT", exchange="NASDAQ",
                asset_class="us_equity", name="Microsoft", active=True,
            )
        )
        await session.commit()


def _ctx(session_factory, **overrides) -> tuple[StrategyContext, list]:
    submit_calls: list = []

    async def fake_submit(req):
        submit_calls.append(req)
        return MagicMock(id=42, status=MagicMock(value="submitted"))

    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    indicator_computer = MagicMock()

    ctx = StrategyContext(
        strategy_id=overrides.get("strategy_id", 99),
        user_id=overrides.get("user_id", 1),
        account_id=overrides.get("account_id", 1),
        symbols=overrides.get("symbols", ["AAPL"]),
        session_factory=session_factory,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        submit_order_fn=fake_submit,
    )
    return ctx, submit_calls


async def test_submit_order_stamps_source_attribution(session_factory, seeded):
    ctx, submit_calls = _ctx(session_factory)
    req = OrderRequest(
        user_id=0,
        account_id=0,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("1"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,  # caller forgot to set STRATEGY
    )
    await ctx.submit_order(req)

    assert len(submit_calls) == 1
    sent = submit_calls[0]
    assert sent.source_type == OrderSourceType.STRATEGY
    assert sent.source_id == "99"
    assert sent.user_id == 1
    assert sent.account_id == 1


async def test_submit_order_preserves_existing_attribution(session_factory, seeded):
    """If the caller already set STRATEGY source_id, don't clobber it."""
    ctx, submit_calls = _ctx(session_factory)
    req = OrderRequest(
        user_id=1,
        account_id=1,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("1"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.STRATEGY,
        source_id="custom-source-id",
    )
    await ctx.submit_order(req)
    assert submit_calls[0].source_id == "custom-source-id"


async def test_get_positions_filtered_by_strategy_symbols(session_factory, seeded):
    async with session_factory() as session:
        # AAPL is in the strategy's universe; MSFT is not.
        session.add(
            Position(
                user_id=1, account_id=1, symbol_id=1,
                qty=Decimal("10"), avg_entry_price=Decimal("190"), side="long",
                market_value=Decimal("1900"), cost_basis=Decimal("1900"),
                unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
                updated_at=_now(),
            )
        )
        session.add(
            Position(
                user_id=1, account_id=1, symbol_id=2,
                qty=Decimal("5"), avg_entry_price=Decimal("400"), side="long",
                market_value=Decimal("2000"), cost_basis=Decimal("2000"),
                unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
                updated_at=_now(),
            )
        )
        await session.commit()

    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    positions = await ctx.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol_id == 1


async def test_log_signal_persists_row(session_factory, seeded):
    ctx, _ = _ctx(session_factory)
    sig_id = await ctx.log_signal("AAPL", SignalType.ENTRY, payload={"rsi": 28.5})
    assert sig_id > 0

    async with session_factory() as session:
        rows = (await session.execute(select(Signal))).scalars().all()
        assert len(rows) == 1
        assert rows[0].type == SignalType.ENTRY
        assert rows[0].strategy_id == 99
        assert rows[0].payload_json == {"rsi": 28.5}


async def test_log_signal_returns_zero_for_unknown_symbol(session_factory, seeded):
    """Unknown ticker returns 0 instead of raising — a buggy strategy
    shouldn't crash the engine."""
    ctx, _ = _ctx(session_factory, symbols=["AAPL", "ZZZZ"])
    sig_id = await ctx.log_signal("ZZZZ", SignalType.INFO)
    assert sig_id == 0


async def test_get_recent_bars_returns_empty_for_unauthorized_symbol(
    session_factory, seeded
):
    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    df = await ctx.get_recent_bars("MSFT", "1Min", n=10)
    assert df.empty


async def test_log_signal_publishes_on_bus_after_commit(session_factory, seeded):
    """When a bus is passed, log_signal must publish ``signal.new`` AFTER the
    DB commit so subscribers reading back from the DB see the row."""
    bus = MagicMock()
    bus.publish = AsyncMock()

    async def fake_submit(req):
        return MagicMock()

    ctx = StrategyContext(
        strategy_id=99,
        user_id=1,
        account_id=1,
        symbols=["AAPL"],
        session_factory=session_factory,
        bar_cache=MagicMock(),
        indicator_computer=MagicMock(),
        submit_order_fn=fake_submit,
        bus=bus,
    )
    sig_id = await ctx.log_signal("AAPL", SignalType.ENTRY, payload={"rsi": 28.5})
    assert sig_id > 0

    bus.publish.assert_awaited_once()
    topic, payload = bus.publish.await_args.args
    assert topic == "signal.new"
    assert payload["signal_id"] == sig_id
    assert payload["strategy_id"] == 99
    assert payload["symbol"] == "AAPL"
    assert payload["type"] == "entry"
    assert payload["payload"] == {"rsi": 28.5}
    assert "received_at" in payload


async def test_log_signal_swallows_bus_failure(session_factory, seeded):
    """A publish error must NOT prevent the caller from getting the signal id —
    the DB row is the source of truth, the bus is best-effort."""
    bus = MagicMock()
    bus.publish = AsyncMock(side_effect=RuntimeError("bus down"))

    async def fake_submit(req):
        return MagicMock()

    ctx = StrategyContext(
        strategy_id=99,
        user_id=1,
        account_id=1,
        symbols=["AAPL"],
        session_factory=session_factory,
        bar_cache=MagicMock(),
        indicator_computer=MagicMock(),
        submit_order_fn=fake_submit,
        bus=bus,
    )
    sig_id = await ctx.log_signal("AAPL", SignalType.INFO)
    assert sig_id > 0  # row is still persisted
