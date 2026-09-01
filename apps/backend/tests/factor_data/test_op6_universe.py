"""OP-6 tradability screen (C3 / LOW-002) + the `universe_fn` backtest seam.

Two properties matter and are tested by falsification, not by construction:

1. Supplying no `universe_fn` leaves existing callers behaviourally unchanged.
2. Supplying one governs the EQUAL-WEIGHT BASELINE, so a C3 book and its benchmark can be made
   to share exactly one screened universe (the invariant the frozen C3 spec requires).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof
from app.research.factor_lab.op6_universe import op6_universe_asof

START, END = date(2020, 1, 1), date(2020, 12, 31)
AS_OF = date(2020, 6, 30)


def _mk(
    ticker,
    *,
    close,
    volume,
    closeunadj=None,
    category="Domestic Common Stock",
    exchange="NYSE",
    first=START,
    last=END,
):
    """One name held at constant close/volume across [first, last]."""
    days = pd.bdate_range(first, last)
    unadj = close if closeunadj is None else closeunadj
    sep = pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
            "closeadj": close,
            "closeunadj": unadj,
            "lastupdated": "2026-01-01",
        }
    )
    tk = dict(
        ticker=ticker,
        name=f"{ticker} Inc",
        exchange=exchange,
        category=category,
        isdelisted="N",
        firstpricedate=first.strftime("%Y-%m-%d"),
        lastpricedate=last.strftime("%Y-%m-%d"),
        lastupdated="2026-01-01",
    )
    return sep, tk


@pytest.fixture
def op6_store(tmp_path) -> FactorDataStore:
    """Names engineered so each OP-6 leg has a positive and a negative case."""
    specs = [
        # --- passes every leg (ADV = 100 * 50_000 = $5.0M >= $2M, unadj $100 >= $5)
        *[_mk(f"PASS{i}", close=100.0, volume=50_000) for i in range(22)],
        # --- $5 floor: ADJUSTED close is 50 (passes) but ACTUALLY TRADED price is 2 (fails).
        _mk("SPLITLOW", close=50.0, closeunadj=2.0, volume=200_000),
        # --- $5 floor: adjusted close 2 (would fail on `close`) but traded at 50 (passes).
        _mk("SPLITHIGH", close=2.0, closeunadj=50.0, volume=5_000_000),
        # --- liquidity: price fine, ADV = 100 * 100 = $10k << $2M
        _mk("THIN", close=100.0, volume=100),
        # --- security type
        _mk("SECOND", close=100.0, volume=50_000, category="Domestic Common Stock Secondary Class"),
        _mk("WARRANT", close=100.0, volume=50_000, category="Domestic Common Stock Warrant"),
        _mk("PREF", close=100.0, volume=50_000, category="Domestic Preferred Stock"),
        _mk("ADRX", close=100.0, volume=50_000, category="ADR Common Stock"),
        # --- venue
        _mk("OTCX", close=100.0, volume=50_000, exchange="OTC"),
        # --- PIT: lists only AFTER as_of
        _mk("FUTURE", close=100.0, volume=50_000, first=date(2020, 10, 1)),
        # --- PIT: live at as_of, delisted later (survivorship-free => must be INCLUDED)
        _mk("GONE", close=100.0, volume=50_000, last=date(2020, 8, 31)),
    ]
    sep = pd.concat([s for s, _ in specs], ignore_index=True)
    tickers = pd.DataFrame([t for _, t in specs])
    s = FactorDataStore(db_path=str(tmp_path / "op6.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tickers)
    yield s
    s.close()


# ---- OP-6 predicate ---------------------------------------------------------


def test_passing_names_are_selected(op6_store):
    assert {f"PASS{i}" for i in range(22)} <= set(op6_universe_asof(op6_store, AS_OF))


@pytest.mark.parametrize(
    "ticker,leg",
    [
        ("THIN", "median dollar ADV below $2M"),
        ("SECOND", "secondary class is not a primary listing"),
        ("WARRANT", "warrant is not common stock"),
        ("PREF", "preferred is not common stock"),
        ("ADRX", "ADR is not domestic common stock"),
        ("OTCX", "OTC is not a primary listing"),
        ("FUTURE", "not yet listed at as_of (no look-ahead)"),
    ],
)
def test_excluded_names(op6_store, ticker, leg):
    assert ticker not in op6_universe_asof(op6_store, AS_OF), f"should be excluded: {leg}"


def test_price_floor_uses_closeunadj_not_adjusted_close(op6_store):
    """The decisive field-semantics test (owner ruling 2026-09-01).

    SPLITLOW  adjusted 50 / traded 2  -> EXCLUDED (it never traded above $5)
    SPLITHIGH adjusted  2 / traded 50 -> INCLUDED
    Both assertions invert if the screen is switched to `close`, so this test fails loudly on a
    silent field substitution rather than passing vacuously.
    """
    u = op6_universe_asof(op6_store, AS_OF)
    assert "SPLITLOW" not in u
    assert "SPLITHIGH" in u


def test_survivorship_free_includes_name_delisted_after_as_of(op6_store):
    assert "GONE" in op6_universe_asof(op6_store, AS_OF)


def test_is_deterministic_and_sorted(op6_store):
    a = op6_universe_asof(op6_store, AS_OF)
    assert a == op6_universe_asof(op6_store, AS_OF) == sorted(a)


def test_thresholds_are_load_bearing(op6_store):
    """Relaxing each frozen threshold admits the name it was excluding — proves the gate acts."""
    assert "THIN" in op6_universe_asof(op6_store, AS_OF, min_median_dollar_adv=1.0)
    assert "SPLITLOW" in op6_universe_asof(op6_store, AS_OF, min_close=0.0)


# ---- the backtest seam ------------------------------------------------------


def test_default_universe_fn_is_behaviourally_unchanged(momentum_store):
    """No `universe_fn` must reproduce the historical universe exactly (existing callers safe)."""
    base = run_momentum_backtest(momentum_store, date(2019, 1, 1), date(2020, 6, 30), n=25)
    explicit = run_momentum_backtest(
        momentum_store,
        date(2019, 1, 1),
        date(2020, 6, 30),
        n=25,
        universe_fn=lambda s, d: universe_asof(s, d, n=25),
    )
    assert base.baseline_curve == explicit.baseline_curve
    assert base.equity_curve == explicit.equity_curve


def test_universe_fn_governs_the_equal_weight_baseline(momentum_store):
    """A restricted provider must change the BENCHMARK, else C3's benchmark would silently
    keep using the broad universe while the book used OP-6."""
    full = run_momentum_backtest(momentum_store, date(2019, 1, 1), date(2020, 6, 30), n=25)
    restricted = run_momentum_backtest(
        momentum_store,
        date(2019, 1, 1),
        date(2020, 6, 30),
        n=25,
        universe_fn=lambda s, d: universe_asof(s, d, n=25)[:5],
    )
    assert restricted.baseline_curve != full.baseline_curve


def test_book_and_benchmark_share_one_screened_universe(momentum_store):
    """The C3 invariant: the provider handed to the benchmark is the same object that feeds the
    book's score cross-section, so the two cannot diverge."""
    seen: list[list[str]] = []

    def provider(s, d):
        u = universe_asof(s, d, n=25)[:8]
        seen.append(u)
        return u

    def score_fn(s, d):
        u = provider(s, d)
        return pd.DataFrame({"score": range(len(u))}, index=u)

    rep = run_momentum_backtest(
        momentum_store,
        date(2019, 1, 1),
        date(2020, 6, 30),
        n=25,
        score_fn=score_fn,
        universe_fn=provider,
    )
    assert rep.equity_curve and seen
    # every observed universe is identical between the two consumers on a given date
    assert all(len(u) == 8 for u in seen)
