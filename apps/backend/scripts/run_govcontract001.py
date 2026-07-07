"""GOVCONTRACT-001 study runner — Primary → Sensitivity → Decision (EAD Phase 2; ADR 0037 §3.2).

Reads research-eligible government-contract events, applies the LOCKED calibration (disclosure lag
21, materiality 0.25%-mktcap + $250k, cost 10bps/side), de-overlaps, runs the primary matched-
control excess study for the verdict, then the one-factor-at-a-time sensitivity (lag {14,46}, cost
{20}, holding {5,10,60}) as a robustness confirmation. **Data-gated:** needs the ingested events +
the factor spine. Pre-registration discipline: the verdict is computed ONCE; below the 100-event
gate it terminates "Insufficient Evidence" (do not relax materiality). Read-only, off the order path.

Note: the study recomputes entry = event_date + lag internally, so it does not depend on the
available_time stored at ingest time (which may reflect an earlier lag).

Usage (from apps/backend, after the deploy gate):
    python scripts/run_govcontract001.py
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.insider_program import make_price_fn
from app.altdata.quiver.govcontract_study import (
    DISCLOSURE_LAG_PRIMARY,
    HOLD_PRIMARY,
    MIN_EVENTS,
    factor_feature_fn,
    factor_mktcap_fn,
    filter_material,
    is_robust,
    run_primary,
    run_sensitivity,
)
from app.factor_data.store import FactorDataStore


def _dedupe_overlapping(events, hold_days: int) -> tuple[list[CorporateEvent], frozenset[str]]:
    """Collapse multiple awards to the same ticker within the holding window into one event (first
    action) — an event study must not double-count an overlapping drift window (plan §2). De-overlap
    on event_date (lag-independent). Returns (de-overlapped events, all tickers for control-exclusion)."""
    last: dict[str, date] = {}
    kept: list[CorporateEvent] = []
    all_tickers: set[str] = set()
    for ev in sorted(events, key=lambda e: e.event_date or date.min):
        if not ev.event_date or not ev.ticker:
            continue
        all_tickers.add(ev.ticker)
        prev = last.get(ev.ticker)
        if prev is not None and (ev.event_date - prev).days < int(hold_days * 1.5):
            continue
        last[ev.ticker] = ev.event_date
        kept.append(ev)
    return kept, frozenset(all_tickers)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the GOVCONTRACT-001 matched-control study.")
    ap.add_argument("--events-db", default=None)
    ap.add_argument("--factor-db", default=None)
    ap.add_argument("--min-controls", type=int, default=10)
    ap.add_argument("--n-resamples", type=int, default=2000)
    ap.add_argument("--n-universe", type=int, default=2000,
                    help="candidate-pool size (top-by-dollar-volume). Small-cap peers need a "
                         "large pool (e.g. ~9000) or they are excluded from the matched controls.")
    args = ap.parse_args()

    with EventStore(args.events_db, read_only=True) as store:
        events = store.events_asof_eligible(date.today(), event_type="gov_contract_award")
    if not events:
        print("no research-eligible gov_contract_award events - run the migration + ingest first.")
        return

    # read-only: the live app holds the factor-store write lock (research is read-only anyway)
    factor_store = FactorDataStore(args.factor_db, read_only=True)
    mktcap_fn = factor_mktcap_fn(factor_store)
    price_fn = make_price_fn(factor_store)

    material = filter_material(events, mktcap_fn=mktcap_fn, lag_days=DISCLOSURE_LAG_PRIMARY)
    deduped, exclude = _dedupe_overlapping(material, HOLD_PRIMARY)
    # the (small/mid-cap) event tickers must be in the candidate pool so they get features — the
    # top-liquidity universe alone would drop them (which produced n_benchmarked=0 the first run).
    feature_fn = factor_feature_fn(factor_store, n_universe=args.n_universe,
                                   always_include=frozenset(exclude))
    common = dict(price_fn=price_fn, feature_fn=feature_fn, exclude_fn=lambda _d: exclude,
                  min_controls=args.min_controls, n_resamples=args.n_resamples)

    # 1) PRIMARY (the verdict)
    primary = run_primary(deduped, **common)
    # 2) SENSITIVITY (confirmation only)
    sens = run_sensitivity(deduped, **common)
    robust = is_robust(primary["outcome"], sens)
    # 3) DECISION
    interim = primary["metrics"]["n_benchmarked"] < MIN_EVENTS

    print(f"\n=== GOVCONTRACT-001 {'[INTERIM]' if interim else '[REGISTERED VERDICT]'} ===")
    print("eligible_events:", len(events), "| material:", len(material), "| de-overlapped:", len(deduped))
    print("\n-- PRIMARY (lag 21, hold 20, cost 10bps) --")
    print(json.dumps({k: primary[k] for k in ("metrics", "outcome", "action")}, indent=2, default=str))
    print("\n-- SENSITIVITY (one-factor-at-a-time; confirmation, not the verdict) --")
    for r in sens["rows"]:
        print(f"  {r.dimension:14s}={r.value:<6g} n={r.n_benchmarked:<4d} "
              f"net_excess={r.mean_excess:+.4f} CI[{r.ci_low:+.4f},{r.ci_high:+.4f}] "
              f"{'sig+' if r.significant_positive else '.'}")
    print(f"  BH-FDR (q={sens['fdr_q']}) across holding family: "
          f"{sens['holding_family_fdr_survivors']}/{sens['holding_family_n']} survive")
    print("\n-- DECISION --")
    print(f"  verdict : {primary['outcome']}")
    print(f"  robust  : {robust}  (would a reasonable alternative flip it? {'no' if robust else 'YES - fragile'})")
    print(f"  action  : {primary['action']}")
    if interim:
        print(f"\nINTERIM: {primary['metrics']['n_benchmarked']} benchmarked events < {MIN_EVENTS} gate "
              "-> terminates Insufficient Evidence. Do NOT relax materiality (pre-registration v0.2).")


if __name__ == "__main__":
    main()
