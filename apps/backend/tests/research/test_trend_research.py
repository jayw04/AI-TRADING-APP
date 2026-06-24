"""TREND-001 research harness — focused tests for the novel logic.

Research harnesses in `scripts/` are normally validated by running (the seeded,
reproducible evidence package is the deliverable), but TREND-001 introduces a
**cash-aware participation simulator** (`simulate_cash`) that the verdict depends on
— trend following's signature is that gross exposure falls in downtrends, which the
shared `run_momentum_backtest` cannot model (it drops, not banks, sub-1.0 weights).
These tests pin that arithmetic and the in-trend signal so the verdict rests on
proven mechanics. The harness is loaded by path (it lives in `scripts/`, not a
package)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd

from app.factor_data.store import FactorDataStore

_HARNESS = Path(__file__).resolve().parents[2] / "scripts" / "trend_research.py"
_spec = importlib.util.spec_from_file_location("trend_research", _HARNESS)
assert _spec and _spec.loader
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)


def _store(tmp_path, specs: dict[str, list[float]], start: str = "2020-01-06"):
    """Tiny store from explicit per-day closes (one ticker → one close list)."""
    bdays = pd.bdate_range(start, periods=max(len(v) for v in specs.values()))
    sep, tk = [], []
    for ticker, closes in specs.items():
        for d, c in zip(bdays, closes, strict=False):
            sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"), open=c, high=c, low=c,
                            close=c, volume=1_000_000, closeadj=c, closeunadj=c,
                            lastupdated="2026-01-01"))
        tk.append(dict(ticker=ticker, name=ticker, exchange="NYSE",
                       category="Domestic Common Stock", isdelisted="N",
                       firstpricedate="2019-01-01", lastpricedate="2026-01-01",
                       lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "t.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    return s, list(bdays)


def test_simulate_cash_banks_uninvested_fraction(tmp_path) -> None:
    """A name doubling over the segment: 50% invested + 50% cash → 1.5×, NOT 2×
    (fully invested) and NOT 1× (the `_simulate` bug that drops the cash). This is
    the property the whole participation verdict rests on."""
    s, bdays = _store(tmp_path, {"AAA": [100.0, 100.0, 200.0]})
    try:
        days = [d.date() for d in bdays]
        rebs = [days[0]]
        half, gross = tr.simulate_cash(s, rebs, days, lambda d: {"AAA": 0.5},
                                       initial_equity=100_000.0, cost_bps=0.0)
        full, _ = tr.simulate_cash(s, rebs, days, lambda d: {"AAA": 1.0},
                                   initial_equity=100_000.0, cost_bps=0.0)
        assert round(half[-1][1]) == 150_000   # 0.5·(2×) + 0.5·cash
        assert round(full[-1][1]) == 200_000   # fully invested doubles
        assert gross[0] == (days[0], 0.5)
    finally:
        s.close()


def test_simulate_cash_all_cash_is_flat(tmp_path) -> None:
    """An empty selection (no names in-trend) → 100% cash → equity stays flat at the
    initial value across the segment (the de-risk-to-cash mechanism), gross = 0."""
    s, bdays = _store(tmp_path, {"AAA": [100.0, 100.0, 200.0]})
    try:
        days = [d.date() for d in bdays]
        curve, gross = tr.simulate_cash(s, [days[0]], days, lambda d: {},
                                        initial_equity=100_000.0, cost_bps=0.0)
        assert curve  # the segment is still marked (flat), not skipped
        assert all(round(eq) == 100_000 for _, eq in curve)  # 100% cash → flat
        assert gross == [(days[0], 0.0)]
    finally:
        s.close()


def test_in_trend_names_filters_by_sma(tmp_path) -> None:
    """In-trend iff last close (strictly before as_of) > its SMA: a rising name is
    in, a falling name is out."""
    up = [float(i) for i in range(1, 13)]        # 1..12 rising → last > SMA
    down = [float(i) for i in range(12, 0, -1)]  # 12..1 falling → last < SMA
    s, bdays = _store(tmp_path, {"UP": up, "DOWN": down})
    try:
        universe, in_trend = tr.in_trend_names(s, bdays[-1].date(), n=10, sma_days=5)
        assert set(universe) == {"UP", "DOWN"}
        assert in_trend == ["UP"]
    finally:
        s.close()


def test_trend_select_weights_one_over_universe(tmp_path) -> None:
    """Each in-trend name is weighted 1/|universe| (so gross = #in-trend / N)."""
    up = [float(i) for i in range(1, 13)]
    down = [float(i) for i in range(12, 0, -1)]
    s, bdays = _store(tmp_path, {"UP": up, "DOWN": down})
    try:
        w = tr._trend_select(s, bdays[-1].date(), n=10, sma_days=5)
        assert w == {"UP": 0.5}  # 1 of 2 names in-trend, weight 1/2
    finally:
        s.close()


# ---- pure helpers --------------------------------------------------------------

def test_windows_partitions_the_range() -> None:
    ws = tr._windows(date(2000, 1, 1), date(2010, 1, 1), 5)
    assert len(ws) == 5
    assert ws[0][0] == date(2000, 1, 1)
    assert ws[-1][1] == date(2010, 1, 1)


def test_excludes_zero_pos_is_nan_safe() -> None:
    assert tr._excludes_zero_pos({"ci_low": 0.1, "ci_high": 0.5})
    assert not tr._excludes_zero_pos({"ci_low": -0.1, "ci_high": 0.5})
    assert not tr._excludes_zero_pos({"ci_low": float("nan"), "ci_high": 0.5})


def test_returns_corr() -> None:
    a = [0.01 * i for i in range(50)]
    assert tr._returns_corr(a, a) == 1.0       # identical → perfectly correlated
    assert tr._returns_corr([0.1, 0.2], [0.1, 0.2]) is None  # <30 obs → None


# ---- verdict tree (frozen plan v0.2 §4) ------------------------------------------

def _classify(**over):
    base = dict(h1_real=False, consistent=False, blend_helps=False,
                dd_vs_mom=0.0, dd_vs_eqw=0.0, beats_regime=False, h1_ci_high=0.0)
    base.update(over)
    return tr.classify_outcome(**base)[0]


def test_verdict_A_when_h1_clears_and_consistent() -> None:
    assert _classify(h1_real=True, consistent=True).startswith("A")


def test_verdict_B_on_h3_beyond_regime_even_with_high_correlation() -> None:
    """The actual full-run scenario: H1 fails, blend doesn't help, but trend drawdown
    is shallower than BOTH momentum and eqw AND it beats the regime filter → B. A high
    trend↔momentum correlation must NOT block this (the plan triggers B on H2 OR H3)."""
    assert _classify(h1_real=False, consistent=True, blend_helps=False,
                     dd_vs_mom=0.302, dd_vs_eqw=0.23, beats_regime=True,
                     h1_ci_high=0.33).startswith("B")


def test_verdict_B_on_blend_help() -> None:
    assert _classify(blend_helps=True, beats_regime=True).startswith("B")


def test_verdict_C_when_subsumed_by_regime_filter() -> None:
    """Per-name trend does NOT beat the portfolio-level regime filter → the benefit is
    subsumed → Rejected, even if drawdown looks shallow vs momentum."""
    assert _classify(dd_vs_mom=0.30, dd_vs_eqw=0.20, beats_regime=False,
                     h1_ci_high=-0.05).startswith("C")


def test_verdict_D_when_borderline() -> None:
    """Beats the regime filter (not subsumed) but no axis clears and H1 CI straddles
    zero on the high side → Inconclusive, not Rejected."""
    assert _classify(h1_real=False, blend_helps=False, dd_vs_mom=-0.01,
                     dd_vs_eqw=-0.01, beats_regime=True, h1_ci_high=0.20).startswith("D")


def test_blend_curve_averages_daily_returns() -> None:
    a = [(date(2020, 1, 1), 100.0), (date(2020, 1, 2), 110.0)]  # +10%
    b = [(date(2020, 1, 1), 100.0), (date(2020, 1, 2), 90.0)]   # −10%
    blend = tr._blend_curve(a, b, initial_equity=100.0)
    assert round(blend[-1][1], 6) == 100.0  # 0.5·(+0.1) + 0.5·(−0.1) = 0
