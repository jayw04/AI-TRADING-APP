"""WP6 AMD-03 — estimator ladder E0/E1/E2 (hermetic; no broker)."""

from __future__ import annotations

from decimal import Decimal as D

from app.risk.loss_control.phase0_contracts import VERDICT_INDETERMINATE
from app.risk.loss_control.phase0_estimator import (
    E0_DEFAULT_LOWER_TAIL_QUANTILE,
    EstimateStatus,
    EstimatorLevel,
    EstimatorRegistry,
    GovernedGraduation,
    GraduationRefuseReason,
    StratumObservations,
    assert_no_order_path_imports,
    empirical_lower_tail_quantile,
    estimate_e0,
    estimate_e1,
    estimate_e2_bootstrap_lower,
)


def _stratum(n: int = 20, base: str = "10.00") -> StratumObservations:
    # Spread losses around base so quantile is well-defined.
    losses = tuple(D(base) + D(i) * D("0.10") for i in range(n))
    return StratumObservations(symbol="KOKU", losses=losses)


def test_default_quantile_is_lower_tail_tenth() -> None:
    assert D("0.10") == E0_DEFAULT_LOWER_TAIL_QUANTILE


def test_e0_under_stratum_min_is_indeterminate() -> None:
    r = estimate_e0(_stratum(n=5))
    assert r.status == EstimateStatus.INDETERMINATE
    assert r.verdict_hint == VERDICT_INDETERMINATE
    assert r.conservative_min_supported_loss is None
    assert r.as_dict()["active_estimator_level"] == "E0"


def test_e0_emits_lower_tail_bound() -> None:
    s = _stratum(20)
    r = estimate_e0(s)
    assert r.status == EstimateStatus.OK
    expected = empirical_lower_tail_quantile(s.losses, D("0.10"))
    assert r.conservative_min_supported_loss == expected
    # Lower-tail is below the median.
    assert r.conservative_min_supported_loss < empirical_lower_tail_quantile(s.losses, D("0.50"))


def test_e1_monotone_nondecreasing_in_size() -> None:
    s = _stratum(20)
    small = estimate_e1(
        s,
        reference_notional=D("25000"),
        reference_qty=D("100"),
        notional=D("25000"),
        qty=D("100"),
    )
    large = estimate_e1(
        s,
        reference_notional=D("25000"),
        reference_qty=D("100"),
        notional=D("50000"),
        qty=D("200"),
    )
    assert small.status == large.status == EstimateStatus.OK
    assert large.conservative_min_supported_loss is not None
    assert small.conservative_min_supported_loss is not None
    assert large.conservative_min_supported_loss >= small.conservative_min_supported_loss
    assert large.level == EstimatorLevel.E1


def test_e2_refused_without_governed_graduation() -> None:
    reg = EstimatorRegistry()  # still E0
    r = estimate_e2_bootstrap_lower(_stratum(20), registry=reg)
    assert r.status == EstimateStatus.REFUSED
    assert "never automatic" in r.detail


def test_graduate_e2_requires_n_and_oos() -> None:
    reg = EstimatorRegistry()
    assert (
        reg.graduate(
            GovernedGraduation(
                to_level=EstimatorLevel.E2,
                decision_id="g-1",
                note="attempt E2",
                pooled_n=10,
                oos_coverage_e0=0.9,
                oos_coverage_candidate=0.95,
            )
        )
        is GraduationRefuseReason.N_BELOW_THRESHOLD
    )
    assert (
        reg.graduate(
            GovernedGraduation(
                to_level=EstimatorLevel.E2,
                decision_id="g-2",
                note="bad oos",
                pooled_n=59,
                oos_coverage_e0=0.95,
                oos_coverage_candidate=0.90,
            )
        )
        is GraduationRefuseReason.OOS_WORSE_THAN_E0
    )


def test_graduate_e1_then_e2_then_estimate() -> None:
    reg = EstimatorRegistry()
    assert (
        reg.graduate(
            GovernedGraduation(
                to_level=EstimatorLevel.E1,
                decision_id="g-e1",
                note="enable monotone adjustment",
                pooled_n=30,
                oos_coverage_e0=0.9,
                oos_coverage_candidate=0.9,
            )
        )
        is None
    )
    assert reg.active_level == EstimatorLevel.E1
    assert (
        reg.graduate(
            GovernedGraduation(
                to_level=EstimatorLevel.E2,
                decision_id="g-e2",
                note="OOS coverage no worse than E0",
                pooled_n=59,
                oos_coverage_e0=0.92,
                oos_coverage_candidate=0.93,
            )
        )
        is None
    )
    r = estimate_e2_bootstrap_lower(_stratum(20), registry=reg)
    assert r.status == EstimateStatus.OK
    assert r.level == EstimatorLevel.E2
    assert r.conservative_min_supported_loss is not None


def test_negative_loss_rejected_in_stratum() -> None:
    try:
        StratumObservations(symbol="X", losses=(D("-1"),))
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
