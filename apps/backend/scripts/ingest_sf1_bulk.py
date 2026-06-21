"""Bulk SF1 fundamentals ingest by calendar quarter (ADR 0023) — the fast full-history load.

The per-ticker path in ``ingest_sharadar.py --datasets sf1`` issues one HTTP call + one DuckDB
upsert per name (~12.5k of each) — fine for incremental single-name refresh, but slow for the
initial full load. SF1's ``calendardate`` filter returns the ENTIRE universe for one quarter in a
single (paginated) call (~6.1k tickers x 6 dimensions ~= 37k rows), so sweeping ~40 quarter-ends
loads all of 2016+ in ~40 calls + ~40 batched upserts instead of ~25k tiny operations.

Idempotent: ``ingest_sf1`` upserts on (ticker, dimension, calendardate, datekey), so re-running
converges and merges cleanly with anything the per-ticker path already wrote.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/ingest_sf1_bulk.py --db data/factor_data_full.duckdb

Read-only against the vendor; writes only the local DuckDB store. Key hygiene per ADR 0018 §5
(printed as a length only, never a value). TLS via the OS trust store (ADR 0017; Norton-safe).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import truststore

truststore.inject_into_ssl()

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[3]
    for _env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)
except Exception:
    pass

from app.factor_data.providers.sharadar import SharadarConfigError, SharadarProvider  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

# SF1 normalizes calendardate to calendar quarter-ends.
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


def quarter_end_dates(from_year: int, to: date) -> list[str]:
    """Calendar quarter-end ISO strings from ``from_year``-01-01 through ``to`` (inclusive)."""
    out: list[str] = []
    for year in range(from_year, to.year + 1):
        for mon, day in _QUARTER_ENDS:
            d = date(year, mon, day)
            if d <= to:
                out.append(d.isoformat())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bulk SF1 ingest by calendar quarter (ADR 0023).")
    ap.add_argument("--db", help="store path (default: WORKBENCH_FACTOR_DATA_DB_PATH)")
    ap.add_argument("--from-year", type=int, default=2016,
                    help="first calendar year to sweep (default 2016 — the SF1 tier floor)")
    args = ap.parse_args(argv)

    dates = quarter_end_dates(args.from_year, date.today())
    print(f"sweeping {len(dates)} quarter-ends {dates[0]} .. {dates[-1]}")

    try:
        provider = SharadarProvider()
    except SharadarConfigError as e:
        print(str(e), file=sys.stderr)
        return 1

    store = FactorDataStore(db_path=args.db)
    total = 0
    try:
        for i, cd in enumerate(dates, 1):
            started = datetime.now()
            try:
                df = provider.fetch_table("SF1", calendardate=cd)
                rows = store.ingest_sf1(df)
                store.record_ingest_run(f"sf1_bulk:{cd}", started, datetime.now(), rows, "ok")
                total += rows
                print(f"[{i}/{len(dates)}] {cd}: {rows} rows "
                      f"({(datetime.now() - started).total_seconds():.1f}s)")
            except Exception as e:  # one bad quarter must not kill the sweep
                store.record_ingest_run(f"sf1_bulk:{cd}", started, datetime.now(), 0, "failed")
                print(f"[{i}/{len(dates)}] {cd}: FAILED {e!r}", file=sys.stderr)
        row = store.con.execute("SELECT COUNT(DISTINCT ticker) FROM sf1_fundamentals").fetchone()
        n_tickers = row[0] if row else 0
        print(f"\nsf1_fundamentals total rows: {store.row_count('sf1_fundamentals')} "
              f"(+{total} this run); distinct tickers: {n_tickers}")
    finally:
        store.close()
        provider.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
