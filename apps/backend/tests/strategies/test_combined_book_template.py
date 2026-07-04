"""PORT-001 §4 — combined-book template (Risk-Balanced Multi-Asset Portfolio).

Covers schema parity, the production-frozen 40/60 blend + frozen sleeve params, the weekly
cadence, the two-sleeve weighted target (equity equal-weight at 0.40 + cross-asset TSMOM at
0.60), the equity-sleeve crash-protection regime filter (cross-asset sleeve unaffected), the
cross-asset insufficient-history bail-out, and the rejection policy — all against a synthetic
StrategyContext (no engine, no DB, no broker).

The cross-asset sleeve runs the *validated* ``cross_asset_tsmom`` (PORT-001 §1) over a daily
close panel; tests shorten its windows (via params) so a small synthetic panel suffices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.factor_data.accessor import FactorDataUnavailable
from app.market_data.alpaca_distributions import FetchSummary
from app.strategies.context import Bar
from strategies_user.templates import combined_book
from strategies_user.templates.combined_book import CombinedBook

WK1_A = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)   # Mon
WK1_B = datetime(2026, 6, 8, 14, 1, tzinfo=UTC)   # same ISO week
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)    # next ISO week

# Short cross-asset windows so a ~40-row synthetic panel clears cross_asset_tsmom's need.
_CA_SHORT = {"ca_lookback_days": 20, "ca_skip_days": 2, "ca_vol_lookback_days": 5,
             "cross_asset_symbols": ["TLT", "GLD"]}


def _bar(ts: datetime) -> Bar:
    return Bar(symbol="AAA", timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame({"score": [s for _, s in order]}, index=[t for t, _ in order])
    df.index.name = "ticker"
    return df


def _trend_bars(n: int, start: float, step: float) -> pd.DataFrame:
    """n daily bars with a linear trend (step>0 rising → in 12-1 trend; step<0 falling)."""
    base = datetime(2025, 1, 1, tzinfo=UTC)
    t = [base + timedelta(days=i) for i in range(n)]
    c = [max(1.0, start + step * i) for i in range(n)]
    return pd.DataFrame({"t": t, "c": c})


def _pos(qty: int):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(qty)
    return p


def _params(**over):
    return {
        **CombinedBook.default_params,
        "use_market_regime_filter": False,
        "cash_buffer_pct": 0.0,
        "max_position_pct": 1.0,
        "min_trade_pct": 0.0,
        "order_pacing_seconds": 0.0,
        **_CA_SHORT,
        **over,
    }


def _ctx(symbols, scores, *, holdings=None, equity=100_000, spy_bars=None,
         tlt=("up", 40), gld=("down", 40)):
    """Synthetic StrategyContext. Equity via ctx.factors.momentum_scores; ETF panels + pricing
    via ctx.get_recent_bars (branch on n: n==1 is a pricing call, large n is a panel/regime call)."""
    holdings = holdings or {}
    panels = {
        "TLT": _trend_bars(tlt[1], 100.0, +1.0 if tlt[0] == "up" else -2.0),
        "GLD": _trend_bars(gld[1], 100.0, +1.0 if gld[0] == "up" else -2.0),
    }
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)
    ctx.get_position_for = AsyncMock(
        side_effect=lambda s: _pos(holdings[s]) if s in holdings else None)

    def _bars(sym, tf, n):
        if n == 1:  # a pricing call → last close
            if sym in panels:
                return panels[sym].tail(1)
            return pd.DataFrame({"c": [100.0]})
        if sym == "SPY" and spy_bars is not None:
            return spy_bars
        if sym in panels:
            return panels[sym]
        return pd.DataFrame({"c": [100.0] * n})

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
    return CombinedBook(ctx=ctx, params=_params(**over))


# ---- schema / defaults --------------------------------------------------------

def test_schema_matches_default_params() -> None:
    """The typed form is derived from params_schema; it must list exactly the params the code
    reads (CLAUDE.md: schema↔code drift breaks the form)."""
    assert set(CombinedBook.params_schema) == set(CombinedBook.default_params)


def test_production_frozen_blend_and_sleeve_defaults() -> None:
    assert CombinedBook.default_params["equity_sleeve_weight"] == 0.40
    assert CombinedBook.default_params["cross_asset_weight"] == 0.60
    assert CombinedBook.default_params["cross_asset_symbols"] == \
        ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"]  # §5.6: KMLM added
    assert CombinedBook.default_params["momentum_lookback_days"] == 252
    assert CombinedBook.schedule == "0 14 * * mon"
    # Correlation-aware tilt ON at the sibling live setting (PORT-001 §5.6/§11 #1).
    assert CombinedBook.default_params["ca_corr_aware"] is True
    assert CombinedBook.default_params["ca_corr_lambda"] == 0.5
    # Equity-beta-cap governor (lever #2) ships DEFAULT OFF with the dry-run report on (PORT-001 §6.2).
    assert CombinedBook.default_params["enforce_beta_cap"] is False
    assert CombinedBook.default_params["beta_cap_report_only"] is True
    assert CombinedBook.default_params["beta_cap_max_rc"] == 0.80


async def test_rebalances_once_per_iso_week() -> None:
    ctx = _ctx(["AAA", "BBB", "TLT", "GLD"], _scores([("AAA", 2.0), ("BBB", 1.0)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))   # same week → no second rebalance
    assert ctx.factors.momentum_scores.call_count == 1
    await strat.on_bar(_bar(WK2))     # new week → rebalances again
    assert ctx.factors.momentum_scores.call_count == 2


# ---- two-sleeve weighted blend ------------------------------------------------

async def test_blend_sizes_equity_at_40pct_and_cross_asset_at_60pct() -> None:
    """Equity names get equal-weight × 0.40; the in-trend ETF (TLT) gets its TSMOM weight × 0.60.
    With AAA+BBB held (k=2) each equity target notional ≈ 0.40·0.5·equity; GLD trends down → 0."""
    ctx = _ctx(["AAA", "BBB", "TLT", "GLD"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               equity=100_000)
    strat = _strat(ctx, equity_top_quantile=1.0)  # hold both equity names
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    # equity sleeve: AAA, BBB each 0.40 * 1/2 * 100k = $20k / $100 = 200 sh
    assert orders["AAA"] == ("buy", Decimal(200))
    assert orders["BBB"] == ("buy", Decimal(200))
    # cross-asset: TLT in-trend gets a positive 0.60-scaled weight; GLD (down) absent
    assert "TLT" in orders and orders["TLT"][0] == "buy"
    assert "GLD" not in orders


async def test_regime_bear_zeros_equity_but_keeps_cross_asset() -> None:
    """Below-MA market de-risks ONLY the equity sleeve to cash; the cross-asset TSMOM sleeve
    (its own vol-target de-risk) still trades (the crash-protection split)."""
    spy = pd.DataFrame({"c": [300.0 - i for i in range(201)]})  # falling → last < MA
    ctx = _ctx(["AAA", "BBB", "TLT", "GLD", "SPY"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               holdings={"AAA": 5}, equity=100_000, spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True, market_filter_symbol="SPY")
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert orders.get("AAA") == ("sell", Decimal(5))           # equity exited to cash
    assert "BBB" not in orders                                  # no equity buys
    assert "TLT" in orders and orders["TLT"][0] == "buy"        # cross-asset still on


async def test_cross_asset_insufficient_history_holds_that_sleeve() -> None:
    """Too few ETF bars → the cross-asset sleeve is empty (logged); the equity sleeve still trades."""
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]),
               equity=100_000, tlt=("up", 10), gld=("down", 10))  # 10 < need
    strat = _strat(ctx, equity_top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" in orders and orders["AAA"][0] == "buy"        # equity sleeve on
    assert "TLT" not in orders and "GLD" not in orders          # cross-asset sleeve cash
    assert any("cross_asset_insufficient_history" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


async def test_equity_factor_unavailable_holds_equity_only() -> None:
    """No equity factor data → equity sleeve holds (no equity orders); cross-asset still trades."""
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]), equity=100_000)
    ctx.factors.momentum_scores = MagicMock(side_effect=FactorDataUnavailable("no store"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" not in orders                                  # equity sleeve held
    assert "TLT" in orders                                      # cross-asset sleeve on
    assert any("equity_factor_unavailable_hold" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


async def test_max_position_pct_caps_a_name() -> None:
    """A per-name cap limits the target notional (here 0.05 of equity = $5k → 50 sh @ $100)."""
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]), equity=100_000)
    strat = _strat(ctx, equity_top_quantile=1.0, max_position_pct=0.05)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    # AAA equity target 0.40*1.0*100k=$40k but capped to 0.05*100k=$5k → 50 sh
    assert _orders(ctx)["AAA"] == ("buy", Decimal(50))


async def test_order_rejection_is_logged_not_raised() -> None:
    ctx = _ctx(["AAA", "BBB", "TLT", "GLD"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               equity=100_000)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason="position_size_exceeded"))
    strat = _strat(ctx, equity_top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))   # must not raise
    assert any("rejected" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


# ---- PORT-001 #3 total-return live pricing (default OFF) -----------------------

def _signal(ctx, reason):
    """The payload of the first logged signal with payload.reason == reason, else None."""
    for c in ctx.log_signal.call_args_list:
        payload = c.kwargs.get("payload") or (c.args[2] if len(c.args) > 2 else {})
        if payload.get("reason") == reason:
            return payload
    return None


class _FakeDist:
    """A distributions provider that pays TLT a large dividend (visible divergence) and nothing else."""

    fallback = False

    def __init__(self, *a, **k) -> None:
        pass

    async def prefetch(self, symbols, start, end) -> FetchSummary:
        return FetchSummary(provider="fake", provider_sdk="fake", fetched_at="2026-01-01T00:00:00Z",
                            window=("2025-01-01", "2026-01-01"), symbols=len(symbols), dividends=1,
                            splits=0, rejected=0, elapsed_ms=1, fallback=self.fallback)

    def distributions(self, sym, start, end):
        if sym.upper() == "TLT":  # $5 div inside the 2025-01-01+ TLT panel → clear divergence
            return pd.Series({pd.Timestamp("2025-01-20"): 5.0}), pd.Series(dtype="float64")
        return pd.Series(dtype="float64"), pd.Series(dtype="float64")


class _FakeDistFailOpen(_FakeDist):
    fallback = True


async def test_tr_off_by_default_never_constructs_provider(monkeypatch) -> None:
    """Both flags default False ⇒ the provider is never even constructed (no network, no signal)."""
    made = {"n": 0}

    class _Boom:
        def __init__(self, *a, **k):
            made["n"] += 1

    monkeypatch.setattr(combined_book, "AlpacaDistributionsProvider", _Boom)
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx)  # defaults: use_total_return_pricing / tr_pricing_report_only both False
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert made["n"] == 0
    assert _signal(ctx, "total_return_pricing") is None


async def test_tr_report_only_logs_divergence_without_arming_panel(monkeypatch) -> None:
    monkeypatch.setattr(combined_book, "AlpacaDistributionsProvider", _FakeDist)
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx, tr_pricing_report_only=True)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    sig = _signal(ctx, "total_return_pricing")
    assert sig is not None
    assert sig["pricing_method"] == "RAW"        # report-only never changes the panel
    assert sig["report_only"] is True
    assert sig["divergence_bps"].get("TLT", 0.0) != 0.0
    assert strat._dist_provider is None          # panel NOT armed


async def test_tr_enabled_arms_panel_and_reports_total_return(monkeypatch) -> None:
    monkeypatch.setattr(combined_book, "AlpacaDistributionsProvider", _FakeDist)
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx, use_total_return_pricing=True)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    sig = _signal(ctx, "total_return_pricing")
    assert sig is not None
    assert sig["pricing_method"] == "TOTAL_RETURN"
    assert strat._dist_provider is not None       # panel armed to price on TR


async def test_tr_fail_open_falls_back_to_raw(monkeypatch) -> None:
    monkeypatch.setattr(combined_book, "AlpacaDistributionsProvider", _FakeDistFailOpen)
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 2.0)]))
    strat = _strat(ctx, use_total_return_pricing=True)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))               # must not raise
    sig = _signal(ctx, "total_return_pricing")
    assert sig is not None
    assert sig["fallback"] is True
    assert sig["pricing_method"] == "RAW"         # fell back despite the flag
    assert strat._dist_provider is None
