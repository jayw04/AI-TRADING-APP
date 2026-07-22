"""BacktestContext — the branches the harness tests never reach.

`tests/backtester` drives the happy long-only path, so whole behaviours of the simulated
context went unasserted: short-side position arithmetic, equity before any bar exists, the
fill-cursor filter that `recent_fills` depends on for crash recovery, the open-order prefix
filter the seed lifecycle depends on, and the order-rejection paths.

These assert BEHAVIOUR — what the simulated book actually holds and what the context reports —
because backtest fidelity is the whole point of this class: a strategy that sizes or recovers
differently here than it would live produces a backtest that cannot be trusted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.risk import OrderRequest
from app.strategies.backtest_context import BacktestContext

D = Decimal
T0 = datetime(2026, 6, 8, 14, 30, tzinfo=UTC)


def _bars(opens: list[float], closes: list[float] | None = None) -> pd.DataFrame:
    closes = closes if closes is not None else opens
    return pd.DataFrame(
        {
            "t": [T0 + timedelta(days=i) for i in range(len(opens))],
            "o": opens,
            "h": [max(o, c) for o, c in zip(opens, closes, strict=True)],
            "l": [min(o, c) for o, c in zip(opens, closes, strict=True)],
            "c": closes,
            "v": [1000] * len(opens),
        }
    )


def _ctx(bars=None, *, equity="10000", slippage_bps=0.0, commission=0.0) -> BacktestContext:
    return BacktestContext(
        symbols=["AAPL"],
        bars_by_symbol=bars if bars is not None else {"AAPL": _bars([100.0, 101.0, 102.0])},
        initial_equity=D(equity),
        slippage_bps=slippage_bps,
        commission_per_share=commission,
        indicator_computer=None,
    )


def _req(side: OrderSide, qty: str, *, type_=OrderType.MARKET, coid=None) -> OrderRequest:
    return OrderRequest(
        user_id=0, account_id=0, symbol_ticker="AAPL", side=side, qty=D(qty),
        type=type_, tif=TimeInForce.DAY, source_type=OrderSourceType.STRATEGY,
        source_id=None, client_order_id=coid,
    )


async def _fill(ctx: BacktestContext, side: OrderSide, qty: str, *, coid=None) -> None:
    """Submit on this bar and settle it on the next, as the harness does."""
    await ctx.submit_order(_req(side, qty, coid=coid))
    ctx._advance_cursor(ctx._cursor + 1)
    ctx._settle_pending_orders(T0 + timedelta(days=ctx._cursor))


# ---- short-side position arithmetic --------------------------------------------

async def test_a_sell_with_no_position_opens_a_short():
    ctx = _ctx()
    await _fill(ctx, OrderSide.SELL, "10")
    pos = ctx.positions["AAPL"]
    assert pos.side == "short" and pos.qty == D("10")
    assert pos.avg_entry_price == D("101")          # next bar's open
    assert ctx.cash == D("10000") + D("1010")       # a short credits the proceeds


async def test_adding_to_a_short_averages_the_entry_price():
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 200.0])})
    await _fill(ctx, OrderSide.SELL, "10")          # @100
    await _fill(ctx, OrderSide.SELL, "10")          # @200
    pos = ctx.positions["AAPL"]
    assert pos.side == "short" and pos.qty == D("20")
    assert pos.avg_entry_price == D("150")          # (100*10 + 200*10) / 20


async def test_buying_against_a_short_reduces_it_rather_than_flipping_side():
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 100.0])})
    await _fill(ctx, OrderSide.SELL, "10")
    await _fill(ctx, OrderSide.BUY, "4")
    pos = ctx.positions["AAPL"]
    assert pos.side == "short" and pos.qty == D("6")


async def test_selling_against_a_long_reduces_it_rather_than_flipping_side():
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 100.0])})
    await _fill(ctx, OrderSide.BUY, "10")
    await _fill(ctx, OrderSide.SELL, "4")
    pos = ctx.positions["AAPL"]
    assert pos.side == "long" and pos.qty == D("6")


async def test_adding_to_a_long_averages_the_entry_price():
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 300.0])})
    await _fill(ctx, OrderSide.BUY, "10")           # @100
    await _fill(ctx, OrderSide.BUY, "10")           # @300
    assert ctx.positions["AAPL"].avg_entry_price == D("200")


# ---- equity ---------------------------------------------------------------------

async def test_equity_falls_back_to_initial_before_any_bar_exists():
    """No bars at all: at the start of the run the context must still report the seed
    equity, or a strategy that sizes from equity cannot place its first order."""
    ctx = _ctx({"AAPL": pd.DataFrame()})
    assert await ctx.get_account_equity() == D("10000")


async def test_equity_is_unknown_once_the_cursor_has_moved_past_the_data():
    ctx = _ctx({"AAPL": pd.DataFrame()})
    ctx._advance_cursor(5)
    assert await ctx.get_account_equity() is None


async def test_equity_marks_a_long_to_the_current_close():
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 100.0], [100.0, 100.0, 130.0])})
    await _fill(ctx, OrderSide.BUY, "10")           # cash 10000 - 1000 = 9000
    ctx._advance_cursor(2)                          # close 130
    assert await ctx.get_account_equity() == D("9000") + D("1300")


async def test_equity_marks_a_short_so_a_falling_price_is_a_gain():
    """The short branch: profit is (entry - current) per share, on top of the returned
    collateral. A rising price must reduce equity."""
    ctx = _ctx({"AAPL": _bars([100.0, 100.0, 100.0], [100.0, 100.0, 80.0])})
    await _fill(ctx, OrderSide.SELL, "10")          # cash 10000 + 1000 = 11000, entry 100
    ctx._advance_cursor(2)                          # close 80 -> 20/share gain
    equity = await ctx.get_account_equity()
    assert equity == D("11000") + (D("100") - D("80")) * D("10") + D("100") * D("10")


# ---- order rejection paths ------------------------------------------------------

@pytest.mark.parametrize("order_type", [OrderType.LIMIT, OrderType.STOP])
async def test_non_market_orders_are_rejected_not_silently_queued(order_type):
    ctx = _ctx()
    res = await ctx.submit_order(_req(OrderSide.BUY, "1", type_=order_type))
    assert res.status == "rejected"
    assert res.rejection_reason == "non_market_orders_unsupported_in_backtest"
    assert ctx.pending_orders == []


async def test_a_non_positive_quantity_is_rejected():
    ctx = _ctx()
    res = await ctx.submit_order(_req(OrderSide.BUY, "0"))
    assert res.status == "rejected" and res.rejection_reason == "invalid_qty"


# ---- open_orders / recent_fills: what crash recovery reads ----------------------

async def test_open_orders_reports_pending_orders_and_filters_by_prefix():
    """The seed lifecycle recovers by client_order_id prefix, so the filter must be real."""
    ctx = _ctx()
    await ctx.submit_order(_req(OrderSide.BUY, "1", coid="seed:1:a:AAPL"))
    await ctx.submit_order(_req(OrderSide.BUY, "2", coid="other:zzz"))

    assert {o.client_order_id for o in await ctx.open_orders()} == {
        "seed:1:a:AAPL", "other:zzz"}
    matched = await ctx.open_orders(client_order_id_prefix="seed:1:")
    assert [o.client_order_id for o in matched] == ["seed:1:a:AAPL"]
    assert matched[0].symbol == "AAPL" and matched[0].status == "submitted"


async def test_a_settled_order_is_no_longer_open():
    ctx = _ctx()
    await _fill(ctx, OrderSide.BUY, "1", coid="seed:1:a:AAPL")
    assert await ctx.open_orders() == []


async def test_recent_fills_filters_by_prefix():
    ctx = _ctx()
    await _fill(ctx, OrderSide.BUY, "1", coid="seed:1:a:AAPL")
    await _fill(ctx, OrderSide.BUY, "1", coid="other:zzz")
    got = await ctx.recent_fills(client_order_id_prefix="seed:1:")
    assert [f.client_order_id for f in got] == ["seed:1:a:AAPL"]


async def test_recent_fills_cursor_excludes_everything_up_to_and_including_the_cursor():
    """(since, after_fill_id) is the resume cursor: a fill AT `since` with an id at or below
    `after_fill_id` has already been consumed and must not be replayed."""
    ctx = _ctx({"AAPL": _bars([100.0] * 5)})
    await _fill(ctx, OrderSide.BUY, "1")
    await _fill(ctx, OrderSide.BUY, "1")
    all_fills = await ctx.recent_fills()
    assert len(all_fills) == 2
    first = all_fills[0]

    resumed = await ctx.recent_fills(since=first.filled_at, after_fill_id=first.fill_id)
    assert first.fill_id not in {f.fill_id for f in resumed}


async def test_recent_fills_with_only_since_drops_strictly_earlier_fills():
    ctx = _ctx({"AAPL": _bars([100.0] * 5)})
    await _fill(ctx, OrderSide.BUY, "1")
    await _fill(ctx, OrderSide.BUY, "1")
    fills = await ctx.recent_fills()
    later = fills[-1]
    got = await ctx.recent_fills(since=later.filled_at)
    assert {f.fill_id for f in got} == {later.fill_id}


# ---- signals --------------------------------------------------------------------

async def test_log_signal_records_the_bar_timestamp():
    ctx = _ctx()
    n = await ctx.log_signal("aapl", SignalType.ENTRY, payload={"reason": "x"})
    assert n == 1
    sig = ctx.signals[0]
    assert sig["symbol"] == "AAPL" and sig["type"] == SignalType.ENTRY.value
    assert sig["payload"] == {"reason": "x"} and sig["ts"] is not None


async def test_log_signal_tolerates_having_no_current_bar():
    """Signals must still be recorded off the end of the data, with a null timestamp rather
    than an exception — a strategy logging in a teardown path must not crash the run."""
    ctx = _ctx({"AAPL": pd.DataFrame()})
    await ctx.log_signal("AAPL", SignalType.INFO)
    assert ctx.signals[0]["ts"] is None
    assert ctx.signals[0]["payload"] == {}


# ---- position views -------------------------------------------------------------

async def test_get_position_for_is_case_insensitive_and_none_when_flat():
    ctx = _ctx()
    assert await ctx.get_position_for("AAPL") is None
    await _fill(ctx, OrderSide.BUY, "3")
    view = await ctx.get_position_for("aapl")
    assert view is not None and view.qty == D("3") and view.side == "long"
