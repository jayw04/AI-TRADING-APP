"""§5c gate — evaluate_gate pure-function tests (pre-registered acceptance, v0.2).

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


def test_runner_backtest_config_kwargs_are_valid_fields():
    """Regression: the CLI runner (_run_window / evidence) is network-bound so
    isn't unit-run; this guards the BacktestConfig contract it depends on, which
    previously broke (`starting_equity` was not a field; `initial_equity` is)."""
    from app.strategies.backtest_models import BacktestConfig

    fields = set(BacktestConfig.__dataclass_fields__)
    assert {"start", "end", "timeframe", "initial_equity", "slippage_bps", "params"} <= fields
    # evidence reads the seed field default without constructing the config
    assert BacktestConfig.__dataclass_fields__["seed"].default is not None


def _good_is(**over) -> GateMetrics:
    base = dict(profit_factor=1.6, win_rate=0.52, trade_count=55,
                avg_win=130.0, avg_loss=-100.0, max_drawdown=-0.05,
                p95_hold_seconds=3600.0)
    base.update(over)
    return GateMetrics(**base)


def _good_oos(**over) -> GateMetrics:
    base = dict(profit_factor=1.4, win_rate=0.50, trade_count=22,
                avg_win=120.0, avg_loss=-100.0, max_drawdown=-0.04)
    base.update(over)
    return GateMetrics(**base)


def _failed(v):
    return [c[0] for c in v.checks if not c[1]]


def test_clean_pass_is_go_no_warnings():
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO", _failed(v)
    assert v.go and v.eligible and not v.warnings


def test_thin_sample_30_to_49_is_go_warning():
    v = evaluate_gate(_good_is(trade_count=35), _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO-WARNING"
    assert not v.go and v.eligible  # eligible, but needs Owner signoff
    assert any("Owner signoff required" in w for w in v.warnings)


def test_below_30_trades_is_inconclusive():
    v = evaluate_gate(_good_is(trade_count=18), _good_oos(), all_trades_closed=True)
    assert v.verdict == "INCONCLUSIVE"
    assert not v.go and v.warnings


def test_thin_profit_factor_no_go():
    v = evaluate_gate(_good_is(profit_factor=1.15), _good_oos(), all_trades_closed=True)
    assert v.verdict == "NO-GO"


def test_expectancy_below_min_no_go():
    # win 45%, payoff 1.2 (passes), but expectancy ~ -0.01R < 0.15R
    m = _good_is(win_rate=0.45, avg_win=120.0, avg_loss=-100.0, profit_factor=1.35)
    v = evaluate_gate(m, _good_oos(), all_trades_closed=True)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("expectancy") for name in _failed(v))


def test_drawdown_over_bound_no_go():
    v = evaluate_gate(_good_is(max_drawdown=-0.10), _good_oos(), all_trades_closed=True)
    assert v.verdict == "NO-GO"


def test_oos_below_absolute_floor_no_go():
    # IS PF 1.2 → 0.8xIS = 0.96, but floor is max(1.0, 0.96) = 1.0; OOS 0.95 fails
    v = evaluate_gate(_good_is(profit_factor=1.2), _good_oos(profit_factor=0.95),
                      all_trades_closed=True)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("OOS PF") for name in _failed(v))


def test_oos_ratio_collapse_no_go():
    # IS PF 1.6 → floor max(1.0, 1.28) = 1.28; OOS 1.1 fails the ratio
    v = evaluate_gate(_good_is(), _good_oos(profit_factor=1.1), all_trades_closed=True)
    assert v.verdict == "NO-GO"


def test_stuck_position_no_go():
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=False)
    assert v.verdict == "NO-GO"


def test_hold_time_drift_no_go():
    v = evaluate_gate(_good_is(p95_hold_seconds=30000.0), _good_oos(), all_trades_closed=True)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("hold time") for name in _failed(v))


def test_hold_time_absent_skips_check():
    v = evaluate_gate(_good_is(p95_hold_seconds=None), _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO"
    assert not any(name.startswith("hold time") for name, _, _ in v.checks)


def test_robustness_pf_collapse_no_go():
    # worst perturbed PF 1.0 < 0.8 x IS PF (1.28); trade counts healthy
    runs = [(1.5, 55), (1.45, 54), (1.0, 56), (1.4, 53), (1.55, 55), (1.3, 52)]
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=True, robustness_runs=runs)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("robustness") for name in _failed(v))


def test_robustness_trade_count_collapse_no_go():
    # PFs fine, but a perturbation fires almost no trades (10 < 0.8 x 55 = 44)
    runs = [(1.5, 55), (1.45, 54), (1.5, 10), (1.4, 53), (1.55, 55), (1.3, 52)]
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=True, robustness_runs=runs)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("robustness") for name in _failed(v))


def test_robustness_ok_go():
    runs = [(1.5, 55), (1.45, 54), (1.35, 50), (1.4, 53), (1.55, 55), (1.3, 48)]
    v = evaluate_gate(_good_is(), _good_oos(), all_trades_closed=True, robustness_runs=runs)
    assert v.verdict == "GO"


def test_low_data_coverage_no_go():
    # 96% is below the tightened 97% intraday floor → NO-GO
    v = evaluate_gate(_good_is(data_coverage=0.96), _good_oos(), all_trades_closed=True)
    assert v.verdict == "NO-GO"
    assert any(name.startswith("data coverage") for name in _failed(v))


def test_good_data_coverage_go():
    v = evaluate_gate(_good_is(data_coverage=0.99), _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO"


def test_data_coverage_absent_skips_check():
    v = evaluate_gate(_good_is(data_coverage=None), _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO"
    assert not any(name.startswith("data coverage") for name, _, _ in v.checks)


def test_no_losses_infinite_payoff_and_expectancy_pass():
    # avg_loss=0 → payoff & expectancy are infinite (div-by-zero guarded), not a
    # crash; PF kept normal so the OOS floor stays attainable.
    m = _good_is(avg_loss=0.0)
    v = evaluate_gate(m, _good_oos(), all_trades_closed=True)
    assert v.verdict == "GO"


def test_thresholds_are_conservative_defaults():
    t = GateThresholds()
    assert t.min_trades_floor == 30 and t.min_trades_strong == 50
    assert t.min_profit_factor == 1.3 and t.min_win_rate == 0.45
    assert t.min_avg_win_loss == 1.0 and t.min_expectancy_r == 0.15
    assert t.oos_pf_floor == 1.0 and t.oos_pf_ratio == 0.8
    assert t.max_drawdown_bound == pytest.approx(0.08)
    assert t.oos_floor(1.6) == pytest.approx(1.28)
    assert t.oos_floor(1.1) == pytest.approx(1.0)  # absolute floor wins
    assert t.min_data_coverage == 0.97
    assert t.robustness_min_ratio == 0.8 and t.robustness_min_trade_ratio == 0.8
