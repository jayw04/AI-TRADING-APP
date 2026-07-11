"""MR-002 V2 build runner — EDGAR effective-dated SIC history + mapping application.

Per ticker: resolves CIK, fetches 10-K/10-Q(-/A) filing headers via the throttled
CAP-015 client, extracts the PIT SIC from each SEC-HEADER, assembles effective-dated
segments under the frozen precedence rules, applies the draft effective-dated
SIC->sector-ETF mapping, and persists everything to DuckDB + a metrics JSON.

The mapping table and crosswalk are hashed only AFTER manual validation (owner
control) — this runner reports the would-be hashes for the record but the §8a
freeze values are set at the gate.

Run:
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/mr002_build_sic_history.py --tickers META,AAPL,... --since 2012-01-01

Data provenance only — no MR-002 signals or backtests (owner directive 2026-07-11).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import truststore

truststore.inject_into_ssl()

import duckdb  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    _root = Path(__file__).resolve().parents[3]
    for env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
except Exception:
    pass

os.environ.setdefault("SEC_EDGAR_USER_AGENT", "GlobalComplyAI LLC jay.w0416@gmail.com")

from app.altdata.mr002.sic_history import (  # noqa: E402
    build_segments,
    collect_sic_observations,
)
from app.altdata.sec.cik_map import load_cik_map  # noqa: E402
from app.altdata.sec.client import EdgarClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
EVIDENCE_DIR = ROOT / "Docs" / "implementation" / "evidence" / "mr_002"
MAPPING_CSV = EVIDENCE_DIR / "sic_sector_etf_mapping_v0.8.csv"
SEC_OVERRIDES_CSV = EVIDENCE_DIR / "security_sector_overrides_v0.6.csv"

DDL = """
CREATE TABLE IF NOT EXISTS sic_observations (
    cik BIGINT, ticker VARCHAR, accession VARCHAR, form VARCHAR,
    accepted_utc TIMESTAMPTZ, sic VARCHAR, sic_name VARCHAR, built_at TIMESTAMPTZ,
    PRIMARY KEY (cik, accession)
);
CREATE TABLE IF NOT EXISTS sic_segments (
    cik BIGINT, ticker VARCHAR, sic VARCHAR, sic_name VARCHAR,
    effective_from TIMESTAMPTZ, effective_to TIMESTAMPTZ,
    source_accession VARCHAR, built_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS sic_conflicts (
    detail VARCHAR, built_at TIMESTAMPTZ
);
"""


class Mapping:
    """Effective-dated SIC-range -> (research_sector, sector_etf) lookup."""

    def __init__(self, csv_path: Path) -> None:
        self.rows: list[dict] = []
        self.low_confidence_hits: list[str] = []   # reported separately, never forced
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.rows.append({
                    "lo": int(row["sic_start"]), "hi": int(row["sic_end"]),
                    "from": date.fromisoformat(row["effective_from"]) if row["effective_from"] else None,
                    "to": date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
                    "sector": row["research_sector"], "etf": row["sector_etf"],
                    "confidence": row.get("mapping_confidence", "MEDIUM"),
                })

    def resolve(self, sic: str, on: date) -> tuple[str, str] | None:
        """Primary resolution. LOW-confidence rows are EXCLUDED from the primary
        construction (v0.5 §5) — a LOW match returns None (stock unmapped-excluded
        for that period) and is logged for the separate low-confidence report."""
        code = int(sic)
        for r in self.rows:
            if r["lo"] <= code <= r["hi"] and (r["from"] is None or on >= r["from"]) \
                    and (r["to"] is None or on <= r["to"]):
                if r["confidence"] == "LOW":
                    self.low_confidence_hits.append(f"{sic}@{on}:{r['sector']}/{r['etf']}")
                    return None
                return r["sector"], r["etf"]
        return None  # unmapped -> excluded downstream, never defaulted


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class SecurityOverrides:
    """Frozen effective-dated security-level sector overrides (owner review §F):
    for issuers whose SIC cannot determine the sector reliably (e.g. post-2018 SIC
    7370). An override WINS over the SIC mapping inside its window; names covered by
    neither are excluded, never forced."""

    def __init__(self, csv_path: Path) -> None:
        self.rows: list[dict] = []
        if not csv_path.exists():
            return
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.rows.append({
                    "ticker": row["ticker"].upper(),
                    "from": date.fromisoformat(row["effective_from"]) if row["effective_from"] else None,
                    "to": date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
                    "sector": row["research_sector"], "etf": row["sector_etf"],
                })

    def resolve(self, label_tickers: list[str], on: date) -> tuple[str, str] | None:
        for r in self.rows:
            if r["ticker"] in label_tickers and (r["from"] is None or on >= r["from"]) \
                    and (r["to"] is None or on <= r["to"]):
                return r["sector"], r["etf"]
        return None


def resolve_sector(sec_ovr: SecurityOverrides, mapping: Mapping,
                   label_tickers: list[str], sic: str, on: date):
    """security override > SIC mapping > None (excluded). Returns
    (source, (sector, etf)) or (None, None)."""
    hit = sec_ovr.resolve(label_tickers, on)
    if hit is not None:
        return "security_override", hit
    hit = mapping.resolve(sic, on)
    if hit is not None:
        return "sic_mapping", hit
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--since", default="2012-01-01")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--metrics-out", default=str(EVIDENCE_DIR / "v2_sic_metrics.json"))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    built_at = datetime.now(UTC)
    mapping = Mapping(MAPPING_CSV)
    sec_ovr = SecurityOverrides(SEC_OVERRIDES_CSV)

    with EdgarClient() as edgar:
        cmap = load_cik_map(edgar)
        resolved, unresolved = cmap.resolve_all(tickers)
        print(f"CIK resolved: {len(resolved)}/{len(tickers)}; unresolved={unresolved}")

        # issuer-level like V1: dual-class tickers share the CIK's SIC history
        by_cik: dict[int, list[str]] = {}
        for t, cik in resolved.items():
            by_cik.setdefault(cik, []).append(t)

        all_obs, all_segs, all_conflicts, missing_total = [], [], [], 0
        per_ticker: dict[str, dict] = {}
        for cik, cik_tickers in by_cik.items():
            label = "/".join(sorted(cik_tickers))
            res = collect_sic_observations(edgar, cik, label, since=args.since)
            res = build_segments(res)
            all_obs.extend(res.observations)
            all_segs.extend(res.segments)
            all_conflicts.extend(res.conflicts)
            missing_total += res.missing_sic

            # mapped timeline (for the validation write-up): sector at each segment start
            label_tickers = sorted(cik_tickers)
            timeline = []
            for s in res.segments:
                d0 = s.effective_from.date()
                src0, mapped0 = resolve_sector(sec_ovr, mapping, label_tickers, s.sic, d0)
                timeline.append({
                    "sic": s.sic, "sic_name": s.sic_name,
                    "effective_from": str(d0),
                    "effective_to": str(s.effective_to.date()) if s.effective_to else None,
                    "mapped_at_start": mapped0, "resolution_source": src0,
                })
                # mapping-driven sector changes INSIDE an unchanged-SIC segment
                # (the META case: SIC constant, sector flips at a boundary date)
                prev_mapped = mapped0
                for boundary in (date(2016, 9, 1), date(2018, 10, 1)):
                    end = s.effective_to.date() if s.effective_to else date.today()
                    if d0 < boundary <= end:
                        src_b, mapped_b = resolve_sector(sec_ovr, mapping, label_tickers,
                                                         s.sic, boundary)
                        if mapped_b != prev_mapped:
                            timeline.append({
                                "sic": s.sic, "boundary": str(boundary),
                                "mapped_before": prev_mapped, "mapped_after": mapped_b,
                                "resolution_source": src_b,
                                "note": "sector change WITHOUT SIC change "
                                        "(mapping/override effective-dating)",
                            })
                            prev_mapped = mapped_b
            per_ticker[label] = {
                "filings_processed": len(res.observations),
                "filings_missing_sic": res.missing_sic,
                "segments": len(res.segments),
                "conflicts": len(res.conflicts),
                "timeline": timeline,
            }
            print(f"  {label}: {len(res.observations)} filings -> {len(res.segments)} SIC segment(s), "
                  f"{res.missing_sic} missing-SIC, {len(res.conflicts)} conflicts")

    con = duckdb.connect(args.db)
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            con.execute(stmt)
    ciks = list(by_cik.keys())
    if ciks:
        ph = ",".join("?" * len(ciks))
        for tbl in ("sic_observations", "sic_segments"):
            con.execute(f"DELETE FROM {tbl} WHERE cik IN ({ph})", ciks)
    for o in all_obs:
        con.execute("INSERT OR REPLACE INTO sic_observations VALUES (?,?,?,?,?,?,?,?)",
                    [o.cik, o.ticker, o.accession, o.form, o.accepted_utc, o.sic, o.sic_name, built_at])
    for s in all_segs:
        con.execute("INSERT INTO sic_segments VALUES (?,?,?,?,?,?,?,?)",
                    [s.cik, s.ticker, s.sic, s.sic_name, s.effective_from, s.effective_to,
                     s.source_accession, built_at])
    for c in all_conflicts:
        con.execute("INSERT INTO sic_conflicts VALUES (?,?)", [c, built_at])
    con.close()

    metrics = {
        "tickers_requested": len(tickers),
        "unresolved_tickers": unresolved,
        "filings_processed": len(all_obs),
        "filings_missing_sic": missing_total,
        "segments_total": len(all_segs),
        "same_day_conflicts": all_conflicts,
        "mapping_csv": str(MAPPING_CSV.relative_to(ROOT)),
        "mapping_artifact_sha256": sha256_file(MAPPING_CSV),
        "security_overrides_csv": str(SEC_OVERRIDES_CSV.relative_to(ROOT)),
        "security_overrides_artifact_sha256": sha256_file(SEC_OVERRIDES_CSV),
        "hash_note": "artifact hashes (raw bytes), PROVISIONAL — frozen only after "
                     "owner countersign; canonical_data_sha256 lives in the validator report",
        "low_confidence_hits": mapping.low_confidence_hits,
        "since": args.since,
        "built_at": built_at.isoformat(),
        "per_ticker": per_ticker,
    }
    out = Path(args.metrics_out)
    out.write_text(json.dumps(metrics, indent=2, default=str))
    print(f"\nsegments={len(all_segs)} conflicts={len(all_conflicts)} db={args.db}")
    print(f"metrics -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
