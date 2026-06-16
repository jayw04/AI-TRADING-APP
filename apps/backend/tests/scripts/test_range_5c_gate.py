"""§5c gate — evaluate_gate pure-function tests (pre-registered acceptance).

Loaded via importlib (scripts/ isn't a package). No harness / network needed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "range_5c_gate.py"
_spec = importlib.util.spec_from_file_location("range_5c_gate", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod  # so the module's dataclasses resolve their module
_spec.loader.exec_module(_mod)
evaluate_gate = _mod.evaluate_gate
GateMetrics = _mod.GateMetrics
GateThresholds = _mod.GateThresholds


def _good_is() -> GateMetrics:
    # Clears every threshold: 40 trades, PF 1.6, 52% win, 1.3 payoff, 5% DD.
    return GateMetrics(profit_factor=1.6, win_rate=0.52, trade_count=40,
                       avg_win=130.0, avg_loss=-100.0, max_drawdown=-0.05)


def _good_oos() -> GateMetrics:
    return GateMetrics(profit_factor=1.4, win_rate=0.50, trade_count=18,
                       avg_win=120.0, avg_loss=-100.0, max_drawdown=-0.04)


def test_all_pass_is_go():
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=True)
    assert v.go, [c for c in v.checks if not c[1]]


def test_too_few_trades_no_go():
    m = GateMetrics(1.6, 0.52, 12, 130.0, -100.0, -0.05)  # 12 < 30
    v = evaluate_gate(m, _good_oos(), all_trades_closed=True)
    assert not v.go
    assert any(name.startswith("trade_count") and not ok for name, ok, _ in v.checks)


def test_thin_profit_factor_no_go():
    m = GateMetrics(1.15, 0.52, 40, 130.0, -100.0, -0.05)  # PF < 1.3
    assert not evaluate_gate(m, _good_oos(), all_trades_closed=True).go


def test_payoff_below_one_no_go():
    m = GateMetrics(1.6, 0.52, 40, 90.0, -100.0, -0.05)  # 0.9 < 1.0
    assert not evaluate_gate(m, _good_oos(), all_trades_closed=True).go


def test_drawdown_over_bound_no_go():
    # default bound = 2 * 1% * 4 = 8%; 10% exceeds it
    m = GateMetrics(1.6, 0.52, 40, 130.0, -100.0, -0.10)
    assert not evaluate_gate(m, _good_oos(), all_trades_closed=True).go


def test_oos_collapse_no_go():
    # IS PF 1.6 → OOS floor 1.28; OOS PF 1.0 fails (curve-fit signal)
    oos = GateMetrics(1.0, 0.50, 18, 120.0, -100.0, -0.04)
    assert not evaluate_gate(_good_is(), oos, all_trades_closed=True).go


def test_stuck_position_no_go():
    assert not evaluate_gate(_good_is(), _good_oos(), all_trades_closed=False).go


def test_no_losses_payoff_is_infinite_passes():
    m = GateMetrics(profit_factor=5.0, win_rate=0.6, trade_count=40,
                    avg_win=130.0, avg_loss=0.0, max_drawdown=-0.03)
    v = evaluate_gate(m, _good_oos(), all_trades_closed=True)
    assert any(name.startswith("avg_win/avg_loss") and ok for name, ok, _ in v.checks)


def test_thresholds_are_conservative_defaults():
    t = GateThresholds()
    assert t.min_trades == 30 and t.min_profit_factor == 1.3
    assert t.min_win_rate == 0.45 and t.min_avg_win_loss == 1.0
    assert t.max_drawdown_bound == pytest.approx(0.08)
