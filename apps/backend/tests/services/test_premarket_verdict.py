"""SCAN-001 premarket-data gate — increment (D) verdict tests.

Covers the frozen forward classification (INSUFFICIENT / TRANSFERS / DOES-NOT-TRANSFER) over
back-filled records, the two admission rules that stand in front of it (record integrity and
selection-contrast identifiability), and the fail-soft record loader.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services import premarket_verdict as pv


def _day(i: int) -> str:
    """A distinct ISO date per index (2024-03-01 + i days, within one month)."""
    return f"2024-03-{i + 1:02d}"


def _filled(
    edge_e: float,
    i: int = 0,
    *,
    candidate_count: int = 2,
    eligible_count: int = 5,
    **overrides: object,
) -> dict[str, object]:
    """An admissible, contrast-bearing record: same-day provenance and candidates ⊊ eligible."""
    record: dict[str, object] = {
        "asof": _day(i),
        "source_date": _day(i),
        "stale": False,
        "funnel": {"candidate_count": candidate_count, "eligible_count": eligible_count},
        "outcome_status": "filled",
        "outcomes": {"edge_E": edge_e},
    }
    record.update(overrides)
    return record


def _series(edges: list[float]) -> list[dict[str, object]]:
    return [_filled(e, i) for i, e in enumerate(edges)]


# --- the frozen classification ------------------------------------------------------------


def test_insufficient_below_min_days() -> None:
    out = pv.gate_verdict(_series([0.5] * 3), min_days=40)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["filled_days"] == 3 and out["min_days"] == 40
    assert out["contrast_days"] == 3


def test_pending_records_do_not_count() -> None:
    records = [_filled(0.5, i, outcome_status="pending", outcomes=None) for i in range(28)]
    out = pv.gate_verdict(records, min_days=40)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["valid_days"] == 0
    assert out["exclusions"] == {pv.EXCLUDE_NOT_FILLED: 28}


def test_transfers_when_edge_ci_separated_positive() -> None:
    # a clearly positive, low-variance edge series → CI separated > 0
    out = pv.gate_verdict(_series([0.5 + (i % 3) * 0.01 for i in range(60)]),
                          min_days=40, bootstrap=500)
    assert out["verdict"] == "TRANSFERS"
    assert out["edge_E"]["ci_low"] > 0


def test_does_not_transfer_when_edge_around_zero() -> None:
    # edges centered on ~0 (alternating sign) → CI includes 0
    out = pv.gate_verdict(_series([0.2 if i % 2 else -0.2 for i in range(60)]),
                          min_days=40, bootstrap=500)
    assert out["verdict"] == "DOES-NOT-TRANSFER"
    assert out["edge_E"]["ci_low"] <= 0


# --- (1) record admission: evidence integrity ---------------------------------------------


def test_stale_record_is_excluded() -> None:
    """The 2026-07-21 shape: a stale snapshot republished under the next day's asof."""
    records = _series([0.5] * 3)
    records.append(_filled(0.5, 3, asof=_day(3), source_date=_day(2), stale=True))
    out = pv.gate_verdict(records, min_days=40)
    assert out["contrast_days"] == 3          # not 4 — the stale day contributes nothing
    assert out["exclusions"] == {pv.EXCLUDE_STALE: 1}


def test_source_date_mismatch_is_excluded_even_when_stale_flag_is_false() -> None:
    """``stale`` is a writer-set flag; ``source_date != asof`` is the structural proof."""
    records = _series([0.5] * 3)
    records.append(_filled(0.5, 3, source_date=_day(2), stale=False))
    out = pv.gate_verdict(records, min_days=40)
    assert out["contrast_days"] == 3
    assert out["exclusions"] == {pv.EXCLUDE_SOURCE_DATE_MISMATCH: 1}


def test_duplicate_source_date_counted_once() -> None:
    """One market snapshot cannot contribute two forward days under two asof dates."""
    duplicate = _filled(0.5, 0)
    out = pv.gate_verdict([_filled(0.5, 0), duplicate], min_days=40)
    assert out["contrast_days"] == 1
    assert out["exclusions"] == {pv.EXCLUDE_DUPLICATE_SOURCE_DATE: 1}


def test_missing_provenance_fields_are_excluded() -> None:
    bare = {"outcome_status": "filled", "outcomes": {"edge_E": 0.5}}
    out = pv.gate_verdict([bare], min_days=40)
    assert out["valid_days"] == 0
    assert out["exclusions"] == {pv.EXCLUDE_MISSING_PROVENANCE: 1}


def test_missing_funnel_counts_are_excluded() -> None:
    out = pv.gate_verdict([_filled(0.5, 0, funnel={})], min_days=40)
    assert out["valid_days"] == 0
    assert out["exclusions"] == {pv.EXCLUDE_MISSING_FUNNEL_COUNTS: 1}


# --- (2) selection-contrast admission: identifiability -------------------------------------


def test_no_selection_contrast_is_invalid_evidence_not_a_verdict() -> None:
    """The live 2026-06-08..07-24 shape: candidate_count == eligible_count on every day.

    edge_E is 0.0 by construction, so a bootstrap over the series can never separate from 0 and
    would otherwise emit a confident DOES-NOT-TRANSFER that tested nothing.
    """
    records = [_filled(0.0, i, candidate_count=3, eligible_count=3) for i in range(60)]
    out = pv.gate_verdict(records, min_days=40, bootstrap=500)
    assert out["verdict"] == "INVALID-EVIDENCE"
    assert out["reason"] == "NO_SELECTION_CONTRAST"
    assert out["valid_days"] == 60 and out["contrast_days"] == 0
    assert out["zero_contrast_days"] == 60
    assert out["mean_selection_ratio"] == 1.0
    assert "edge_E" not in out                 # no statistic is published


def test_zero_contrast_days_are_not_treated_as_zero_edge_days() -> None:
    """Structural zeros must not dilute a real edge series toward 0."""
    real = _series([0.5] * 45)
    structural = [_filled(0.0, 45 + i, candidate_count=3, eligible_count=3) for i in range(60)]
    out = pv.gate_verdict(real + structural, min_days=40, bootstrap=500)
    assert out["verdict"] == "TRANSFERS"        # not dragged to DOES-NOT-TRANSFER
    assert out["contrast_days"] == 45 and out["zero_contrast_days"] == 60


def test_zero_contrast_days_do_not_count_toward_min_days() -> None:
    mixed = _series([0.5] * 5) + [
        _filled(0.0, 5 + i, candidate_count=4, eligible_count=4) for i in range(50)
    ]
    out = pv.gate_verdict(mixed, min_days=40)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["contrast_days"] == 5            # 55 admitted days, only 5 measure anything


def test_empty_records_are_insufficient_not_invalid() -> None:
    out = pv.gate_verdict([], min_days=40)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["valid_days"] == 0


# --- governed contrast-quality floors (ungoverned by default) ------------------------------


def test_governed_floors_are_not_enforced_when_unset() -> None:
    out = pv.gate_verdict(_series([0.5 + (i % 3) * 0.01 for i in range(60)]),
                          min_days=40, bootstrap=500)
    assert out["verdict"] == "TRANSFERS"
    assert out["min_contrast_days"] is None
    assert out["max_mean_selection_ratio"] is None


def test_governed_min_contrast_days_withholds_verdict_when_set() -> None:
    out = pv.gate_verdict(_series([0.5 + (i % 3) * 0.01 for i in range(60)]),
                          min_days=40, bootstrap=500, min_contrast_days=100)
    assert out["verdict"] == "INSUFFICIENT"
    assert "governed minimum 100" in out["note"]


def test_governed_max_selection_ratio_withholds_verdict_when_set() -> None:
    # candidates are 4 of 5 eligible → ratio 0.8, above a governed 0.5 ceiling
    records = [_filled(0.5 + (i % 3) * 0.01, i, candidate_count=4, eligible_count=5)
               for i in range(60)]
    out = pv.gate_verdict(records, min_days=40, bootstrap=500, max_mean_selection_ratio=0.5)
    assert out["verdict"] == "INSUFFICIENT"
    assert "mean_selection_ratio 0.8" in out["note"]


# --- the loader ----------------------------------------------------------------------------


def test_load_records_reads_and_sorts(tmp_path: Path) -> None:
    for d, edge in (("2024-03-02", 0.3), ("2024-03-01", 0.5)):
        (tmp_path / f"premarket_scan_{d}.json").write_text(
            json.dumps({"asof": d, "outcome_status": "filled", "outcomes": {"edge_E": edge}}),
            encoding="utf-8",
        )
    records = pv.load_records(str(tmp_path))
    assert [r["asof"] for r in records] == ["2024-03-01", "2024-03-02"]   # sorted by filename/date


def test_load_records_missing_dir_is_empty() -> None:
    assert pv.load_records("/no/such/dir/scan") == []
