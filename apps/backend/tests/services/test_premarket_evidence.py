"""SCAN-001 premarket-data gate — increment (C) forward-evidence accumulator tests.

Covers wrapping a scan report into a durable, back-fillable record (outcomes pending), the
dated one-per-day file write (idempotent overwrite), and the record_premarket_scan pipeline,
including the empty/stale path so the record exists even on a no-gapper day.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.services import premarket_evidence as pe


def _report(**kw: Any) -> dict[str, Any]:
    base = {
        "date": "2024-03-01", "scanned_at": "2024-03-01T13:00:00Z", "stale": False,
        "gappers_in": 5, "store_covered": 3, "eligible_panel": 2, "candidate_count": 1,
        "candidates": [{"symbol": "AAA", "rank": 1, "reason": "Gap + RVOL + ATR"}],
    }
    base.update(kw)
    return base


def test_evidence_record_wraps_with_pending_outcomes() -> None:
    rec = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    assert rec["schema"] == pe.RECORD_SCHEMA
    assert rec["asof"] == "2024-03-01"
    assert rec["source_date"] == "2024-03-01"
    assert rec["funnel"] == {"gappers_in": 5, "store_covered": 3,
                             "eligible_panel": 2, "candidate_count": 1}
    assert rec["candidates"][0]["symbol"] == "AAA"
    assert rec["outcome_status"] == "pending"
    assert rec["outcomes"] is None


def test_evidence_record_exists_even_when_empty_stale() -> None:
    # a no-gapper day still produces an identifiable record (asof is the identity)
    rec = pe.evidence_record(
        {"date": None, "stale": True, "gappers_in": 0, "candidate_count": 0, "candidates": []},
        asof=date(2024, 3, 2),
    )
    assert rec["asof"] == "2024-03-02"
    assert rec["source_date"] is None
    assert rec["stale"] is True
    assert rec["funnel"]["gappers_in"] == 0


def test_persist_record_writes_dated_file(tmp_path: Path) -> None:
    rec = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    path = pe.persist_record(rec, str(tmp_path))
    assert path.endswith("premarket_scan_2024-03-01.json")
    written = json.loads(Path(path).read_text(encoding="utf-8"))
    assert written["asof"] == "2024-03-01"
    assert written["candidates"][0]["symbol"] == "AAA"


def test_persist_record_is_idempotent_per_day(tmp_path: Path) -> None:
    pe.persist_record(pe.evidence_record(_report(candidate_count=1), asof=date(2024, 3, 1)),
                      str(tmp_path))
    pe.persist_record(pe.evidence_record(_report(candidate_count=9), asof=date(2024, 3, 1)),
                      str(tmp_path))
    files = list(tmp_path.glob("premarket_scan_*.json"))
    assert len(files) == 1                                   # same day → one record, overwritten
    assert json.loads(files[0].read_text())["funnel"]["candidate_count"] == 9


def test_record_premarket_scan_runs_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pe, "run_premarket_scan", lambda store, *, asof, top_n: _report())
    rec = pe.record_premarket_scan(object(), asof=date(2024, 3, 1), directory=str(tmp_path))
    assert rec["outcome_status"] == "pending"
    assert Path(rec["_path"]).exists()
    assert rec["_path"].endswith("premarket_scan_2024-03-01.json")
