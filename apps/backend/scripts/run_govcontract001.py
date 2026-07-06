"""GOVCONTRACT-001 study runner (EAD Phase 2; ADR 0037 §3.2).

Reads research-eligible government-contract events from the Event Store, de-overlaps them,
builds the matched-control benchmark over the factor spine, and applies the pre-registered
verdict tree. **Data-gated:** requires the migration+ingest to have run (real event store) and
the factor spine. Pre-registration discipline (plan §0): the verdict is computed ONCE on the
complete pull — this driver stamps INTERIM until the ≥100-event floor and the USAspending
calibration are met. Read-only.

Usage (from apps/backend, after the deploy gate):
    python scripts/run_govcontract001.py --hold-days 20
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.insider_program import make_price_fn
from app.altdata.matched_control import EventPoint
from app.altdata.quiver.govcontract_study import (
    MIN_EVENTS,
    factor_feature_fn,
    run_govcontract_study,
)
from app.factor_data.store import FactorDataStore


def _dedupe_overlapping(events, hold_days: int) -> tuple[list[EventPoint], frozenset[str]]:
    """Collapse multiple awards to the same ticker within the holding window into one event
    (first available_time) — an event study must not double-count an overlapping drift window
    (plan §2). Returns (de-overlapped points, all event tickers for the control-exclusion set)."""
    last: dict[str, date] = {}
    points: list[EventPoint] = []
    all_tickers: set[str] = set()
    for ev in sorted(events, key=lambda e: e.available_time or e.filed_at):
        if not ev.available_time or not ev.ticker:
            continue
        entry = ev.available_time.date()
        all_tickers.add(ev.ticker)
        prev = last.get(ev.ticker)
        if prev is not None and (entry - prev).days < int(hold_days * 1.5):
            continue                                  # still inside the prior drift window
        last[ev.ticker] = entry
        points.append(EventPoint(ev.ticker, entry))
    return points, frozenset(all_tickers)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the GOVCONTRACT-001 matched-control study.")
    ap.add_argument("--events-db", default=None)
    ap.add_argument("--factor-db", default=None)
    ap.add_argument("--hold-days", type=int, default=20)
    ap.add_argument("--min-controls", type=int, default=10)
    args = ap.parse_args()

    with EventStore(args.events_db, read_only=True) as store:
        events = store.events_asof_eligible(date.today(), event_type="gov_contract_award")
    if not events:
        print("no research-eligible gov_contract_award events - run the migration + ingest first.")
        return

    points, exclude = _dedupe_overlapping(events, args.hold_days)
    factor_store = FactorDataStore(args.factor_db) if args.factor_db else FactorDataStore()

    evidence = run_govcontract_study(
        points,
        price_fn=make_price_fn(factor_store),
        feature_fn=factor_feature_fn(factor_store),
        exclude_fn=lambda _d: exclude,               # never use another awarded name as a control
        hold_days=args.hold_days, min_controls=args.min_controls,
    )

    interim = evidence["metrics"]["n_benchmarked"] < MIN_EVENTS
    print(f"\n=== GOVCONTRACT-001 {'[INTERIM]' if interim else '[REGISTERED VERDICT]'} ===")
    print(json.dumps(evidence, indent=2, default=str))
    if interim:
        print(f"\nINTERIM: only {evidence['metrics']['n_benchmarked']} benchmarked events "
              f"(< {MIN_EVENTS} floor) — NOT the registered verdict (plan §5). Ingest more history "
              "and run the USAspending cross-check to calibrate the disclosure lag first.")


if __name__ == "__main__":
    main()
