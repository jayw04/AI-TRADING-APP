"""Quiver ↔ USAspending cross-check (EAD Phase 1 exit gate; ADR 0037 §9).

Samples research-eligible ``gov_contract_award`` events from the Event Store and reconciles each
against USAspending.gov (the official record), reporting: mapping-plausibility match rate, agency
match rate, and the availability-lag distribution — which **calibrates** the normalizer's
``DISCLOSURE_LAG_DAYS`` (currently a conservative placeholder). Read-only.

Usage (from apps/backend):
    python scripts/quiver_usaspending_crosscheck.py --sample 100
    python scripts/quiver_usaspending_crosscheck.py --events-db data/event_store.duckdb --sample 50
"""

from __future__ import annotations

import argparse
import statistics
from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.quiver.usaspending import USAspendingClient, reconcile_event
from app.altdata.sec.cik_map import CikMap, load_cik_map
from app.altdata.sec.client import EdgarClient, EdgarDisabled


def _company_names() -> CikMap | None:
    """CIK→title map for USAspending recipient search. Needs SEC_EDGAR_USER_AGENT; if absent we
    fall back to the ticker as the recipient query (weaker)."""
    try:
        with EdgarClient() as ec:
            return load_cik_map(ec)
    except EdgarDisabled:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile sampled Quiver gov-contract events vs USAspending.")
    ap.add_argument("--events-db", default=None)
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--window-days", type=int, default=45)
    args = ap.parse_args()

    cmap = _company_names()
    with EventStore(args.events_db, read_only=True) as store:
        events = store.events_asof_eligible(date.today(), event_type="gov_contract_award")
    if not events:
        print("no research-eligible gov_contract_award events in the store — ingest first.")
        return
    sample = events[: args.sample]
    print(f"reconciling {len(sample)} of {len(events)} eligible events vs USAspending "
          f"(company names: {'SEC titles' if cmap else 'ticker fallback'})")

    results = []
    with USAspendingClient() as usa:
        for ev in sample:
            name = (cmap.titles.get(ev.cik) if cmap else None) or ev.ticker or ""
            agency = (ev.payload or {}).get("agency")
            if not ev.event_date:
                continue
            results.append(reconcile_event(
                ticker=ev.ticker or "", company_name=name, agency=agency,
                action_date=ev.event_date, usa_client=usa, window_days=args.window_days,
            ))

    n = len(results)
    matched = sum(1 for r in results if r.matched)
    agency_ok = sum(1 for r in results if r.agency_matched)
    lags = [r.availability_lag_days for r in results if r.availability_lag_days is not None]

    print("\n=== Quiver ↔ USAspending cross-check ===")
    print(f"  sampled            : {n}")
    print(f"  recipient matched  : {matched} ({matched / n:.0%})" if n else "  (none)")
    print(f"  agency matched     : {agency_ok} ({agency_ok / n:.0%})" if n else "")
    if lags:
        print(f"  availability lag d : min {min(lags)}  median {int(statistics.median(lags))}  "
              f"p90 {sorted(lags)[int(0.9 * (len(lags) - 1))]}  max {max(lags)}  (n={len(lags)})")
        print(f"  -> suggested DISCLOSURE_LAG_DAYS ≈ p90 = {sorted(lags)[int(0.9 * (len(lags) - 1))]}")
    else:
        print("  availability lag d : no Last Modified Dates returned")
    print("\nNOTE: mapping-plausibility check (Quiver per-action vs USAspending award-aggregate); "
          "a low match rate flags Quiver normalization/mapping issues (a §2.6a kill signal).")


if __name__ == "__main__":
    main()
