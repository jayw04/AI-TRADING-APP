"""Strategy 9 governance-v1.3 (C40) template — the six owner-required regression families
(production-activation conditional approval, 2026-07-28).

1. Cap semantics: cross-asset cap applied PRE-BLEND, sleeve-internal min(w, cap/c);
   never a post-blend/global cap.
2. Equity cap: 4% applies ONLY inside the equity sleeve; cross-asset instruments are
   never clipped by it.
3. Bounded hybrid threshold: max($50, min(3% x target, 0.10% x account equity));
   EXITS-ONLY structural exemption (evidence-exact ruling); partial trims — including
   governor/cap-driven — remain thresholded; operational-debt telemetry.
4. Default-parameter merge: the engine merges default_params at registration; a bare
   params dict silently restores OLD (quantile) sleeve behavior — which is exactly why
   the merge invariant is load-bearing.
5. Holdings visibility: a held symbol absent from the target book still exits (the
   registration contract keeps held names in ctx.symbols).
6. Regime convention (frozen): freshest available price vs the MA of the prior 200
   COMPLETED bars — the current partial bar never enters the average; insufficient
   history fails open (None + signal), never a silently shortened window.

Mandatory account-level risk actions (circuit breakers, daily-loss, operator de-risking)
are enforced OUTSIDE this template via the risk engine and OrderRouter; no template-level
bypass exists or is simulated here (owner ruling — a broader bypass requires its own
specification and a re-run of the validation walk-forward).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.strategies.context import Bar
from strategies_user.templates.combined_book_v13 import CombinedBook

WK1 = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)   # Mon
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)  # next ISO week

_CA_SHORT = {"ca_lookback_days": 20, "ca_skip_days": 2, "ca_vol_lookback_days": 5,
             "cross_asset_symbols": ["TLT", "GLD"]}


def _bar(ts: datetime) -> Bar:
    return Bar(symbol="AAA", timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame({"score": [s for _, s in order]}, index=[t for t, _ in order])
    df.index.name = "ticker"
    return df


def _trend_bars(n: int, start: float, step: float) -> pd.DataFrame:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return pd.DataFrame({"t": [base + timedelta(days=i) for i in range(n)],
                         "c": [max(1.0, start + step * i) for i in range(n)]})


def _pos(qty):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(str(qty))
    return p


def _params(**over):
    return {
        **CombinedBook.default_params,
        "use_market_regime_filter": False,
        "cash_buffer_pct": 0.0,
        "order_pacing_seconds": 0.0,
        "enforce_beta_cap": False,       # governor exercised elsewhere; isolate the axis
        "beta_cap_report_only": False,
        **_CA_SHORT,
        **over,
    }


def _ctx(symbols, scores, *, holdings=None, equity=100_000, spy_bars=None):
    holdings = holdings or {}
    panels = {"TLT": _trend_bars(40, 100.0, +1.0), "GLD": _trend_bars(40, 100.0, -2.0)}
    ctx = MagicMock()
    ctx.strategy_id = 9
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)
    ctx.get_position_for = AsyncMock(
        side_effect=lambda s: _pos(holdings[s]) if s in holdings else None)

    def _bars(sym, tf, n):
        if n == 1:
            return panels[sym].tail(1) if sym in panels else pd.DataFrame({"c": [100.0]})
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


def _orders(ctx):
    out = {}
    for call in ctx.submit_order.call_args_list:
        req = call.args[0]
        out[req.symbol_ticker] = (req.side.value, req.qty)
    return out


def _debt_signals(ctx):
    return [c.kwargs.get("payload") or c.args[2] if len(c.args) > 2 else c.kwargs["payload"]
            for c in ctx.log_signal.call_args_list
            if (c.kwargs.get("payload") or (c.args[2] if len(c.args) > 2 else {}))
            .get("reason") == "trade_threshold_operational_debt"]


def _strat(ctx, **over):
    return CombinedBook(ctx=ctx, params=_params(**over))


# ---- family 0: schema/version sync -----------------------------------------------------

# Genuinely intentional schema-vs-code default divergences ONLY (Tier-3 review
# requirement). Empty by design: any entry needs a documented governance reason.
_INTENTIONAL_SCHEMA_DIFFS: dict[str, object] = {}


def test_schema_matches_default_params() -> None:
    """Keys AND default values must match between params_schema and default_params. A
    schema default contradicting the governed runtime default (e.g. enforce_beta_cap)
    could let a schema-initialized registration silently recreate the WS-1
    governor-registration ambiguity — the exact class of defect v1.3 exists to close."""
    assert set(CombinedBook.params_schema) == set(CombinedBook.default_params)
    for key, spec in CombinedBook.params_schema.items():
        if "default" not in spec:
            continue
        expected = (_INTENTIONAL_SCHEMA_DIFFS[key] if key in _INTENTIONAL_SCHEMA_DIFFS
                    else CombinedBook.default_params[key])
        assert spec["default"] == expected, (
            f"params_schema['{key}']['default'] = {spec['default']!r} contradicts "
            f"default_params[{key!r}] = {CombinedBook.default_params[key]!r}")


def test_v13_settled_defaults() -> None:
    d = CombinedBook.default_params
    assert d["equity_fixed_n"] == 40
    assert d["ca_book_cap"] == 0.20
    assert d["max_position_pct"] == 0.04
    assert d["trade_floor_usd"] == 50.0
    assert d["trade_rel_pct"] == 0.03
    assert d["trade_ceiling_equity_pct"] == 0.0010
    assert d["enforce_beta_cap"] is True          # governor enforced by the sealed spec
    assert "min_trade_pct" not in d               # legacy threshold retired
    assert CombinedBook.version == "1.4.0"        # governance name "v1.3"


# ---- family 1+2: cap semantics ---------------------------------------------------------

async def test_ca_cap_is_preblend_sleeve_internal_and_untouched_by_equity_cap() -> None:
    """TLT trends up hard, GLD down → the raw sleeve concentrates in TLT above the cap.
    The cap must bind SLEEVE-INTERNALLY at ca_book_cap / cross_asset_weight (0.20/0.60),
    so TLT's blended book weight is exactly 0.20 — five times the 4% equity cap, proving
    the CF-2 global-cap defect cannot recur."""
    ctx = _ctx(["TLT", "GLD"], _scores([]))
    strat = _strat(ctx)
    await strat.on_init()
    ca = await strat._cross_asset_sleeve_weights()
    cap_internal = 0.20 / 0.60
    assert ca["TLT"] == cap_internal            # truncated exactly at the sleeve cap
    assert max(ca.values()) <= cap_internal + 1e-12
    await strat.on_bar(_bar(WK1))
    side, qty = _orders(ctx)["TLT"]
    assert side == "buy"
    price = float(_trend_bars(40, 100.0, +1.0)["c"].iloc[-1])
    notional = float(qty) * price
    assert abs(notional - 100_000 * 0.20) < 1.0   # 20% of the book — NOT capped to 4%


async def test_equity_cap_binds_only_inside_the_equity_sleeve() -> None:
    """equity_fixed_n=10 → equal weight would be 10%; the sleeve-internal cap pins 4%."""
    names = [(f"S{i}", 10.0 - i) for i in range(12)]
    ctx = _ctx([t for t, _ in names] + ["TLT", "GLD"], _scores(names))
    strat = _strat(ctx, equity_fixed_n=10)
    await strat.on_init()
    eq = await strat._equity_sleeve_weights()
    assert len(eq) == 10
    assert all(abs(w - 0.04) < 1e-12 for w in eq.values())   # min(1/10, 0.04) == 0.04


# ---- family 3: bounded hybrid threshold ------------------------------------------------

async def _threshold_case(book_pct, held_qty, **over):
    """One equity name 'AAA' at a chosen book weight (via equity_sleeve_weight), price 100,
    cross-asset disabled. Returns (orders, ctx)."""
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 5.0)]),
               holdings={"AAA": held_qty} if held_qty else None)
    strat = _strat(ctx, equity_fixed_n=1, cross_asset_weight=0.0,
                   equity_sleeve_weight=book_pct / 0.04, **over)
    await strat.on_init()
    await strat.on_bar(_bar(WK1))
    return _orders(ctx), ctx


async def test_exits_are_structurally_exempt_from_any_floor() -> None:
    """A held name outside the target book exits in full even under an absurd floor —
    including a name that rotated out of the score universe entirely (family 5)."""
    ctx = _ctx(["AAA", "OLD", "TLT", "GLD"], _scores([("AAA", 5.0)]),
               holdings={"OLD": 5})
    strat = _strat(ctx, equity_fixed_n=1, cross_asset_weight=0.0,
                   trade_floor_usd=1e9)
    await strat.on_init()
    await strat.on_bar(_bar(WK1))
    side, qty = _orders(ctx)["OLD"]
    assert side == "sell" and qty == Decimal("5")


async def test_floor_arm_binds_small_targets() -> None:
    # book 1.6% → target $1,600 → 3% = $48 < $50 floor → threshold $50
    orders, ctx = await _threshold_case(0.016, held_qty=16.4)   # delta ≈ -$40 < $50
    assert "AAA" not in orders                                   # skipped
    assert _debt_signals(ctx), "skipped trim must be reported as operational debt"
    orders, _ = await _threshold_case(0.016, held_qty=17.0)      # delta = -$100 ≥ $50
    assert orders["AAA"][0] == "sell"


async def test_relative_arm_binds_mid_targets() -> None:
    # book 2.4% → target $2,400 → threshold = min($72, $100) = $72
    orders, _ = await _threshold_case(0.024, held_qty=24.6)      # delta -$60 < $72
    assert "AAA" not in orders
    orders, _ = await _threshold_case(0.024, held_qty=24.8)      # delta -$80 ≥ $72
    assert orders["AAA"][0] == "sell"


async def test_ceiling_arm_caps_thresholds_of_large_positions() -> None:
    """book 4% → target $4,000 → 3% = $120 but the 0.10%-of-equity ceiling pins $100.
    A $110 governor/cap-style partial trim EXECUTES (the F2/F3 interaction fix); a $90
    trim is skipped and accumulated (partial trims stay thresholded — evidence-exact)."""
    orders, _ = await _threshold_case(0.040, held_qty=41.1)      # delta -$110 ≥ $100
    assert orders["AAA"][0] == "sell"
    orders, ctx = await _threshold_case(0.040, held_qty=40.9)    # delta -$90 < $100
    assert "AAA" not in orders
    sig = _debt_signals(ctx)[0]
    row = sig["skipped"][0]
    assert row["symbol"] == "AAA"
    assert row["direction"] == "risk_reducing"
    assert row["sleeve"] == "equity"
    assert abs(row["delta_usd"] + 90) < 1.5
    assert abs(row["pct_equity"] + 0.09) < 0.01


async def test_operational_debt_streak_accumulates_across_rebalances() -> None:
    ctx = _ctx(["AAA", "TLT", "GLD"], _scores([("AAA", 5.0)]),
               holdings={"AAA": 40.9})
    strat = _strat(ctx, equity_fixed_n=1, cross_asset_weight=0.0,
                   equity_sleeve_weight=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1))
    await strat.on_bar(_bar(WK2))
    sigs = _debt_signals(ctx)
    assert len(sigs) == 2
    assert sigs[1]["skipped"][0]["consecutive_rebalances"] == 2
    assert sigs[1]["skipped"][0]["cum_abs_usd"] > sigs[0]["skipped"][0]["cum_abs_usd"]


def test_no_template_level_emergency_bypass_exists() -> None:
    """Mandatory account-level risk actions act OUTSIDE the template (risk engine +
    OrderRouter). The template must not simulate them: no bypass parameter exists."""
    assert not any("bypass" in k for k in CombinedBook.default_params)


# ---- family 4: default-parameter merge -------------------------------------------------

def test_engine_merges_default_params_and_bare_params_regress_behavior() -> None:
    """The engine registers instances with {**cls.default_params, **row_params}. Without
    that merge, a bare params dict silently restores the OLD quantile sleeve (the exact
    failure the v1.3 parity run 1 exposed) — so the merge is load-bearing."""
    engine_src = (Path(__file__).parents[2] / "app" / "strategies" / "engine.py").read_text()
    assert "{**cls.default_params, **(row.params_json or {})}" in engine_src
    merged = {**CombinedBook.default_params, **{}}
    assert merged["equity_fixed_n"] == 40 and merged["ca_book_cap"] == 0.20
    bare = CombinedBook(ctx=MagicMock(), params={})
    # in-code fallback WITHOUT the merge = quantile mode (equity_fixed_n absent) — the
    # regression this test guards against ever being reachable through registration.
    assert bare.params.get("equity_fixed_n") is None


# ---- family 6: regime-filter convention ------------------------------------------------

def _spy(prior: list[float], last: float) -> pd.DataFrame:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    c = [*prior, last]
    return pd.DataFrame({"t": [base + timedelta(days=i) for i in range(len(c))], "c": c})


async def test_ma_uses_exactly_the_prior_200_completed_bars() -> None:
    """First bar is extreme: included ⟺ the implementation uses the prior-200 window.
    prior = [1e6] + 199×100 → prior-200 mean 5099.5 → last 100.5 is BELOW. A tail-200-
    including-the-last-bar implementation would drop the extreme bar and answer ABOVE."""
    spy = _spy([1_000_000.0] + [100.0] * 199, last=100.5)
    ctx = _ctx(["AAA", "TLT", "GLD", "SPY"], _scores([("AAA", 5.0)]), spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True)
    await strat.on_init()
    assert await strat._market_below_ma() is True
    # the current (possibly partial) bar is only the comparison price, never in the MA:
    spy2 = _spy([100.0] * 200, last=1_000_000.0)
    ctx2 = _ctx(["AAA", "TLT", "GLD", "SPY"], _scores([("AAA", 5.0)]), spy_bars=spy2)
    strat2 = _strat(ctx2, use_market_regime_filter=True)
    await strat2.on_init()
    assert await strat2._market_below_ma() is False   # 1e6 vs MA 100 — MA unpolluted
    # the request asks for exactly days+1 sessions (200 completed + the current bar)
    call = ctx2.get_recent_bars.call_args_list[0]
    assert call.kwargs.get("n", call.args[-1] if call.args else None) == 201


async def test_insufficient_history_fails_open_never_shortens_the_window() -> None:
    spy = _spy([100.0] * 199, last=99.0)   # only 200 rows < 201 required
    ctx = _ctx(["AAA", "TLT", "GLD", "SPY"], _scores([("AAA", 5.0)]), spy_bars=spy)
    strat = _strat(ctx, use_market_regime_filter=True)
    await strat.on_init()
    assert await strat._market_below_ma() is None      # governed fail-open, not a guess
