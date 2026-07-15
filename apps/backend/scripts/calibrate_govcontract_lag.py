"""GOVCONTRACT-001 availability-assumption calibration — a governed, gated research artifact.

Per the 2026-07-15 reviews this does NOT estimate true public-disclosure lag. It estimates a
**USAspending reconciliation-based availability PROXY under imperfect award-level matching**, with
an explicit operational/semantic split so an infrastructure defect can never masquerade as a
data-quality finding.

Pipeline: seeded sample of eligible events → concurrent reconcile through a SHARED adaptive rate
limiter + the retry-aware client (operational failures are retried, then reported AS operational,
never as "unreconciled") → operational-completeness gate → staged plausibility rates (recipient /
agency / plausible-award) with correct denominators → lag PROXY distribution (median/p75/p90/p95,
exceedance shares, seeded bootstrap CI on p90) → missingness (reconciled vs unreconciled by strata)
→ stratified diagnostics → reason-coded outliers → versioned artifact + a 10-check Availability
Assumption gate. It does NOT change DISCLOSURE_LAG_DAYS and does NOT re-derive the event store.

    python scripts/calibrate_govcontract_lag.py --sample 1000 --workers 4 \
        --out data/govcontract_lag_calibration_v1.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.altdata.events.store import EventStore
from app.altdata.quiver.govcontracts import DISCLOSURE_LAG_DAYS
from app.altdata.quiver.usaspending import (
    OPERATIONAL_OUTCOMES,
    SEMANTIC_OUTCOMES,
    ReconcileOutcome,
    USAspendingClient,
    reconcile_event,
)
from app.altdata.sec.cik_map import CikMap, load_cik_map
from app.altdata.sec.client import EdgarClient

# The exact matcher this calibration was run against (frozen BEFORE adjudication). Recipient =
# USAspending recipient_search_text; agency = distinctive-token overlap; window = ±N days; lag
# proxy = min(Last Modified − action_date). Bump on any matcher-logic change.
MATCHER_VERSION = "usaspending-plausibility/v1"
EXCEEDANCE_THRESHOLDS = [21, 27, 30, 45, 60, 90]


class AdaptiveRateLimiter:
    """One shared global limiter for all workers. Enforces a minimum inter-request interval that
    grows on 429 and relaxes after sustained success — so throughput self-tunes instead of a fixed
    worker count hammering the API."""

    def __init__(self, *, min_interval: float = 0.15, max_interval: float = 5.0) -> None:
        self._lock = threading.Lock()
        self._interval = min_interval
        self._min, self._max = min_interval, max_interval
        self._next = 0.0
        self._ok_streak = 0

    def gate(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._interval
        if wait:
            time.sleep(wait)

    def note_429(self) -> None:
        with self._lock:
            self._interval = min(self._max, self._interval * 2)
            self._ok_streak = 0

    def note_success(self) -> None:
        with self._lock:
            self._ok_streak += 1
            if self._ok_streak >= 25 and self._interval > self._min:
                self._interval = max(self._min, self._interval * 0.8)
                self._ok_streak = 0


def _pctile(xs: list[int], p: float) -> int:
    s = sorted(xs)
    return s[int(p * (len(s) - 1))] if s else 0


def _bootstrap_ci(xs: list[int], p: float, *, reps: int, seed: int) -> list[int]:
    if len(xs) < 2:
        return [_pctile(xs, p), _pctile(xs, p)]
    rng = random.Random(seed)
    n = len(xs)
    boots = [_pctile([xs[rng.randrange(n)] for _ in range(n)], p) for _ in range(reps)]
    return [_pctile(boots, 0.025), _pctile(boots, 0.975)]


def _rate_ci(k: int, n: int, *, reps: int, seed: int) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    rng = random.Random(seed)
    boots = sorted(sum(rng.random() < (k / n) for _ in range(n)) / n for _ in range(reps))
    return [round(boots[int(0.025 * (reps - 1))], 4), round(boots[int(0.975 * (reps - 1))], 4)]


def _size_bucket(amount: float | None) -> str:
    if amount is None:
        return "unknown"
    for hi, name in [(100_000, "<100K"), (1_000_000, "100K-1M"), (10_000_000, "1-10M")]:
        if amount < hi:
            return name
    return ">10M"


def _reason_code(row: dict[str, Any]) -> str:
    lag = row["lag"]
    if lag is None:
        return "NO_LAG"
    if lag > 540:
        return "HISTORICAL_BACKFILL"  # far beyond any plausible reporting cycle
    if not row["agency_matched"]:
        return "ENTITY_LINKAGE_AMBIGUITY"  # matched a recipient award, wrong agency -> maybe not the same award
    if lag > 180:
        return "LATE_DISCLOSURE"
    return "WITHIN_EXPECTED"


def _strata_lag(rows: list[dict[str, Any]], key: str, p: float, *, min_n: int) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = collections.defaultdict(list)
    for r in rows:
        if r["lag"] is not None:
            groups[str(r[key])].append(r["lag"])
    out = [{"key": k, "n": len(v), "p90": _pctile(v, p), "median": int(statistics.median(v))}
           for k, v in groups.items() if len(v) >= min_n]
    return sorted(out, key=lambda s: s["n"], reverse=True)


def _missingness(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Reconciled-vs-unreconciled share by stratum — the selection-bias check."""
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        if r["outcome"] in SEMANTIC_OUTCOMES:
            groups[str(r[key])].append(r)
    out = []
    for k, v in groups.items():
        rec = sum(1 for r in v if r["outcome"] == ReconcileOutcome.RECONCILED)
        out.append({"key": k, "n": len(v), "reconciled_share": round(rec / len(v), 3)})
    return sorted(out, key=lambda s: s["n"], reverse=True)


@dataclass
class Calibration:
    version: str
    metric: str
    source: str
    calibrated_at: str
    matcher_version: str
    seed: int
    window_days: int
    percentile: float
    bootstrap: dict[str, Any]
    # funnel
    eligible_events: int
    sampled: int
    semantically_adjudicated: int
    operational_failures: int
    operational_completion_rate: float
    outcome_counts: dict[str, int]
    # staged plausibility rates (denominator = adjudicated)
    recipient_reconciliation_rate: float
    recipient_rate_ci95: list[float]
    agency_consistency_rate: float
    plausible_award_reconciliation_rate: float
    # the PROXY (never called disclosure lag)
    reconciliation_lag_proxy_days_p90: int
    proxy_ci95: list[int]
    proxy_median: int
    proxy_p75: int
    proxy_p95: int
    proxy_max: int
    proxy_n: int
    exceedance_share: dict[str, float]
    by_agency: list[dict[str, Any]]
    by_size: list[dict[str, Any]]
    by_year: list[dict[str, Any]]
    agency_bias_spread: int
    missingness_by_year: list[dict[str, Any]]
    missingness_by_size: list[dict[str, Any]]
    outliers: list[dict[str, Any]]
    proxy_semantics_note: str
    results_hash: str
    gate: dict[str, Any] = field(default_factory=dict)


def _gate(cal: Calibration) -> dict[str, Any]:
    """The 10-check Availability Assumption gate. Data-quality thresholds are pre-registered here;
    a FAIL is preserved as evidence, not tuned away."""
    ci_lo, ci_hi = cal.proxy_ci95
    checks = {
        "1_population_and_funnel_reported": cal.eligible_events > 0 and cal.sampled > 0,
        "2_seeded_sample_ge_1000": cal.sampled >= 1000,
        "3_matcher_frozen": bool(cal.matcher_version),
        "4_operationally_complete": cal.operational_failures == 0,
        "5_recipient_rate_reported_with_ci": cal.recipient_rate_ci95 != [0.0, 0.0],
        "6_missingness_assessed": bool(cal.missingness_by_year) or bool(cal.missingness_by_size),
        "7_lag_labelled_proxy": cal.metric.endswith("proxy_days") and "proxy" in cal.proxy_semantics_note.lower(),
        "8_proxy_distribution_archived": bool(cal.results_hash),
        "9_proxy_crosschecked_vs_publication_cycle": False,  # Level-B cross-check not yet built
        "10_verdict_sensitivity_documented": False,  # fragility probe run separately (adapter-gated)
        # data-quality acceptance (pre-registered, not pilot-derived)
        "dq_recipient_rate_ge_0_90": cal.recipient_reconciliation_rate >= 0.90,
        "dq_bootstrap_ci_width_le_8": (ci_hi - ci_lo) <= 8,
    }
    return {"pass": all(checks.values()), "checks": checks,
            "note": "checks 9-10 require the publication-cycle cross-check and the fragility "
                    "probe; a data-quality FAIL is evidence the reconciliation architecture is "
                    "not yet adequate — not that the economic signal is null."}


def calibrate(*, sample: int, workers: int, percentile: float, window_days: int,
              bootstrap: int, seed: int) -> Calibration:
    try:
        with EdgarClient() as ec:
            cmap: CikMap | None = load_cik_map(ec)
    except Exception:
        cmap = None

    with EventStore(None, read_only=True) as store:
        eligible = store.events_asof_eligible(date.today(), event_type="gov_contract_award")
    rng = random.Random(seed)
    picks = [e for e in (eligible if len(eligible) <= sample else rng.sample(eligible, sample))
             if e.event_date]
    print(f"reconciling {len(picks)} of {len(eligible)} eligible (seed={seed}, "
          f"names={'SEC' if cmap else 'ticker'}, workers={workers}, adaptive rate limiter)")

    limiter = AdaptiveRateLimiter()
    cache: dict[tuple[str, str], Any] = {}
    cache_lock = threading.Lock()

    def _one(ev: Any) -> dict[str, Any]:
        payload = ev.payload or {}
        agency = payload.get("agency")
        ck = ((ev.ticker or "").upper() + "|" + str(ev.cik), ev.event_date.isoformat())
        with cache_lock:
            cached = cache.get(ck)
        if cached is not None:
            res = cached
        else:
            name = (cmap.titles.get(ev.cik) if cmap else None) or ev.ticker or ""
            res = reconcile_event(ticker=ev.ticker or "", company_name=name, agency=agency,
                                  action_date=ev.event_date, usa_client=usa, window_days=window_days)
            with cache_lock:
                cache[ck] = res
        return {
            "ticker": ev.ticker, "agency": agency or "(none)", "amount": payload.get("amount"),
            "size": _size_bucket(payload.get("amount")), "year": ev.event_date.year,
            "action_date": ev.event_date.isoformat(), "outcome": res.outcome,
            "agency_matched": res.agency_matched, "lag": res.availability_lag_days,
            "attempts": res.attempts,
        }

    with USAspendingClient(rate_gate=limiter.gate, on_429=limiter.note_429,
                           on_success=limiter.note_success) as usa, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_one, picks))

    counts = collections.Counter(str(r["outcome"]) for r in rows)
    op_fail = sum(counts[str(o)] for o in OPERATIONAL_OUTCOMES)
    adjudicated = [r for r in rows if r["outcome"] in SEMANTIC_OUTCOMES]
    nadj = len(adjudicated)
    recip = [r for r in adjudicated if r["outcome"] in
             (ReconcileOutcome.RECONCILED, ReconcileOutcome.AMBIGUOUS_CANDIDATE)]
    reconciled = [r for r in adjudicated if r["outcome"] == ReconcileOutcome.RECONCILED]

    lags = [r["lag"] for r in reconciled if r["lag"] is not None]
    p90 = _pctile(lags, percentile)
    by_agency = _strata_lag(reconciled, "agency", percentile, min_n=30)
    ag_p90s = [s["p90"] for s in by_agency if s["n"] >= 50]
    bias_spread = (max(ag_p90s) - min(ag_p90s)) if len(ag_p90s) >= 2 else 0
    outliers = sorted(
        ({"ticker": r["ticker"], "agency": r["agency"], "amount": r["amount"],
          "action_date": r["action_date"], "lag": r["lag"], "reason_code": _reason_code(r)}
         for r in reconciled if r["lag"] is not None and r["lag"] > 180),
        key=lambda o: o["lag"], reverse=True)[:30]

    cal = Calibration(
        version="v1", metric="reconciliation_lag_proxy_days", source="USAspending",
        calibrated_at=datetime.now(UTC).isoformat(), matcher_version=MATCHER_VERSION,
        seed=seed, window_days=window_days, percentile=percentile,
        bootstrap={"method": "seeded_percentile_bootstrap", "iterations": bootstrap, "seed": seed,
                   "ci_method": "empirical_2.5_97.5"},
        eligible_events=len(eligible), sampled=len(picks), semantically_adjudicated=nadj,
        operational_failures=op_fail,
        operational_completion_rate=round(nadj / len(picks), 4) if picks else 0.0,
        outcome_counts=dict(counts),
        recipient_reconciliation_rate=round(len(recip) / nadj, 4) if nadj else 0.0,
        recipient_rate_ci95=_rate_ci(len(recip), nadj, reps=bootstrap, seed=seed),
        agency_consistency_rate=round(len(reconciled) / len(recip), 4) if recip else 0.0,
        plausible_award_reconciliation_rate=round(len(reconciled) / nadj, 4) if nadj else 0.0,
        reconciliation_lag_proxy_days_p90=p90,
        proxy_ci95=_bootstrap_ci(lags, percentile, reps=bootstrap, seed=seed),
        proxy_median=int(statistics.median(lags)) if lags else 0,
        proxy_p75=_pctile(lags, 0.75), proxy_p95=_pctile(lags, 0.95),
        proxy_max=max(lags) if lags else 0, proxy_n=len(lags),
        exceedance_share={str(t): round(sum(x > t for x in lags) / len(lags), 4) if lags else 0.0
                          for t in EXCEEDANCE_THRESHOLDS},
        by_agency=by_agency, by_size=_strata_lag(reconciled, "size", percentile, min_n=20),
        by_year=_strata_lag(reconciled, "year", percentile, min_n=20), agency_bias_spread=bias_spread,
        missingness_by_year=_missingness(adjudicated, "year"),
        missingness_by_size=_missingness(adjudicated, "size"),
        outliers=outliers,
        proxy_semantics_note=(
            "This metric is a PROXY, not first-public-disclosure. It is min(Quiver action_date to "
            "the earliest qualifying USAspending record's Last Modified date), subject to "
            "corrections/reloads. Cross-check vs agency publication-cycle (Level B) is pending; "
            "bootstrap CI is uncertainty around the proxy's p90 only, not true disclosure lag."),
        results_hash=hashlib.sha256(
            json.dumps([[r["ticker"], r["action_date"], str(r["outcome"]), r["lag"]]
                       for r in rows], sort_keys=True).encode()).hexdigest(),
    )
    cal.gate = _gate(cal)
    return cal


def _report(cal: Calibration, current: int) -> None:
    print("\n=== GOVCONTRACT-001 availability-assumption calibration (v1) ===")
    print(f"  FUNNEL: eligible {cal.eligible_events} -> sampled {cal.sampled} -> "
          f"adjudicated {cal.semantically_adjudicated} (operational failures {cal.operational_failures})")
    print(f"  operational completion: {cal.operational_completion_rate:.1%}   outcomes: {cal.outcome_counts}")
    print(f"  recipient reconciliation: {cal.recipient_reconciliation_rate:.1%}  CI {cal.recipient_rate_ci95}")
    print(f"  agency consistency      : {cal.agency_consistency_rate:.1%}")
    print(f"  plausible-award recon   : {cal.plausible_award_reconciliation_rate:.1%}")
    print(f"  LAG PROXY (days): median {cal.proxy_median}  p75 {cal.proxy_p75}  "
          f"p90 {cal.reconciliation_lag_proxy_days_p90} (CI {cal.proxy_ci95})  p95 {cal.proxy_p95}  "
          f"max {cal.proxy_max}  n={cal.proxy_n}")
    print(f"  exceedance share: {cal.exceedance_share}")
    print(f"  current constant {current} -> proxy p90 {cal.reconciliation_lag_proxy_days_p90}")
    print("  by AGENCY: " + ", ".join(f"{s['key'][:20]}={s['p90']}(n{s['n']})" for s in cal.by_agency[:6]))
    print(f"  agency-bias spread(n>=50): {cal.agency_bias_spread}")
    print("  missingness by year (reconciled share): " +
          ", ".join(f"{s['key']}={s['reconciled_share']}(n{s['n']})" for s in cal.missingness_by_year[:6]))
    print(f"  outliers(>180d): {len(cal.outliers)} " +
          ", ".join(f"{o['ticker']}/{o['lag']}d/{o['reason_code']}" for o in cal.outliers[:4]))
    print("\n  --- Availability Assumption gate (10 checks + data-quality) ---")
    for k, v in cal.gate["checks"].items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  GATE: {'PASS' if cal.gate['pass'] else 'FAIL — preserve as evidence; do NOT freeze or re-derive'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--percentile", type=float, default=0.90)
    ap.add_argument("--window-days", type=int, default=45)
    ap.add_argument("--bootstrap", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cal = calibrate(sample=args.sample, workers=args.workers, percentile=args.percentile,
                    window_days=args.window_days, bootstrap=args.bootstrap, seed=args.seed)
    _report(cal, DISCLOSURE_LAG_DAYS)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(asdict(cal), fh, indent=2, default=str)
        print(f"\n  artifact -> {args.out}  (results_hash {cal.results_hash[:16]})")


if __name__ == "__main__":
    main()
