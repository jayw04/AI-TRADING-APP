"""TV-001-SUPERTREND harness — pure-function tests (offline, no data fetch)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tv001_supertrend_validation.py"
_spec = importlib.util.spec_from_file_location("tv001_supertrend_validation", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def _series(closes):
    c = np.array(closes, dtype=float)
    return c + 0.5, c - 0.5, c  # high, low, close (hl2 ≈ close)


def test_supertrend_flips_up_in_a_sustained_uptrend():
    # a long steady rise → trend resolves to +1 and stays
    h, lo, c = _series(np.linspace(100, 200, 300))
    trend = _mod.supertrend_trend(h, lo, c)
    assert trend.dtype == int and len(trend) == len(c)
    assert trend[-1] == 1

def test_supertrend_flips_down_in_a_downtrend():
    h, lo, c = _series(np.concatenate([np.linspace(100, 200, 150), np.linspace(200, 80, 150)]))
    trend = _mod.supertrend_trend(h, lo, c)
    assert trend[-1] == -1
    # it must have been +1 at the top of the ramp (a real flip occurred)
    assert 1 in set(trend.tolist()) and -1 in set(trend.tolist())

def test_backtest_no_lookahead_and_cost_charged_on_flip():
    # 4 bars, always uptrend (trend=1); long/flat holds from bar 1; cost hits the entry turnover
    c = np.array([100.0, 101.0, 102.0, 103.0])
    trend = np.array([1, 1, 1, 1])
    r0 = _mod.backtest(c, trend, cost_bps=0, allow_short=False, ann_factor=6552)
    r100 = _mod.backtest(c, trend, cost_bps=100, allow_short=False, ann_factor=6552)  # 1% per side
    # with cost the strategy return is strictly lower (entry turnover charged)
    assert r100.strat_ret < r0.strat_ret
    # never in-the-future: bar-0 signal earns bar-1 return only (held is lagged)
    assert r0.n_trades == 1

def test_backtest_buy_and_hold_benchmark_is_uncosted_long():
    c = np.array([100.0, 110.0, 105.0, 121.0])
    trend = np.array([1, -1, 1, 1])  # flips → trades → costs on the strategy, not on B&H
    r = _mod.backtest(c, trend, cost_bps=10, allow_short=False, ann_factor=6552)
    # buy-hold total return = last/first - 1 regardless of the timing signal
    assert abs(r.bh_ret - (121.0 / 100.0 - 1.0)) < 1e-6

def test_classify_verdict_mapping():
    # generalizes + robust + CI>0 → Approved
    assert _mod.classify(0.7, (0.01, 0.002, 0.02), True) == "Approved"
    # majority + CI>0 but not robust/general → Diversifier/Candidate
    assert _mod.classify(0.55, (0.01, 0.001, 0.02), False) == "Diversifier / Candidate-Promising"
    # minority beat / CI spans zero → Rejected
    assert _mod.classify(0.3, (0.0, -0.01, 0.01), False) == "Rejected (Evidenced)"
    assert _mod.classify(0.8, (0.01, -0.001, 0.03), True) == "Rejected (Evidenced)"  # CI touches 0

def test_bootstrap_mean_ci_deterministic_and_short_series_nan():
    xs = list(np.random.default_rng(0).normal(0.001, 0.02, 200))
    a = _mod.bootstrap_mean_ci(xs, seed=17)
    b = _mod.bootstrap_mean_ci(xs, seed=17)
    assert a == b and a[1] <= a[2]
    _, lo, hi = _mod.bootstrap_mean_ci([0.01, 0.02])
    assert lo != lo and hi != hi  # NaN for too-short
