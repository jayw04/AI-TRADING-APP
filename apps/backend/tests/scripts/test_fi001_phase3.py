"""FI-001 Phase 3 allocation — pure-helper tests (offline, no store)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fi001_phase3_allocation.py"
_spec = importlib.util.spec_from_file_location("fi001_phase3_allocation", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def _window(cols=("a", "b", "c"), n=120, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(0, 0.01, size=(n, len(cols))), columns=list(cols))


def test_weight_fns_sum_to_one_and_nonneg():
    win = _window()
    for name, fn in _mod.WEIGHT_FNS.items():
        w = fn(win)
        assert w.shape == (3,), name
        assert w.sum() == pytest.approx(1.0), name
        assert (w >= -1e-9).all(), name  # long-only


def test_inverse_vol_downweights_the_volatile_book():
    # column 'c' is 5x more volatile -> should get the smallest inverse-vol weight
    win = _window(seed=1)
    win["c"] = win["c"] * 5.0
    w = _mod._w_inverse_vol(win)
    assert w[2] < w[0] and w[2] < w[1]


def test_combined_returns_no_lookahead_first_month_is_equal_weight():
    # 3 books over 4 months; the first month has no trailing window -> equal weight
    idx = pd.bdate_range("2020-01-01", periods=84)  # ~4 months
    R = pd.DataFrame({
        "a": [0.01] * 84,
        "b": [0.00] * 84,
        "c": [-0.01] * 84,
    }, index=idx)
    combined = _mod._combined_returns(R, _mod._w_erc)
    # first month: equal weight of (+1%, 0, -1%) = 0% each day
    first_month = combined[(combined.index.year == 2020) & (combined.index.month == 1)]
    assert first_month.round(6).eq(0.0).all()


def test_curve_from_returns_roundtrip():
    idx = pd.to_datetime(["2020-01-02", "2020-01-03"])
    curve = _mod._curve_from_returns(pd.Series([0.1, -0.1], index=idx), initial=100.0)
    assert curve[-1][1] == pytest.approx(99.0)


def test_nan_helper():
    assert _mod._nan(float("nan")) is None
    assert _mod._nan(0.5) == 0.5
