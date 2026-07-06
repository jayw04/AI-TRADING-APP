"""Ingest Quiver government contracts into the PIT Event Store (EAD Phase 1; DCAP-007).

Modes (choose one):
    --live                    recent cross-market awards (one bulk call) — the daily-incremental path
    --universe-file PATH      per-ticker award history for tickers listed in the file (one/line)
    --factor-universe N       per-ticker history over the top-N factor universe as-of today

Requires ``QUIVER_API_KEY`` (Quiver token) and ``SEC_EDGAR_USER_AGENT`` (the Security Master builds
its CIK→name map from SEC ``company_tickers.json``). Read-only vendor fetch, off the order path.

Usage (from apps/backend, or in the backend container):
    python scripts/ingest_govcontracts.py --live
    python scripts/ingest_govcontracts.py --factor-universe 500
    python scripts/ingest_govcontracts.py --universe-file data/defense_contractors.txt
"""

from __future__ import annotations

import argparse
from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.quiver.client import QuiverClient
from app.altdata.quiver.ingest import (
    GovContractIngestReport,
    ingest_govcontracts,
    ingest_govcontracts_bulk,
)
from app.altdata.sec.cik_map import load_cik_map
from app.altdata.sec.client import EdgarClient
from app.altdata.security_master import SecurityMaster


def _security_master() -> SecurityMaster:
    with EdgarClient() as ec:                       # SEC_EDGAR_USER_AGENT required
        return SecurityMaster(load_cik_map(ec))


def _tickers(args: argparse.Namespace) -> list[str]:
    if args.universe_file:
        with open(args.universe_file, encoding="utf-8") as f:
            return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]
    from app.factor_data.store import FactorDataStore
    from app.factor_data.universe import universe_asof
    return universe_asof(FactorDataStore(), date.today(), n=args.factor_universe)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest Quiver government contracts into the Event Store.")
    ap.add_argument("--events-db", default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="recent bulk awards (daily incremental)")
    mode.add_argument("--universe-file", help="per-ticker history over tickers in this file")
    mode.add_argument("--factor-universe", type=int, metavar="N",
                      help="per-ticker history over the top-N factor universe")
    args = ap.parse_args()

    sm = _security_master()
    with QuiverClient() as client, EventStore(args.events_db) as store:
        if args.live:
            rep: GovContractIngestReport = ingest_govcontracts_bulk(client, store, security_master=sm)
        else:
            tickers = _tickers(args)
            print(f"ingesting {len(tickers)} tickers…")
            rep = ingest_govcontracts(client, store, tickers, security_master=sm)

    print("=== Quiver gov-contract ingest ===")
    print(f"  rows seen        : {rep.rows_seen}")
    print(f"  events built     : {rep.events_built}")
    print(f"  newly ingested   : {rep.events_ingested}")
    print(f"  unresolved       : {rep.unresolved}  {dict(rep.unresolved_reasons)}")
    print(f"  fetch failures   : {rep.fetch_failures}")


if __name__ == "__main__":
    main()
