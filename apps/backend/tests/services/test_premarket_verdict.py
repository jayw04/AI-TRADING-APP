"""SCAN-001 premarket-data gate — increment (D) verdict tests.

Covers the frozen forward classification (INSUFFICIENT / TRANSFERS / DOES-NOT-TRANSFER) over
back-filled records, and the fail-soft record loader.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services import premarket_verdict as pv


def _filled(edge_e: float) -> dict[str, object]:
    return {"outcome_status": "filled", "outcomes": {"edge_E": edge_e}}


def test_insufficient_below_min_days() -> None:
    out = pv.gate_verdict([_filled(0.5)] * 3, min_days=40)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["filled_days"] == 3 and out["min_days"] == 40


def test_pending_records_do_not_count() -> None:
    records = [{"outcome_status": "pending", "outcomes": None}] * 50
    assert pv.gate_verdict(records, min_days=40)["verdict"] == "INSUFFICIENT"


def test_transfers_when_edge_ci_separated_positive() -> None:
    # a clearly positive, low-variance edge series → CI separated > 0
    out = pv.gate_verdict([_filled(0.5 + (i % 3) * 0.01) for i in range(60)],
                          min_days=40, bootstrap=500)
    assert out["verdict"] == "TRANSFERS"
    assert out["edge_E"]["ci_low"] > 0


def test_does_not_transfer_when_edge_around_zero() -> None:
    # edges centered on ~0 (alternating sign) → CI includes 0
    out = pv.gate_verdict([_filled(0.2 if i % 2 else -0.2) for i in range(60)],
                          min_days=40, bootstrap=500)
    assert out["verdict"] == "DOES-NOT-TRANSFER"
    assert out["edge_E"]["ci_low"] <= 0


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
