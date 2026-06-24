"""Phase 2 — low-volatility template (LOW-001 Capability Promotion).

Covers schema parity, the weekly rebalance cadence + failure-retry guard, the
top-quintile lowest-volatility selection (``ceil(N · top_quantile)`` held count,
matching the research harness), equal-weight sizing, SPY exclusion, the
factor-unavailable bail-out (→ HOLD), the market-regime filter, and the rejection
policy — all against a synthetic StrategyContext (no engine, no DB).

The selection mirrors the validated LOW-001 V1 research (``run_momentum_backtest``
with ``score_fn=low_vol_score``, ``top_quantile=0.20``): rank by −(trailing realized
vol), hold the lowest-vol quintile equal-weight. These tests pin that behavior so the
promoted strategy stays faithful to the evidence it was validated on (the
Methodology-Transfer discipline)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.factor_data.accessor import FactorDataUnavailable
from app.strategies.context import Bar
from strategies_user.templates.low_volatility import LowVolatility

WK1_A = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)   # Mon
WK1_B = datetime(2026, 6, 8, 14, 1, tzinfo=UTC)   # same ISO week
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)    # next ISO week


def _bar(ts: datetime, symbol: str = "AAA") -> Bar:
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    """A low_vol_scores-shaped frame: indexed by ticker, ``score`` column, already
    sorted by score descending (lowest vol first) — exactly what the accessor returns."""
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
        **LowVolatility.default_params,
        "use_market_regime_filter": False,
        "cash_buffer_pct": 0.0,
        "max_position_pct": 1.0,
        "min_trade_pct": 0.0,
        "order_pacing_seconds": 0.0,  # no real sleeps in tests
        **over,
    }


def _ctx(symbols, scores, holdings=None, price=100.0, equity=None, spy_bars=None):
    """Synthetic StrategyContext driving ``ctx.factors.low_vol_scores``."""
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.low_vol_scores = MagicMock(return_value=scores)
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
    return LowVolatility(ctx=ctx, params=_params(**over))


# ---- schema / cadence ----------------------------------------------------------

def test_schema_matches_default_params() -> None:
    """The typed form is derived from params_schema; it must list exactly the
    params the code reads (CLAUDE.md: schema↔code drift breaks the form)."""
    assert set(LowVolatility.params_schema) == set(LowVolatility.default_params)


def test_research_frozen_defaults() -> None:
    """The validated LOW-001 V1 parameters must not silently drift: 252-day realized
    vol and the top-quintile (0.20) are frozen from the research."""
    assert LowVolatility.default_params["vol_lookback_days"] == 252
    assert LowVolatility.default_params["top_quantile"] == 0.20
    assert LowVolatility.schedule == "0 14 * * mon"


async def test_rebalances_once_per_iso_week() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → no second rebalance
    assert ctx.factors.low_vol_scores.call_count == 1
    await strat.on_bar(_bar(WK2))    # new week → rebalances again
    assert ctx.factors.low_vol_scores.call_count == 2


def _last_kwargs(ctx) -> dict:
    _, kwargs = ctx.factors.low_vol_scores.call_args
    return kwargs


async def test_vol_window_defaults_to_252() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _last_kwargs(ctx)["lookback_days"] == 252


async def test_unexpected_failure_marks_week_and_does_not_retry_same_week() -> None:
    """The week is marked at the START of the attempt, so a rebalance that raises
    is NOT retried on the next per-symbol tick in the same week (storm guard)."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]))
    ctx.factors.low_vol_scores = MagicMock(side_effect=ValueError("boom"))  # not a _HOLD_ON
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → NO retry
    assert ctx.factors.low_vol_scores.call_count == 1
    assert any("rebalance_failed" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
    await strat.on_bar(_bar(WK2))    # next week → attempts again
    assert ctx.factors.low_vol_scores.call_count == 2


# ---- low-vol selection --------------------------------------------------------

async def test_holds_lowest_vol_quintile() -> None:
    """Top ``ceil(N · top_quantile)`` names by score (= lowest realized vol). With
    10 names and 0.20, ceil(10·0.20)=2 → the two highest-score (lowest-vol) names."""
    order = [(f"S{i:02d}", -0.10 - 0.01 * i) for i in range(10)]  # S00 highest score → lowest vol
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=0.20)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"S00", "S01"}
    assert all(side == "buy" for side, _ in orders.values())


async def test_equal_weight_within_book() -> None:
    """Each held name gets an equal target notional = investable / n_names."""
    order = [("AAA", -0.1), ("BBB", -0.2), ("CCC", -0.3), ("DDD", -0.4)]
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0)  # hold all 4; $100k / 4 / $100 = 250 each
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"AAA", "BBB", "CCC", "DDD"}
    assert all(qty == Decimal(250) for _, qty in orders.values())


async def test_excludes_market_proxy_from_book() -> None:
    """SPY may be registered only for the regime filter; it is never selected or
    held as a portfolio position, even with a strong (low-vol) score."""
    order = [("SPY", -0.01), ("AAA", -0.1), ("BBB", -0.2)]  # SPY has the best score
    ctx = _ctx(["SPY", "AAA", "BBB"], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, market_filter_symbol="SPY")
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "SPY" not in _orders(ctx)


async def test_sells_names_leaving_the_book() -> None:
    """A held name that drops out of the lowest-vol quintile is sold to flat."""
    order = [("AAA", -0.1), ("BBB", -0.2), ("CCC", -0.9)]  # CCC = highest vol → excluded
    ctx = _ctx([t for t, _ in order], _scores(order),
               holdings={"CCC": 10}, price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=0.20)  # ceil(3·0.20)=1 → only AAA held
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx).get("CCC") == ("sell", Decimal(10))


# ---- bail-out taxonomy --------------------------------------------------------

async def test_factor_unavailable_holds() -> None:
    """No factor data → HOLD the book (no orders), don't crash the tick."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]))
    ctx.factors.low_vol_scores = MagicMock(side_effect=FactorDataUnavailable("no store"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert ctx.submit_order.await_count == 0
    assert any("factor_unavailable_hold" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


# ---- market-regime filter -----------------------------------------------------

async def test_regime_bear_moves_to_cash() -> None:
    """When SPY is below its MA, the book goes to cash (held names sold, no buys)."""
    spy = pd.DataFrame({"c": [300.0 - i for i in range(201)]})  # falling → last < MA
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(["AAA", "BBB", "SPY"], _scores(order),
               holdings={"AAA": 5}, equity=100_000, spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True, market_filter_symbol="SPY",
                   market_ma_days=200)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders.get("AAA") == ("sell", Decimal(5))  # exited to cash
    assert not any(side == "buy" for side, _ in orders.values())


# ---- rejection policy ---------------------------------------------------------

async def test_order_rejection_is_logged_not_raised() -> None:
    """A risk rejection on one order is logged and the rebalance continues."""
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason="position_size_exceeded"))
    strat = _strat(ctx, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))  # must not raise
    assert any("rejected" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
