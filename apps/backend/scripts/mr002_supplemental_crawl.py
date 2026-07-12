"""MR-002 supplemental crawl (owner condition 4: tightly scoped, pinned, hardened).

Three tracks, one deterministic pinned manifest, the HARDENED fetcher (identity
encoding + 256KB read cap + atomic cache writes + disk guard + truststore):

  TRACK A — predecessor CIKs from `predecessor_override_registry_v0.1.csv`
            (10-K/10-Q/-A). Identity remedy.
  TRACK B — FPI form-coverage CIKs (NXPI/TEVA/TEAM/CPRI/CRON/CGC + OVV's Encana):
            the SAME CIK, forms 20-F/40-F(/A). NOT an identity change.
  TRACK D — the 43 accessions whose SIC parsed as NULL in stage-2 because the
            disk-full incident left TRUNCATED cache objects (CIKs 101829/101830/
            101778/1466258). Re-fetched fresh — a data-integrity repair.

PROVENANCE (owner condition 5): observations are stored under the CIK THAT ACTUALLY
FILED them. Nothing is rewritten as though the successor had filed it; the security
attachment happens at gate time through the effective-dated override.

NO unrelated issuer refresh. Partial-report behavior enabled (DiskGuard -> exit 3).

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_supplemental_crawl.py
"""

from __future__ import annotations

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import csv
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
BACKEND = ROOT / "apps" / "backend"
sys.path.insert(0, str(BACKEND))

from app.altdata.mr002.sic_history import (  # noqa: E402
    build_segments,
    collect_sic_observations,
)

FPI_CIKS = {  # track B: same CIK, FPI forms (20-F/40-F) hold the SIC header
    "NXPI": 1413447, "TEVA": 818686, "TEAM": 1650372,
    "CPRI": 1530721, "CRON": 1656472, "CGC": 1737927,
}
TRUNCATED_CIKS = [101829, 101830, 101778, 1466258]   # track D
FPI_FORMS = ("20-F", "40-F", "20-F/A", "40-F/A")
DOM_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")


def load_fetcher():
    spec = importlib.util.spec_from_file_location(
        "mr002_crawl", Path(__file__).with_name("mr002_stage2_edgar_crawl.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mr002_crawl"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    wd = EV / "supplemental"
    wd.mkdir(parents=True, exist_ok=True)
    crawl = load_fetcher()
    fetcher = crawl.ProvenanceFetcher(wd, "GlobalComplyAI LLC jay.w0416@gmail.com")

    # ---- pin the manifest BEFORE any document fetch ----
    with (EV / "predecessor_override_registry_v0.1.csv").open(
            newline="", encoding="utf-8") as f:
        reg = list(csv.DictReader(f))
    track_a = {int(r["predecessor_cik"]): r["ticker"] for r in reg}
    manifest = {
        "generated": datetime.now(UTC).isoformat(),
        "track_A_predecessor_ciks": track_a,
        "track_B_fpi_ciks": FPI_CIKS,
        "track_B_forms": list(FPI_FORMS),
        "track_D_truncated_cache_ciks": TRUNCATED_CIKS,
        "since": "2010-01-01",
        "scope_note": "predecessor + FPI-form + truncated-repair only; no unrelated "
                      "issuer refresh",
    }
    body = json.dumps(manifest, indent=1)
    (wd / "supplemental_manifest.json").write_text(body)
    (wd / "supplemental_manifest.sha256").write_text(
        hashlib.sha256(body.encode()).hexdigest())
    print(f"MANIFEST PINNED: A={len(track_a)} B={len(FPI_CIKS)} D={len(TRUNCATED_CIKS)}",
          flush=True)

    db = duckdb.connect(str(wd / "supplemental.duckdb"))
    db.execute("""CREATE OR REPLACE TABLE sic_observations (
        cik BIGINT, ticker VARCHAR, accession VARCHAR, form VARCHAR,
        accepted_utc TIMESTAMPTZ, sic VARCHAR, sic_name VARCHAR, track VARCHAR,
        PRIMARY KEY (cik, accession))""")
    db.execute("""CREATE OR REPLACE TABLE sic_segments (
        cik BIGINT, ticker VARCHAR, sic VARCHAR, sic_name VARCHAR,
        effective_from TIMESTAMPTZ, effective_to TIMESTAMPTZ,
        source_accession VARCHAR, track VARCHAR)""")
    counters = {"A_obs": 0, "B_obs": 0, "D_obs": 0, "missing_sic": 0, "errors": 0}

    def ingest(cik: int, label: str, forms: tuple, track: str) -> None:
        try:
            res = collect_sic_observations(fetcher, cik, label, since="2010-01-01",
                                           forms=forms)
            res = build_segments(res)
        except Exception as e:  # noqa: BLE001
            counters["errors"] += 1
            print(f"    ERROR {label} cik={cik}: {repr(e)[:90]}", flush=True)
            return
        got = sum(1 for o in res.observations if o.sic)
        counters[f"{track}_obs"] += got
        counters["missing_sic"] += res.missing_sic
        for o in res.observations:
            db.execute("INSERT OR REPLACE INTO sic_observations VALUES (?,?,?,?,?,?,?,?)",
                       [o.cik, o.ticker, o.accession, o.form, o.accepted_utc, o.sic,
                        o.sic_name, track])
        for s in res.segments:
            db.execute("INSERT INTO sic_segments VALUES (?,?,?,?,?,?,?,?)",
                       [s.cik, s.ticker, s.sic, s.sic_name, s.effective_from,
                        s.effective_to, s.source_accession, track])
        print(f"    {label:8} cik={cik:>8} track={track} obs={got} "
              f"segs={len(res.segments)} missing={res.missing_sic}", flush=True)

    print("TRACK A — predecessor CIKs (10-K/10-Q)", flush=True)
    for cik, tick in sorted(track_a.items()):
        ingest(cik, f"{tick}_pred", DOM_FORMS, "A")

    print("TRACK B — FPI forms (20-F/40-F), same CIK", flush=True)
    for tick, cik in FPI_CIKS.items():
        ingest(cik, tick, FPI_FORMS, "B")
    ingest(1157806, "OVV_pred_encana", FPI_FORMS, "B")  # Encana filed 40-F

    print("TRACK D — truncated-cache repair (fresh fetch)", flush=True)
    for cik in TRUNCATED_CIKS:
        ingest(cik, f"repair_{cik}", DOM_FORMS, "D")

    for tbl in ("sic_observations", "sic_segments"):
        db.execute(f"COPY {tbl} TO '{wd / (tbl + '.csv')}' (HEADER, DELIMITER ',')")
    db.close()

    report = {
        "generated": datetime.now(UTC).isoformat(),
        "termination_reason": "COMPLETED",
        "manifest_sha256": (wd / "supplemental_manifest.sha256").read_text().strip(),
        "fetch_counters": dict(fetcher.counters),
        "extraction_counters": counters,
        "snapshots": {
            f"{t}_csv_sha256": hashlib.sha256((wd / f"{t}.csv").read_bytes()).hexdigest()
            for t in ("sic_observations", "sic_segments")},
        "worst_50_response_burst_compressed_bytes": fetcher.worst_burst_bytes(50),
        "largest_10_cache_objects": fetcher.largest_objects_report(10),
    }
    (wd / "supplemental_run_report.json").write_text(json.dumps(report, indent=2,
                                                                default=str))
    print("\n" + json.dumps({"fetch": report["fetch_counters"],
                             "extraction": counters}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
