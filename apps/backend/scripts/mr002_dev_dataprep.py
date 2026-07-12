"""MR-002 development data prep (frozen v1.0 §8a inputs only).

Builds the immutable local research store for the harness:

  prices     — Sharadar SEP for every security in the frozen preliminary universe.
               FOUR SEPARATE SERIES per the frozen §4 policy:
                 signal   = closeadj (total-return adjusted)
                 exec     = open / close (split-adjusted, NOT dividend-adjusted)
                 gap      = exec prices + ACTIONS cash distributions
                 ranking  = close x volume (consistent split-adjusted pair)
  factors    — SPY + the 11 sector SPDRs (Yahoo adjusted close, the registered
               research-grade ETF source; used ONLY for the market/sector factors)
  actions    — Sharadar ACTIONS (announcement-dated exclusions, dividends, splits,
               delistings)
  anchors    — the frozen V1 earnings-anchor population (stage-2, immutable)
  sic        — the frozen PIT-SIC observations/segments (stage-2 + supplemental)
  identity   — crosswalk + countersigned predecessor overrides (v1.0)

Everything is hashed into `dev_data_snapshot.json`. NOTHING here reads the
validation or sealed-OOS windows — the store is built for the FULL frozen window
(warm-up needs 2010+), but the harness itself is bounded to the development
sessions by the runner.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_dev_dataprep.py
"""

from __future__ import annotations

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import hashlib
import json
import os
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[3]
    for _env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
STORE = ROOT / "apps" / "backend" / "data" / "mr002_research.duckdb"
WORK = ROOT / "apps" / "backend" / "data" / "mr002_work"
NDL = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
# frozen sector-factor ETFs (§3): SPY + the 11 sector SPDRs
ETFS = ["SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU",
        "XLV", "XLY"]
WARMUP_START = "2010-01-01"   # 3y warm-up before the 2013-01-02 development start


def log(m: str) -> None:
    print(f"[{datetime.now(UTC).isoformat(timespec='seconds')}] {m}", flush=True)


def bulk(table: str, key: str, dest: Path) -> Path:
    url = f"{NDL}/{table}.json?qopts.export=true&api_key={key}"
    for _ in range(120):
        with urllib.request.urlopen(url, timeout=60) as r:
            meta = json.load(r)
        f = meta["datatable_bulk_download"]["file"]
        if f["status"] == "fresh":
            link = f["link"]
            break
        time.sleep(30)
    else:
        raise RuntimeError(f"{table} export never fresh")
    zp = dest / f"{table}.zip"
    log(f"downloading {table}…")
    urllib.request.urlretrieve(link, zp)
    log(f"{table}: {zp.stat().st_size/1e6:.0f} MB")
    return zp


def yahoo_prices(client: httpx.Client, sym: str) -> list[tuple]:
    """Yahoo daily adjusted close — the registered ETF factor source."""
    r = client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                   params={"period1": 1230768000, "period2": 1784000000,
                           "interval": "1d", "events": "div,splits"},
                   headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    return [(sym, datetime.fromtimestamp(t, UTC).date(), a)
            for t, a in zip(ts, adj, strict=False) if a is not None]


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    key = os.environ["NASDAQ_DATA_LINK_API_KEY"]
    db = duckdb.connect(str(STORE))
    prov: dict = {"built": datetime.now(UTC).isoformat(),
                  "frozen_inputs_only": True, "warmup_start": WARMUP_START}

    # ---- frozen universe (immutable) ----
    db.execute(f"CREATE OR REPLACE TABLE universe AS SELECT * FROM read_csv_auto("
               f"'{EV / 'mr002_preliminary_universe.csv.gz'}', header=true) "
               "WHERE universe_month <= DATE '2026-07-01'")
    tickers = [r[0] for r in db.execute(
        "SELECT DISTINCT ticker FROM universe ORDER BY 1").fetchall()]
    log(f"frozen universe: {len(tickers)} securities, "
        f"{db.execute('SELECT count(*) FROM universe').fetchone()[0]} universe-months")

    # ---- SEP prices (bulk; filtered to the frozen universe) ----
    if not db.execute("SELECT count(*) FROM information_schema.tables "
                      "WHERE table_name='prices'").fetchone()[0]:
        zp = bulk("SEP", key, WORK)
        prov["sep_zip_sha256"] = hashlib.sha256(zp.read_bytes()).hexdigest()
        with zipfile.ZipFile(zp) as z:
            member = z.namelist()[0]
            z.extract(member, WORK)
        csv_path = WORK / member
        db.execute(f"""CREATE OR REPLACE TABLE prices AS
            SELECT ticker, date, open, high, low, close, closeadj, closeunadj, volume
            FROM read_csv_auto('{csv_path}', header=true)
            WHERE date >= DATE '{WARMUP_START}'
              AND ticker IN (SELECT DISTINCT ticker FROM universe)""")
        csv_path.unlink()
        zp.unlink()
    log(f"prices: {db.execute('SELECT count(*) FROM prices').fetchone()[0]:,} rows")

    # ---- ACTIONS (announcement-dated exclusions, dividends, splits, delistings) ----
    zp = bulk("ACTIONS", key, WORK)
    prov["actions_zip_sha256"] = hashlib.sha256(zp.read_bytes()).hexdigest()
    with zipfile.ZipFile(zp) as z:
        member = z.namelist()[0]
        z.extract(member, WORK)
    db.execute(f"""CREATE OR REPLACE TABLE actions AS
        SELECT * FROM read_csv_auto('{WORK / member}', header=true)
        WHERE date >= DATE '{WARMUP_START}'
          AND ticker IN (SELECT DISTINCT ticker FROM universe)""")
    (WORK / member).unlink()
    zp.unlink()
    log(f"actions: {db.execute('SELECT count(*) FROM actions').fetchone()[0]:,} rows")

    # ---- sector-factor ETFs (Yahoo adjusted close) ----
    rows = []
    with httpx.Client(follow_redirects=True) as c:
        for sym in ETFS:
            try:
                px = yahoo_prices(c, sym)
                rows += px
                log(f"  {sym}: {len(px)} sessions")
            except Exception as e:  # noqa: BLE001
                log(f"  {sym}: FAILED {repr(e)[:60]}")
    db.execute("CREATE OR REPLACE TABLE etf_prices (ticker VARCHAR, date DATE, "
               "adjclose DOUBLE)")
    db.executemany("INSERT INTO etf_prices VALUES (?,?,?)", rows)
    log(f"etf_prices: {len(rows):,} rows")

    # ---- frozen V1 anchors + PIT-SIC + identity (immutable copies) ----
    db.execute(f"CREATE OR REPLACE TABLE anchors AS SELECT * FROM read_csv_auto("
               f"'{EV / 'stage2' / 'anchors.csv.gz'}', header=true)")
    db.execute(f"""CREATE OR REPLACE TABLE sic_observations AS
        SELECT cik, accession, form, accepted_utc, sic FROM read_csv_auto(
            '{EV / 'stage2' / 'sic_observations.csv.gz'}', header=true)
        WHERE sic IS NOT NULL AND cik NOT IN (101829,101830,101778,1466258)
        UNION ALL
        SELECT cik, accession, form, accepted_utc, sic FROM read_csv_auto(
            '{EV / 'supplemental' / 'sic_observations.csv.gz'}', header=true)
        WHERE sic IS NOT NULL""")
    db.execute(f"CREATE OR REPLACE TABLE crosswalk AS SELECT * FROM read_csv_auto("
               f"'{EV / 'identity_crosswalk_v0.1.csv'}', header=true)")
    db.execute(f"CREATE OR REPLACE TABLE predecessor_overrides AS SELECT * FROM "
               f"read_csv_auto('{EV / 'predecessor_override_registry_v1.0.csv'}', "
               "header=true)")
    db.execute(f"CREATE OR REPLACE TABLE sic_mapping AS SELECT * FROM read_csv_auto("
               f"'{EV / 'sic_sector_etf_mapping_v0.8.csv'}', header=true)")
    db.execute(f"CREATE OR REPLACE TABLE security_sector_overrides AS SELECT * FROM "
               f"read_csv_auto('{EV / 'security_sector_overrides_v0.6.csv'}', header=true)")
    for t in ("anchors", "sic_observations", "crosswalk", "predecessor_overrides",
              "sic_mapping", "security_sector_overrides"):
        log(f"{t}: {db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:,} rows")

    prov["tables"] = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                      for t in ("universe", "prices", "actions", "etf_prices",
                                "anchors", "sic_observations", "crosswalk",
                                "predecessor_overrides", "sic_mapping",
                                "security_sector_overrides")}
    prov["sealed_manifest_ref"] = "MR002_SealedManifest_v1.0.json"
    db.close()
    prov["store_sha256"] = hashlib.sha256(STORE.read_bytes()).hexdigest()
    (EV / "dev_data_snapshot.json").write_text(json.dumps(prov, indent=2))
    log(f"store: {STORE} ({STORE.stat().st_size/1e6:.0f} MB)")
    print(json.dumps(prov["tables"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
