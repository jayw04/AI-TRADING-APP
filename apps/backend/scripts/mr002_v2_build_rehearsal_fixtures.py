"""Build the FROZEN rehearsal fixture corpus for the closed-latch Validation-2 rehearsal.

⛔ These fixtures are SYNTHETIC REHEARSAL INPUTS. They are development-corpus rows written under
the production KEY TOPOLOGY so the orchestration can be exercised end to end. They are NOT
Validation-2 data, they are NOT sealed, and no S3 object is touched to build them.

ORDERING DISCIPLINE. The fixtures are built and FROZEN first; their SHA-256 values are then
written into the tracked rehearsal registry and committed. The expected hash therefore exists
BEFORE the rehearsal that is admitted as evidence. The alternative -- compute the hash of
whatever fixture happens to exist at run time -- is a test that passes itself.

Determinism: every table is written with an explicit ORDER BY over its full column list, so the
byte output is reproducible. The builder verifies this by writing twice and comparing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil

import duckdb

SNAPSHOT = "/work/apps/backend/data/mr002_research.duckdb"
SLICE = ("2013-01-02", "2013-12-31")

# table -> (production key it stands in for, SELECT expression, date column or None)
SEALED_TABLES = {
    "actions": ("oos/actions.parquet", "date, action, ticker, name, value, contraticker, "
                "contraname", "date"),
    "anchors": ("oos/anchors.parquet", "cik, ticker, accession, report_date, acceptance_utc, "
                "session_date, availability_class, event_time_basis", "session_date"),
    "etf_prices": ("oos/etf_prices.parquet", "ticker, date, adjclose", "date"),
    "prices": ("oos/prices.parquet", "ticker, date, open, high, low, close, closeadj, volume",
               "date"),
    "sic_observations": ("oos/sic_observations.parquet", "cik, accession, form, accepted_utc, "
                         "sic", None),
    "universe": ("oos/universe.parquet", "universe_month, ticker, permaticker, siccode, "
                 "liquidity_rank, med_dv_60, in_long_universe, in_short_universe", None),
}
REFERENCE_TABLES = {
    "crosswalk": ("reference/crosswalk.parquet",
                  "permaticker, ticker, cik, effective_from, effective_to, relationship_type",
                  None),
    "sic_mapping": ("reference/sic_mapping.parquet",
                    "sic_start, sic_end, effective_from, effective_to, research_sector, "
                    "sector_etf, mapping_confidence", None),
    # REQUIRED_COLUMNS wants review_status on these two, and the development corpus has no such
    # column. It is supplied here as an explicit FIXTURE-ONLY constant so the schema contract is
    # satisfied. Recorded rather than silently synthesised.
    "predecessor_overrides": ("reference/predecessor_overrides.parquet",
                              "permaticker, predecessor_cik, successor_cik, event_date, "
                              "'FIXTURE_ONLY' AS review_status", None),
    "security_sector_overrides": ("reference/security_sector_overrides.parquet",
                                  "permaticker, effective_from, effective_to, sector_etf, "
                                  "'FIXTURE_ONLY' AS review_status", None),
}


def build(root: str) -> dict:
    con = duckdb.connect(SNAPSHOT, read_only=True)
    con.execute("SET TimeZone='UTC'")
    out = {}
    for group in (SEALED_TABLES, REFERENCE_TABLES):
        for table, (key, cols, datecol) in group.items():
            path = os.path.join(root, key.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            where = (f"WHERE {datecol} >= DATE '{SLICE[0]}' AND {datecol} <= DATE '{SLICE[1]}'"
                     if datecol else "")
            con.execute(
                f"COPY (SELECT {cols} FROM {table} {where} ORDER BY ALL) "
                f"TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            with open(path, "rb") as fh:
                payload = fh.read()
            out[key] = {"table": table, "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload)}
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--emit", required=True)
    args = ap.parse_args()

    if os.path.exists(args.root):
        shutil.rmtree(args.root)
    first = build(args.root)

    # determinism control: rebuild into a scratch root and require byte-identical hashes
    scratch = args.root + "__determinism"
    if os.path.exists(scratch):
        shutil.rmtree(scratch)
    second = build(scratch)
    shutil.rmtree(scratch)
    drift = {k: (first[k]["sha256"], second[k]["sha256"])
             for k in first if first[k]["sha256"] != second[k]["sha256"]}
    if drift:
        raise SystemExit(f"FIXTURE BUILD IS NOT DETERMINISTIC: {drift}")

    doc = {"record_type": "MR002_Validation2_RehearsalFixtureCorpus", "version": "1.0",
           "source": "development corpus " + SNAPSHOT + ", slice " + " .. ".join(SLICE),
           "synthetic_rehearsal_inputs_only": True,
           "no_sealed_object_touched": True,
           "determinism_verified_by_double_build": True,
           "fixture_only_columns": {
               "predecessor_overrides.review_status": "FIXTURE_ONLY constant",
               "security_sector_overrides.review_status": "FIXTURE_ONLY constant"},
           "objects": first}
    with open(args.emit, "wb") as fh:
        fh.write((json.dumps(doc, sort_keys=True, indent=2) + "\n").encode("ascii"))
    print(f"built {len(first)} fixtures under {args.root}")
    for k, v in sorted(first.items()):
        print(f"  {k:42s} {v['bytes']:>10,} B  {v['sha256'][:16]}")
    print("determinism: double build produced identical hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
