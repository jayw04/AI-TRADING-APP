"""GOVCONTRACT-001 — fully PIT strategy-eligible reconciliation coverage (fork a).

NARROW OBJECTIVE (owner 2026-07-15): determine whether the award-level reconciliation method is
ADMISSIBLE for the fully-defined GOVCONTRACT-001 PIT-eligible trading universe — NOT whether it can
rehabilitate the failed broad lag-calibration claim (that is already settled: MATERIAL_IMBALANCE,
descriptive_only, not_frozen).

Three NESTED populations, each reconciled with the hardened client + operational/semantic taxonomy:
  (1) broad          — the full sampled Quiver gov-contract population (settled by Run C; cited)
  (2) material        — awards clearing the $250k ABSOLUTE floor
  (3) strategy-eligible — PIT: valid ticker as-of, PIT market cap available as-of (event_date+lag),
      award >= 0.25% of that PIT market cap, in the registered window, de-overlapped (hold*1.5).
  All PIT reads use market cap AS-OF the event, never current. (The equity-universe/liquidity gate
  is NOT applied here — a further restriction that would only SHRINK the eligible set; noted as the
  one remaining criterion, so a PASS here is an upper bound on coverage.)

The DECISION RULE is PRE-DECLARED below and committed BEFORE running (pre-registration discipline).

    python scripts/strategy_eligible_reconciliation.py --factor-db data/factor_data.deepen.duckdb \
        --material-sample 1200 --out data/govcontract_strategy_eligible.json
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any

from analyze_govcontract_missingness import analyze
from calibrate_govcontract_lag import (
    MATERIALITY_USD_FLOOR,
    AdaptiveRateLimiter,
    _name_quality,
    _recency_bucket,
    _size_bucket,
)

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.quiver.govcontract_study import (
    DISCLOSURE_LAG_PRIMARY,
    HOLD_PRIMARY,
    factor_mktcap_fn,
    filter_material,
)
from app.altdata.quiver.usaspending import (
    OPERATIONAL_OUTCOMES,
    SEMANTIC_OUTCOMES,
    ReconcileOutcome,
    USAspendingClient,
    _agency_tokens,
    reconcile_event,
)
from app.altdata.sec.cik_map import load_cik_map
from app.altdata.sec.client import EdgarClient
from app.factor_data.store import FactorDataStore

# ── PRE-DECLARED DECISION RULE (frozen before the run) ────────────────────────────────────────────
MIN_STRATEGY_COVERAGE = 0.90          # predeclared minimum reconciliation coverage (aligns w/ broad dq)
N_INSUFFICIENT = 100                  # n_adjudicated < 100  -> insufficient for a coverage verdict
N_ADJUDICABLE = 200                   # n_adjudicated >= 200 -> potentially adjudicable
# return-relevant features: reconciliation must NOT be materially associated with these
RETURN_RELEVANT = ["year", "recency_bucket", "event_density"]
# agency is handled by check 6 (no material imbalance OR explicitly restrict to covered agencies)
_SEMANTIC = SEMANTIC_OUTCOMES


def _dedupe_overlapping(events: list[CorporateEvent], hold_days: int) -> list[CorporateEvent]:
    """Collapse same-ticker awards within hold*1.5 to the first — an event study must not double-count
    an overlapping window (mirrors run_govcontract001._dedupe_overlapping)."""
    last: dict[str, date] = {}
    kept: list[CorporateEvent] = []
    for ev in sorted(events, key=lambda e: e.event_date or date.min):
        if not ev.event_date or not ev.ticker:
            continue
        prev = last.get(ev.ticker)
        if prev is not None and (ev.event_date - prev).days < int(hold_days * 1.5):
            continue
        last[ev.ticker] = ev.event_date
        kept.append(ev)
    return kept


def _load_material_floor_events(store: EventStore, as_of: date) -> list[CorporateEvent]:
    """Lean SQL pre-filter: eligible gov_contract_award events clearing the $250k ABSOLUTE floor.
    Selects only the needed columns (never the full 890k) so the box stays well within memory."""
    amt_path = "$.amount"
    rows = store._con.execute(
        "SELECT cik, ticker, event_date, available_time, payload FROM corporate_events "
        "WHERE event_type = 'gov_contract_award' AND research_eligible = TRUE "
        "AND available_time IS NOT NULL AND CAST(available_time AS DATE) <= ? "
        "AND TRY_CAST(json_extract_string(payload, ?) AS DOUBLE) >= ?",
        [as_of, amt_path, MATERIALITY_USD_FLOOR],
    ).fetchall()
    out: list[CorporateEvent] = []
    for cik, ticker, ev_date, avail, payload in rows:
        pl = json.loads(payload) if isinstance(payload, str) else (payload or {})
        out.append(CorporateEvent(cik=cik or 0, ticker=ticker, event_type="gov_contract_award",
                                  source="quiver", accession="", filed_at=avail, event_date=ev_date,
                                  payload=pl, available_time=avail))
    return out


def _reconcile_population(events: list[CorporateEvent], *, cmap: Any, workers: int, window_days: int,
                          today: date, seed: int) -> list[dict[str, Any]]:
    limiter = AdaptiveRateLimiter()
    cache: dict[tuple[str, str], Any] = {}
    lock = threading.Lock()

    def _one(ev: CorporateEvent) -> dict[str, Any]:
        assert ev.event_date is not None  # eligible/material events always carry an event_date
        agency = (ev.payload or {}).get("agency")
        name = (cmap.titles.get(ev.cik) if cmap else None) or ev.ticker or ""
        ck = ((ev.ticker or "").upper() + "|" + str(ev.cik), ev.event_date.isoformat())
        with lock:
            cached = cache.get(ck)
        if cached is not None:
            res = cached
        else:
            res = reconcile_event(ticker=ev.ticker or "", company_name=name, agency=agency,
                                  action_date=ev.event_date, usa_client=usa, window_days=window_days)
            with lock:
                cache[ck] = res
        amt = (ev.payload or {}).get("amount")
        return {
            "ticker": ev.ticker, "agency": agency or "(none)", "amount": amt,
            "size": _size_bucket(amt), "year": ev.event_date.year,
            "action_date": ev.event_date.isoformat(), "outcome": res.outcome,
            "reconcile_outcome": str(res.outcome), "agency_matched": res.agency_matched,
            "lag": res.availability_lag_days, "candidate_count": res.n_candidates,
            "amount_ge_250k": (amt is not None and amt >= MATERIALITY_USD_FLOOR),
            "award_amount": amt, "recency_bucket": _recency_bucket(ev.event_date, today),
            "name_quality": _name_quality(name), "agency_normalized": " ".join(sorted(_agency_tokens(agency))),
            "failure_reason": res.note,
        }

    with USAspendingClient(rate_gate=limiter.gate, on_429=limiter.note_429,
                           on_success=limiter.note_success) as usa, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_one, events))
    # event_density = sampled events sharing the ticker (post-pass)
    density = collections.Counter(r["ticker"] for r in rows)
    for r in rows:
        r["event_density"] = density[r["ticker"]]
    return rows


def _pop_summary(name: str, eligible_n: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    adj = [r for r in rows if r["reconcile_outcome"] in _SEMANTIC]
    op_fail = sum(1 for r in rows if r["reconcile_outcome"] in
                  {str(o) for o in OPERATIONAL_OUTCOMES})
    recon = sum(1 for r in adj if r["reconcile_outcome"] in
                {str(ReconcileOutcome.RECONCILED), str(ReconcileOutcome.AMBIGUOUS_CANDIDATE)})
    return {
        "population": name, "eligible_count": eligible_n, "reconciled_attempts": len(rows),
        "semantically_adjudicated": len(adj),
        "operational_completion_rate": round(len(adj) / len(rows), 4) if rows else 0.0,
        "operational_failures": op_fail,
        "reconciliation_rate": round(recon / len(adj), 4) if adj else 0.0,
    }


def _coverage_gate(elig_summary: dict[str, Any], imbalance: dict[str, Any]) -> dict[str, Any]:
    """The PRE-DECLARED STRATEGY_COVERAGE gate. Not tuned to the result."""
    n_adj = elig_summary["semantically_adjudicated"]
    rate = elig_summary["reconciliation_rate"]
    cat = imbalance["categorical_association"]
    cont = imbalance["continuous_standardized_difference"]

    def _material(feat: str) -> bool:
        return (cat.get(feat, {}).get("material_imbalance")
                or cont.get(feat, {}).get("material_imbalance") or False)

    size_verdict = ("insufficient" if n_adj < N_INSUFFICIENT
                    else "conditional" if n_adj < N_ADJUDICABLE else "adjudicable")
    return_relevant_imbalanced = [f for f in RETURN_RELEVANT if _material(f)]
    agency_material = _material("agency_normalized")
    checks = {
        "1_adequate_sample": n_adj >= N_ADJUDICABLE,
        "2_operational_completion_reported": True,
        "3_coverage_meets_min": rate >= MIN_STRATEGY_COVERAGE,
        "4_no_recency_imbalance": not (_material("year") or _material("recency_bucket")),
        "5_no_density_imbalance": not _material("event_density"),
        "6_agency_ok_or_restricted": not agency_material,  # else: restrict to covered agencies
        "7_no_return_relevant_association": not return_relevant_imbalanced,
    }
    passed = all(checks.values())
    if passed:
        disposition = ("STRATEGY_COVERAGE_PASS — run the lag-fragility probe ONLY on the frozen, "
                       "fully-eligible PIT population; supports a NARROW claim (method usable within "
                       "the predeclared eligible universe). Still does NOT justify a global lag freeze.")
    elif size_verdict == "insufficient":
        disposition = ("INSUFFICIENT_STRATEGY_COVERAGE_EVIDENCE — do not interpret the rate; decide "
                       "between expanding the eligible sample and moving to PIID-level reconciliation.")
    elif rate < MIN_STRATEGY_COVERAGE:
        disposition = ("STRATEGY_COVERAGE_FAIL (coverage) — fork (b): b1 PIID/transaction-level "
                       "reconciliation if GOVCONTRACT-001 stays strategically important, else b2 a "
                       "formally restricted research scope.")
    elif return_relevant_imbalanced or agency_material:
        disposition = ("STRATEGY_COVERAGE_FAIL (return-relevant imbalance) — high aggregate coverage "
                       "is NOT enough while failures concentrate on return-relevant features "
                       f"({return_relevant_imbalanced or ['agency']}); current method inadequate -> "
                       "PIID-level work or source-restricted research. Do NOT run the probe.")
    else:
        disposition = "STRATEGY_COVERAGE_CONDITIONAL — see checks; adjudicate strata counts."
    return {"pass": passed, "sample_size_verdict": size_verdict, "checks": checks,
            "return_relevant_imbalanced": return_relevant_imbalanced,
            "predeclared": {"min_coverage": MIN_STRATEGY_COVERAGE, "n_insufficient": N_INSUFFICIENT,
                            "n_adjudicable": N_ADJUDICABLE, "return_relevant": RETURN_RELEVANT},
            "disposition": disposition}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--factor-db", required=True, help="factor store WITH sf1 marketcap (deepen)")
    ap.add_argument("--material-sample", type=int, default=1200,
                    help="reconcile at most this many of the $250k-floor population (nested compare)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--window-days", type=int, default=45)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="build populations + counts only; no reconcile")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    today = date.today()
    try:
        with EdgarClient() as ec:
            cmap = load_cik_map(ec)
    except Exception:
        cmap = None

    with EventStore(None, read_only=True) as store:
        material_floor = _load_material_floor_events(store, today)
    print(f"material-$floor (>=250k) events: {len(material_floor)}")

    factor_store = FactorDataStore(args.factor_db, read_only=True)
    mktcap_fn = factor_mktcap_fn(factor_store)
    material = filter_material(material_floor, mktcap_fn=mktcap_fn, lag_days=DISCLOSURE_LAG_PRIMARY)
    eligible = _dedupe_overlapping(material, HOLD_PRIMARY)
    print(f"  -> material by 0.25%-mktcap (PIT): {len(material)}")
    print(f"  -> strategy-eligible (de-overlapped): {len(eligible)}")
    if args.dry_run:
        return

    rng = random.Random(args.seed)
    mat_sample = (material_floor if len(material_floor) <= args.material_sample
                  else rng.sample(material_floor, args.material_sample))

    print(f"reconciling: material-sample n={len(mat_sample)}, strategy-eligible n={len(eligible)} ...")
    elig_rows = _reconcile_population(eligible, cmap=cmap, workers=args.workers,
                                      window_days=args.window_days, today=today, seed=args.seed)
    mat_rows = _reconcile_population(mat_sample, cmap=cmap, workers=args.workers,
                                     window_days=args.window_days, today=today, seed=args.seed)

    elig_summary = _pop_summary("strategy_eligible_pit", len(eligible), elig_rows)
    mat_summary = _pop_summary("material_250k_floor", len(material_floor), mat_rows)
    imbalance = analyze(elig_rows)
    gate = _coverage_gate(elig_summary, imbalance)

    result = {
        "objective": "admissibility of award-level reconciliation for the GOVCONTRACT-001 "
                     "PIT-eligible universe (NOT rehabilitation of the broad claim)",
        "generated_at": datetime.now(UTC).isoformat(),
        "nested_populations": {
            "1_broad": {"note": "settled by Run C (authoritative complete run): 75.3% "
                                "reconciliation, MATERIAL_IMBALANCE on recency/agency; not re-run"},
            "2_material_250k_floor": mat_summary,
            "3_strategy_eligible_pit": elig_summary,
        },
        "strategy_eligible_reconciliation_rate": elig_summary["reconciliation_rate"],
        "strategy_eligible_imbalance": imbalance,
        "coverage_gate": gate,
        "unapplied_criterion": "equity-universe / liquidity membership (universe_asof) — a further "
                               "restriction; this rate is an upper bound on eligible coverage",
        "recency_hypothesis": {
            "primary": "recent-event under-reconciliation is caused by official-record "
                       "reporting/publication latency or incomplete USAspending backfill",
            "status": "association demonstrated, NOT yet causally confirmed",
            "alternatives": ["query-window behaviour", "award aggregation semantics", "identifier drift",
                             "agency-specific submission practices", "Quiver event-capture differences"],
            "adjudicator": "the Level-B publication-cycle cross-check",
        },
        "run_provenance": {"seed": args.seed, "factor_db": args.factor_db,
                           "run_c": "authoritative complete rate estimate",
                           "run_d": "replication_diagnostic (80% operational completion; not pooled)"},
    }
    print(f"\n  strategy_eligible_reconciliation_rate = {elig_summary['reconciliation_rate']:.1%} "
          f"(n_adj={elig_summary['semantically_adjudicated']}, op_complete="
          f"{elig_summary['operational_completion_rate']:.1%})")
    print(f"  imbalance verdict: {imbalance['verdict'][:60]}")
    print(f"  sample-size verdict: {gate['sample_size_verdict']}")
    for k, v in gate["checks"].items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  GATE pass={gate['pass']}\n  DISPOSITION: {gate['disposition']}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"  artifact -> {args.out}")


if __name__ == "__main__":
    main()
