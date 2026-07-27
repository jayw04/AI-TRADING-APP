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
    OrderStatus,
    OrderType,
    SignalType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk import OrderRequest
from app.services.day_change_basis import BROKER_LAST_EQUITY
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


async def test_log_signal_portfolio_sentinel_persists(session_factory, seeded):
    """The "PORTFOLIO" portfolio-level sentinel is authorized (not a universe
    violation) and persists against a lazily-created non-tradeable sentinel symbol,
    so overlay/liquidation decisions are recorded rather than dropped with a
    spurious ``strategy_logged_unauthorized_signal`` warning."""
    from app.strategies.context import PORTFOLIO_SIGNAL_SYMBOL

    ctx, _ = _ctx(session_factory, symbols=["AAPL"])  # PORTFOLIO is NOT in symbols
    sig_id = await ctx.log_signal(
        PORTFOLIO_SIGNAL_SYMBOL, SignalType.INFO, payload={"gross": 0.8}
    )
    assert sig_id > 0

    async with session_factory() as session:
        sym = (
            await session.execute(
                select(Symbol).where(Symbol.ticker == PORTFOLIO_SIGNAL_SYMBOL)
            )
        ).scalars().first()
        assert sym is not None and sym.active is False
        sig = (
            await session.execute(select(Signal).where(Signal.symbol_id == sym.id))
        ).scalars().first()
        assert sig is not None and sig.payload_json == {"gross": 0.8}

    # A second call reuses the existing sentinel — no duplicate symbol row.
    assert await ctx.log_signal(PORTFOLIO_SIGNAL_SYMBOL, SignalType.EXIT) > 0
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Symbol).where(Symbol.ticker == PORTFOLIO_SIGNAL_SYMBOL)
            )
        ).scalars().all()
        assert len(rows) == 1


async def test_get_recent_bars_returns_empty_for_unauthorized_symbol(
    session_factory, seeded
):
    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    df = await ctx.get_recent_bars("MSFT", "1Min", n=10)
    assert df.empty


async def test_get_recent_bars_daily_window_scales_with_n(session_factory, seeded):
    """★ get_recent_bars('1Day', n) must fetch a window covering >= n trading days. A fixed
    1-year window silently capped large-n daily requests at ~251 bars regardless of cache
    depth, which starved the combined-book cross-asset sleeve (needs ~338 trading days)."""
    from datetime import UTC, datetime

    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    ctx._bar_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    )
    await ctx.get_recent_bars("AAPL", "1Day", n=338)
    start = ctx._bar_cache.get_bars.call_args.args[2]  # (symbol, timeframe, start, end)
    span_days = (datetime.now(UTC) - start).days
    assert span_days >= int(338 * 1.4), f"daily window only {span_days}d — too short for n=338"


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


# ---- P9 §4: live account equity accessor ----

async def test_get_account_equity_returns_snapshot(session_factory, seeded):
    async with session_factory() as session:
        session.add(
            AccountState(
                day_change_basis=BROKER_LAST_EQUITY,
                account_id=1, cash=Decimal("9000"), equity=Decimal("10500.50"),
                last_equity=Decimal("10000"), buying_power=Decimal("38000"),
                portfolio_value=Decimal("10500.50"), status="ACTIVE",
                updated_at=datetime(2026, 6, 14, tzinfo=UTC),
            )
        )
        await session.commit()
    ctx, _ = _ctx(session_factory)
    assert await ctx.get_account_equity() == Decimal("10500.50")


async def test_get_account_equity_none_without_snapshot(session_factory, seeded):
    ctx, _ = _ctx(session_factory)  # no AccountState row seeded
    assert await ctx.get_account_equity() is None


async def _add_order(
    session_factory, *, symbol_id=1, qty="10", side=OrderSide.BUY,
    status=OrderStatus.SUBMITTED, source_id="99",
    source_type=OrderSourceType.STRATEGY, tag="x",
):
    async with session_factory() as session:
        session.add(
            Order(
                user_id=1, account_id=1, symbol_id=symbol_id,
                client_order_id=f"ctx-{tag}",
                side=side, qty=Decimal(qty), type=OrderType.MARKET,
                tif=TimeInForce.DAY, status=status,
                source_type=source_type, source_id=source_id,
                created_at=_now(), updated_at=_now(),
            )
        )
        await session.commit()


async def test_pending_buy_qty_sums_inflight_own_strategy(session_factory, seeded):
    """Sums this strategy's own non-terminal BUY qty per ticker — and excludes
    filled/terminal orders, sells, other strategies, and out-of-universe names."""
    await _add_order(session_factory, symbol_id=1, qty="6", tag="a")   # counts
    await _add_order(session_factory, symbol_id=1, qty="4", tag="b")   # counts → AAPL 10
    await _add_order(session_factory, symbol_id=1, qty="99",
                     status=OrderStatus.FILLED, tag="filled")          # terminal → excluded
    await _add_order(session_factory, symbol_id=1, qty="99",
                     side=OrderSide.SELL, tag="sell")                  # sell → excluded
    await _add_order(session_factory, symbol_id=1, qty="99",
                     source_id="42", tag="other")                     # other strategy → excluded
    await _add_order(session_factory, symbol_id=2, qty="99", tag="msft")  # not in universe → excluded

    ctx, _ = _ctx(session_factory, symbols=["AAPL"], strategy_id=99)
    pending = await ctx.pending_buy_qty()
    assert pending == {"AAPL": Decimal("10")}


async def test_pending_buy_qty_empty_when_none(session_factory, seeded):
    ctx, _ = _ctx(session_factory, symbols=["AAPL"], strategy_id=99)
    assert await ctx.pending_buy_qty() == {}
