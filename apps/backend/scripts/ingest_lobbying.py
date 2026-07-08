"""Ingest Quiver corporate-lobbying spend-spike events into the PIT Event Store (LOBBY-001; DCAP-007).

Per-ticker over the factor-spine universe (there is no bulk lobbying endpoint; the deep history lives
behind ``/beta/historical/lobbying/{ticker}``). Aggregates each firm's filings to firm-quarter spend
PIT-cleanly, detects spend spikes (>= 2.0x the trailing-4Q median over nonzero quarters AND >= $100k,
given >= 4 prior nonzero quarters), and prints the **Phase-0 data-quality report** (plan §7) so PIT
integrity and what v1 drops are explicit. Requires ``QUIVER_API_KEY`` + ``SEC_EDGAR_USER_AGENT``.
Read-only vendor fetch, off the order path.

Usage (from apps/backend, or on the throwaway compute):
    python scripts/ingest_lobbying.py --factor-universe 9000
    python scripts/ingest_lobbying.py --universe-file data/lobby_tickers.txt
"""

from __future__ import annotations

import argparse
from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.quiver.client import QuiverClient
from app.altdata.quiver.lobbying_ingest import ingest_lobbying
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
    ap = argparse.ArgumentParser(description="Ingest Quiver lobbying spend-spikes into the Event Store.")
    ap.add_argument("--events-db", default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--universe-file", help="per-ticker over tickers in this file")
    mode.add_argument("--factor-universe", type=int, metavar="N",
                      help="per-ticker over the top-N factor universe")
    args = ap.parse_args()

    sm = _security_master()
    tickers = _tickers(args)
    print(f"ingesting lobbying spikes over {len(tickers)} tickers…")
    with QuiverClient(timeout=120.0) as client, EventStore(args.events_db) as store:
        rep = ingest_lobbying(client, store, tickers, security_master=sm)

    dq = rep.data_quality
    print("\n=== LOBBY-001 ingest ===")
    print(f"  spike events built : {rep.events_built}  (eligible {rep.eligible})")
    print(f"  newly ingested     : {rep.events_ingested}")
    print(f"  fetch failures     : {rep.fetch_failures}")
    print("--- Phase-0 data quality (PIT integrity + what v1 drops) ---")
    print(f"  tickers seen               : {dq.tickers}")
    print(f"  total filings              : {dq.total_filings}")
    print(f"  filings on-time (<=deadline): {dq.filings_on_time}")
    print(f"  late/amended excluded      : {dq.late_excluded}")
    print(f"  undated/unparseable dropped: {dq.undated_or_unparseable}")
    print(f"  firm-quarters              : {dq.firm_quarters}")
    print(f"  spike events               : {dq.spike_events}")
    print(f"  excluded new-entrant qtrs  : {dq.excluded_new_entrant_quarters}")


if __name__ == "__main__":
    main()
