"""P9 §4 — momentum-portfolio template (v0.2, review-hardened).

Covers schema parity, weekly rebalance + failure-retry, selection/diff, the
bail-out taxonomy, the market-regime filter, live-equity sizing, the turnover
threshold, rank hysteresis, and the rejection policy — all against a synthetic
StrategyContext (no engine, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.strategies.context import Bar
from strategies_user.templates.momentum_portfolio import MomentumPortfolio

WK1_A = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)   # Mon
WK1_B = datetime(2026, 6, 8, 14, 1, tzinfo=UTC)   # same ISO week
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)    # next ISO week


def _bar(ts: datetime, symbol: str = "AAA") -> Bar:
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame({"score": [s for _, s in order]}, index=[t for t, _ in order])
    df.index.name = "ticker"
    return df


def _pos(qty: int):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(qty)
    return p


def _params(**over):
    """Defaults with the regime filter OFF and sizing knobs neutralized, so a test
    can isolate one behavior. Override per test."""
    return {
        **MomentumPortfolio.default_params,
        "use_market_regime_filter": False,
        "cash_buffer_pct": 0.0,
        "max_position_pct": 1.0,
        "min_score": None,
        "rebalance_buffer_rank_pct": 0.0,
        "min_trade_pct": 0.0,
        "order_pacing_seconds": 0.0,  # no real sleeps in tests
        **over,
    }


def _ctx(symbols, scores, holdings=None, price=100.0, equity=None, spy_bars=None):
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)
    ctx.get_position_for = AsyncMock(side_effect=lambda s: _pos(holdings[s]) if s in holdings else None)

    def _bars(sym, tf, n):
        if spy_bars is not None and sym == "SPY":
            return spy_bars
        return pd.DataFrame({"c": [price]})

    ctx.get_recent_bars = AsyncMock(side_effect=_bars)
    ctx.get_account_equity = AsyncMock(return_value=equity)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    return ctx


def _orders(ctx) -> dict[str, tuple[str, Decimal]]:
    out = {}
    for call in ctx.submit_order.call_args_list:
        req = call.args[0]
        out[req.symbol_ticker] = (req.side.value, req.qty)
    return out


def _strat(ctx, **over):
    return MomentumPortfolio(ctx=ctx, params=_params(**over))


# ---- schema / cadence ----------------------------------------------------------

def test_schema_matches_default_params() -> None:
    assert set(MomentumPortfolio.params_schema) == set(MomentumPortfolio.default_params)


async def test_rebalances_once_per_iso_week() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → no second rebalance
    assert ctx.factors.momentum_scores.call_count == 1
    await strat.on_bar(_bar(WK2))    # new week → rebalances again
    assert ctx.factors.momentum_scores.call_count == 2


async def test_momentum_window_defaults_to_12m() -> None:
    """R1: the book defaults to the 12-month window (252/0), the OOS-dominant
    variant — see research/momentum_12m_backtest.md."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    _, kwargs = ctx.factors.momentum_scores.call_args
    assert kwargs["lookback_days"] == 252
    assert kwargs["skip_days"] == 0


async def test_momentum_window_is_parametrized() -> None:
    """The window is configurable — e.g. the old 6-1 (105/21) — and passed through
    to the accessor verbatim."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    strat = _strat(ctx, momentum_lookback_days=105, momentum_skip_days=21)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    _, kwargs = ctx.factors.momentum_scores.call_args
    assert kwargs["lookback_days"] == 105
    assert kwargs["skip_days"] == 21


async def test_unexpected_failure_marks_week_and_does_not_retry_same_week() -> None:
    """★ The week is marked at the START of the attempt, so a rebalance that raises
    is NOT retried on the next per-symbol tick in the same week — preventing the
    submission storm (the engine fires on_bar ~200×/tick). It logs rebalance_failed
    and waits for next week."""
    ctx = _ctx(["AAA"], _scores([("AAA", 1.0)]))
    ctx.factors.momentum_scores = MagicMock(side_effect=ValueError("boom"))  # not a _HOLD_ON
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → NO retry (marked on attempt)
    assert ctx.factors.momentum_scores.call_count == 1
    assert any("rebalance_failed" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
    await strat.on_bar(_bar(WK2))    # next week → attempts again
    assert ctx.factors.momentum_scores.call_count == 2


# ---- selection / diff ----------------------------------------------------------

async def test_selection_diff_buys_targets_sells_leavers() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", 0.0), ("DDD", -1.0), ("EEE", -2.0)])
    ctx = _ctx(["AAA", "BBB", "CCC", "DDD", "EEE"], scores,
               holdings={"CCC": 10, "AAA": 5}, price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=0.4, max_names=10)  # ceil(5*0.4)=2 → {AAA,BBB}
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    # equity 100k / k=2 = 50k per name; price 100 → 500 target
    assert orders["CCC"] == ("sell", Decimal(10))   # dropped out → flat
    assert orders["AAA"] == ("buy", Decimal(495))   # 500 - 5 held
    assert orders["BBB"] == ("buy", Decimal(500))
    assert "DDD" not in orders and "EEE" not in orders


async def test_names_outside_universe_never_traded() -> None:
    scores = _scores([("ZZZ", 9.0), ("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "ZZZ" not in _orders(ctx)


async def test_min_score_floor_excludes_low_names() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", -0.5)])
    ctx = _ctx(["AAA", "BBB"], scores, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, max_names=10, min_score=0.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" in orders and "BBB" not in orders  # BBB below the 0.0 floor


async def test_default_min_score_is_zero() -> None:
    assert MomentumPortfolio.default_params["min_score"] == 0.0


async def test_market_symbol_never_selected_as_holding() -> None:
    """SPY may be registered only for the regime filter — it must never be bought
    as a portfolio holding even with a top score."""
    scores = _scores([("SPY", 9.0), ("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB", "SPY"], scores, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, max_names=10, market_filter_symbol="SPY")
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "SPY" not in orders  # excluded from targets
    assert "AAA" in orders and "BBB" in orders


# ---- bail-out taxonomy + rejection policy --------------------------------------

@pytest.mark.parametrize(
    "exc",
    [FactorDataUnavailable("no store"), FactorUnavailable("thin"), UniverseUnavailable("floor")],
)
async def test_holds_on_any_no_data_exception(exc) -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 1.0)]))
    ctx.factors.momentum_scores = MagicMock(side_effect=exc)
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))  # must not raise
    ctx.submit_order.assert_not_called()
    assert any("factor_unavailable_hold" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
    assert strat._last_rebalance_week is not None  # deliberate hold = week handled


async def test_rejected_sell_does_not_block_buys() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB", "CCC"], scores, holdings={"CCC": 10}, price=100.0, equity=100_000)

    def _result(req):
        return MagicMock(rejection_reason="risk_blocked" if req.symbol_ticker == "CCC" else None)

    ctx.submit_order = AsyncMock(side_effect=_result)
    strat = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders["CCC"][0] == "sell"
    assert orders["AAA"][0] == "buy" and orders["BBB"][0] == "buy"


async def test_skips_target_with_no_price() -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), equity=100_000)
    ctx.get_recent_bars = AsyncMock(return_value=pd.DataFrame({"c": []}))
    strat = _strat(ctx, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.submit_order.assert_not_called()


# ---- live equity / sizing knobs ------------------------------------------------

async def test_live_equity_preferred_over_estimate() -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=100.0, equity=50_000)
    strat = _strat(ctx, top_quantile=1.0, initial_equity_estimate=100_000)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    # live equity 50k (not the 100k estimate) → 50k/1/100 = 500 shares
    assert _orders(ctx)["AAA"] == ("buy", Decimal(500))


async def test_falls_back_to_estimate_when_no_live_equity() -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=100.0, equity=None)
    strat = _strat(ctx, top_quantile=1.0, initial_equity_estimate=100_000)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal(1000))  # 100k estimate / 100


async def test_cash_buffer_and_max_position_cap() -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000)
    # 10% cash buffer → 90k investable; max_position 10% → cap 9k → 90 shares
    strat = _strat(ctx, top_quantile=1.0, cash_buffer_pct=0.10, max_position_pct=0.10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal(90))


async def test_turnover_threshold_skips_small_adjustment() -> None:
    # target_qty 1000 (100k/100), held 995 → delta 5 → 5*100=500 < 100k*0.03 → skip
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={"AAA": 995}, price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, min_trade_pct=0.03)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.submit_order.assert_not_called()  # adjustment too small → no churn


# ---- rank hysteresis -----------------------------------------------------------

async def test_hysteresis_keeps_boundary_held_name() -> None:
    # core = top 20% of 5 = 1 name (AAA); buffer 0.2 → zone = top 40% = {AAA,BBB}.
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", 0.5), ("DDD", 0.2), ("EEE", 0.1)])
    ctx = _ctx(["AAA", "BBB", "CCC", "DDD", "EEE"], scores, holdings={"BBB": 10}, equity=100_000)
    strat = _strat(ctx, top_quantile=0.2, rebalance_buffer_rank_pct=0.2, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    # BBB held + within buffer zone → kept (not sold to flat)
    assert not (orders.get("BBB", ("", 0))[0] == "sell" and orders["BBB"][1] == Decimal(10))


# ---- market-regime filter ------------------------------------------------------

def _spy(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"c": values})


async def test_regime_bearish_goes_to_cash() -> None:
    # 201 bars (days+1); MA over the first 200 ≈ 95.1, latest bar 80 < MA → bearish
    spy = _spy([100.0] * 151 + [80.0] * 50)
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), holdings={"AAA": 10},
               equity=100_000, spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders["AAA"] == ("sell", Decimal(10))  # risk-off → exit to cash
    assert all(side == "sell" for side, _ in orders.values())  # no buys


async def test_regime_bullish_trades_normally() -> None:
    # 201 bars; MA over the first 200 ≈ 89.8, latest bar 120 > MA → bullish
    spy = _spy([80.0] * 151 + [120.0] * 50)
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), equity=100_000, spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"][0] == "buy"  # bull → trades


async def test_regime_unavailable_fails_open() -> None:
    # SPY not in symbols → get_recent_bars returns 1 row < threshold → fail open (trade)
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), equity=100_000)  # no SPY, no spy_bars
    strat = _strat(ctx, use_market_regime_filter=True, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"][0] == "buy"  # filter unavailable → fail open, still trades
    assert any("regime_filter_unavailable_failopen" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


# ---- order pacing --------------------------------------------------------------

async def test_order_pacing_sleeps_between_submits(monkeypatch) -> None:
    """With order_pacing_seconds > 0, each submission is followed by a sleep so a
    multi-name burst spreads under the per-strategy order-rate cap."""
    import strategies_user.templates.momentum_portfolio as mod

    slept: list[float] = []

    async def _fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(mod.asyncio, "sleep", _fake_sleep)
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, max_names=10, order_pacing_seconds=0.5)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert slept == [0.5, 0.5]  # one paced sleep per submitted order (2 buys)


async def test_order_pacing_zero_no_sleep(monkeypatch) -> None:
    import strategies_user.templates.momentum_portfolio as mod

    slept: list[float] = []
    monkeypatch.setattr(mod.asyncio, "sleep", lambda s: slept.append(s))
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, order_pacing_seconds=0.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert slept == []  # pacing disabled → no sleeps


# ---- portfolio EWMA-vol targeting (v0.4.0, review Priority 1) -------------------

def _spy_high_vol(n: int = 61, daily: float = 0.04) -> pd.DataFrame:
    """A SPY proxy series with high daily vol (alternating ±daily) → annualized
    vol well above a 0.15 target → vol-scaling cuts gross exposure."""
    px = [100.0]
    for i in range(n - 1):
        px.append(px[-1] * (1 + daily if i % 2 == 0 else 1 - daily))
    return pd.DataFrame({"c": px})


async def test_vol_scaling_off_by_default_leaves_sizing_unchanged() -> None:
    # High-vol SPY present, but use_vol_scaling stays False (the default) → full
    # exposure, identical to v0.3.0: 100k / 1 / 100 = 1000 shares.
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000,
               spy_bars=_spy_high_vol())
    strat = _strat(ctx, top_quantile=1.0)  # use_vol_scaling defaults False
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal(1000))


async def test_vol_scaling_reduces_exposure_in_high_vol() -> None:
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000,
               spy_bars=_spy_high_vol())
    strat = _strat(ctx, top_quantile=1.0, use_vol_scaling=True, vol_target_annual=0.15)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    qty = _orders(ctx)["AAA"][1]
    assert Decimal(0) < qty < Decimal(1000)  # gross scaled down, but still trading


async def test_vol_scaling_caps_at_full_in_low_vol() -> None:
    # Flat SPY → zero realized vol → scale capped at 1.0 → full exposure.
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000,
               spy_bars=pd.DataFrame({"c": [100.0] * 61}))
    strat = _strat(ctx, top_quantile=1.0, use_vol_scaling=True, vol_target_annual=0.15)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal(1000))


async def test_vol_scaling_fails_open_when_proxy_unavailable() -> None:
    # No SPY series → too few bars → fail open (full exposure), loudly logged.
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, use_vol_scaling=True, vol_target_annual=0.15)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal(1000))
    assert any("vol_scaling_unavailable_failopen" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


# ---- sector caps (P10 §3) ------------------------------------------------------

def test_sector_cap_disabled_by_default() -> None:
    assert MomentumPortfolio.default_params["max_sector_pct"] is None


async def test_sector_cap_diversifies_and_backfills() -> None:
    """max_sector_pct caps names per sector and backfills the freed slot from the
    next-best name in another sector (diversify without shrinking the book)."""
    scores = _scores([("AAA", 5.0), ("BBB", 4.0), ("CCC", 3.0), ("DDD", 2.0), ("EEE", 1.0)])
    ctx = _ctx(["AAA", "BBB", "CCC", "DDD", "EEE"], scores, price=100.0, equity=100_000)
    ctx.factors.sectors = MagicMock(return_value={
        "AAA": "Tech", "BBB": "Tech", "CCC": "Tech", "DDD": "Energy", "EEE": "Energy",
    })
    # top-4 by score = AAA,BBB,CCC,DDD (3 Tech, 1 Energy). max_per = floor(0.5*4)=2
    # → drop CCC (3rd Tech), backfill EEE (Energy) → {AAA,BBB,DDD,EEE}.
    strat = _strat(ctx, top_quantile=1.0, max_names=4, max_sector_pct=0.5)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    bought = {s for s, (side, _) in _orders(ctx).items() if side == "buy"}
    assert bought == {"AAA", "BBB", "DDD", "EEE"}


async def test_sector_cap_fails_open_when_sectors_unavailable() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, price=100.0, equity=100_000)
    ctx.factors.sectors = MagicMock(side_effect=RuntimeError("no sector data"))
    strat = _strat(ctx, top_quantile=1.0, max_names=4, max_sector_pct=0.5)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" in orders and "BBB" in orders  # fail open → both traded, no cap


async def test_sector_cap_unset_does_not_query_sectors() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, price=100.0, equity=100_000)
    ctx.factors.sectors = MagicMock(return_value={})
    strat = _strat(ctx, top_quantile=1.0, max_names=4)  # max_sector_pct defaults None
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.factors.sectors.assert_not_called()  # disabled → never looks up sectors


# ---- fractional shares (P10 §7) ------------------------------------------------

def test_fractional_shares_disabled_by_default() -> None:
    assert MomentumPortfolio.default_params["fractional_shares"] is False


async def test_fractional_shares_buys_sub_one_share() -> None:
    """With fractional on, a name priced ABOVE the per-name budget gets a
    fractional qty instead of flooring to 0 (the ~67%-deployment fix)."""
    # equity 100, 1 name → per_name 100; price 200 → 0.5 shares fractional.
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=200.0, equity=100)
    strat = _strat(ctx, top_quantile=1.0, max_names=1, fractional_shares=True)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["AAA"] == ("buy", Decimal("0.500000"))


async def test_whole_shares_floor_sub_one_to_zero() -> None:
    """Default (whole shares): the same below-one-share target floors to 0 → no
    order (this is exactly the under-deployment fractional mode fixes)."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=200.0, equity=100)
    strat = _strat(ctx, top_quantile=1.0, max_names=1)  # fractional defaults False
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.submit_order.assert_not_called()


# ---- daily gross-exposure overlay (P10 §2, ADR 0020) ---------------------------

def test_daily_overlay_disabled_by_default() -> None:
    assert MomentumPortfolio.default_params["use_daily_overlay"] is False


async def _overlay_strat(holdings, *, equity=10_000, price=100.0, target_gross=0.10, **over):
    """A strategy holding ``holdings`` with the overlay on; the vol math is stubbed via
    _overlay_target_gross so these tests isolate the RE-SIZE logic (the desired_gross
    math is unit-tested in test_overlay.py). base=equity (cash_buffer 0) → with all
    names at ``price``, current_gross = invested/equity."""
    from unittest.mock import AsyncMock as _AM
    ctx = _ctx(["AAA", "BBB", "SPY"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               holdings=holdings, price=price, equity=equity)
    strat = _strat(ctx, use_daily_overlay=True, **over)
    await strat.on_init()
    strat._overlay_target_gross = _AM(return_value=target_gross)  # type: ignore[method-assign]
    return strat, ctx


async def test_overlay_disabled_noops() -> None:
    """use_daily_overlay False → on_overlay_tick is inert (no orders, no vol read)."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), holdings={"AAA": 10},
               price=100.0, equity=10_000)
    strat = _strat(ctx)  # use_daily_overlay defaults False
    await strat.on_init()
    await strat.on_overlay_tick()
    ctx.submit_order.assert_not_called()


async def test_overlay_noop_when_flat() -> None:
    """No holdings → the overlay never SELECTS, so it cannot re-enter — pure no-op."""
    strat, ctx = await _overlay_strat({})  # no positions
    await strat.on_overlay_tick()
    ctx.submit_order.assert_not_called()


async def test_overlay_scales_down_in_high_vol() -> None:
    """current_gross 0.20 (2×10×100 / 10k), target 0.10 → ratio 0.5 → each held name
    trimmed from 10 → 5 (SELL 5), composition preserved (equal names, equal trims)."""
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.10)
    await strat.on_overlay_tick()
    orders = _orders(ctx)
    assert orders["AAA"] == ("sell", Decimal(5))
    assert orders["BBB"] == ("sell", Decimal(5))


async def test_overlay_scales_up_toward_target() -> None:
    """target 0.40 vs current 0.20 → ratio 2.0 → each held name 10 → 20 (BUY 10).
    Adds to EXISTING names only — never a new symbol."""
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.40)
    await strat.on_overlay_tick()
    orders = _orders(ctx)
    assert orders["AAA"] == ("buy", Decimal(10))
    assert orders["BBB"] == ("buy", Decimal(10))


async def test_overlay_drift_gate_skips() -> None:
    """target within overlay_drift_pct of current gross → skip (no churn)."""
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.205)  # cur 0.20
    await strat.on_overlay_tick()
    ctx.submit_order.assert_not_called()


async def test_overlay_never_touches_unheld_names() -> None:
    """Only held names are re-sized; a high-scored but UNHELD name is never bought
    (the overlay does not select)."""
    strat, ctx = await _overlay_strat({"AAA": 10}, target_gross=0.05)  # only AAA held
    await strat.on_overlay_tick()
    orders = _orders(ctx)
    assert set(orders) == {"AAA"}  # BBB (unheld) never traded


async def test_overlay_sets_gross_gauge_and_counter() -> None:
    """A scaled tick exports the gross gauge (= target; current/avg/min are PromQL
    over it) and increments the 'scaled' outcome counter."""
    from prometheus_client import REGISTRY

    from app.observability.metrics import overlay_actions_total

    before = REGISTRY.get_sample_value(
        "workbench_overlay_actions_total", {"strategy_id": "1", "outcome": "scaled"}
    ) or 0.0
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.10)
    await strat.on_overlay_tick()

    gross = REGISTRY.get_sample_value("workbench_overlay_gross", {"strategy_id": "1"})
    assert gross == pytest.approx(0.10)
    after = REGISTRY.get_sample_value(
        "workbench_overlay_actions_total", {"strategy_id": "1", "outcome": "scaled"}
    )
    assert after == pytest.approx(before + 1.0)
    _ = overlay_actions_total  # imported for clarity; assertion reads via REGISTRY


async def test_overlay_idempotent_resize_then_noop() -> None:
    """Restart-safe idempotency: after a re-size brings the book to target, a second
    tick at the same target finds the book already there → no further orders. Modelled
    by updating holdings to the re-sized qty and re-running."""
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.10)
    await strat.on_overlay_tick()  # trims 10 → 5
    # Book is now at the target (5 each → gross 0.10); a re-fire must no-op.
    ctx.get_position_for = AsyncMock(side_effect=lambda s: _pos(5) if s in ("AAA", "BBB") else None)
    ctx.submit_order.reset_mock()
    await strat.on_overlay_tick()
    ctx.submit_order.assert_not_called()


async def test_fractional_shares_deploys_more_than_whole() -> None:
    """Fractional target qty exceeds the whole-share floor for a pricey name."""
    # per_name = 20000 (100k/5 = 20k), price 271.78 → 73.59 frac vs 73 whole.
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=271.78, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, max_names=5, max_position_pct=0.20,
                   fractional_shares=True)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    qty = _orders(ctx)["AAA"][1]
    assert qty > Decimal(73) and qty < Decimal(74)  # fractional, not floored to 73
