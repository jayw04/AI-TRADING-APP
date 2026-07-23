"""StrategyContext / BacktestContext durable-state parity (2026-07-22).

momentum-daily's discipline — the once-per-day latch, the deployment-lifecycle blob, regime
persistence, and the CAS-guarded seed reconciliation — all live in durable state. Before this the
trio get_state/set_state/compare_and_set_state existed only on the live StrategyContext (and the
DriftCtxAdapter), so momentum-daily could not run through BacktestContext at all. These tests pin
that the backtest twin now behaves identically to the live contract for a single-threaded replay.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from app.db.models.account import Account, AccountMode
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.strategies.backtest_context import BacktestContext
from app.strategies.context import StrategyContext

T0 = datetime(2026, 6, 8, 14, 30, tzinfo=UTC)


def _bt() -> BacktestContext:
    bars = pd.DataFrame({"t": [T0], "o": [100.0], "h": [100.0], "l": [100.0],
                         "c": [100.0], "v": [1000]})
    return BacktestContext(
        symbols=["AAPL"], bars_by_symbol={"AAPL": bars}, initial_equity=Decimal("100000"),
        slippage_bps=0.0, commission_per_share=0.0, indicator_computer=None)


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return 1


def _live(session_factory) -> StrategyContext:
    return StrategyContext(
        strategy_id=7, user_id=1, account_id=1, symbols=["AAPL"],
        session_factory=session_factory, bar_cache=None, indicator_computer=None,
        submit_order_fn=lambda *a, **k: None)


# ---- get / set / clear -----------------------------------------------------------

async def test_get_returns_default_when_unset_on_both(session_factory, acct):
    assert await _live(session_factory).get_state("k", "d") == "d"
    assert await _bt().get_state("k", "d") == "d"


async def test_set_then_get_roundtrips_on_both(session_factory, acct):
    live = _live(session_factory)
    await live.set_state("last_eval_date", "2026-06-08")
    assert await live.get_state("last_eval_date") == "2026-06-08"

    bt = _bt()
    await bt.set_state("last_eval_date", "2026-06-08")
    assert await bt.get_state("last_eval_date") == "2026-06-08"


async def test_set_is_last_write_wins_on_both(session_factory, acct):
    live = _live(session_factory)
    await live.set_state("k", {"a": 1})
    await live.set_state("k", {"a": 2})
    assert await live.get_state("k") == {"a": 2}

    bt = _bt()
    await bt.set_state("k", {"a": 1})
    await bt.set_state("k", {"a": 2})
    assert await bt.get_state("k") == {"a": 2}


async def test_clear_removes_the_key_on_both(session_factory, acct):
    live = _live(session_factory)
    await live.set_state("k", "v")
    await live.clear_state("k")
    assert await live.get_state("k", "gone") == "gone"

    bt = _bt()
    await bt.set_state("k", "v")
    await bt.clear_state("k")
    assert await bt.get_state("k", "gone") == "gone"


# ---- compare_and_set: the seed-lifecycle CAS -------------------------------------

async def test_cas_create_if_absent_succeeds_then_a_second_create_fails_on_both(
    session_factory, acct
):
    for ctx in (_live(session_factory), _bt()):
        assert await ctx.compare_and_set_state("dep", expected_rev=None,
                                               new_value={"_rev": 0, "state": "NEVER"}) is True
        # a second create-if-absent must fail (row/value already exists)
        assert await ctx.compare_and_set_state("dep", expected_rev=None,
                                               new_value={"_rev": 0, "state": "X"}) is False
        assert (await ctx.get_state("dep"))["state"] == "NEVER"


async def test_cas_advances_only_on_matching_rev_on_both(session_factory, acct):
    for ctx in (_live(session_factory), _bt()):
        await ctx.compare_and_set_state("dep", expected_rev=None, new_value={"_rev": 0, "n": 0})
        # correct rev advances
        assert await ctx.compare_and_set_state("dep", expected_rev=0,
                                               new_value={"_rev": 1, "n": 1}) is True
        # stale rev is refused — the optimistic-concurrency guard
        assert await ctx.compare_and_set_state("dep", expected_rev=0,
                                               new_value={"_rev": 2, "n": 99}) is False
        cur = await ctx.get_state("dep")
        assert cur["_rev"] == 1 and cur["n"] == 1


async def test_two_reads_of_the_same_rev_cannot_both_write_on_both(session_factory, acct):
    """The property the seed write-ahead depends on: two callers that read rev 0 cannot both
    commit — the first wins, the second's stale CAS fails."""
    for ctx in (_live(session_factory), _bt()):
        await ctx.compare_and_set_state("dep", expected_rev=None, new_value={"_rev": 0})
        first = await ctx.compare_and_set_state("dep", expected_rev=0, new_value={"_rev": 1, "who": "A"})
        second = await ctx.compare_and_set_state("dep", expected_rev=0, new_value={"_rev": 1, "who": "B"})
        assert (first, second) == (True, False)
        assert (await ctx.get_state("dep"))["who"] == "A"


# ---- persistence across on_bar (the "survives a reload" property) ----------------

async def test_backtest_state_persists_across_evaluations():
    """A backtest runs ONE context for the whole session sequence, so state written on one bar is
    visible on the next — the backtest analogue of the DB row surviving a live reload."""
    bt = _bt()
    await bt.set_state("last_review_date", "2026-06-08")
    # ... many bars later, same context instance ...
    assert await bt.get_state("last_review_date") == "2026-06-08"
