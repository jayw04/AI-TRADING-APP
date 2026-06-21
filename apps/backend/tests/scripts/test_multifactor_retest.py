"""P14 SF1 multi-factor re-test — pure helper tests (offline, no store/network)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "multifactor_retest.py"
_spec = importlib.util.spec_from_file_location("multifactor_retest", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
window_bounds = _mod._window_bounds
paired_ci = _mod._paired_sharpe_diff_ci


def test_window_bounds_contiguous_and_covers_range():
    wins = window_bounds(date(2017, 1, 1), date(2026, 1, 1), 5)
    assert len(wins) == 5
    assert wins[0][0] == date(2017, 1, 1)
    assert wins[-1][1] == date(2026, 1, 1)  # last window ends exactly at `end`
    for a, b in zip(wins, wins[1:], strict=False):
        assert a[1] == b[0]  # contiguous, no gap/overlap


def test_paired_ci_identical_series_is_zero():
    r = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 10
    ci = paired_ci(r, list(r), n_resamples=200, seed=17)
    assert ci["delta"] == 0.0
    assert ci["ci_low"] == 0.0 and ci["ci_high"] == 0.0  # identical -> no difference, ever


def test_paired_ci_is_deterministic_and_brackets_point():
    mom = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, -0.003] * 8
    mf = [x * 1.2 for x in mom]  # scaled -> same Sharpe (scale-invariant) -> delta ~ 0
    a = paired_ci(mom, mf, n_resamples=300, seed=17)
    b = paired_ci(mom, mf, n_resamples=300, seed=17)
    assert a == b  # seeded -> reproducible
    assert a["ci_low"] <= a["delta"] <= a["ci_high"]


def test_paired_ci_too_short_returns_nan_ci():
    short = [0.01, -0.01, 0.02]  # < block*2
    ci = paired_ci(short, short, n_resamples=100, seed=1)
    assert ci["ci_low"] != ci["ci_low"]  # NaN
