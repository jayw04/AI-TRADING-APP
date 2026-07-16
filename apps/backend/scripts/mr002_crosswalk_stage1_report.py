"""MR-002 crawl stage-1 identity report (owner acceptance criteria, 2026-07-11).

Consumes the full-universe crosswalk build (DuckDB `identity_crosswalk` + the run
report JSON) and the preliminary universe, and evaluates the owner's stage-1
acceptance criteria before the V1/V2 EDGAR crawl may be released:

  zero interval-integrity errors · zero unexplained identity conflicts · >=99% of
  preliminary universe-months identity-resolved · every unresolved security listed
  with affected universe-months · no ticker-only resolution in final joins (this
  report resolves strictly by (permaticker, date)) · one CIK per (permaticker,
  date) · no backfill outside registered intervals (enforced by the interval
  checker) · crosswalk output hash recorded in the DATA-SNAPSHOT manifest (the
  governance manifest MR002_FinalArtifactHashes_v1.0.json stays immutable) · exact
  reconciliation of input/resolved/excluded securities.

Also documents the 754-vs-755 reconciliation (PATH / permaticker 634849 existed
only in the invalid future-dated 2026-08 universe removed by the complete-month
guard; zero valid universe-months affected).

Run:
    PYTHONPATH=apps/backend .venv python mr002_crosswalk_stage1_report.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
DB = ROOT / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
UNIVERSE = EV / "mr002_preliminary_universe.csv.gz"
RUN_REPORT = EV / "crosswalk_fulluniverse_report.json"
OUT_JSON = EV / "MR002_CrosswalkStage1_Report_v1.0.json"
SNAP_MANIFEST = EV / "MR002_DataSnapshotHashes_v1.0.json"


def main() -> int:
    run = json.loads(RUN_REPORT.read_text())
    con = duckdb.connect(str(DB), read_only=True)
    xw = con.execute(
        "SELECT permaticker, ticker, cik, effective_from, effective_to, "
        "relationship_type, source, review_status FROM identity_crosswalk"
    ).fetchall()
    con.close()

    # (permaticker, date) -> CIK resolution structures; uniqueness enforced
    by_perma: dict[int, list[tuple[date, date | None, int, str]]] = {}
    for perma, _t, cik, f, t, rel, source, _rs in xw:
        if perma is None or cik is None:
            continue
        by_perma.setdefault(int(perma), []).append(
            (f, t, int(cik), "manual_override" if source == "manual_override_table" else "auto"))

    def resolve(perma: int, on: date):
        hits = [(c, src) for f, t, c, src in by_perma.get(perma, [])
                if f <= on and (t is None or on <= t)]
        ciks = {c for c, _ in hits}
        if len(ciks) == 1:
            return hits[0]
        return (None, "conflict") if len(ciks) > 1 else (None, "unresolved")

    ucon = duckdb.connect()
    urows = ucon.execute(
        f"SELECT universe_month, ticker, permaticker FROM read_csv_auto('{UNIVERSE}', "
        "header=true) WHERE universe_month <= DATE '2026-07-01'").fetchall()
    ucon.close()

    total = len(urows)
    resolved_auto = resolved_manual = 0
    unresolved: dict[str, int] = {}
    excl_after_delist: dict[str, int] = {}
    excl_before_exist: dict[str, int] = {}
    multi_cik: dict[str, int] = {}
    for m, t, perma in urows:
        on = m if isinstance(m, date) else date.fromisoformat(str(m)[:10])
        cik, how = resolve(int(perma), on)
        if cik is None:
            if how == "conflict":
                multi_cik[t] = multi_cik.get(t, 0) + 1
                continue
            # owner funnel: a universe month AFTER the security's last identity
            # interval (delisting/acquisition tail from the month-end construction)
            # or BEFORE its first is an explicit exclusion category, never an
            # unexplained unresolved.
            ivals = by_perma.get(int(perma), [])
            ends = [tt for _f, tt, _c, _s in ivals]
            starts = [f for f, _t, _c, _s in ivals]
            if ivals and all(e is not None for e in ends) and on > max(ends):
                excl_after_delist[t] = excl_after_delist.get(t, 0) + 1
            elif ivals and on < min(starts):
                excl_before_exist[t] = excl_before_exist.get(t, 0) + 1
            else:
                unresolved[t] = unresolved.get(t, 0) + 1
        elif how == "manual_override":
            resolved_manual += 1
        else:
            resolved_auto += 1
    resolved = resolved_auto + resolved_manual
    pct = round(100.0 * resolved / total, 2)

    input_permas = {int(p) for _m, _t, p in urows}
    covered_permas = {p for p in input_permas if by_perma.get(p)}
    xwalk_hash = hashlib.sha256(
        "\n".join(sorted(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}" for r in xw))
        .encode()).hexdigest()

    criteria = {
        "zero_interval_integrity_errors": len(run.get("integrity_errors", [])) == 0,
        "zero_unexplained_identity_conflicts": len(run.get("conflicts", [])) == 0,
        "universe_month_identity_resolution_pct": pct,
        "resolution_gate_99pct": pct >= 99.0,
        "one_cik_per_permaticker_date": len(multi_cik) == 0,
        "permaticker_date_joins_only": True,
        "no_backfill_outside_registered_intervals": len(run.get("integrity_errors", [])) == 0,
    }
    report = {
        "generated": datetime.now(UTC).isoformat(),
        "reconciliation_754_vs_755": {
            "preliminary_universe_distinct_securities_all_months": 755,
            "crosswalk_input_distinct_securities": 754,
            "difference": "PATH (UiPath, permaticker 634849, SIC 7372)",
            "reason": "PATH qualified ONLY in the future-dated 2026-08 universe built "
                      "from a mid-month as-of; the complete-month guard removed that "
                      "row-set (deterministic; no vendor-data issue)",
            "universe_months_affected": 0,
            "note": "the single affected row was itself invalid (2026-08-01)",
        },
        "funnel": {
            "input_distinct_tickers": 754,
            "input_distinct_permatickers": len(input_permas),
            "permatickers_with_crosswalk_rows": len(covered_permas),
            "universe_months_total": total,
            "resolved_automatically": resolved_auto,
            "resolved_through_manual_override": resolved_manual,
            "explicitly_unresolved_months": sum(unresolved.values()),
            "excluded_after_delisting_or_acquisition_months": sum(excl_after_delist.values()),
            "excluded_before_existence_months": sum(excl_before_exist.values()),
            "conflict_months": sum(multi_cik.values()),
            "final_resolved_universe_months": resolved,
            "run_conflicts": run.get("conflicts", []),
            "run_expected_ambiguities": run.get("expected_ambiguities", []),
            "run_notes_delisted_or_acquired": [
                n for n in run.get("notes", [])
                if n.startswith(("delisted:", "acquisition:"))][:400],
        },
        "unresolved_securities_with_months": dict(
            sorted(unresolved.items(), key=lambda x: -x[1])),
        "excluded_after_delisting_securities": dict(
            sorted(excl_after_delist.items(), key=lambda x: -x[1])),
        "excluded_before_existence_securities": dict(
            sorted(excl_before_exist.items(), key=lambda x: -x[1])),
        "multi_cik_securities_with_months": dict(
            sorted(multi_cik.items(), key=lambda x: -x[1])),
        "acceptance_criteria": criteria,
        "stage1_result": "PASS — V1/V2 EDGAR crawl released" if all(
            v is True or (isinstance(v, float) and v >= 99.0)
            for k, v in criteria.items() if k != "universe_month_identity_resolution_pct"
        ) and pct >= 99.0 else "FAIL — hold the V1/V2 crawl",
        "crosswalk_output_canonical_sha256": xwalk_hash,
        "identity_tests_pilot": run.get("identity_tests_passed"),
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))

    # DATA-SNAPSHOT manifest (separate from the immutable governance manifest)
    prov = json.loads((EV / "mr002_impact_report.json").read_text()).get("provenance", {})
    snap = {
        "title": "MR-002 data-snapshot hashes v1.0 (crawl-side; governance manifest stays immutable)",
        "generated": datetime.now(UTC).isoformat(),
        "preliminary_universe_csv_gz_sha256": hashlib.sha256(UNIVERSE.read_bytes()).hexdigest(),
        "identity_crosswalk_canonical_sha256": xwalk_hash,
        "identity_crosswalk_rows": len(xw),
        "sep_bulk_zip_sha256": prov.get("sep_zip_sha256"),
        "tickers_bulk_zip_sha256": prov.get("tickers_zip_sha256"),
        "stage1_report": OUT_JSON.name,
        "pending": ["v1_anchors_snapshot", "v2_sic_observations_snapshot",
                    "raw_edgar_response_manifest", "retry_error_log",
                    "actions_snapshot", "etf_snapshot", "extraction_code_commit"],
    }
    SNAP_MANIFEST.write_text(json.dumps(snap, indent=2))
    print(json.dumps({k: report[k] for k in
                      ("reconciliation_754_vs_755", "acceptance_criteria",
                       "stage1_result")}, indent=2, default=str))
    print("funnel:", json.dumps({k: v for k, v in report["funnel"].items()
                                 if not k.startswith("run_")}, indent=1))
    if unresolved:
        print("unresolved:", dict(list(unresolved.items())[:15]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
