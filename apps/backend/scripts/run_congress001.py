"""CONGRESS-001 study runner — Purchase Primary → Sensitivity → Decision + Sale diagnostic
(EAD Phase 3; ADR 0037 §3.2).

Reads research-eligible ``congress_trade`` events, builds de-overlapped Purchase CLUSTERS (materiality
= summed Range lower-bounds ≥ $50k), enters each on the first trading day strictly after the OBSERVABLE
ReportDate, and runs the matched-control excess study with a DATE-CLUSTERED bootstrap for the verdict —
then a one-factor-at-a-time sensitivity (cost, holding {5,10,60}) as robustness. Sales are reported as
a sign diagnostic only (never the verdict). **Data-gated:** needs the ingested events + the factor
spine (use the small-cap-broad ``deepen`` copy, and a large ``--n-universe`` so small-cap peers are in
the candidate pool). Pre-registration discipline: the verdict is computed ONCE; below the 100-cluster
gate it terminates "Insufficient Evidence" (do NOT relax materiality). Read-only, off the order path.

Usage (from apps/backend, on the separate compute after the ingest):
    python scripts/run_congress001.py --factor-db data/factor_data.deepen.duckdb --n-universe 9000
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.insider_program import make_price_fn
from app.altdata.quiver.congress_study import (
    MIN_EVENTS,
    build_clusters,
    cluster_tickers,
    is_robust,
    run_primary,
    run_sensitivity,
)
from app.altdata.quiver.govcontract_study import factor_feature_fn
from app.factor_data.store import FactorDataStore


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the CONGRESS-001 matched-control study.")
    ap.add_argument("--events-db", default=None)
    ap.add_argument("--factor-db", default=None)
    ap.add_argument("--min-controls", type=int, default=10)
    ap.add_argument("--n-resamples", type=int, default=2000)
    ap.add_argument("--n-universe", type=int, default=9000,
                    help="candidate-pool size (top-by-dollar-volume). Small-cap peers need a large "
                         "pool (~9000) or they are excluded from the matched controls.")
    args = ap.parse_args()

    with EventStore(args.events_db, read_only=True) as store:
        events = store.events_asof_eligible(date.today(), event_type="congress_trade")
    if not events:
        print("no research-eligible congress_trade events - run the ingest first.")
        return

    # read-only: the live app holds the factor-store write lock (research is read-only anyway)
    factor_store = FactorDataStore(args.factor_db, read_only=True)
    price_fn = make_price_fn(factor_store)
    exclude = cluster_tickers(events)   # every Congress-traded ticker excluded from control baskets
    feature_fn = factor_feature_fn(factor_store, n_universe=args.n_universe, always_include=exclude)
    common = dict(price_fn=price_fn, feature_fn=feature_fn, exclude_fn=lambda _d: exclude,
                  min_controls=args.min_controls, n_resamples=args.n_resamples)

    buys = build_clusters(events, direction="buy")
    sells = build_clusters(events, direction="sell")

    # 1) PRIMARY (the verdict) — Purchases only
    primary = run_primary(buys, **common)
    # 2) SENSITIVITY (confirmation only)
    sens = run_sensitivity(buys, **common)
    robust = is_robust(primary["outcome"], sens)
    # 3) DECISION
    interim = primary["metrics"]["n_benchmarked"] < MIN_EVENTS

    print(f"\n=== CONGRESS-001 {'[INTERIM]' if interim else '[REGISTERED VERDICT]'} ===")
    print(f"congress_trade events: {len(events)} | Purchase clusters (material): {len(buys)} "
          f"| Sale clusters (material): {len(sells)}")
    print("\n-- PRIMARY (Purchase, hold 20, cost 10bps, DATE-CLUSTERED bootstrap) --")
    print(json.dumps({k: primary[k] for k in ("metrics", "outcome", "action")}, indent=2, default=str))
    print("\n-- SENSITIVITY (one-factor-at-a-time; confirmation, not the verdict) --")
    for r in sens["rows"]:
        print(f"  {r.dimension:12s}={r.value:<6g} n={r.n_benchmarked:<4d} "
              f"net_excess={r.mean_excess:+.4f} CI[{r.ci_low:+.4f},{r.ci_high:+.4f}] "
              f"{'sig+' if r.significant_positive else '.'}")
    print(f"  BH-FDR (q={sens['fdr_q']}) across holding family: "
          f"{sens['holding_family_fdr_survivors']}/{sens['holding_family_n']} survive")

    # DIAGNOSTIC (never the verdict): do Sales precede negative drift? Sign is informational only —
    # sales are liquidity/tax-driven and a short would carry borrow cost (plan §8).
    if sells:
        sale = run_primary(sells, **common)
        sm = sale["metrics"]
        print("\n-- SALE DIAGNOSTIC (informational; not shorted, not the verdict) --")
        print(f"  n={sm['n_benchmarked']} net_excess={sm['mean_excess']:+.4f} "
              f"CI[{sm['ci_low']:+.4f},{sm['ci_high']:+.4f}]")

    print("\n-- DECISION --")
    print(f"  verdict : {primary['outcome']}")
    print(f"  robust  : {robust}  (would a reasonable alternative flip it? "
          f"{'no' if robust else 'YES - fragile'})")
    print(f"  action  : {primary['action']}")
    if interim:
        print(f"\nINTERIM: {primary['metrics']['n_benchmarked']} benchmarked clusters < {MIN_EVENTS} "
              "gate -> terminates Insufficient Evidence. Do NOT relax materiality (pre-registration).")


if __name__ == "__main__":
    main()
