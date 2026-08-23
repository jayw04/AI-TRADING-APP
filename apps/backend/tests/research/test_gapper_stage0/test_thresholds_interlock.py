"""Verdict seam: NOT_EVALUABLE guards, interlock token, DIAGNOSTIC_ONLY brand."""

from __future__ import annotations

from pathlib import Path

from app.research.gapper_stage0.dataset_contract import DatasetContract
from app.research.gapper_stage0.design_latch import APPROVED_DESIGN_SHA256, SUPERSEDED_SHA256
from app.research.gapper_stage0.interlock import (
    EXECUTION_TOKEN,
    NOT_AUTHORIZED_REASON,
    verify_execution_token,
)
from app.research.gapper_stage0.thresholds import (
    GO_MAX_EXECUTION_FAILURE_RATE,
    GO_MAX_FRICTION_TO_IQR,
    GO_MIN_CHEAP_SIGNAL_EDGE_BPS,
    GO_MIN_ELIGIBLE_DAY_FRACTION,
    GO_MIN_ELIGIBLE_NAMES,
    GO_MIN_ORACLE_NET_POSITIVE,
    GO_MIN_POSITIVE_DAY_FRACTION,
    GO_MIN_PRIMARY_IQR_BPS,
    NOT_EVALUABLE,
    ORACLE_BRAND,
    ORACLE_METRIC,
    REQUIRED_MEASUREMENTS,
    evaluate_thresholds,
    stage0_verdict,
)


def _complete_contract() -> DatasetContract:
    return DatasetContract(
        date_range=("2024-01-02", "2026-06-30"),
        target_event_days=500,
        source_vendor="OWNER-DECIDED-VENDOR",
        survivorship_rules="pit universe",
        corporate_action_handling="closeadj",
        pit_rules="date < asof",
        min_analyzable_sample=100,
    )


def _passing_measurements() -> dict[str, float]:
    return {
        "eligible_day_fraction": 0.60,
        "primary_iqr_bps": 200.0,
        "friction_to_iqr": 0.20,
        "oracle_net_positive_fraction": 0.70,
        "cheap_signal_edge_bps": 25.0,
        "positive_day_fraction": 0.60,
        "execution_failure_rate": 0.05,
    }


def _token_file(tmp_path: Path, content: str = EXECUTION_TOKEN) -> Path:
    p = tmp_path / "token"
    p.write_text(content, encoding="utf-8")
    return p


# ---- frozen constants -------------------------------------------------------


def test_frozen_section_3_3_values() -> None:
    assert GO_MIN_ELIGIBLE_NAMES == 10
    assert GO_MIN_ELIGIBLE_DAY_FRACTION == 0.50
    assert GO_MIN_PRIMARY_IQR_BPS == 150.0
    assert GO_MAX_FRICTION_TO_IQR == 0.25
    assert GO_MIN_ORACLE_NET_POSITIVE == 0.65
    assert GO_MIN_CHEAP_SIGNAL_EDGE_BPS == 20.0
    assert GO_MIN_POSITIVE_DAY_FRACTION == 0.55
    assert GO_MAX_EXECUTION_FAILURE_RATE == 0.10
    assert EXECUTION_TOKEN == "G4-STAGE0-EXECUTION-AUTHORIZED"


# ---- interlock --------------------------------------------------------------


def test_token_absent_or_wrong_is_unauthorized(tmp_path: Path) -> None:
    assert verify_execution_token(None) is False
    assert verify_execution_token(tmp_path / "missing") is False
    assert verify_execution_token(_token_file(tmp_path, "WRONG-TOKEN")) is False


def test_token_exact_content_verifies(tmp_path: Path) -> None:
    assert verify_execution_token(_token_file(tmp_path)) is True
    # surrounding whitespace tolerated; content must match exactly
    assert verify_execution_token(_token_file(tmp_path, f"\n{EXECUTION_TOKEN}\n")) is True


# ---- NOT_EVALUABLE guards ---------------------------------------------------


def test_missing_token_is_not_evaluable_with_g4_reason(tmp_path: Path) -> None:
    v = stage0_verdict(
        contract=_complete_contract(),
        measurements=_passing_measurements(),
        token_path=None,
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v["verdict"] == NOT_EVALUABLE
    assert NOT_AUTHORIZED_REASON in v["reasons"]
    assert "thresholds" not in v


def test_incomplete_contract_is_not_evaluable(tmp_path: Path) -> None:
    v = stage0_verdict(
        contract=DatasetContract(),  # source_vendor unset — owner decision open
        measurements=_passing_measurements(),
        token_path=_token_file(tmp_path),
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v["verdict"] == NOT_EVALUABLE
    assert any("source_vendor" in r for r in v["reasons"])


def test_superseded_design_is_not_evaluable(tmp_path: Path) -> None:
    v = stage0_verdict(
        contract=_complete_contract(),
        measurements=_passing_measurements(),
        token_path=_token_file(tmp_path),
        design_sha=SUPERSEDED_SHA256,
    )
    assert v["verdict"] == NOT_EVALUABLE
    assert any("SUPERSEDED" in r for r in v["reasons"])


def test_missing_measurements_is_not_evaluable(tmp_path: Path) -> None:
    m = _passing_measurements()
    del m["primary_iqr_bps"]
    v = stage0_verdict(
        contract=_complete_contract(),
        measurements=m,
        token_path=_token_file(tmp_path),
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v["verdict"] == NOT_EVALUABLE
    assert any("primary_iqr_bps" in r for r in v["reasons"])
    v_none = stage0_verdict(
        contract=_complete_contract(),
        measurements=None,
        token_path=_token_file(tmp_path),
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v_none["verdict"] == NOT_EVALUABLE


def test_all_guards_report_together(tmp_path: Path) -> None:
    v = stage0_verdict(
        contract=DatasetContract(),
        measurements=None,
        token_path=None,
        design_sha="deadbeef",
    )
    assert v["verdict"] == NOT_EVALUABLE
    assert len(v["reasons"]) == 4  # design, contract, token, measurements


# ---- oracle brand + threshold math ------------------------------------------


def test_oracle_brand_is_in_the_output_schema_itself() -> None:
    checks = evaluate_thresholds(_passing_measurements())
    oracle = checks["oracle_net_positive_fraction"]
    assert oracle["metric"] == ORACLE_METRIC == "oracle_top_subset"
    assert oracle["brand"] == ORACLE_BRAND == "DIAGNOSTIC_ONLY"
    assert oracle["gates"] is False


def test_evaluate_thresholds_covers_all_required_measurements() -> None:
    checks = evaluate_thresholds(_passing_measurements())
    assert set(checks) == set(REQUIRED_MEASUREMENTS)
    assert all(c["passes"] for c in checks.values())


def test_threshold_failures_detected() -> None:
    m = _passing_measurements()
    m["friction_to_iqr"] = 0.30  # > 25% cap
    m["positive_day_fraction"] = 0.40  # < 55%
    checks = evaluate_thresholds(m)
    assert checks["friction_to_iqr"]["passes"] is False
    assert checks["positive_day_fraction"]["passes"] is False


# ---- authorized path (interlock proven in both directions) ------------------


def test_authorized_verdict_is_gated_by_gating_checks_only(tmp_path: Path) -> None:
    # With the owner token present, a complete contract, the approved design,
    # and full measurements, the seam evaluates. A failed ORACLE (diagnostic
    # only) must NOT gate; a failed gating check must.
    m = _passing_measurements()
    m["oracle_net_positive_fraction"] = 0.10  # diagnostic failure only
    v = stage0_verdict(
        contract=_complete_contract(),
        measurements=m,
        token_path=_token_file(tmp_path),
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v["verdict"] != NOT_EVALUABLE
    assert v["verdict"] == "GO"  # oracle never gates
    assert v["oracle"]["brand"] == "DIAGNOSTIC_ONLY"
    assert v["oracle"]["passes"] is False

    m["cheap_signal_edge_bps"] = 5.0  # gating failure
    v2 = stage0_verdict(
        contract=_complete_contract(),
        measurements=m,
        token_path=_token_file(tmp_path),
        design_sha=APPROVED_DESIGN_SHA256,
    )
    assert v2["verdict"] == "HOLD"
