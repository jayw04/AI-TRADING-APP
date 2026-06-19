"""P10 §3B-3 SPY / Market benchmark — exact beta/alpha math on a controlled pair, the
committed real fixture loads, and shape_portfolio_result surfaces the spy_* keys."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.store import FactorDataStore
from app.research.engine import (
    benchmark_metrics,
    load_spy_curve,
    shape_portfolio_result,
)
from app.research.engine.benchmark import _DEFAULT_FIXTURE

from ..factor_data.conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


def _bench_and_book(k: float, n: int = 80):
    """A benchmark with non-constant returns, and a book whose daily returns are exactly
    ``k`` × the benchmark's → beta should be k, alpha 0, correlation 1 (for k>0)."""
    days = list(pd.bdate_range("2019-01-01", periods=n).date)
    bench, book = [], []
    bv, kv = 100.0, 100.0
    bench.append((days[0], bv))
    book.append((days[0], kv))
    for i in range(1, n):
        r = 0.01 if i % 2 else -0.006  # alternating, non-degenerate
        bv *= 1 + r
        kv *= 1 + k * r
        bench.append((days[i], bv))
        book.append((days[i], kv))
    return bench, book


def test_beta_alpha_exact() -> None:
    bench, book = _bench_and_book(k=2.0)
    m = benchmark_metrics(book, bench)
    assert m["spy_beta"] == pytest.approx(2.0, rel=1e-6)
    assert m["spy_alpha_annual"] == pytest.approx(0.0, abs=1e-9)
    assert m["spy_correlation"] == pytest.approx(1.0, rel=1e-9)
    assert m["spy_overlap_days"] == 80


def test_identical_book_is_market() -> None:
    bench, book = _bench_and_book(k=1.0)
    m = benchmark_metrics(book, bench)
    assert m["spy_beta"] == pytest.approx(1.0, rel=1e-6)
    assert m["spy_excess_return"] == pytest.approx(0.0, abs=1e-9)
    assert m["spy_tracking_error"] == pytest.approx(0.0, abs=1e-9)


def test_empty_or_thin_overlap_returns_nothing() -> None:
    assert benchmark_metrics([], [(date(2019, 1, 1), 100.0)]) == {}
    short = [(date(2019, 1, d), 100.0 + d) for d in range(1, 10)]  # < 30 days
    assert benchmark_metrics(short, short) == {}


# ---- the committed real fixture --------------------------------------------------

def test_real_spy_fixture_loads() -> None:
    curve = load_spy_curve()
    assert _DEFAULT_FIXTURE.exists()
    assert len(curve) > 2000                        # ~2625 daily closes
    assert curve == sorted(curve)                   # ascending by date
    assert curve[0][0].year == 2016                 # Alpaca/IEX depth starts ~2016
    assert all(c > 0 for _, c in curve)


# ---- end-to-end through shape_portfolio_result -----------------------------------

@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def test_shape_adds_spy_keys_when_benchmark_supplied(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    spy = load_spy_curve()
    s = shape_portfolio_result(report, bt_store, benchmark_curve=spy).metrics_summary
    for k in ("spy_total_return", "spy_excess_return", "spy_beta", "spy_alpha_annual",
              "spy_tracking_error", "spy_information_ratio", "spy_correlation",
              "spy_overlap_start", "spy_overlap_end"):
        assert k in s
    # the book is 2018–2020; the overlap with SPY sits inside that window.
    assert s["spy_overlap_start"] >= "2018-07-01"
    assert s["spy_overlap_end"] <= "2020-12-31"


def test_shape_omits_spy_without_benchmark(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    s = shape_portfolio_result(report, bt_store).metrics_summary  # no benchmark_curve
    assert "spy_beta" not in s
