"""StrategyContext / BacktestContext contract parity (2026-07-22).

momentum-daily runs UNCHANGED in backtest and live — that is the point of BacktestContext. If a
method it calls exists on only one of the two contexts, or the two disagree on semantics, then a
validation backtest cannot establish evidence about the live strategy: the harness would be
measuring a different program.

`pending_buy_qty` was missing from BacktestContext entirely (a strategy that nets target buys
against it — the duplicate-basket guard, incident 2026-06-22 — would double-submit in backtest
where it does not live). These tests pin (a) that every ctx method momentum-daily uses exists on
BOTH contexts, and (b) that `pending_buy_qty` returns the SAME answer from both for identical
synthetic order states.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk import OrderRequest
from app.strategies.backtest_context import BacktestContext
from app.strategies.context import StrategyContext

D = Decimal
T0 = datetime(2026, 6, 8, 14, 30, tzinfo=UTC)
MOMENTUM_DAILY = (
    Path(__file__).resolve().parents[2]
    / "strategies_user/templates/momentum_daily.py"
)


# ---- (a) structural contract: no method exists on only one context --------------

def _ctx_methods_used_by_momentum_daily() -> set[str]:
    """Every `self.ctx.<name>(...)` (and `ctx.<name>(...)`) the template calls."""
    tree = ast.parse(MOMENTUM_DAILY.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        val = node.func.value
        # self.ctx.<name> or ctx.<name>
        if (isinstance(val, ast.Attribute) and val.attr == "ctx") or (
            isinstance(val, ast.Name) and val.id == "ctx"
        ):
            names.add(node.func.attr)
    return names


# KNOWN, ADJUDICATED parity gaps between BacktestContext and the live StrategyContext (owner
# ruling 2026-07-22: durable state is a SEPARATE follow-up, not this PR). momentum-daily's durable
# state — the daily latch, the deployment-lifecycle blob, regime persistence, and the CAS-guarded
# seed reconciliation — needs `get_state`/`set_state`/`compare_and_set_state`, none of which
# BacktestContext implements, so momentum-daily cannot run through it at all (the §8 audit used the
# DriftCtxAdapter, which does). Adding them is not like-for-like: compare-and-set in a
# single-threaded replay, and whether state survives strategy-instance recreation, are real design
# decisions that need their own adjudication before the equal-weight validation program.
#
# ⚠ THIS SET MAY ONLY SHRINK. A method removed from it must exist on BOTH contexts. Adding a name
# here to silence the test would defeat its purpose — resolve the gap or adjudicate it, never
# allowlist a NEW one.
_KNOWN_BACKTEST_PARITY_GAPS = frozenset({"get_state", "set_state", "compare_and_set_state"})


def test_every_ctx_method_momentum_daily_uses_exists_on_both_contexts():
    used = _ctx_methods_used_by_momentum_daily()
    assert used, "parser found no ctx.* calls — the extractor is broken, not the contexts"
    missing_live = [m for m in used if not hasattr(StrategyContext, m)]
    assert not missing_live, f"momentum-daily calls ctx methods absent on LIVE ctx: {missing_live}"

    missing_bt = {m for m in used if not hasattr(BacktestContext, m)}
    new_gaps = missing_bt - _KNOWN_BACKTEST_PARITY_GAPS
    assert not new_gaps, (
        f"NEW backtest-context parity gap(s): {sorted(new_gaps)} — momentum-daily calls these but "
        f"BacktestContext does not implement them, so a backtest cannot reproduce the live "
        f"strategy contract. Implement them (or adjudicate and add to _KNOWN_BACKTEST_PARITY_GAPS)."
    )
    # And the allowlist may only shrink: a gap that has since been CLOSED must be removed from it.
    stale = _KNOWN_BACKTEST_PARITY_GAPS - missing_bt
    assert not stale, (
        f"these are no longer gaps — remove them from _KNOWN_BACKTEST_PARITY_GAPS: {sorted(stale)}"
    )


def test_the_durable_state_gap_is_the_only_known_gap_and_is_documented():
    """Pin the known-gap set explicitly, so closing `pending_buy_qty` (this PR) is visible and the
    durable-state follow-up is on the record rather than implicit."""
    assert {"get_state", "set_state", "compare_and_set_state"} == _KNOWN_BACKTEST_PARITY_GAPS
    assert not hasattr(BacktestContext, "get_state")   # the follow-up has not silently landed
    assert hasattr(BacktestContext, "pending_buy_qty")  # this PR's fix is present


def test_pending_buy_qty_signatures_match():
    """Same name, both async, same declared return — a shape check the AttributeError guard
    above cannot see (a sync stub or a differently-shaped return would still pass hasattr)."""
    live = StrategyContext.pending_buy_qty
    bt = BacktestContext.pending_buy_qty
    assert inspect.iscoroutinefunction(live) and inspect.iscoroutinefunction(bt)
    assert (inspect.signature(live).return_annotation
            == inspect.signature(bt).return_annotation)


# ---- (b) semantic parity: identical order states, identical answer --------------

@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        s.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ", asset_class="us_equity",
                     name="MSFT", active=True))
        s.add(Symbol(id=3, ticker="TSLA", exchange="NASDAQ", asset_class="us_equity",
                     name="TSLA", active=True))
        await s.commit()
    return 1


def _live_ctx(session_factory, symbols=("AAPL", "MSFT")) -> StrategyContext:
    return StrategyContext(
        strategy_id=7, user_id=1, account_id=1, symbols=list(symbols),
        session_factory=session_factory, bar_cache=None, indicator_computer=None,
        submit_order_fn=lambda *a, **k: None,
    )


def _bt_ctx(symbols=("AAPL", "MSFT")) -> BacktestContext:
    bars = pd.DataFrame({"t": [T0], "o": [100.0], "h": [100.0], "l": [100.0],
                         "c": [100.0], "v": [1000]})
    return BacktestContext(
        symbols=list(symbols), bars_by_symbol={s: bars for s in symbols},
        initial_equity=D("100000"), slippage_bps=0.0, commission_per_share=0.0,
        indicator_computer=None,
    )


async def _seed_live_order(session_factory, *, oid, symbol_id, side, qty, status,
                           strategy_id=7, source=OrderSourceType.STRATEGY):
    now = datetime.now(UTC)
    async with session_factory() as s, s.begin():
        s.add(Order(
            id=oid, user_id=1, account_id=1, symbol_id=symbol_id,
            client_order_id=f"twb-{oid}", side=side, qty=D(qty), type=OrderType.MARKET,
            tif=TimeInForce.DAY, status=status, source_type=source,
            source_id=str(strategy_id), created_at=now, updated_at=now))


def _bt_submit(ctx: BacktestContext, symbol, side, qty):
    """Queue an order into the backtest's pending set WITHOUT settling — the in-flight state
    pending_buy_qty reads. Mirrors submit_order's append at cursor 0."""
    from app.strategies.backtest_context import _PendingOrder

    ctx._order_seq += 1
    ctx.pending_orders.append(_PendingOrder(
        submit_ts=T0, symbol=symbol.upper(), side=side, qty=D(qty), type=OrderType.MARKET,
        limit_price=None, stop_price=None, order_id=ctx._order_seq))


async def test_identical_in_flight_buys_give_the_same_answer_on_both_contexts(
    session_factory, acct
):
    """Two in-flight BUYs (AAPL 5, MSFT 3) as SUBMITTED live orders and as pending backtest
    orders. Both contexts must report {AAPL: 5, MSFT: 3}."""
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED)
    await _seed_live_order(session_factory, oid=2, symbol_id=2, side=OrderSide.BUY,
                           qty="3", status=OrderStatus.SUBMITTED)
    live = await _live_ctx(session_factory).pending_buy_qty()

    bt_ctx = _bt_ctx()
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "5")
    _bt_submit(bt_ctx, "MSFT", OrderSide.BUY, "3")
    bt = await bt_ctx.pending_buy_qty()

    assert live == {"AAPL": D("5"), "MSFT": D("3")}
    assert bt == live


async def test_sells_are_excluded_on_both_contexts(session_factory, acct):
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED)
    await _seed_live_order(session_factory, oid=2, symbol_id=1, side=OrderSide.SELL,
                           qty="9", status=OrderStatus.SUBMITTED)
    live = await _live_ctx(session_factory).pending_buy_qty()

    bt_ctx = _bt_ctx()
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "5")
    _bt_submit(bt_ctx, "AAPL", OrderSide.SELL, "9")
    bt = await bt_ctx.pending_buy_qty()

    assert live == {"AAPL": D("5")} and bt == live


@pytest.mark.parametrize("terminal", [OrderStatus.FILLED, OrderStatus.CANCELED,
                                       OrderStatus.REJECTED])
async def test_terminal_buys_are_excluded_on_the_live_context(session_factory, acct, terminal):
    """Live: a terminal BUY drops out of the non-terminal filter. (Backtest twin: a settled or
    rejected order is not in pending_orders — asserted in test_backtest_context_behaviour.)"""
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED)
    await _seed_live_order(session_factory, oid=2, symbol_id=2, side=OrderSide.BUY,
                           qty="3", status=terminal)
    assert await _live_ctx(session_factory).pending_buy_qty() == {"AAPL": D("5")}


async def test_orders_outside_the_allowed_universe_are_excluded_on_both(session_factory, acct):
    """TSLA is not in the strategy's universe; both contexts must drop it."""
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED)
    await _seed_live_order(session_factory, oid=2, symbol_id=3, side=OrderSide.BUY,
                           qty="4", status=OrderStatus.SUBMITTED)
    live = await _live_ctx(session_factory, symbols=("AAPL", "MSFT")).pending_buy_qty()

    bt_ctx = _bt_ctx(symbols=("AAPL", "MSFT"))
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "5")
    _bt_submit(bt_ctx, "TSLA", OrderSide.BUY, "4")
    bt = await bt_ctx.pending_buy_qty()

    assert live == {"AAPL": D("5")} and bt == live


async def test_another_strategys_buys_are_excluded_on_the_live_context(session_factory, acct):
    """Live scoping is by source_id; the backtest context is single-strategy by construction."""
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED, strategy_id=7)
    await _seed_live_order(session_factory, oid=2, symbol_id=1, side=OrderSide.BUY,
                           qty="8", status=OrderStatus.SUBMITTED, strategy_id=99)
    assert await _live_ctx(session_factory).pending_buy_qty() == {"AAPL": D("5")}


async def test_multiple_buys_same_symbol_sum_on_both(session_factory, acct):
    await _seed_live_order(session_factory, oid=1, symbol_id=1, side=OrderSide.BUY,
                           qty="5", status=OrderStatus.SUBMITTED)
    await _seed_live_order(session_factory, oid=2, symbol_id=1, side=OrderSide.BUY,
                           qty="2", status=OrderStatus.SUBMITTED)
    live = await _live_ctx(session_factory).pending_buy_qty()

    bt_ctx = _bt_ctx()
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "5")
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "2")
    bt = await bt_ctx.pending_buy_qty()

    assert live == {"AAPL": D("7")} and bt == live


async def test_no_in_flight_buys_is_an_empty_map_on_both(session_factory, acct):
    live = await _live_ctx(session_factory).pending_buy_qty()
    bt = await _bt_ctx().pending_buy_qty()
    assert live == {} and bt == {}


async def test_the_backtest_answer_is_symbol_specific_and_nonnegative(session_factory, acct):
    bt_ctx = _bt_ctx()
    _bt_submit(bt_ctx, "AAPL", OrderSide.BUY, "5")
    out = await bt_ctx.pending_buy_qty()
    assert set(out) <= {"AAPL", "MSFT"}
    assert all(v >= 0 for v in out.values())


async def test_a_settled_backtest_buy_stops_being_pending(session_factory):
    """The real submit->settle path: once an order settles it leaves pending_orders, so the
    live 'not yet in positions' semantics hold."""
    bars = pd.DataFrame({
        "t": [T0, T0.replace(day=9)],
        "o": [100.0, 100.0], "h": [100.0, 100.0], "l": [100.0, 100.0],
        "c": [100.0, 100.0], "v": [1000, 1000],
    })
    ctx = BacktestContext(
        symbols=["AAPL"], bars_by_symbol={"AAPL": bars}, initial_equity=D("100000"),
        slippage_bps=0.0, commission_per_share=0.0, indicator_computer=None)
    await ctx.submit_order(OrderRequest(
        user_id=0, account_id=0, symbol_ticker="AAPL", side=OrderSide.BUY, qty=D("5"),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.STRATEGY,
        source_id=None))
    assert await ctx.pending_buy_qty() == {"AAPL": D("5")}       # in flight
    ctx._advance_cursor(1)
    ctx._settle_pending_orders(T0.replace(day=9))
    assert await ctx.pending_buy_qty() == {}                     # settled -> not pending
