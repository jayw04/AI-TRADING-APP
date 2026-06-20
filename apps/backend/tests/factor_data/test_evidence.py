"""Edge-evidence statistics tests (P12 §1).

Covers the pure curve/return metrics, the seeded block-bootstrap (CI brackets the point,
determinism under seed, p-value separates a real edge from noise), the stability label, and
the dataset-health gate against a tiny tmp store.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import pytest

from app.factor_data import evidence as ev
from app.factor_data.store import FactorDataStore


def _curve(values: list[float], start: date = date(2020, 1, 1)) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


# ---- pure metrics --------------------------------------------------------------

def test_daily_returns_and_total_return() -> None:
    curve = _curve([100.0, 110.0, 121.0])
    assert ev.daily_returns(curve) == pytest.approx([0.1, 0.1])
    assert ev.total_return(curve) == pytest.approx(0.21)


def test_cagr_one_year_doubling() -> None:
    curve = [(date(2020, 1, 1), 100.0), (date(2021, 1, 1), 200.0)]
    assert ev.cagr(curve) == pytest.approx(1.0, abs=0.01)  # ~+100%/yr


def test_max_drawdown_negative_fraction() -> None:
    curve = _curve([100.0, 120.0, 60.0, 90.0])  # peak 120 → trough 60 = -50%
    assert ev.max_drawdown(curve) == pytest.approx(-0.5)


def test_sharpe_sortino_calmar_signs() -> None:
    # positive drift with real up AND down days (so downside deviation is defined)
    rets = [0.003 + 0.01 * math.sin(i) for i in range(60)]
    assert any(r < 0 for r in rets) and any(r > 0 for r in rets)
    assert ev.sharpe(rets) > 0
    assert ev.sortino(rets) > 0
    assert ev.calmar(0.2, -0.1) == pytest.approx(2.0)


def test_zero_dispersion_is_safe() -> None:
    flat = [0.0, 0.0, 0.0]
    assert ev.sharpe(flat) == 0.0
    assert ev.ann_volatility(flat) == 0.0


def test_benchmark_characteristics_keys() -> None:
    chars = ev.benchmark_characteristics(_curve([100.0, 101.0, 102.0, 101.5]))
    assert set(chars) == {"total_return", "cagr", "ann_volatility", "max_drawdown", "sharpe"}


# ---- bootstrap -----------------------------------------------------------------

def _noisy(mean: float, n: int = 120) -> list[float]:
    # deterministic pseudo-series: mean drift + a fixed oscillation (no RNG in the fixture)
    return [mean + 0.01 * math.sin(i) for i in range(n)]


def test_bootstrap_deterministic_under_seed() -> None:
    r = _noisy(0.001)
    a = ev.block_bootstrap_ci(r, ev.sharpe, n_resamples=300, seed=17, block=5)
    b = ev.block_bootstrap_ci(r, ev.sharpe, n_resamples=300, seed=17, block=5)
    assert a == b  # same seed → identical ConfidenceResult


def test_bootstrap_ci_brackets_point() -> None:
    r = _noisy(0.001)
    res = ev.block_bootstrap_ci(r, ev.sharpe, n_resamples=400, seed=3, block=5)
    assert res.ci_low <= res.point <= res.ci_high


def test_bootstrap_pvalue_separates_edge_from_noise() -> None:
    strong = ev.block_bootstrap_ci(_noisy(0.01), ev.sharpe, n_resamples=400, seed=5, block=5)
    none = ev.block_bootstrap_ci(_noisy(0.0), ev.sharpe, n_resamples=400, seed=5, block=5)
    assert strong.p_value < 0.2           # a real positive edge is significant
    assert none.p_value > 0.2             # zero-mean noise is not


# ---- stability -----------------------------------------------------------------

def test_stability_labels() -> None:
    assert ev.stability_label([1.0, 1.1, 0.9, 1.05]) == "stable"
    assert ev.stability_label([1.0, -0.5, 0.8, -0.6]) == "unstable"
    assert ev.stability_label([1.5, 0.1, 0.9, 1.2]) in {"moderately stable", "stable"}
    assert ev.stability_label([]) == "unknown"


# ---- dataset-health gate -------------------------------------------------------

def _seed_store(tmp_path) -> FactorDataStore:
    days = [d.date() for d in pd.bdate_range("2020-01-06", periods=10)]
    rows = []
    for t in ("AAA", "BBB"):
        for d in days:
            rows.append(dict(ticker=t, date=d.strftime("%Y-%m-%d"), open=100, high=100,
                             low=100, close=100, volume=1_000_000, closeadj=100.0,
                             closeunadj=100.0, lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "health.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    return s


def test_dataset_health_ok_window(tmp_path) -> None:
    s = _seed_store(tmp_path)
    try:
        h = ev.dataset_health(s, date(2020, 1, 6), date(2020, 1, 10))
        assert h["n_sep_rows"] > 0
        assert h["n_tickers"] == 2
        assert h["covers_window"] is True
    finally:
        s.close()


def test_dataset_health_flags_empty_window(tmp_path) -> None:
    s = _seed_store(tmp_path)
    try:
        h = ev.dataset_health(s, date(2030, 1, 1), date(2030, 12, 31))
        assert h["ok"] is False
        assert any("no rows" in f for f in h["flags"])
    finally:
        s.close()
