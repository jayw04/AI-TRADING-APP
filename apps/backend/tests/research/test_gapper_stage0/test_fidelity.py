"""Fidelity check: overlap/Jaccard, disagreement records, honest low-N."""

from __future__ import annotations

from app.research.gapper_stage0.fidelity import (
    MIN_COMPARABLE_DAYS,
    STATUS_BLOCKS_0B,
    STATUS_NOT_EVALUABLE,
    STATUS_OK,
    compare_day,
    fidelity_report,
)


def test_compare_day_overlap_and_disagreements() -> None:
    d = compare_day("2026-08-14", ["aaa", "BBB", "CCC"], ["BBB", "CCC", "DDD"])
    assert d["overlap_count"] == 2
    assert d["jaccard"] == 0.5
    assert d["disagreement_rate"] == 0.5
    syms = {rec["symbol"]: rec for rec in d["disagreements"]}
    assert syms["AAA"] == {"symbol": "AAA", "in_reconstruction": True, "in_scanner": False}
    assert syms["DDD"] == {"symbol": "DDD", "in_reconstruction": False, "in_scanner": True}


def test_compare_day_identical_sets() -> None:
    d = compare_day("2026-08-14", ["A", "B"], ["B", "A"])
    assert d["jaccard"] == 1.0
    assert d["disagreements"] == []


def test_low_n_is_not_evaluable_and_fails_closed() -> None:
    days = [compare_day("d", ["A"], ["A"])] * (MIN_COMPARABLE_DAYS - 1)
    r = fidelity_report(days)
    assert r["status"] == STATUS_NOT_EVALUABLE
    assert r["blocks_0b"] is True  # unmeasured fidelity is never a pass
    assert r["mean_disagreement_rate"] is None
    assert "unmeasured" in r["reason"]


def test_agreement_passes() -> None:
    days = [compare_day("d", ["A", "B"], ["A", "B"])] * MIN_COMPARABLE_DAYS
    r = fidelity_report(days)
    assert r["status"] == STATUS_OK
    assert r["blocks_0b"] is False
    assert r["mean_disagreement_rate"] == 0.0


def test_material_disagreement_blocks_0b() -> None:
    days = [compare_day("d", ["A", "B", "C"], ["A", "B", "D"])] * MIN_COMPARABLE_DAYS
    r = fidelity_report(days)  # per-day jaccard 0.5 ⇒ disagreement 0.5 > 0.10
    assert r["status"] == STATUS_BLOCKS_0B
    assert r["blocks_0b"] is True
    assert r["mean_disagreement_rate"] == 0.5
