"""simulate_cash_book — banks the uninvested fraction (participation books).

Mirrors backtest._simulate's daily closeadj marking, but a sub-1.0 gross is held as
cash rather than dropped. Two properties pin the cash mechanics, plus a regression
guard that a fully-invested (Σw=1) book is byte-identical to _simulate.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.backtest import _simulate, simulate_cash_book
from app.factor_data.store import FactorDataStore

_INIT = 100_000.0


def _store(tmp_path, *, double: bool) -> tuple[FactorDataStore, list[date]]:
    """2 names over 10 business days. ``double`` → each ramps 100→200; else flat at 100."""
    bdays = list(pd.bdate_range("2020-01-01", periods=10))
    sep, tk = [], []
    for ticker in ("AAA", "BBB"):
        for i, d in enumerate(bdays):
            px = 100.0 + (100.0 * i / (len(bdays) - 1)) if double else 100.0
            sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"), open=px, high=px,
                            low=px, close=px, volume=1_000_000, closeadj=px,
                            closeunadj=px, lastupdated="2026-01-01"))
        tk.append(dict(ticker=ticker, name=ticker, exchange="NYSE",
                       category="Domestic Common Stock", sector="X", industry="Y",
                       isdelisted="N", firstpricedate="2019-01-01", lastpricedate="2026-01-01",
                       lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "cash.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    return s, [d.date() for d in bdays]


def test_cash_sleeve_holds_flat_when_prices_flat(tmp_path) -> None:
    """gross=0.5 on flat prices, zero cost → equity never moves (sleeves + cash both flat)."""
    s, days = _store(tmp_path, double=False)
    try:
        curve, gross = simulate_cash_book(
            s, [days[0]], days, lambda d: {"AAA": 0.25, "BBB": 0.25},
            initial_equity=_INIT, turnover_cost_bps=0.0)
        assert gross == [(days[0], 0.5)]
        assert curve and all(abs(eq - _INIT) < 1e-6 for _, eq in curve)
    finally:
        s.close()


def test_participation_scales_return_by_gross(tmp_path) -> None:
    """gross=0.5 while the invested names double → final = init·(0.5·2 + 0.5·1) = 1.5·init.

    The banked half earns nothing; only the invested half participates in the doubling."""
    s, days = _store(tmp_path, double=True)
    try:
        curve, _ = simulate_cash_book(
            s, [days[0]], days, lambda d: {"AAA": 0.25, "BBB": 0.25},
            initial_equity=_INIT, turnover_cost_bps=0.0)
        assert abs(curve[-1][1] - _INIT * 1.5) < 1e-3
    finally:
        s.close()


def test_fully_invested_matches_simulate(tmp_path) -> None:
    """Σw=1 (no cash) → byte-identical to the fully-invested _simulate (regression guard)."""
    s, days = _store(tmp_path, double=True)
    try:
        weights = {"AAA": 0.5, "BBB": 0.5}
        cash_curve, gross = simulate_cash_book(
            s, [days[0]], days, lambda d: dict(weights),
            initial_equity=_INIT, turnover_cost_bps=10.0)
        base_curve, _ = _simulate(
            s, [days[0]], days, lambda d: dict(weights),
            initial_equity=_INIT, turnover_cost_bps=10.0)
        assert gross == [(days[0], 1.0)]
        assert [eq for _, eq in cash_curve] == [eq for _, eq in base_curve]
    finally:
        s.close()
