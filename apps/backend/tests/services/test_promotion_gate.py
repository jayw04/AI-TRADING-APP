"""P6b §3a-gate — the 4-criterion promotion gate evaluator (ADR 0007).

Pure-function tests over synthetic VariantComparison objects.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.paper_variant import VariantComparison, VariantSideMetrics
from app.services.promotion_gate import (
    EvidenceBundle,
    _check_absolute_return,
    _check_drawdown_divergence,
    _check_duration,
    _check_sharpe_margin,
    _read_thresholds,
    evaluate_gate,
)

START = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _side(*, sharpe=1.0, max_dd=-0.10, trades=60, win_rate=0.6, avg_ret=0.01):
    return VariantSideMetrics(
        trade_count=trades,
        win_rate=win_rate,
        avg_return_per_trade=avg_ret,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
    )


def _curve(values, start=START):
    return [
        (start + timedelta(days=i), Decimal(str(v))) for i, v in enumerate(values)
    ]


def _comp(
    *,
    days=31,
    variant_trades=60,
    live_sharpe=1.0,
    variant_sharpe=1.10,
    live_max_dd=-0.10,
    capital_base=100000,
    variant_curve=None,
):
    return VariantComparison(
        parent_strategy_id=1,
        variant_strategy_id=2,
        window_start=START,
        window_end=START + timedelta(days=days),
        live_metrics=_side(sharpe=live_sharpe, max_dd=live_max_dd),
        variant_metrics=_side(sharpe=variant_sharpe, trades=variant_trades),
        deltas={},
        live_trade_count=60,
        variant_trade_count=variant_trades,
        live_equity_curve=_curve([capital_base, capital_base]),
        variant_equity_curve=(
            variant_curve
            if variant_curve is not None
            else _curve([capital_base, capital_base + 500])
        ),
        capital_base=Decimal(str(capital_base)),
    )


T = _read_thresholds(None)


# ---- duration (AND) ----


def test_duration_passes_when_both_days_and_trades_exceed():
    r = _check_duration(_comp(days=31, variant_trades=60), T)
    assert r.passed


def test_duration_fails_when_days_ok_but_trades_short():
    r = _check_duration(_comp(days=31, variant_trades=40), T)
    assert not r.passed  # AND, not OR


def test_duration_fails_when_trades_ok_but_days_short():
    r = _check_duration(_comp(days=10, variant_trades=60), T)
    assert not r.passed


def test_duration_fails_when_neither():
    r = _check_duration(_comp(days=10, variant_trades=10), T)
    assert not r.passed


# ---- sharpe margin (relative x1.05) ----


def test_sharpe_margin_passes_at_5pct_relative():
    r = _check_sharpe_margin(_comp(live_sharpe=1.0, variant_sharpe=1.05), T)
    assert r.passed
    assert abs(r.details["required_variant_sharpe"] - 1.05) < 1e-9


def test_sharpe_margin_fails_just_below_required():
    r = _check_sharpe_margin(_comp(live_sharpe=1.0, variant_sharpe=1.04), T)
    assert not r.passed


def test_sharpe_margin_zero_baseline_passes_at_zero():
    r = _check_sharpe_margin(_comp(live_sharpe=0.0, variant_sharpe=0.0), T)
    assert r.passed  # required = 0, variant 0 >= 0


# ---- absolute return (strict > 0, final - capital_base) ----


def test_absolute_return_passes_when_final_above_capital_base():
    r = _check_absolute_return(_comp(capital_base=100000, variant_curve=_curve([100000, 100800])))
    assert r.passed
    assert r.details["variant_total_return"] == 800.0


def test_absolute_return_fails_at_zero():
    r = _check_absolute_return(_comp(variant_curve=_curve([100000, 100000])))
    assert not r.passed  # strict > 0


def test_absolute_return_fails_when_below_capital_base():
    r = _check_absolute_return(_comp(variant_curve=_curve([100000, 99000])))
    assert not r.passed


def test_absolute_return_skips_when_no_curve():
    r = _check_absolute_return(_comp(variant_curve=[]))
    assert not r.passed
    assert r.details["skip_reason"] == "no_equity_curve"


# ---- drawdown divergence (<= 1.20x live max-dd) ----


def test_drawdown_divergence_passes_within_120pct():
    # live max-dd 10% → allowed 12%. variant worst 10% drop within 7 days.
    curve = _curve([100000, 110000, 99000, 105000])  # peak 110k → trough 99k = 10%
    r = _check_drawdown_divergence(
        _comp(live_max_dd=-0.10, variant_curve=curve), T
    )
    assert r.passed
    assert abs(r.details["variant_worst_window_drawdown"] - (11000 / 110000)) < 1e-9


def test_drawdown_divergence_fails_above_120pct():
    # peak 110k → trough 95k = 13.6% > 12% allowed.
    curve = _curve([100000, 110000, 95000, 100000])
    r = _check_drawdown_divergence(
        _comp(live_max_dd=-0.10, variant_curve=curve), T
    )
    assert not r.passed


def test_drawdown_divergence_trivial_pass_when_live_dd_zero():
    curve = _curve([100000, 110000, 80000])  # big drop, but no live reference
    r = _check_drawdown_divergence(
        _comp(live_max_dd=0.0, variant_curve=curve), T
    )
    assert r.passed
    assert r.details["skip_reason"] == "live_drawdown_zero_no_reference"


def test_drawdown_divergence_trivial_pass_when_insufficient_data():
    r = _check_drawdown_divergence(
        _comp(live_max_dd=-0.10, variant_curve=_curve([100000])), T
    )
    assert r.passed


def test_drawdown_rolling_window_caps_at_window_span():
    # A slow 2%/day decline over 15 days: the FULL peak-to-trough drawdown is
    # ~24.5%, but any single 7-day window only spans ~13.2% (1 - 0.98**7). The
    # rolling-window check must report the ~13% window figure, not the full 24%.
    vals = [100000 * (0.98**i) for i in range(15)]
    curve = _curve(vals)
    r = _check_drawdown_divergence(
        _comp(live_max_dd=-0.50, variant_curve=curve), T
    )
    worst = r.details["variant_worst_window_drawdown"]
    full_decline = (vals[0] - vals[-1]) / vals[0]  # ~0.245
    assert full_decline > 0.20
    assert 0.10 < worst < 0.16  # the 7-day span amount, well below the full decline


# ---- composite + envelope ----


def test_all_passed_only_when_all_four_pass():
    good = _comp(
        days=31, variant_trades=60, live_sharpe=1.0, variant_sharpe=1.10,
        live_max_dd=-0.10, variant_curve=_curve([100000, 100500, 100800]),
    )
    bundle = evaluate_gate(good)
    assert isinstance(bundle, EvidenceBundle)
    assert bundle.all_criteria_passed
    # Flip one criterion (trades short) → composite fails.
    bad = _comp(
        days=31, variant_trades=10, live_sharpe=1.0, variant_sharpe=1.10,
        live_max_dd=-0.10, variant_curve=_curve([100000, 100800]),
    )
    assert not evaluate_gate(bad).all_criteria_passed


def test_threshold_envelope_overrides_defaults():
    # 10 trades fails default min_trades=50, passes override min_trades=5.
    comp = _comp(days=31, variant_trades=10)
    assert not _check_duration(comp, _read_thresholds(None)).passed
    env = {"promotion_thresholds": {"min_trades": 5}}
    assert _check_duration(comp, _read_thresholds(env)).passed
