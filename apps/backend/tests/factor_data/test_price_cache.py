"""_CachedPriceStore (P10 perf): a read-through price cache that makes
run_momentum_backtest's price reads O(unique names) instead of
O(rebalances × names). The whole point is to remove redundant I/O *without*
moving a single backtest number — so these tests pin byte-identity to the
underlying store, that the cache really dedupes reads, and that the end-to-end
backtest is unchanged with the wrapper in the path."""

from __future__ import annotations

from datetime import date

import pandas.testing as pdt
import pytest

from app.factor_data.backtest import _CachedPriceStore, run_momentum_backtest
from app.factor_data.store import FactorDataStore

from .conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


@pytest.fixture
def store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "pc.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def _all_tickers(store: FactorDataStore) -> list[str]:
    rows = store.con.execute("SELECT DISTINCT ticker FROM sep ORDER BY ticker").fetchall()
    return [r[0] for r in rows]


@pytest.mark.parametrize("adjusted", [True, False])
def test_cache_get_prices_byte_identical(store: FactorDataStore, adjusted: bool) -> None:
    """★ For every (ticker, window) the cache returns exactly what the store returns —
    same rows, same order, same dtypes. This contract is what lets the cache sit in the
    backtest path without changing results."""
    cached = _CachedPriceStore(store)
    floor, ceil = store.price_date_bounds()
    assert floor is not None and ceil is not None
    windows = [
        (floor, ceil),                          # full range
        (_START, _END),                         # study window
        (date(2019, 7, 1), date(2019, 7, 1)),   # single trading day
        (date(2019, 3, 1), date(2019, 3, 31)),  # interior month
        (date(1990, 1, 1), floor),              # open-ended start, includes floor row
        (ceil, date(2099, 1, 1)),               # open-ended end, includes ceil row
        (date(2010, 1, 1), date(2010, 12, 31)), # entirely before history → empty
    ]
    for ticker in _all_tickers(store):
        for lo, hi in windows:
            ref = store.get_prices(ticker, lo, hi, adjusted=adjusted)
            got = cached.get_prices(ticker, lo, hi, adjusted=adjusted)
            pdt.assert_frame_equal(got, ref)


def test_cache_dedupes_underlying_reads(store: FactorDataStore, monkeypatch) -> None:
    """The cache loads each (ticker, adjusted) full history at most once regardless of
    how many windowed reads are issued — that dedup is the speedup."""
    calls: dict[str, int] = {}
    real = store.get_prices

    def counting(ticker, lo, hi, *, adjusted=True):
        calls[ticker] = calls.get(ticker, 0) + 1
        return real(ticker, lo, hi, adjusted=adjusted)

    monkeypatch.setattr(store, "get_prices", counting)
    cached = _CachedPriceStore(store)
    ticker = _all_tickers(store)[0]
    for _ in range(12):  # many overlapping windowed reads...
        cached.get_prices(ticker, _START, _END)
        cached.get_prices(ticker, date(2019, 3, 1), date(2019, 6, 30))
    assert calls[ticker] == 1  # ...collapse to exactly one underlying read


def test_cache_delegates_non_price_methods(store: FactorDataStore) -> None:
    """Only get_prices is intercepted; everything else passes through unchanged."""
    cached = _CachedPriceStore(store)
    assert cached.price_date_bounds() == store.price_date_bounds()
    assert cached.trading_days(_START, _END) == store.trading_days(_START, _END)


@pytest.mark.parametrize("method", ["equal_weight", "inverse_vol", "risk_parity_diagonal"])
def test_cached_backtest_matches_uncached(
    store: FactorDataStore, method: str, monkeypatch
) -> None:
    """★ End-to-end: run_momentum_backtest (which wraps the store in the cache) reproduces
    the exact curves/metrics/holdings of the un-wrapped path. Proven by neutralising the
    wrapper to a transparent pass-through for one run and comparing."""
    cached_report = run_momentum_backtest(
        store, _START, _END, top_quantile=0.2, weighting=method, vol_target_annual=0.15
    )
    monkeypatch.setattr("app.factor_data.backtest._CachedPriceStore", lambda s: s)
    raw_report = run_momentum_backtest(
        store, _START, _END, top_quantile=0.2, weighting=method, vol_target_annual=0.15
    )
    assert cached_report.equity_curve == raw_report.equity_curve
    assert cached_report.baseline_curve == raw_report.baseline_curve
    assert cached_report.metrics == raw_report.metrics
    assert cached_report.vol_scaled_curve == raw_report.vol_scaled_curve
    assert [h.weights for h in cached_report.holdings] == [
        h.weights for h in raw_report.holdings
    ]
