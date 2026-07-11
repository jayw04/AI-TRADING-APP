"""MR-002 historical identity crosswalk runner (pre-reg v0.5 §2).

Builds the effective-dated permaticker/ticker/CIK crosswalk for a ticker set under
the frozen source precedence, merges the reviewed manual-override table, persists to
DuckDB, exports the review CSV, and executes the MANDATORY identity tests (v0.5 §2):
TWTR (delisted) · FB (retired ticker) · Google->Alphabet (predecessor/successor CIK
chain) · GOOG/GOOGL (share class + time-ambiguous GOOG symbol) · GEHC (spin-off
boundary). The crosswalk hash stays PROVISIONAL until owner countersign of the
override rows.

Run:
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/mr002_build_crosswalk.py \
        --tickers TWTR,META,GOOG,GOOGL,GEHC,KVUE,AAPL,AMT,NFLX,VZ

Data provenance only — no MR-002 signals or backtests (owner directive 2026-07-11).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import truststore

truststore.inject_into_ssl()

import duckdb  # noqa: E402
import httpx  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    _root = Path(__file__).resolve().parents[3]
    for env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
except Exception:
    pass

os.environ.setdefault("SEC_EDGAR_USER_AGENT", "GlobalComplyAI LLC jay.w0416@gmail.com")

from app.altdata.mr002.crosswalk import (  # noqa: E402
    CrosswalkBuild,
    CrosswalkRow,
    build_security,
    cik_from_secfilings,
    integrity_check,
    share_class_pass,
)
from app.altdata.sec.client import EdgarClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
EVIDENCE_DIR = ROOT / "Docs" / "implementation" / "evidence" / "mr_002"
OVERRIDES_CSV = EVIDENCE_DIR / "crosswalk_manual_overrides_v0.2.csv"
NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"

DDL = """
CREATE TABLE IF NOT EXISTS identity_crosswalk (
    permaticker BIGINT, ticker VARCHAR, cik BIGINT,
    effective_from DATE, effective_to DATE,
    relationship_type VARCHAR, source VARCHAR, source_record_id VARCHAR,
    confidence VARCHAR, mapping_rationale VARCHAR, review_status VARCHAR,
    built_at TIMESTAMPTZ
);
"""


def ndl_rows(client: httpx.Client, dataset: str, **params) -> list[dict]:
    params["api_key"] = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")
    out, cursor = [], None
    while True:
        q = dict(params)
        if cursor:
            q["qopts.cursor_id"] = cursor
        r = client.get(f"{NDL_BASE}/{dataset}.json", params=q, timeout=60)
        r.raise_for_status()
        dt = r.json()["datatable"]
        cols = [c["name"] for c in dt["columns"]]
        out.extend(dict(zip(cols, row, strict=False)) for row in dt["data"])
        cursor = r.json().get("meta", {}).get("next_cursor_id")
        if not cursor:
            return out


def load_overrides(path: Path) -> dict[int, list[CrosswalkRow]]:
    by_perma: dict[int, list[CrosswalkRow]] = {}
    if not path.exists():
        return by_perma
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row = CrosswalkRow(
                permaticker=int(r["permaticker"]), ticker=r["ticker"].upper(),
                cik=int(r["cik"]) if r["cik"] else None,
                effective_from=date.fromisoformat(r["effective_from"]),
                effective_to=date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
                relationship_type=r["relationship_type"], source=r["source"],
                source_record_id=r["source_record_id"], confidence=r["confidence"],
                mapping_rationale=r["mapping_rationale"],
                review_status="pending_owner_review",
            )
            by_perma.setdefault(row.permaticker, []).append(row)
    return by_perma


def run_identity_tests(build: CrosswalkBuild) -> dict[str, dict]:
    """The v0.5 §2 mandatory identity tests, asserted programmatically."""
    t: dict[str, dict] = {}

    r = build.resolve("TWTR", date(2020, 1, 1))
    t["twtr_delisted_resolves_in_life"] = {
        "pass": bool(r and r.permaticker == 187959 and r.cik == 1418091),
        "got": asdict(r) if r else None}
    t["twtr_excluded_after_delisting"] = {
        "pass": build.resolve("TWTR", date(2023, 6, 1)) is None}

    r = build.resolve("FB", date(2015, 6, 1))
    t["fb_retired_ticker_resolves_historically"] = {
        "pass": bool(r and r.permaticker == 194817 and r.cik == 1326801),
        "got": asdict(r) if r else None}
    t["fb_not_resolvable_after_rename"] = {
        "pass": build.resolve("FB", date(2023, 1, 1)) is None}
    r = build.resolve("META", date(2023, 1, 1))
    t["meta_resolves_after_rename_same_permaticker"] = {
        "pass": bool(r and r.permaticker == 194817)}

    t["google_predecessor_cik_pre_reorg"] = {
        "pass": build.cik_for(195146, date(2010, 6, 1)) == 1288776}
    t["alphabet_successor_cik_post_reorg"] = {
        "pass": build.cik_for(195146, date(2020, 6, 1)) == 1652044}
    t["goog_classC_predecessor_window"] = {
        "pass": build.cik_for(119496, date(2015, 1, 15)) == 1288776}

    early = build.resolve("GOOG", date(2010, 1, 1))
    late = build.resolve("GOOG", date(2020, 1, 1))
    t["goog_symbol_time_ambiguity_resolved"] = {
        "pass": bool(early and late and early.permaticker == 195146
                     and late.permaticker == 119496),
        "got": {"2010": early.permaticker if early else None,
                "2020": late.permaticker if late else None}}
    t["share_class_distinct_permatickers_same_cik"] = {
        "pass": build.cik_for(195146, date(2020, 1, 1))
        == build.cik_for(119496, date(2020, 1, 1)) == 1652044}

    r = build.resolve("GEHC", date(2023, 6, 1))
    t["gehc_spinoff_resolves_post_spin"] = {
        "pass": bool(r and r.permaticker == 639312 and r.cik == 1932393)}
    t["gehc_excluded_pre_spin"] = {
        "pass": build.resolve("GEHC", date(2022, 6, 1)) is None}
    t["gehc_spinoff_parent_evidence"] = {
        "pass": any(n.startswith("spin_off:GEHC") and "parent=GE" in n for n in build.notes)}

    r = build.resolve("AAPL", date(2018, 1, 1))
    t["control_aapl_direct"] = {"pass": bool(r and r.cik == 320193)}

    # acquisition: no successor history backfilled into predecessor dates — TWTR's
    # own CIK holds through its life; nothing resolves after delisting (no acquirer
    # inheritance), and nothing resolves before the security existed.
    r = build.resolve("TWTR", date(2022, 10, 1))
    t["acquisition_no_successor_backfill"] = {
        "pass": bool(r and r.cik == 1418091)
        and build.resolve("TWTR", date(2023, 6, 1)) is None}
    t["unresolved_identity_explicit_exclusion"] = {
        "pass": build.resolve("TWTR", date(2010, 1, 1)) is None
        and build.resolve("ZZZZNOTREAL", date(2020, 1, 1)) is None}

    # owner-required boundary tests (review 2026-07-11): the overrides must be
    # historically correct at the exact transition dates, not merely internally
    # consistent with the resolver.
    r = build.resolve("GOOG", date(2014, 4, 2))
    t["boundary_2014_04_02_goog_still_classA"] = {
        "pass": bool(r and r.permaticker == 195146 and r.cik == 1288776) or r is None,
        "note": "None allowed: GOOG is EXPECTEDLY ambiguous 2014-03-27..04-02 "
                "(Class A regular-way + Class C when-issued); ambiguity must be recorded",
        "got": (r.permaticker if r else "unresolved")}
    t["boundary_when_issued_ambiguity_recorded"] = {
        "pass": any("GOOG@2014-04-02" in a for a in build.ambiguities)
        or bool(r and r.permaticker == 195146)}
    r = build.resolve("GOOG", date(2014, 4, 3))
    t["boundary_2014_04_03_goog_is_classC"] = {
        "pass": bool(r and r.permaticker == 119496 and r.cik == 1288776)}
    r = build.resolve("GOOGL", date(2014, 4, 3))
    t["boundary_2014_04_03_googl_is_classA"] = {
        "pass": bool(r and r.permaticker == 195146 and r.cik == 1288776)}
    t["boundary_2015_10_01_predecessor"] = {
        "pass": build.cik_for(195146, date(2015, 10, 1)) == 1288776
        and build.cik_for(119496, date(2015, 10, 1)) == 1288776}
    t["boundary_2015_10_02_successor"] = {
        "pass": build.cik_for(195146, date(2015, 10, 2)) == 1652044
        and build.cik_for(119496, date(2015, 10, 2)) == 1652044}
    t["when_issued_window_cik_via_permaticker"] = {
        "pass": build.cik_for(119496, date(2014, 3, 28)) == 1288776}
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--report-out", default=str(EVIDENCE_DIR / "crosswalk_identity_tests.json"))
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    built_at = datetime.now(UTC)

    overrides = load_overrides(OVERRIDES_CSV)
    build = CrosswalkBuild()

    with httpx.Client(follow_redirects=True) as ndl, EdgarClient() as edgar:
        for t in tickers:
            trows = ndl_rows(ndl, "TICKERS", table="SEP", ticker=t)
            if not trows:
                build.conflicts.append(f"no_tickers_row:{t}")
                continue
            trow = trows[0]
            actions = ndl_rows(ndl, "ACTIONS", ticker=t)
            cik = cik_from_secfilings(trow.get("secfilings"))
            edgar_tickers = None
            delisted = str(trow.get("isdelisted", "N")).upper() in ("Y", "TRUE", "1")
            if cik and not delisted:
                try:
                    subs = edgar.get_json(
                        f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
                    edgar_tickers = subs.get("tickers") or []
                except Exception:  # noqa: BLE001 — cross-check absence is logged, not fatal
                    build.conflicts.append(f"edgar_submissions_unavailable:{t}:cik{cik}")
            build_security(build, trow, actions,
                           edgar_tickers_now=edgar_tickers,
                           overrides=overrides.get(int(trow["permaticker"])))
            print(f"  {t}: perma={trow['permaticker']} cik={cik} "
                  f"rows_so_far={len(build.rows)}")

    share_class_pass(build)
    integrity_errors = integrity_check(build)
    tests = run_identity_tests(build)

    con = duckdb.connect(str(DB))
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            con.execute(stmt)
    con.execute("DELETE FROM identity_crosswalk")
    for r in build.rows:
        con.execute("INSERT INTO identity_crosswalk VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [r.permaticker, r.ticker, r.cik, r.effective_from, r.effective_to,
                     r.relationship_type, r.source, r.source_record_id, r.confidence,
                     r.mapping_rationale, r.review_status, built_at])
    con.close()

    review_csv = EVIDENCE_DIR / "identity_crosswalk_v0.1.csv"
    with review_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["permaticker", "ticker", "cik", "effective_from", "effective_to",
                    "relationship_type", "source", "source_record_id", "confidence",
                    "mapping_rationale", "review_status"])
        for r in sorted(build.rows, key=lambda x: (x.permaticker, x.effective_from)):
            w.writerow([r.permaticker, r.ticker, r.cik, r.effective_from,
                        r.effective_to or "", r.relationship_type, r.source,
                        r.source_record_id, r.confidence, r.mapping_rationale,
                        r.review_status])

    passed = sum(1 for v in tests.values() if v["pass"])
    report = {
        "built_at": built_at.isoformat(),
        "tickers": tickers,
        "rows": len(build.rows),
        "conflicts": build.conflicts,
        "notes": build.notes,
        "identity_tests": tests,
        "integrity_errors": integrity_errors,
        "expected_ambiguities": build.ambiguities,
        "identity_tests_passed": f"{passed}/{len(tests)}",
        "review_csv": str(review_csv.relative_to(ROOT)),
        "crosswalk_artifact_sha256": hashlib.sha256(review_csv.read_bytes()).hexdigest(),
        "overrides_artifact_sha256": hashlib.sha256(OVERRIDES_CSV.read_bytes()).hexdigest(),
        "canonicalization": {
            "canonicalization_version": 1,
            "canonical_fields": ["permaticker", "ticker", "cik", "effective_from",
                                  "effective_to", "relationship_type"],
            "canonical_sort_key": ["permaticker", "effective_from", "ticker"],
            "line_ending_policy": "LF, no trailing newline in the canonical payload",
        },
        "crosswalk_canonical_data_sha256": hashlib.sha256("\n".join(
            f"{r.permaticker},{r.ticker},{r.cik},{r.effective_from},{r.effective_to or ''},{r.relationship_type}"
            for r in sorted(build.rows, key=lambda x: (x.permaticker, x.effective_from, x.ticker))
        ).encode()).hexdigest(),
        "hash_note": "artifact_sha256 = raw file bytes; canonical_data_sha256 = sorted canonical rows. "
                     "Both PROVISIONAL — final hashes generated after owner countersign, before the gate",
    }
    Path(args.report_out).write_text(json.dumps(report, indent=2, default=str))
    print(f"\nrows={len(build.rows)} conflicts={len(build.conflicts)} "
          f"tests={passed}/{len(tests)} -> {args.report_out}")
    for name, v in tests.items():
        print(f"  [{'PASS' if v['pass'] else 'FAIL'}] {name}")
    return 0 if passed == len(tests) and not build.conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
