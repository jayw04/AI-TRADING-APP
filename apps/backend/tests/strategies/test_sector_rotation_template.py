"""P12 §4 — sector-rotation template (SEC-001 Capability Promotion).

Covers schema parity, the weekly rebalance cadence + failure-retry guard, the
top-K sector selection → full-basket construction, sector ranking by mean
momentum, the bail-out taxonomy (factor / sector-data unavailable → HOLD), the
market-regime filter, SPY exclusion, equal-weight sizing, and the rejection
policy — all against a synthetic StrategyContext (no engine, no DB).

The construction mirrors the validated SEC-001 V2 research
(``scripts/sector_rotation_v2_research.py``): rank sectors by mean 12-month
momentum, take the top-K, hold every name in each chosen sector equal-weight.
These tests pin that behavior so the promoted strategy stays faithful to the
research it was validated on (the Methodology-Transfer discipline)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.factor_data.accessor import FactorDataUnavailable
from app.strategies.context import Bar
from strategies_user.templates.sector_rotation import SectorRotation

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
        **SectorRotation.default_params,
        "use_market_regime_filter": False,
        "cash_buffer_pct": 0.0,
        "max_position_pct": 1.0,
        "min_trade_pct": 0.0,
        "order_pacing_seconds": 0.0,  # no real sleeps in tests
        **over,
    }


def _ctx(symbols, scores, sectors, holdings=None, price=100.0, equity=None, spy_bars=None):
    """Synthetic StrategyContext. ``sectors`` maps ticker -> sector name (or None)."""
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)
    ctx.factors.sectors = MagicMock(return_value=dict(sectors))
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
    return SectorRotation(ctx=ctx, params=_params(**over))


# ---- schema / cadence ----------------------------------------------------------

def test_schema_matches_default_params() -> None:
    """The typed form is derived from params_schema; it must list exactly the
    params the code reads (CLAUDE.md: schema↔code drift breaks the form)."""
    assert set(SectorRotation.params_schema) == set(SectorRotation.default_params)


def test_research_frozen_defaults() -> None:
    """The validated SEC-001 V2 parameters must not silently drift: 12-month
    momentum (252/0) and K=3 sectors are frozen from the research."""
    assert SectorRotation.default_params["sector_momentum_lookback_days"] == 252
    assert SectorRotation.default_params["sector_momentum_skip_days"] == 0
    assert SectorRotation.default_params["top_k_sectors"] == 3
    assert SectorRotation.schedule == "0 14 * * mon"


async def test_rebalances_once_per_iso_week() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               sectors={"AAA": "Tech", "BBB": "Energy"})
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → no second rebalance
    assert ctx.factors.momentum_scores.call_count == 1
    await strat.on_bar(_bar(WK2))    # new week → rebalances again
    assert ctx.factors.momentum_scores.call_count == 2


async def test_momentum_window_defaults_to_12m() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               sectors={"AAA": "Tech", "BBB": "Energy"})
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    _, kwargs = ctx.factors.momentum_scores.call_args
    assert kwargs["lookback_days"] == 252
    assert kwargs["skip_days"] == 0


async def test_unexpected_failure_marks_week_and_does_not_retry_same_week() -> None:
    """The week is marked at the START of the attempt, so a rebalance that raises
    is NOT retried on the next per-symbol tick in the same week (storm guard)."""
    ctx = _ctx(["AAA"], _scores([("AAA", 1.0)]), sectors={"AAA": "Tech"})
    ctx.factors.momentum_scores = MagicMock(side_effect=ValueError("boom"))  # not a _HOLD_ON
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → NO retry
    assert ctx.factors.momentum_scores.call_count == 1
    assert any("rebalance_failed" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
    await strat.on_bar(_bar(WK2))    # next week → attempts again
    assert ctx.factors.momentum_scores.call_count == 2


# ---- sector selection / basket construction -----------------------------------

async def test_selects_top_k_sectors_full_baskets() -> None:
    """Top-K sectors by mean momentum, holding EVERY name in each chosen sector."""
    scores = _scores([
        ("AAA", 2.0), ("BBB", 1.5),   # Tech     mean 1.75  (rank 1)
        ("CCC", 1.0), ("DDD", 0.5),   # Energy   mean 0.75  (rank 2)
        ("EEE", 0.0), ("FFF", -0.5),  # Health   mean -0.25 (rank 3)
        ("GGG", -1.0),                # Finance  mean -1.0  (rank 4)
    ])
    sectors = {"AAA": "Tech", "BBB": "Tech", "CCC": "Energy", "DDD": "Energy",
               "EEE": "Health", "FFF": "Health", "GGG": "Finance"}
    ctx = _ctx(list(sectors), scores, sectors=sectors, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=2)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    # Top-2 sectors = Tech + Energy → all four names bought, none from Health/Finance.
    assert set(orders) == {"AAA", "BBB", "CCC", "DDD"}
    assert all(side == "buy" for side, _ in orders.values())


async def test_ranks_sectors_by_mean_not_max_momentum() -> None:
    """A sector with one very strong name but a weak mean ranks below a sector
    whose names are uniformly strong (mean-of-names ranking, per V2)."""
    scores = _scores([
        ("AAA", 5.0), ("BBB", -3.0),  # Spiky  mean 1.0
        ("CCC", 2.0), ("DDD", 2.0),   # Steady mean 2.0  → ranks ABOVE Spiky
    ])
    sectors = {"AAA": "Spiky", "BBB": "Spiky", "CCC": "Steady", "DDD": "Steady"}
    ctx = _ctx(list(sectors), scores, sectors=sectors, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=1)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"CCC", "DDD"}  # Steady wins on mean


async def test_equal_weight_within_book() -> None:
    """Each held name gets an equal target notional = investable / n_names."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", 0.5), ("DDD", 0.4)])
    sectors = {"AAA": "Tech", "BBB": "Tech", "CCC": "Energy", "DDD": "Energy"}
    ctx = _ctx(list(sectors), scores, sectors=sectors, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=2)  # 4 names, $100k, $100 price → 250 each
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"AAA", "BBB", "CCC", "DDD"}
    # investable 100_000 / 4 names = 25_000 per name / $100 = 250 shares each.
    assert all(qty == Decimal(250) for _, qty in orders.values())


async def test_excludes_market_proxy_from_book() -> None:
    """SPY may be registered only for the regime filter; it is never selected or
    held as a portfolio position."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("SPY", 5.0)])
    sectors = {"AAA": "Tech", "BBB": "Energy", "SPY": "Index"}
    ctx = _ctx(["AAA", "BBB", "SPY"], scores, sectors=sectors, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=3, market_filter_symbol="SPY")
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "SPY" not in _orders(ctx)


async def test_sells_names_leaving_the_book() -> None:
    """A held name whose sector drops out of the top-K is sold to flat."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", -1.0)])
    sectors = {"AAA": "Tech", "BBB": "Energy", "CCC": "Laggard"}
    ctx = _ctx(list(sectors), scores, sectors=sectors,
               holdings={"CCC": 10}, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=2)  # Tech + Energy in; Laggard out
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders.get("CCC") == ("sell", Decimal(10))


# ---- bail-out taxonomy --------------------------------------------------------

async def test_factor_unavailable_holds() -> None:
    """No factor data → HOLD the book (no orders), don't crash the tick."""
    ctx = _ctx(["AAA"], _scores([("AAA", 1.0)]), sectors={"AAA": "Tech"})
    ctx.factors.momentum_scores = MagicMock(side_effect=FactorDataUnavailable("no store"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert ctx.submit_order.await_count == 0
    assert any("factor_unavailable_hold" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


async def test_sector_data_unavailable_holds() -> None:
    """Sector classification missing → can't build baskets → HOLD, fail safe."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               sectors={"AAA": "Tech", "BBB": "Energy"})
    ctx.factors.sectors = MagicMock(side_effect=RuntimeError("no sector column"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert ctx.submit_order.await_count == 0
    assert any("sector_data_unavailable_hold" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


async def test_unknown_sector_names_are_skipped() -> None:
    """A name with no sector classification can't be placed in a basket → skipped,
    while the rest of the book is constructed normally."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.5), ("CCC", 1.0)])
    sectors = {"AAA": "Tech", "BBB": "Tech", "CCC": None}  # CCC unclassified
    ctx = _ctx(list(sectors), scores, sectors=sectors, price=100.0, equity=100_000)
    strat = _strat(ctx, top_k_sectors=3)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"AAA", "BBB"}  # CCC (unknown sector) omitted


# ---- market-regime filter -----------------------------------------------------

async def test_regime_bear_moves_to_cash() -> None:
    """When SPY is below its MA, the book goes to cash (held names sold, no buys)."""
    # 201 daily closes: a falling series so the last close < its trailing MA.
    spy = pd.DataFrame({"c": [300.0 - i for i in range(201)]})
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    sectors = {"AAA": "Tech", "BBB": "Energy"}
    ctx = _ctx(["AAA", "BBB", "SPY"], scores, sectors=sectors,
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
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    sectors = {"AAA": "Tech", "BBB": "Energy"}
    ctx = _ctx(list(sectors), scores, sectors=sectors, price=100.0, equity=100_000)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason="position_size_exceeded"))
    strat = _strat(ctx, top_k_sectors=2)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))  # must not raise
    assert any("rejected" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)
