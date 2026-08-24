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
        "gappers_in": 5, "store_covered": 3, "eligible_panel": 2, "eligible_count": 2,
        "candidate_count": 1,
        "candidates": [{"symbol": "AAA", "rank": 1, "reason": "Gap + RVOL + ATR"}],
        "eligible": [{"symbol": "AAA", "atr_pct": 4.0}, {"symbol": "BBB", "atr_pct": 5.0}],
    }
    base.update(kw)
    return base


def test_evidence_record_wraps_with_pending_outcomes() -> None:
    rec = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    assert rec["schema"] == pe.RECORD_SCHEMA
    assert rec["asof"] == "2024-03-01"
    assert rec["source_date"] == "2024-03-01"
    assert rec["funnel"] == {"gappers_in": 5, "store_covered": 3, "eligible_panel": 2,
                             "eligible_count": 2, "candidate_count": 1}
    assert rec["candidates"][0]["symbol"] == "AAA"
    assert [e["symbol"] for e in rec["eligible"]] == ["AAA", "BBB"]   # baseline field persisted
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


# ---------------------------------------------------------------------------------------------
# §5.5 write-time provenance — the /v2 schema bump.
#
# Governing: docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md §5
# (owner disposition, 2026-08-23, Option B). These tests encode the binding terms, not just the
# happy path — in particular term 9, "no retroactive repair or backfill of provenance", which is
# the term a future well-meaning fix is most likely to violate.
# ---------------------------------------------------------------------------------------------


def test_v2_records_carry_a_complete_conformant_write_time_stamp() -> None:
    from app.research.gapper_stage0.provenance import validate_provenance

    rec = pe.evidence_record(
        _report(source_path="/g/premarket_gappers_2024-03-01.json", source_sha256="d" * 64),
        asof=date(2024, 3, 1),
        created_at="2024-03-01T13:25:00Z",
        run_id="run-1",
    )
    assert rec["schema"] == "scan_001_premarket_gate/v2"
    # Reuses the already-merged conformant implementation rather than re-inventing one, and is
    # validated by that module's own validator — the point of the disposition's term 7.
    validate_provenance(rec, expected_write_class="collection")
    assert rec["provenance"]["source_artifact"] == "/g/premarket_gappers_2024-03-01.json"
    assert rec["provenance"]["source_sha256"] == "d" * 64
    assert rec["provenance"]["created_at"] == "2024-03-01T13:25:00Z"
    assert rec["provenance"]["run_id"] == "run-1"


def test_the_write_class_is_collection_never_reconstruction_or_repair() -> None:
    """A live daily record is *collected*. Stamping it 'reconstruction' (the gapper harness's
    default) would misdescribe forward evidence as rebuilt evidence."""
    rec = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    assert rec["provenance"]["write_class"] == "collection"


def test_a_no_source_day_stamps_honest_sentinels_not_a_plausible_digest() -> None:
    """There is no gappers file on a no-scan day. The stamp must say so in a form nobody can
    mistake for a hash — a 64-hex-looking value here would be a fabricated digest of nothing."""
    from app.services.premarket_gappers import NO_SOURCE_ARTIFACT, NO_SOURCE_SHA256

    rec = pe.evidence_record(
        {"date": None, "stale": True}, asof=date(2024, 3, 1)
    )
    assert rec["provenance"]["source_artifact"] == NO_SOURCE_ARTIFACT
    assert rec["provenance"]["source_sha256"] == NO_SOURCE_SHA256
    assert len(NO_SOURCE_SHA256) != 64


def test_each_write_gets_its_own_run_id() -> None:
    """run_id identifies the *invocation*, not the day — two writes of the same scan day are two
    events, and a shared id would make them indistinguishable in an audit."""
    a = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    b = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    assert a["provenance"]["run_id"] != b["provenance"]["run_id"]


def test_provenance_semantics_is_stamped_and_names_the_v1_ambiguity() -> None:
    """Term 8: a future consumer must not be able to confuse the legacy /v1 provenance *string*
    with the conformant /v2 *structure*."""
    rec = pe.evidence_record(_report(), asof=date(2024, 3, 1))
    semantics = rec["provenance_semantics"]
    assert "v1" in semantics and "retroactiv" in semantics.lower()
    assert isinstance(rec["provenance"], dict)


def test_v1_is_still_a_known_schema_so_legacy_records_are_never_orphaned() -> None:
    assert pe.LEGACY_RECORD_SCHEMA == "scan_001_premarket_gate/v1"
    assert set(pe.KNOWN_RECORD_SCHEMAS) == {pe.LEGACY_RECORD_SCHEMA, pe.RECORD_SCHEMA}


def test_the_backfill_never_adds_provenance_to_a_legacy_v1_record() -> None:
    """TERM 9 — no retroactive repair, permanently.

    25 of the 51 live /v1 records carry no provenance at all. The 16:30 ET outcome back-fill
    rewrites records in place, so it is the one production path that could quietly stamp them.
    It must not: a stamp applied at back-fill time would describe the back-fill, not the write,
    which is precisely the defect that quarantined the repair script."""
    from app.services.premarket_outcomes import backfill_record

    legacy = {
        "schema": "scan_001_premarket_gate/v1",
        "asof": "2026-07-20", "source_date": "2026-07-20", "stale": False,
        "funnel": {"candidate_count": 1, "eligible_count": 2},
        "candidates": [{"symbol": "AAA", "atr_pct": 4.0}],
        "eligible": [{"symbol": "AAA", "atr_pct": 4.0}, {"symbol": "BBB", "atr_pct": 5.0}],
        "outcome_status": "pending", "outcomes": None,
    }
    filled = backfill_record(legacy, {"AAA": {"open": 10.0, "high": 11.0, "low": 9.5,
                                              "close": 10.5}})
    assert "provenance" not in filled
    assert "provenance_semantics" not in filled
    assert filled["schema"] == "scan_001_premarket_gate/v1"   # not upgraded behind our back


def test_the_backfill_leaves_a_legacy_provenance_string_exactly_as_found() -> None:
    """The 26 repaired /v1 records carry provenance as a STRING. The back-fill must neither
    normalise it into the /v2 dict shape nor drop it — term 1, byte-unchanged in substance."""
    from app.services.premarket_outcomes import backfill_record

    legacy = {
        "schema": "scan_001_premarket_gate/v1",
        "asof": "2026-06-22", "source_date": "2026-06-22", "stale": False,
        "provenance": "replayed",
        "funnel": {"candidate_count": 1, "eligible_count": 2},
        "candidates": [{"symbol": "AAA", "atr_pct": 4.0}],
        "eligible": [{"symbol": "AAA", "atr_pct": 4.0}],
        "outcome_status": "pending", "outcomes": None,
    }
    filled = backfill_record(legacy, {"AAA": {"open": 10.0, "high": 11.0, "low": 9.5,
                                              "close": 10.5}})
    assert filled["provenance"] == "replayed"


def test_the_quarantined_repair_tool_has_no_write_path() -> None:
    """The quarantine is structural, not a promise.

    A quarantined tool that can still write is not quarantined — it is inconvenient. This asserts
    the property directly on the file, so a well-meaning restoration of the ``--apply`` branch
    fails CI instead of reaching the evidence corpus a second time."""
    import re
    from pathlib import Path

    tool = (Path(__file__).resolve().parents[4]
            / "tools" / "quarantine" / "repair_premarket_gate_provenance.py")
    assert tool.exists(), "the quarantined artifact is evidence — it must not be deleted"
    body = tool.read_text(encoding="utf-8")
    assert "QUARANTINED" in body.splitlines()[0]
    # No write-mode open, no serializer call, in any form.
    assert not re.search(r"""open\([^)]*["'][wax]b?\+?["']""", body), "a write-mode open survived"
    assert "json.dump" not in body, "a serializer call survived"
