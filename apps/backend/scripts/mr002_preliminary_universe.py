"""MR-002 preliminary-universe construction + mapping-impact report (pre-reg v0.8 §3.3-3.4).

Owner-approved to proceed (countersign review 2026-07-11). Runs the frozen v0.5 §3
anti-circularity sequence FIRST STAGE ONLY: SEP price/liquidity/type filters ->
monthly preliminary universe (top-250 long / top-150 short) — BEFORE any V1/V2
eligibility. Then produces the mapping-impact-by-universe-months report against
mapping v0.4 + the approved security overrides.

⚠ SECTOR SOURCE DISCLOSURE: per-security PIT SIC histories do not exist until the
(held) full-universe V2 crawl. This impact report uses the CURRENT Sharadar TICKERS
``siccode`` as an explicitly-labeled APPROXIMATION for coverage planning only — it
feeds the mapping countersign, never research construction. The report is recomputed
from PIT SIC after the crawl. Every output artifact carries this label.

Designed to run on a temp EC2 box (or anywhere with disk + bandwidth):
    python3 mr002_preliminary_universe.py --workdir /data \
        [--download] [--start 2013-01-01]
--download fetches the SHARADAR SEP + TICKERS bulk exports (NDL export API,
NASDAQ_DATA_LINK_API_KEY env) and ingests them into DuckDB; without it, an existing
{workdir}/mr002_sep.duckdb is reused. No MR-002 signals or backtests here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import urllib.request
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
APPROX_LABEL = ("SECTOR SOURCE = CURRENT TICKERS siccode (APPROXIMATION for coverage "
                "planning only; recomputed from PIT SIC after the V2 crawl)")

ETF_LIVE_FROM = {"XLC": date(2018, 6, 19), "XLRE": date(2015, 10, 8)}


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------------- bulk download & ingest ----------------

def bulk_export(table: str, dest: Path, api_key: str) -> Path:
    """Fetch a SHARADAR datatable bulk export (poll until fresh, download zip)."""
    url = f"{NDL_BASE}/{table}.json?qopts.export=true&api_key={api_key}"
    for attempt in range(120):
        with urllib.request.urlopen(url, timeout=60) as r:
            meta = json.load(r)
        f = meta["datatable_bulk_download"]["file"]
        if f["status"] == "fresh":
            link = f["link"]
            break
        log(f"{table} export {f['status']} — waiting (attempt {attempt})")
        time.sleep(30)
    else:
        raise RuntimeError(f"{table} export never became fresh")
    zip_path = dest / f"{table}.zip"
    log(f"downloading {table} export…")
    urllib.request.urlretrieve(link, zip_path)
    log(f"{table}: {zip_path.stat().st_size/1e6:.0f} MB")
    return zip_path


def ingest(db: duckdb.DuckDBPyConnection, workdir: Path, api_key: str) -> dict:
    prov = {}
    for table in ("TICKERS", "SEP"):
        zp = bulk_export(table, workdir, api_key)
        prov[f"{table.lower()}_zip_sha256"] = hashlib.sha256(zp.read_bytes()).hexdigest()
        with zipfile.ZipFile(zp) as z:
            member = z.namelist()[0]
            z.extract(member, workdir)
        csv_path = workdir / member
        db.execute(f"CREATE OR REPLACE TABLE {table.lower()} AS "
                   f"SELECT * FROM read_csv_auto('{csv_path}', header=true)")
        n = db.execute(f"SELECT count(*) FROM {table.lower()}").fetchone()[0]
        prov[f"{table.lower()}_rows"] = n
        log(f"ingested {table}: {n:,} rows")
        csv_path.unlink()
    return prov


# ---------------- preliminary universe (frozen v0.2 §2 filters ONLY) ----------------

UNIVERSE_SQL = """
WITH common AS (  -- type filter: US domestic common stock only (frozen)
    SELECT ticker, permaticker, category, siccode
    FROM tickers
    WHERE "table" = 'SEP' AND category LIKE 'Domestic Common Stock%'
),
px AS (
    SELECT s.ticker, s.date, s.close, s.volume, s.close * s.volume AS dv
    FROM sep s JOIN common c USING (ticker)
    WHERE s.date >= DATE '{warmup_start}'
),
feat AS (
    SELECT ticker, date, close,
           median(dv) OVER w60 AS med_dv_60,
           count(*)  OVER wall AS n_hist,
           row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn_dummy
    FROM px
    WINDOW w60 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
           wall AS (PARTITION BY ticker ORDER BY date ROWS UNBOUNDED PRECEDING)
),
month_ends AS (  -- last trading day of each COMPLETE month = the reconstitution
    -- as-of. The month containing the newest SEP date is incomplete: using its
    -- mid-month max(date) would future-date a universe (the 2026-08 bug caught by
    -- the owner review) — the registered rule requires the PRIOR MONTH-END close.
    SELECT max(date) AS asof, date_trunc('month', date) + INTERVAL 1 MONTH AS eff_month
    FROM (SELECT DISTINCT date FROM sep WHERE date >= DATE '{warmup_start}')
    GROUP BY date_trunc('month', date)
    HAVING date_trunc('month', max(date)) < (SELECT date_trunc('month', max(date)) FROM sep)
),
candidates AS (
    SELECT m.eff_month, f.ticker, f.close, f.med_dv_60, f.n_hist
    FROM feat f JOIN month_ends m ON f.date = m.asof
    WHERE f.close > 10 AND f.med_dv_60 > 25e6 AND f.n_hist >= 252
),
ranked AS (
    SELECT eff_month, ticker, med_dv_60,
           row_number() OVER (PARTITION BY eff_month ORDER BY med_dv_60 DESC, ticker) AS rnk
    FROM candidates
)
SELECT r.eff_month::DATE AS universe_month, r.ticker, c.permaticker, c.siccode,
       r.rnk AS liquidity_rank, r.med_dv_60,
       (r.rnk <= 250) AS in_long_universe, (r.rnk <= 150) AS in_short_universe
FROM ranked r JOIN common c USING (ticker)
WHERE r.rnk <= 250 AND r.eff_month >= DATE '{start}'
ORDER BY universe_month, liquidity_rank
"""


# ---------------- mapping + overrides (impact tiers) ----------------

def load_mapping(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "lo": int(r["sic_start"]), "hi": int(r["sic_end"]),
                "from": date.fromisoformat(r["effective_from"]) if r["effective_from"] else None,
                "to": date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
                "sector": r["research_sector"], "etf": r["sector_etf"],
                "conf": r["mapping_confidence"],
                "key": f"{r['sic_start']}-{r['sic_end']}@{r['effective_from'] or 'open'}",
            })
    return rows


def load_sec_overrides(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "ticker": r["ticker"].upper(),
                "from": date.fromisoformat(r["effective_from"]) if r["effective_from"] else None,
                "to": date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
                "etf": r["sector_etf"],
            })
    return rows


def classify(mapping, sec_ovr, ticker: str, sic, on: date):
    """-> (tier, etf, mapping_row_key). Tiers: SECURITY_OVERRIDE / HIGH / MEDIUM /
    EXCLUDED_LOW_CONFIDENCE / UNMAPPED / NO_SICCODE. ETF-liveness enforced."""
    for o in sec_ovr:
        if o["ticker"] == ticker and (o["from"] is None or on >= o["from"]) \
                and (o["to"] is None or on <= o["to"]):
            return "SECURITY_OVERRIDE", o["etf"], "security_override"
    if sic is None or str(sic).strip() in ("", "0", "None", "nan"):
        return "NO_SICCODE", None, None
    code = int(float(sic))
    for r in mapping:
        if r["lo"] <= code <= r["hi"] and (r["from"] is None or on >= r["from"]) \
                and (r["to"] is None or on <= r["to"]):
            live = ETF_LIVE_FROM.get(r["etf"])
            if live and on < live:
                return "UNMAPPED", None, r["key"]         # proxy not yet live -> excluded
            if r["conf"] == "LOW":
                return "EXCLUDED_LOW_CONFIDENCE", None, r["key"]
            return r["conf"], r["etf"], r["key"]
    return "UNMAPPED", None, None


FLAGGED_ROWS = ["1500-1519@open", "5045-5045@open", "5047-5047@open",
                "5171-5171@open", "7375-7375@open", "5200-5399@open"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--start", default="2013-01-01",
                    help="first universe month (gate picks the real window later)")
    ap.add_argument("--mapping-csv", default="sic_sector_etf_mapping_v0.6.csv")
    ap.add_argument("--sec-overrides-csv", default="security_sector_overrides_v0.4.csv")
    ap.add_argument("--universe-csv", default=None,
                    help="reuse an existing preliminary-universe CSV(.gz) — skips "
                         "SEP download/SQL; drops any universe month later than the "
                         "last complete month implied by the data")
    args = ap.parse_args()
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(wd / "mr002_sep.duckdb"))
    prov = {"run_started": datetime.now(UTC).isoformat(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "approximation_disclosure": APPROX_LABEL}

    if args.download:
        key = os.environ["NASDAQ_DATA_LINK_API_KEY"]
        prov.update(ingest(db, wd, key))

    if args.universe_csv:
        log(f"reusing universe from {args.universe_csv} (complete-month guard applied)")
        db.execute("CREATE OR REPLACE TABLE preliminary_universe AS "
                   f"SELECT * FROM read_csv_auto('{args.universe_csv}', header=true) "
                   "WHERE universe_month <= date_trunc('month', current_date)")
    else:
        warmup = "2010-01-01" if args.start <= "2013-01-01" else str(
            date.fromisoformat(args.start).replace(year=date.fromisoformat(args.start).year - 3))
        log("constructing monthly preliminary universe…")
        db.execute("CREATE OR REPLACE TABLE preliminary_universe AS " +
                   UNIVERSE_SQL.format(warmup_start=warmup, start=args.start))
    uni = db.execute("SELECT * FROM preliminary_universe").fetchall()
    cols = [d[0] for d in db.description]
    log(f"universe rows: {len(uni):,} "
        f"({db.execute('SELECT count(DISTINCT universe_month) FROM preliminary_universe').fetchone()[0]} months)")

    out_csv = wd / "mr002_preliminary_universe.csv"
    db.execute(f"COPY preliminary_universe TO '{out_csv}' (HEADER, DELIMITER ',')")
    prov["universe_csv_sha256"] = hashlib.sha256(out_csv.read_bytes()).hexdigest()
    prov["universe_rows"] = len(uni)

    # ---------------- impact report ----------------
    mapping = load_mapping(wd / args.mapping_csv)
    sec_ovr = load_sec_overrides(wd / args.sec_overrides_csv)
    i_month = cols.index("universe_month")
    i_tick = cols.index("ticker")
    i_sic = cols.index("siccode")
    i_short = cols.index("in_short_universe")

    tier_months: dict[str, int] = {}
    by_security: dict[str, dict] = {}
    by_year: dict[int, dict[str, int]] = {}
    flagged: dict[str, dict[str, int]] = {k: {} for k in FLAGGED_ROWS}
    boundary_medium: set[str] = set()

    for row in uni:
        m = row[i_month]
        t = row[i_tick]
        sic = row[i_sic]
        on = m if isinstance(m, date) else date.fromisoformat(str(m)[:10])
        tier, etf, rkey = classify(mapping, sec_ovr, t, sic, on)
        tier_months[tier] = tier_months.get(tier, 0) + 1
        y = on.year
        by_year.setdefault(y, {})
        by_year[y][tier] = by_year[y].get(tier, 0) + 1
        s = by_security.setdefault(t, {"months": 0, "MEDIUM": 0, "tiers": set(),
                                       "sic": str(sic), "short": bool(row[i_short])})
        s["months"] += 1
        s["tiers"].add(tier)
        if tier == "MEDIUM":
            s["MEDIUM"] += 1
        if rkey in flagged:
            flagged[rkey][t] = flagged[rkey].get(t, 0) + 1
        if tier == "EXCLUDED_LOW_CONFIDENCE":
            s.setdefault("LOW", 0)
            s["LOW"] += 1
        # MEDIUM row driving a boundary change (XLC/XLRE)
        if tier == "MEDIUM" and etf in ("XLC",) :
            boundary_medium.add(t)

    total = sum(tier_months.values())
    top_medium = sorted(((t, s["MEDIUM"], s["sic"]) for t, s in by_security.items()
                         if s["MEDIUM"]), key=lambda x: -x[1])[:20]
    medium_removed = {
        y: round(100.0 * (v.get("HIGH", 0) + v.get("SECURITY_OVERRIDE", 0)) /
                 max(1, sum(v.values())), 2)
        for y, v in sorted(by_year.items())
    }
    eligible = (tier_months.get("HIGH", 0) + tier_months.get("MEDIUM", 0)
                + tier_months.get("SECURITY_OVERRIDE", 0))
    top_low = sorted(((t, s.get("LOW", 0), s["sic"]) for t, s in by_security.items()
                      if s.get("LOW")), key=lambda x: -x[1])[:25]
    report = {
        "generated": datetime.now(UTC).isoformat(),
        "disclosure": APPROX_LABEL,
        "coverage_gate_check": {
            "eligible_universe_months(HIGH+MEDIUM+OVERRIDE)": eligible,
            "max_primary_coverage_pct": round(100.0 * eligible / max(1, total), 2),
            "registered_v2_gate_pct": 98.0,
            "gate_met_if_all_MEDIUM_approved": bool(100.0 * eligible / max(1, total) >= 98.0),
        },
        "top_securities_by_LOW_excluded_months": [
            {"ticker": t, "low_months": n, "siccode": sic} for t, n, sic in top_low],
        "universe_months_total": total,
        "distinct_securities": len(by_security),
        "months": db.execute(
            "SELECT min(universe_month), max(universe_month) FROM preliminary_universe"
        ).fetchall()[0],
        "universe_months_by_tier": dict(sorted(tier_months.items(), key=lambda x: -x[1])),
        "pct_by_tier": {k: round(100.0 * v / total, 2) for k, v in tier_months.items()},
        "per_year_tier_counts": {str(y): v for y, v in sorted(by_year.items())},
        "coverage_pct_with_MEDIUM_removed_by_year": medium_removed,
        "top20_securities_by_MEDIUM_universe_months": [
            {"ticker": t, "medium_months": n, "siccode": sic} for t, n, sic in top_medium],
        "flagged_row_exposure": {k: dict(sorted(v.items(), key=lambda x: -x[1])[:15])
                                  for k, v in flagged.items() if v},
        "medium_rows_at_XLC_boundary_securities": sorted(boundary_medium)[:30],
        "provenance": prov,
    }
    (wd / "mr002_impact_report.json").write_text(json.dumps(report, indent=2, default=str))
    log("impact report written")
    print(json.dumps({k: report[k] for k in
                      ("universe_months_total", "distinct_securities", "months",
                       "universe_months_by_tier", "pct_by_tier")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
