"""momentum-daily (Workstream B) — the distinctive daily-evaluation behaviours.

The selection logic (A1 dual filter, A2 rank bands, A5 regime) is shared with v0.9 and covered by
`test_momentum_portfolio`. These tests cover what is NEW: the durable once-per-day latch, condition-
driven trading (trade only when a §5.1 trigger fires), per-trigger reason logging, and the incoherent
-band refusal — all against a state-backed mock context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.strategies.context import Bar
from strategies_user.templates.momentum_daily import (
    _K_LAST_EVAL,
    MomentumDaily,
)

D1 = datetime(2026, 6, 8, 21, 10, tzinfo=UTC)   # Mon post-close
D2 = datetime(2026, 6, 9, 21, 10, tzinfo=UTC)   # Tue post-close


def _bar(ts, symbol="AAA"):
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order, raw=None):
    tickers = [t for t, _ in order]
    z = [s for _, s in order]
    raw = raw or {}
    mom = [raw.get(t, 0.10 + 0.01 * i) for i, t in enumerate(reversed(tickers))][::-1]
    df = pd.DataFrame({"momentum": mom, "winsorized": z, "zscore": z,
                       "rank": list(range(1, len(tickers) + 1)), "score": z}, index=tickers)
    df.index.name = "ticker"
    return df


def _spy(above=True, n=201):
    closes = [100.0] * (n - 1) + [110.0 if above else 90.0]
    idx = pd.to_datetime([datetime(2026, 6, 8).date()] * n)
    df = pd.DataFrame({"c": closes}, index=idx)
    df.index.name = "t"
    return df


def _ctx(symbols, scores, holdings=None, spy_bars=None, price=100.0, equity=100_000):
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)

    def _pos(s):
        if s not in holdings:
            return None
        p = MagicMock()
        p.side = "long"
        p.qty = Decimal(holdings[s])
        return p
    ctx.get_position_for = AsyncMock(side_effect=_pos)

    def _bars(sym, tf, n):
        return spy_bars if (spy_bars is not None and sym == "SPY") else pd.DataFrame({"c": [price]})
    ctx.get_recent_bars = AsyncMock(side_effect=_bars)
    ctx.get_account_equity = AsyncMock(return_value=equity)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    ctx.pending_buy_qty = AsyncMock(return_value={})

    # durable state, dict-backed
    store: dict[str, object] = {}
    ctx._store = store
    ctx.get_state = AsyncMock(side_effect=lambda k, d=None: store.get(k, d))

    async def _set(k, v):
        store[k] = v
    ctx.set_state = AsyncMock(side_effect=_set)

    async def _clear(k):
        store.pop(k, None)
    ctx.clear_state = AsyncMock(side_effect=_clear)
    return ctx


def _strat(ctx, **over):
    params = {**MomentumDaily.default_params, "order_pacing_seconds": 0.0,
              "use_market_regime_filter": False, "exit_confirm_closes": 1, **over}
    return MomentumDaily(ctx=ctx, params=params)


def _orders(ctx):
    out = {}
    for c in ctx.submit_order.call_args_list:
        r = c.args[0]
        out[r.symbol_ticker] = (r.side.value, r.qty)
    return out


def _reasons(ctx):
    return [c.kwargs.get("payload", {}).get("reason", "") for c in ctx.log_signal.call_args_list]


async def test_schema_matches_default_params():
    assert set(MomentumDaily.params_schema) == set(MomentumDaily.default_params)


async def test_incoherent_rank_band_is_refused():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    with pytest.raises(ValueError, match="incoherent rank bands"):
        await _strat(ctx, entry_rank=5, hold_rank=3).on_init()


async def test_the_daily_latch_is_DURABLE_evaluates_once_per_day():
    """The once-per-day latch lives in durable state, so a second tick the SAME day — even from a
    fresh instance (a reload) — does not re-evaluate."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores)
    s1 = _strat(ctx, entry_rank=2, max_names=2)
    await s1.on_init()
    await s1.on_bar(_bar(D1))
    calls_after_first = ctx.factors.momentum_scores.call_count
    assert calls_after_first >= 1
    assert ctx._store.get(_K_LAST_EVAL) == "2026-06-08"

    # a FRESH instance (reload) on the same day must NOT re-evaluate
    s2 = _strat(ctx, entry_rank=2, max_names=2)
    await s2.on_init()
    await s2.on_bar(_bar(datetime(2026, 6, 8, 21, 11, tzinfo=UTC)))
    assert ctx.factors.momentum_scores.call_count == calls_after_first  # unchanged -> latched


async def test_a_new_day_evaluates_again():
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    s = _strat(ctx, entry_rank=2, max_names=2)
    await s.on_init()
    await s.on_bar(_bar(D1))
    n1 = ctx.factors.momentum_scores.call_count
    await s.on_bar(_bar(D2))                       # next day -> evaluates again
    assert ctx.factors.momentum_scores.call_count > n1


async def test_no_trigger_means_REVIEW_not_TRADE():
    """The core of the policy: a valid book with nothing breached is reviewed, not traded."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.9)])
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"AAA": 5, "BBB": 5})
    s = _strat(ctx, entry_rank=2, hold_rank=2, max_names=2, weight_drift_pct=0.0)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert not _orders(ctx), "traded when no trigger fired"
    assert "reviewed_no_trigger" in _reasons(ctx)


async def test_raw_momentum_negative_is_a_trigger_and_is_LOGGED():
    """A holding whose raw momentum turns <= 0 fires raw_momentum_negative and the book trades."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.5)], raw={"AAA": 0.20, "BBB": -0.05})
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"BBB": 5}, equity=100_000)
    s = _strat(ctx, entry_rank=2, hold_rank=2, max_names=2)
    await s.on_init()
    await s.on_bar(_bar(D1))
    orders = _orders(ctx)
    assert "BBB" in orders and orders["BBB"][0] == "sell"   # the falling holding is exited
    assert any("raw_momentum_negative" in r for r in _reasons(ctx))


async def test_regime_flip_to_risk_off_trades_to_cash_and_logs_regime_change():
    scores = _scores([("AAA", 2.0)])
    ctx = _ctx(["AAA", "SPY"], scores, holdings={"AAA": 5},
               spy_bars=_spy(above=False), equity=100_000)
    s = _strat(ctx, use_market_regime_filter=True, regime_mode="binary",
               entry_rank=1, max_names=1)
    await s.on_init()
    # seed the "previous regime" as risk-on so this close is a flip
    s._prev_regime_below = False
    await s.on_bar(_bar(D1))
    orders = _orders(ctx)
    assert orders.get("AAA", ("", 0))[0] == "sell"          # flattened to cash
    assert any("regime" in r for r in _reasons(ctx))


def _spy_at(last: float, ma: float = 100.0, n: int = 201):
    """SPY bars whose 200d MA == ``ma`` and whose last close == ``last``."""
    closes = [ma] * (n - 1) + [last]
    idx = pd.to_datetime([datetime(2026, 6, 8).date()] * n)
    df = pd.DataFrame({"c": closes}, index=idx)
    df.index.name = "t"
    return df


@pytest.mark.parametrize(("last", "expected_gross"), [
    (110.0, 0.98),   # rel +10% > +2% band  -> clearly above
    (101.0, 0.60),   # rel  +1% within ±2%  -> mid buffer zone
    (90.0, 0.15),    # rel −10% < −2% band  -> clearly below
])
async def test_graduated_regime_steps_gross_with_distance_from_ma(last, expected_gross):
    """Stage-4 winner: graduated gross = 0.98 / 0.60 / 0.15 by distance from the 200d MA."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(last))
    s = _strat(ctx, use_market_regime_filter=True)   # default regime_mode == "graduated"
    await s.on_init()
    below, gross, _ = await s._regime()
    assert below is False                            # graduated never hard-flips to cash while fresh
    assert gross == pytest.approx(expected_gross)


async def test_graduated_regime_degrosses_below_ma_without_going_flat():
    """Below the MA, graduated stays PARTIALLY invested (gross 0.15) — not fully to cash like binary."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), holdings={},
               spy_bars=_spy_at(90.0), equity=100_000)
    s = _strat(ctx, use_market_regime_filter=True, entry_rank=1, max_names=1)
    await s.on_init()
    s._regime_gross = (await s._regime())[1]
    inv = await s._investable_equity()
    # ~ equity * (1 - cash_buffer 0.02) * gross 0.15  ->  clearly > 0 and well below full
    assert Decimal("10000") < inv < Decimal("20000")


async def test_graduated_gross_change_is_a_regime_change_flip():
    """A move across a gross boundary flips the regime (fires the regime_change trigger)."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(110.0))
    s = _strat(ctx, use_market_regime_filter=True)
    await s.on_init()
    s._prev_regime_gross = 0.60                       # was in the buffer zone last eval
    _, gross, flipped = await s._regime()
    assert gross == pytest.approx(0.98) and flipped is True


async def test_retries_are_bounded_within_the_day():
    """A failing evaluation is retried a bounded number of times WITHIN the day, then gives up — it
    does not re-run on every one of the ~200 per-symbol ticks (storm guard), and the retry budget is
    durable so a reload cannot reset it."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"AAA": 5})
    ctx.factors.momentum_scores = MagicMock(side_effect=RuntimeError("boom"))
    s = _strat(ctx, entry_rank=2, max_names=2, max_daily_retries=3)
    await s.on_init()
    for _ in range(6):                                       # six ticks the same day
        await s.on_bar(_bar(D1))
    fails = [r for r in _reasons(ctx) if r == "daily_eval_failed"]
    exhausted = [r for r in _reasons(ctx) if r == "daily_eval_retries_exhausted"]
    assert len(fails) == 3                                   # exactly the retry budget
    assert exhausted                                         # then it gives up for the day
