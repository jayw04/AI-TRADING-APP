"""FI-001 Phase 4 adaptive — pure-helper tests (offline, no store)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fi001_phase4_adaptive.py"
_spec = importlib.util.spec_from_file_location("fi001_phase4_adaptive", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def test_regime_riskon_is_boolean_and_shifted():
    # rising then falling price series; the risk-on flag must lag by one day (no look-ahead)
    idx = pd.bdate_range("2020-01-01", periods=260)
    px = pd.Series(np.concatenate([np.linspace(100, 200, 210), np.linspace(200, 120, 50)]), index=idx)
    r = _mod._regime_riskon(px)
    assert r.dtype == bool
    assert len(r) == len(px)
    # after a long uptrend the flag is risk-ON; deep in the downtrend it flips OFF
    assert bool(r.iloc[205]) is True
    assert bool(r.iloc[-1]) is False


def test_regime_riskon_no_lookahead_first_value_is_failopen():
    idx = pd.bdate_range("2020-01-01", periods=10)
    px = pd.Series(range(10), index=idx, dtype=float)
    r = _mod._regime_riskon(px)
    assert bool(r.iloc[0]) is True  # warm-up defaults risk-ON


def test_trailing_avg_corr_is_shifted_and_bounded():
    idx = pd.bdate_range("2020-01-01", periods=200)
    rng = np.random.default_rng(3)
    R = pd.DataFrame({"a": rng.normal(0, 0.01, 200), "b": rng.normal(0, 0.01, 200),
                      "c": rng.normal(0, 0.01, 200)}, index=idx)
    ac = _mod._trailing_avg_corr(R, window=63)
    assert len(ac) == 200
    assert pd.isna(ac.iloc[0])           # shifted -> first value undefined
    body = ac.dropna()
    assert (body.abs() <= 1.0 + 1e-9).all()


def test_curve_from_returns_roundtrip():
    idx = pd.to_datetime(["2020-01-02", "2020-01-03"])
    curve = _mod._curve_from_returns(pd.Series([0.2, -0.1], index=idx), initial=100.0)
    assert curve[-1][1] == pytest.approx(108.0)


def test_calmar_and_nan_helpers():
    assert _mod._calmar(0.3, -0.30) == pytest.approx(1.0)
    assert _mod._calmar(0.3, 0.0) is None
    assert _mod._nan(float("nan")) is None
    assert _mod._nan(1.5) == 1.5
