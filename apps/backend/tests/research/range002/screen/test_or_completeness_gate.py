# ruff: noqa: F811  (pytest fixtures imported from the rehearsal module are re-requested by name)
"""The prospective OR-completeness gate: both measures reported, defect status, no advancement."""

from __future__ import annotations

from typing import Any

import pytest

from tests.research.range002.screen.test_descriptive_run_rehearsal import (  # noqa: F401
    minutes_root,
    rds,
    world,
)


def test_gate_not_met_labels_run_with_data_quality_defect(world: dict[str, Any]) -> None:
    out = rds.run(**world["kwargs"], or_completeness_threshold=0.999)
    rep = out.report
    assert out.status == rds.STATUS_OR_DEFECT == "DESCRIPTIVE_COMPLETE_WITH_DATA_QUALITY_DEFECT"
    g = rep["or_completeness_gate"]
    assert g["evaluated"] and g["meets_threshold"] is False
    assert g["numerator"] == rep["or_completeness"]["complete_count"]
    assert g["denominator"] == rep["coverage"]["denominator"]
    # returned coverage is a separate, still-reported measure and it passed
    assert rep["coverage"]["meets_threshold"] is True
    assert "no candidate may be advanced" in rep["defect_note"]
    assert out.report_json.exists() and out.report_md.exists()


def test_gate_met_and_gate_not_requested(world: dict[str, Any], tmp_path: Any) -> None:
    ok = rds.run(**world["kwargs"], or_completeness_threshold=0.5)
    assert ok.status == rds.STATUS_COMPLETE
    assert ok.report["or_completeness_gate"]["meets_threshold"] is True


def test_gate_not_requested_is_recorded_as_not_evaluated(world: dict[str, Any]) -> None:
    out = rds.run(**world["kwargs"])
    assert out.status == rds.STATUS_COMPLETE
    assert out.report["or_completeness_gate"]["evaluated"] is False


def test_invalid_threshold_refused(world: dict[str, Any]) -> None:
    with pytest.raises(rds.DescriptiveRunRefusal):
        rds.run(**world["kwargs"], or_completeness_threshold=1.5)
