"""P9 §4 — momentum-portfolio template (v0.2, review-hardened).

Covers schema parity, weekly rebalance + failure-retry, selection/diff, the
bail-out taxonomy, the market-regime filter, live-equity sizing, the turnover
threshold, rank hysteresis, and the rejection policy — all against a synthetic
StrategyContext (no engine, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def _scores(
    order: list[tuple[str, float]],
    raw: dict[str, float] | None = None,
) -> pd.DataFrame:
    """The factor frame as the ENGINE actually returns it: [momentum, winsorized, zscore, rank,
    score], with `score == zscore`.

    ⚠ Until v0.9.0 this helper produced a `score` column and NOTHING ELSE. The real engine has
    always returned a `momentum` column too — the RAW trailing return. Because the mock omitted it,
    no test in this file could express, let alone catch, the A1 defect: that a positive z-score
    never implied positive absolute momentum, so the book could go fully long names that were
    falling. The mock was not merely incomplete; it made the bug invisible.

    `raw` overrides the raw momentum per ticker. It defaults to a small POSITIVE value so the
    pre-existing tests, which only ever cared about ranking, keep meaning what they meant.
    """
    tickers = [t for t, _ in order]
    z = [s for _, s in order]
    raw = raw or {}
    momentum = [raw.get(t, 0.10 + 0.01 * i) for i, t in enumerate(reversed(tickers))][::-1]
    df = pd.DataFrame(
        {
            "momentum": momentum,
            "winsorized": z,
            "zscore": z,
            "rank": list(range(1, len(tickers) + 1)),
            "score": z,
        },
        index=tickers,
    )
    df.index.name = "ticker"
    return df


def _spy_dated(*, above: bool = True, n: int = 201, stale_days: int = 0) -> pd.DataFrame:
    """A market-proxy series with REAL timestamps, ending `stale_days` before the tick.

    The timestamps are the point: A5 judges staleness from the DATA, not from a remembered
    "last good" value that a restart would silently reset to "perfectly fresh".
    """
    closes = [100.0] * (n - 1) + [110.0 if above else 90.0]
    end = WK1_A.date() - timedelta(days=stale_days)
    idx = pd.to_datetime([end - timedelta(days=n - 1 - i) for i in range(n)])
    df = pd.DataFrame({"c": closes}, index=idx)
    df.index.name = "t"
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
    # No in-flight orders by default → buy sizing is unaffected. Tests that
    # exercise idempotency override this.
    ctx.pending_buy_qty = AsyncMock(return_value={})
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


async def test_momentum_window_defaults_to_12_MINUS_1() -> None:
    """A3: the book ranks on 12-1 (252/21), not 252/0.

    252/0 includes the most recent month, contaminating the signal with short-term reversal,
    earnings gaps and spike noise. It was never the intended window: `default_params` merged
    silently at registration and the stored strategy row did not override it, so the documented
    window and the running one diverged with nothing to say so.
    """
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    _, kwargs = ctx.factors.momentum_scores.call_args
    assert kwargs["lookback_days"] == 252
    assert kwargs["skip_days"] == 21


async def test_the_effective_merged_parameters_are_LOGGED_on_load() -> None:
    """A3: the 252/0 drift was only ever discoverable by archaeology. The window the strategy will
    actually rank on is now stated out loud every time it loads."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx)
    await strat.on_init()
    eff = [c.kwargs.get("payload", {}) for c in ctx.log_signal.call_args_list
           if c.kwargs.get("payload", {}).get("reason") == "effective_params"]
    assert eff, "the effective parameters were not logged"
    assert eff[0]["momentum_lookback_days"] == 252
    assert eff[0]["momentum_skip_days"] == 21
    assert eff[0]["version"] == "0.9.0"


async def test_an_incoherent_rank_band_is_REFUSED_not_traded() -> None:
    """hold_rank < entry_rank would sell a name the very week it was bought. That is not a
    preference to be honoured — it is incoherent, and it stops the strategy loading."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx, entry_rank=5, hold_rank=3)
    with pytest.raises(ValueError, match="incoherent rank bands"):
        await strat.on_init()


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
    """A2: entry is by ABSOLUTE RANK now. entry_rank=2 -> {AAA, BBB}; CCC is held but ranks 3, which
    is outside hold_rank=2, and its exit confirms, so it is sold."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", 0.0), ("DDD", -1.0), ("EEE", -2.0)])
    ctx = _ctx(["AAA", "BBB", "CCC", "DDD", "EEE"], scores,
               holdings={"CCC": 10, "AAA": 5}, price=100.0, equity=100_000)
    strat = _strat(ctx, entry_rank=2, hold_rank=2, exit_confirm_closes=1, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    # equity 100k / k=2 = 50k per name; price 100 → 500 target
    assert orders["CCC"] == ("sell", Decimal(10))   # rank 3 > hold_rank 2 → exit
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


async def test_regime_unavailable_goes_FLAT_and_no_longer_fails_open() -> None:
    """A5: the regime filter must NEVER fail open again.

    v0.8 traded FULLY EXPOSED when the market series was missing. That compounds with the A1 defect
    in exactly the worst conditions: a data outage during a drawdown produced a fully-invested,
    possibly negative-momentum book with the one safety filter silently disabled. Blind now means
    flat, not bold.
    """
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), equity=100_000)  # no SPY, no spy_bars
    strat = _strat(ctx, use_market_regime_filter=True, entry_rank=1)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" not in orders or orders["AAA"][0] != "buy", (
        "no regime data, yet the book still bought — this is the fail-open defect")
    assert any("regime_data_unavailable_flat" in str(c.kwargs.get("payload", {}))
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

def test_fractional_shares_enabled_by_default() -> None:
    # Default ON: whole-share rounding under-deploys the book (single $400 shares vs a
    # ~$600 per-name budget → ~63% deployed). Fractional deploys ~fully; non-fractionable
    # names reject gracefully.
    assert MomentumPortfolio.default_params["fractional_shares"] is True


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
    """Whole-share mode (fractional_shares=False): a below-one-share target floors to 0 → no
    order. Fractional is now the DEFAULT (deploys ~fully); this is the opt-out behavior it fixes."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), price=200.0, equity=100)
    strat = _strat(ctx, top_quantile=1.0, max_names=1, fractional_shares=False)
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


async def test_overlay_partial_fill_converges_next_tick() -> None:
    """P11 §5 (ADR 0021 property 6): a re-size that only PARTIALLY fills leaves the book
    between states; the next tick converges it the rest of the way toward target, never
    compounding or oscillating. Self-heal = the actor's own next scheduled tick, computed
    against the LIVE book (no stored 'applied' flag — restart-safe by construction)."""
    strat, ctx = await _overlay_strat({"AAA": 10, "BBB": 10}, target_gross=0.10)
    await strat.on_overlay_tick()  # wants to trim 10 → 5 each
    # Partial fill: the SELLs only partly execute → book settles at 7 each (gross 0.14),
    # still above the 0.10 target.
    ctx.get_position_for = AsyncMock(side_effect=lambda s: _pos(7) if s in ("AAA", "BBB") else None)
    ctx.submit_order.reset_mock()
    await strat.on_overlay_tick()  # converges the remaining gap: 7 → 5 (SELL 2 each)
    orders = _orders(ctx)
    assert orders["AAA"] == ("sell", Decimal(2))
    assert orders["BBB"] == ("sell", Decimal(2))
    # Fully applied now → a further tick is a no-op (gap closed, never compounded).
    ctx.get_position_for = AsyncMock(side_effect=lambda s: _pos(5) if s in ("AAA", "BBB") else None)
    ctx.submit_order.reset_mock()
    await strat.on_overlay_tick()
    ctx.submit_order.assert_not_called()


# ---- P10 §5 regime overlay plumbing (breadth / VIX) ----------------------------

def test_regime_overlay_disabled_by_default() -> None:
    assert MomentumPortfolio.default_params["use_breadth_overlay"] is False
    assert MomentumPortfolio.default_params["use_vix_overlay"] is False


def _calm_spy_ctx():
    """A ctx with a flat SPY series (calm → vol-target gross caps at 1.0), so the
    regime factor alone determines _overlay_target_gross."""
    flat = pd.DataFrame({"c": [100.0] * 70})
    return _ctx(["AAA", "SPY"], _scores([("AAA", 1.0)]), price=100.0, equity=10_000, spy_bars=flat)


async def test_overlay_target_gross_off_ignores_regime() -> None:
    """Regime params off → factors never read → gross stays the vol target (1.0)."""
    ctx = _calm_spy_ctx()
    ctx.factors.market_breadth = MagicMock(return_value=0.20)  # would de-risk IF read
    strat = _strat(ctx, use_daily_overlay=True)  # both regime flags default False
    await strat.on_init()
    assert await strat._overlay_target_gross() == pytest.approx(1.0)
    ctx.factors.market_breadth.assert_not_called()


async def test_overlay_target_gross_applies_breadth() -> None:
    """use_breadth_overlay on + low breadth (≤floor) → gross fully de-risked."""
    ctx = _calm_spy_ctx()
    ctx.factors.market_breadth = MagicMock(return_value=0.20)
    strat = _strat(ctx, use_daily_overlay=True, use_breadth_overlay=True)
    await strat.on_init()
    assert await strat._overlay_target_gross() == 0.0


async def test_overlay_target_gross_applies_vix() -> None:
    """use_vix_overlay on + high VIX percentile (≥stress) → gross fully de-risked."""
    ctx = _calm_spy_ctx()
    ctx.factors.vix_percentile = MagicMock(return_value=0.95)
    strat = _strat(ctx, use_daily_overlay=True, use_vix_overlay=True)
    await strat.on_init()
    assert await strat._overlay_target_gross() == 0.0


async def test_overlay_target_gross_regime_fails_open() -> None:
    """A regime-read error → fail open (no cut), never crash the tick."""
    ctx = _calm_spy_ctx()
    ctx.factors.market_breadth = MagicMock(side_effect=RuntimeError("store gone"))
    strat = _strat(ctx, use_daily_overlay=True, use_breadth_overlay=True)
    await strat.on_init()
    assert await strat._overlay_target_gross() == pytest.approx(1.0)


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


# ---- rebalance idempotency: net against in-flight buys (incident 2026-06-22) ----

async def test_inflight_buys_are_not_reordered() -> None:
    """A rebalance re-run while the basket is still in flight submits nothing."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), equity=20_000)
    ctx.pending_buy_qty = AsyncMock(
        return_value={"AAA": Decimal(100), "BBB": Decimal(100)}
    )
    strat = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx) == {}  # both target buys already on the way → skipped


async def test_partial_inflight_reduces_buy() -> None:
    """An in-flight partial only shrinks the new buy; it never flips to a sell."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), equity=20_000)
    ctx.pending_buy_qty = AsyncMock(return_value={"AAA": Decimal(40)})  # 40 of 100
    strat = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders["AAA"] == ("buy", Decimal(60))    # 100 target − 40 in flight
    assert orders["BBB"] == ("buy", Decimal(100))   # none in flight → full


async def test_reactivation_does_not_duplicate_basket() -> None:
    """Incident shape: after the first basket is routed, a fresh instance (on_init
    resets the in-memory weekly guard) must NOT re-buy — in-flight orders net out."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, equity=20_000)
    strat1 = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat1.on_init()
    await strat1.on_bar(_bar(WK1_A))
    assert _orders(ctx) == {
        "AAA": ("buy", Decimal(100)),
        "BBB": ("buy", Decimal(100)),
    }

    # Those orders are now in flight; reactivate (new instance, fresh guard).
    ctx.submit_order.reset_mock()
    ctx.pending_buy_qty = AsyncMock(
        return_value={"AAA": Decimal(100), "BBB": Decimal(100)}
    )
    strat2 = _strat(ctx, top_quantile=1.0, max_names=10)
    await strat2.on_init()              # weekly guard reset to None
    await strat2.on_bar(_bar(WK1_B))    # same ISO week, different instance
    assert _orders(ctx) == {}           # nothing re-ordered


# =====================================================================================
# v0.9.0 — Workstream A. Each of these FAILS on v0.8.0. They are the fixes, stated as
# assertions rather than as intentions.
# =====================================================================================
async def test_A1_a_positive_zscore_with_NEGATIVE_raw_momentum_is_not_bought() -> None:
    """A1. The whole defect in one test.

    In a broad drawdown every name can be falling, yet the cross-sectional z-score is relative, so
    the least-bad name still scores +2.0 and cleared the v0.8 `min_score = 0` floor. The book would
    then go fully long a stock that is DOWN 30%. `min_score` was never a momentum filter; it was a
    ranking floor wearing one's clothes.
    """
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)], raw={"AAA": -0.30, "BBB": -0.10})
    ctx = _ctx(["AAA", "BBB"], scores, equity=100_000, spy_bars=_spy_dated(above=True))
    strat = _strat(ctx, entry_rank=2, hold_rank=2)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert not [s for s, (side, _) in orders.items() if side == "buy"], (
        f"bought {list(orders)} — every candidate has NEGATIVE absolute momentum")


async def test_A1_the_raw_filter_is_INDEPENDENT_of_the_zscore_floor() -> None:
    """Two separate questions: is it strong relative to its peers, and is it going up at all. A name
    can pass one and fail the other, which is exactly why they cannot be collapsed into one gate."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.5)], raw={"AAA": -0.05, "BBB": 0.20})
    ctx = _ctx(["AAA", "BBB"], scores, equity=100_000, spy_bars=_spy_dated(above=True))
    strat = _strat(ctx, entry_rank=2, hold_rank=2)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" not in orders                       # best z-score, but falling -> refused
    assert orders["BBB"][0] == "buy"                 # weaker z-score, but actually rising


async def test_A2_a_held_name_that_has_decayed_far_past_the_band_is_SOLD() -> None:
    """A2. v0.8's buffer was top_quantile + 5% ≈ the top 25% ≈ rank ~50 of ~200. Since this book has
    no per-name stops, rank decay is its ONLY exit discipline — so a "top-5" strategy could hold a
    rank-30 name indefinitely and call it hysteresis."""
    order = [(f"T{i:02d}", 3.0 - 0.1 * i) for i in range(40)]
    ctx = _ctx([t for t, _ in order], _scores(order), holdings={"T30": 10},
               equity=100_000, price=100.0, spy_bars=_spy_dated(above=True))
    strat = _strat(ctx, entry_rank=5, hold_rank=10, exit_confirm_closes=1, max_names=5)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["T30"] == ("sell", Decimal(10)), "a rank-31 name was retained"


async def test_A2_one_breach_is_not_enough___the_exit_needs_CONFIRMATION() -> None:
    """A single bad close is noise; the exit confirms over consecutive closes.

    The confirmation is read from the PIT factor store, NOT from a counter in memory. That is the
    whole point: an in-memory breach count is silently reset by every strategy reload, and reloads
    are routine — so a decaying name would have its count zeroed and be re-held, defeating the only
    exit discipline this book has, precisely when it is churning enough to warrant a reload.

    The book is left with free slots here, so the DISPLACEMENT rule (a separate trigger) cannot
    evict T30 and confuse what is being tested.
    """
    order = [(f"T{i:02d}", 3.0 - 0.1 * i) for i in range(40)]
    ctx = _ctx([t for t, _ in order], _scores(order), holdings={"T30": 10},
               equity=100_000, price=100.0, spy_bars=_spy_dated(above=True))
    ctx.factors.momentum_scores.side_effect = [
        _scores(order),                                                        # now: T30 rank 31
        _scores([("T30", 3.0)] + [(k, s) for k, s in order if k != "T30"]),    # prior: T30 rank 1
    ]
    strat = _strat(ctx, entry_rank=5, hold_rank=10, exit_confirm_closes=2, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    sells = {s for s, (side, _) in _orders(ctx).items() if side == "sell"}
    assert "T30" not in sells, "sold on a single unconfirmed breach"


async def test_A2_a_CONFIRMED_breach_across_both_closes_does_exit() -> None:
    """The other half: confirmation must not become a way to never sell anything."""
    order = [(f"T{i:02d}", 3.0 - 0.1 * i) for i in range(40)]
    ctx = _ctx([t for t, _ in order], _scores(order), holdings={"T30": 10},
               equity=100_000, price=100.0, spy_bars=_spy_dated(above=True))
    # The prior frame must be a DISTINCT close (an identical one is not two closes, and the
    # not-distinct guard correctly refuses to confirm from it). So perturb two other names while
    # leaving T30 outside the hold band on both.
    prior = [("T01", 5.0), *[(k, s) for k, s in order if k != "T01"]]   # a different RANKING
    ctx.factors.momentum_scores.side_effect = [_scores(order), _scores(prior)]  # T30 rank 31 twice
    strat = _strat(ctx, entry_rank=5, hold_rank=10, exit_confirm_closes=2, max_names=10)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx)["T30"] == ("sell", Decimal(10)), "a twice-confirmed breach was not sold"


async def test_A2_a_challenger_needs_a_MATERIAL_edge_to_displace_a_holding() -> None:
    """Ranks 5 and 6 swap constantly on noise. Without the z-score advantage, every such swap would
    churn the book — which is the outcome the rule exists to prevent, not a side effect of it."""
    order = [("AAA", 2.00), ("BBB", 1.99), ("CCC", 1.98)]
    ctx = _ctx(["AAA", "BBB", "CCC"], _scores(order), holdings={"BBB": 10, "CCC": 10},
               equity=100_000, price=100.0, spy_bars=_spy_dated(above=True))
    strat = _strat(ctx, entry_rank=3, hold_rank=3, exit_confirm_closes=1,
                   max_names=2, replace_score_advantage=0.30)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    sells = {s for s, (side, _) in _orders(ctx).items() if side == "sell"}
    assert not sells, "AAA displaced a holding on a 0.01 z-score edge"


async def test_A5_stale_regime_data_REDUCES_gross_rather_than_ignoring_the_filter() -> None:
    """A5. Between 'perfectly fine' and 'unknown' there is a middle, and v0.8 had no name for it: it
    either trusted the regime or ignored it entirely. Stale data now buys a smaller book."""
    scores = _scores([("AAA", 2.0)])
    fresh = _ctx(["AAA", "SPY"], scores, equity=100_000, price=100.0,
                 spy_bars=_spy_dated(above=True))
    s1 = _strat(fresh, entry_rank=1, max_names=1, cash_buffer_pct=0.0,
                use_market_regime_filter=True)
    await s1.on_init()
    await s1.on_bar(_bar(WK1_A))
    full = _orders(fresh)["AAA"][1]

    stale = _ctx(["AAA", "SPY"], scores, equity=100_000, price=100.0,
                 spy_bars=_spy_dated(above=True, stale_days=3))
    s2 = _strat(stale, entry_rank=1, max_names=1, cash_buffer_pct=0.0,
                use_market_regime_filter=True,
                regime_stale_max_days=2, regime_degraded_gross=0.5)
    await s2.on_init()
    await s2.on_bar(_bar(WK1_A))
    degraded = _orders(stale)["AAA"][1]

    assert degraded < full, "stale regime data bought the same size as fresh data"
    assert abs(float(degraded) / float(full) - 0.5) < 0.02
