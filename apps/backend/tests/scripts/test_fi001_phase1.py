"""FI-001 Phase 1 measurement — pure-helper tests (offline, no store)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fi001_phase1_measurement.py"
_spec = importlib.util.spec_from_file_location("fi001_phase1_measurement", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def _curve(vals: list[float]) -> list[tuple[date, float]]:
    d0 = date(2020, 1, 1)
    return [(d0 + timedelta(days=i), v) for i, v in enumerate(vals)]


def test_worst_drawdown_window_finds_peak_to_trough():
    # rise to 120 (peak), fall to 90 (trough), recover to 110
    curve = _curve([100, 110, 120, 100, 90, 100, 110])
    lo, hi = _mod._worst_drawdown_window(curve)
    assert lo == pd.Timestamp(date(2020, 1, 3))  # the 120 peak
    assert hi == pd.Timestamp(date(2020, 1, 5))  # the 90 trough


def test_worst_drawdown_window_empty():
    assert _mod._worst_drawdown_window([]) is None
    assert _mod._worst_drawdown_window(_curve([100])) is None


def test_returns_series_is_date_indexed_pct_change():
    s = _mod._returns_series(_curve([100, 110, 99]))
    assert list(s.round(4)) == [0.1, -0.1]
    assert s.index[0] == pd.Timestamp(date(2020, 1, 2))


def test_corr_perfect_and_short():
    a = pd.Series([0.01, 0.02, -0.01, 0.03])
    assert _mod._corr(a, a) == pytest.approx(1.0)  # perfect self-correlation
    assert _mod._corr(a.iloc[:2], a.iloc[:2]) is None  # < 3 paired points -> None


def test_rolling_corr_profile_bounds():
    idx = pd.bdate_range("2020-01-01", periods=200)
    a = pd.Series(range(200), index=idx, dtype=float).pct_change().dropna()
    prof = _mod._rolling_corr_profile(a, a, 63)
    assert prof["window"] == 63
    # a rolling-correlated-with-itself is 1.0 throughout
    assert prof["mean"] == pytest.approx(1.0) and prof["min"] == pytest.approx(1.0)


def test_rolling_corr_profile_too_short():
    a = pd.Series([0.01, 0.02, 0.03])
    prof = _mod._rolling_corr_profile(a, a, 63)
    assert prof["mean"] is None
