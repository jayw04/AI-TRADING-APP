"""FI-001 Phase 2 interaction — pure-helper tests (offline, no store)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fi001_phase2_interaction.py"
_spec = importlib.util.spec_from_file_location("fi001_phase2_interaction", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def test_curve_from_returns_compounds():
    idx = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    ret = pd.Series([0.10, -0.10, 0.05], index=idx)
    curve = _mod._curve_from_returns(ret, initial=100.0)
    assert curve[0] == (date(2020, 1, 2), pytest.approx(110.0))
    assert curve[1][1] == pytest.approx(99.0)          # 110 * 0.9
    assert curve[2][1] == pytest.approx(103.95)        # 99 * 1.05


def test_calmar_sign_and_zero():
    assert _mod._calmar(0.20, -0.40) == pytest.approx(0.5)
    assert _mod._calmar(0.20, 0.0) is None


def test_verdict_tiers():
    assert _mod._verdict(True, -5.0) == "IMPROVES (Sharpe CI > 0)"       # improves wins regardless of DD
    assert _mod._verdict(False, 5.0).startswith("DIVERSIFIES")           # DD >= 3pp shallower
    assert _mod._verdict(False, 1.0) == "NO HELP"                        # neither
    assert _mod._verdict(False, None) == "NO HELP"


def test_metrics_on_flat_series_is_zero_dd():
    idx = pd.bdate_range("2020-01-01", periods=30)
    ret = pd.Series([0.0] * 30, index=idx)
    m = _mod._metrics("flat", ret)
    assert m.max_drawdown == 0.0
    assert m.sharpe == 0.0
