"""Tests for the GAP-NATIVE-001 daily source-parity accrual (ADR 0041; GAPPER v2.1.1 §3.1).

Read-only file comparison — no network, no DB. The behaviours that matter are:
the overlap denominator is the EXTERNAL list (what the native source would have
missed), a missing source is recorded rather than skipped, and every record
carries the native file's discovery provenance so parity can be stratified by path.
"""

from __future__ import annotations

import json

from app.services import gapper_source_parity as gsp


def _gapper(symbol: str, rank: int = 1, gap: float = 10.0, vol: int = 100_000) -> dict:
    return {"rank": rank, "symbol": symbol, "price": 20.0, "gap_pct": gap,
            "premarket_volume": vol, "catalyst": None, "headlines": []}


def _write(directory, day: str, gappers: list[dict], **extra) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"scanned_at": f"{day}T12:30:00Z", "gappers": gappers, **extra}
    (directory / f"premarket_gappers_{day}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_overlap_is_measured_against_the_external_list() -> None:
    """★ The denominator is the question. A native source that finds 2 names, both
    of which the external also found, is 100% corroborated but has missed 60% of
    the field — which is exactly the path-B small-cap-sparsity risk."""
    native = [_gapper("AAA", 1), _gapper("BBB", 2)]
    external = [_gapper(s, i) for i, s in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE"), 1)]
    out = gsp.compare_day(native, external)
    assert out["native_count"] == 2
    assert out["external_count"] == 5
    assert out["overlap_count"] == 2
    assert out["overlap_pct_of_external"] == 40.0
    assert out["external_only"] == ["CCC", "DDD", "EEE"]
    assert out["native_only"] == []


def test_gap_and_volume_deltas_on_overlapping_symbols_only() -> None:
    native = [_gapper("AAA", 1, gap=10.0, vol=100_000)]
    external = [_gapper("AAA", 1, gap=12.0, vol=180_000), _gapper("ZZZ", 2)]
    out = gsp.compare_day(native, external)
    assert out["mean_gap_pct_delta"] == 2.0
    assert out["mean_pm_volume_delta"] == 80_000


def test_empty_external_yields_no_overlap_pct_rather_than_zero() -> None:
    """No external field is 'not measured', not 'zero overlap' — a zero would
    silently drag the probation-window mean down."""
    out = gsp.compare_day([_gapper("AAA")], [])
    assert out["overlap_pct_of_external"] is None


def test_missing_source_is_recorded_not_skipped(tmp_path) -> None:
    native_dir, external_dir, ev = tmp_path / "n", tmp_path / "e", tmp_path / "ev"
    _write(external_dir, "2026-08-11", [_gapper("AAA")])
    rec = gsp.parity_record(
        "2026-08-11", native_dir=str(native_dir), external_dir=str(external_dir),
        evidence_dir=str(ev),
    )
    assert rec["native_present"] is False
    assert rec["external_present"] is True
    assert rec["both_present"] is False
    assert rec["comparison"] is None
    assert "native file missing" in rec["note"]


def test_record_carries_native_discovery_provenance(tmp_path) -> None:
    """Parity must be stratifiable by discovery path — a path-B day and a path-A
    day are not the same experiment."""
    native_dir, external_dir, ev = tmp_path / "n", tmp_path / "e", tmp_path / "ev"
    _write(native_dir, "2026-08-11", [_gapper("AAA")],
           source="box_native_alpaca_v1", discovery_path="store_sweep",
           discovery_reason="DISCOVERY_STALE")
    _write(external_dir, "2026-08-11", [_gapper("AAA"), _gapper("BBB", 2)])
    rec = gsp.parity_record(
        "2026-08-11", native_dir=str(native_dir), external_dir=str(external_dir),
        evidence_dir=str(ev),
    )
    assert rec["both_present"] is True
    assert rec["native_discovery_path"] == "store_sweep"
    assert rec["native_discovery_reason"] == "DISCOVERY_STALE"
    assert rec["native_source"] == "box_native_alpaca_v1"
    assert rec["comparison"]["overlap_pct_of_external"] == 50.0


def test_gate_candidates_are_attributed_to_each_source(tmp_path) -> None:
    native_dir, external_dir, ev = tmp_path / "n", tmp_path / "e", tmp_path / "ev"
    _write(native_dir, "2026-08-11", [_gapper("AAA")],
           discovery_path="movers", discovery_reason="MOVERS_FRESH")
    _write(external_dir, "2026-08-11", [_gapper("BBB")])
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "premarket_scan_2026-08-11.json").write_text(
        json.dumps({"candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
                    "gappers_source": "box_native_alpaca_v1"}),
        encoding="utf-8",
    )
    rec = gsp.parity_record(
        "2026-08-11", native_dir=str(native_dir), external_dir=str(external_dir),
        evidence_dir=str(ev),
    )
    assert rec["gate"]["candidates_in_native"] == ["AAA"]
    assert rec["gate"]["candidates_in_external"] == ["BBB"]
    assert rec["gate"]["gappers_source"] == "box_native_alpaca_v1"


def test_persist_is_idempotent_per_day(tmp_path) -> None:
    """A parity record is a derived measurement over two source files, so a re-run
    overwrites — unlike a gate evidence record, which is immutable once written."""
    rec = {"schema": gsp.RECORD_SCHEMA, "asof": "2026-08-11", "comparison": None}
    p1 = gsp.persist_parity_record(rec, str(tmp_path))
    p2 = gsp.persist_parity_record({**rec, "comparison": {"native_count": 1}}, str(tmp_path))
    assert p1 == p2
    with open(p1, encoding="utf-8") as fh:
        assert json.load(fh)["comparison"] == {"native_count": 1}


def test_summarize_reports_the_probation_window_view() -> None:
    records = [
        {"native_present": True, "external_present": True,
         "native_discovery_reason": "DISCOVERY_STALE",
         "comparison": {"overlap_pct_of_external": 40.0}},
        {"native_present": True, "external_present": True,
         "native_discovery_reason": "DISCOVERY_STALE",
         "comparison": {"overlap_pct_of_external": 20.0}},
        {"native_present": False, "external_present": True,
         "native_discovery_reason": None, "comparison": None},
    ]
    out = gsp.summarize(records)
    assert out["days_seen"] == 3
    assert out["days_compared"] == 2
    assert out["days_native_missing"] == 1
    assert out["mean_overlap_pct_of_external"] == 30.0
    assert out["min_overlap_pct_of_external"] == 20.0
    assert out["discovery_reason_counts"] == {"DISCOVERY_STALE": 2, "NO_NATIVE_FILE": 1}
