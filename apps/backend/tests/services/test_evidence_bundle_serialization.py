"""P6b §3a-gate — evidence bundle JSON serialization."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.paper_variant import VariantComparison, VariantSideMetrics
from app.services.promotion_gate import bundle_to_json, evaluate_gate

START = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _side():
    return VariantSideMetrics(
        trade_count=60, win_rate=0.6, avg_return_per_trade=0.01,
        sharpe_ratio=1.1, max_drawdown=-0.08,
    )


def _comp():
    curve = [
        (START + timedelta(days=i), Decimal(str(100000 + i * 100)))
        for i in range(3)
    ]
    return VariantComparison(
        parent_strategy_id=1, variant_strategy_id=2,
        window_start=START, window_end=START + timedelta(days=31),
        live_metrics=_side(), variant_metrics=_side(),
        deltas={"sharpe_delta_pct": 10.0, "win_rate_delta_pp": 5.0,
                "max_drawdown_delta_pct": None, "avg_return_delta_pct": 2.0},
        live_trade_count=60, variant_trade_count=60,
        live_equity_curve=curve, variant_equity_curve=curve,
        capital_base=Decimal("100000"),
    )


def test_bundle_to_json_includes_all_top_level_fields():
    out = bundle_to_json(evaluate_gate(_comp()))
    assert set(out) == {"captured_at", "all_criteria_passed", "comparison", "gate_results"}
    assert isinstance(out["all_criteria_passed"], bool)
    assert set(out["gate_results"]) == {
        "duration", "sharpe_margin", "absolute_return", "drawdown_divergence",
    }
    for crit in out["gate_results"].values():
        assert set(crit) == {"name", "passed", "details"}


def test_bundle_to_json_serializes_equity_curves_and_decimals_to_float():
    out = bundle_to_json(evaluate_gate(_comp()))
    comp = out["comparison"]
    assert isinstance(comp["capital_base"], float)
    assert comp["capital_base"] == 100000.0
    pts = comp["variant_equity_curve"]
    assert len(pts) == 3
    assert set(pts[0]) == {"ts", "equity"}
    assert isinstance(pts[0]["equity"], float)
    assert isinstance(pts[0]["ts"], str)  # ISO


def test_bundle_to_json_is_json_round_trippable():
    import json

    out = bundle_to_json(evaluate_gate(_comp()))
    # No Decimal/datetime leaks → json.dumps must not raise.
    assert json.loads(json.dumps(out))["comparison"]["capital_base"] == 100000.0
