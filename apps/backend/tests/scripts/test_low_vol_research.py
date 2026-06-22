"""LOW-001 Low Volatility research — pure helpers (offline)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "low_vol_research.py"
_spec = importlib.util.spec_from_file_location("low_vol_research", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

windows = _mod._windows
paired_ci = _mod._paired_sharpe_diff_ci
excludes_zero_pos = _mod._excludes_zero_pos


def test_windows_contiguous_and_cover_range():
    ws = windows(date(2000, 1, 1), date(2026, 6, 12), 5)
    assert len(ws) == 5
    assert ws[0][0] == date(2000, 1, 1) and ws[-1][1] == date(2026, 6, 12)
    for a, b in zip(ws, ws[1:], strict=False):
        assert a[1] == b[0]


def test_paired_ci_identical_series_is_zero():
    r = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 10
    ci = paired_ci(r, list(r), n_resamples=200, seed=17)
    assert ci["delta"] == 0.0 and ci["ci_low"] == 0.0 and ci["ci_high"] == 0.0


def test_paired_ci_deterministic_and_brackets_point():
    a = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, -0.003] * 8
    b = [x * 0.8 for x in a]  # scaled -> same Sharpe -> delta ~ 0
    p = paired_ci(a, b, n_resamples=300, seed=17)
    assert p == paired_ci(a, b, n_resamples=300, seed=17)
    assert p["ci_low"] <= p["delta"] <= p["ci_high"]


def test_excludes_zero_pos():
    assert excludes_zero_pos({"ci_low": 0.05}) is True
    assert excludes_zero_pos({"ci_low": -0.01}) is False
    assert excludes_zero_pos({"ci_low": float("nan")}) is False


def test_factor_helpers_importable_and_frozen():
    assert callable(_mod.low_vol_score)
    assert callable(_mod.single_momentum_score)
    assert callable(_mod.blend_score)
    assert _mod.VOL_LOOKBACK_DAYS == 252  # frozen, no optimization
