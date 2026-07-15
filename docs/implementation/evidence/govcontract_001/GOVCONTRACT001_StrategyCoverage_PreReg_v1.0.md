# GOVCONTRACT-001 — Strategy-Eligible Coverage: Pre-Registration v1.0

**Date:** 2026-07-15 (frozen and committed BEFORE the run — `strategy_eligible_reconciliation.py`)
**Fork:** (a), per owner 2026-07-15.

## Objective (narrow)

Determine whether the award-level reconciliation method is **admissible for the fully-defined
GOVCONTRACT-001 PIT-eligible population** — *not* whether it can rehabilitate the failed broad
lag-calibration claim (already settled: MATERIAL_IMBALANCE, `descriptive_only`, `not_frozen`).

If this gate fails, stop trying to rescue the award-level proxy and move to PIID-level
reconciliation or a formally restricted scope.

## Three nested populations

1. **Broad** — full sampled Quiver gov-contract population (settled by **Run C**, cited, not re-run).
2. **Material** — awards clearing the **$250k absolute** floor.
3. **Strategy-eligible (PIT)** — valid ticker as-of · **PIT market cap available as-of**
   (event_date + 21d) · award ≥ **0.25% of that PIT market cap** · in the registered window ·
   de-overlapped (hold×1.5). Market cap is read **as-of the event, never current.**

*Un-applied criterion (documented):* equity-universe / liquidity membership (`universe_asof`) — a
further restriction that only shrinks the set, so the reported rate is an **upper bound** on
eligible coverage.

For each population: eligible count, semantically-adjudicated count, reconciliation rate,
operational completion rate, and (for pop 3) the full imbalance analysis across
year / recency / agency / name-quality / event-density / award-size.

## Pre-declared decision rule — `STRATEGY_COVERAGE_PASS` only if ALL:

1. Adequate eligible sample (**n_adjudicated ≥ 200**).
2. Operational completion independently reported.
3. Strategy-eligible reconciliation coverage ≥ **0.90** (predeclared minimum).
4. **No material imbalance on event year/recency.**
5. **No material imbalance on event density.**
6. No material imbalance on agency — **or** the study is explicitly restricted to adequately-covered agencies.
7. Reconciliation status **not** materially associated with registered return-relevant features
   (year, recency, event density).

**Material imbalance** = |SMD| > 0.20 OR reconciliation-rate gap > 10pp (governance rule).

**Sample-size heuristics** (governance, not statistical law): n < 100 → insufficient for a verdict;
100–199 → diagnostic/conditional; n ≥ 200 → potentially adjudicable, subject to strata counts.
The encouraging $≥250k rate (92.9%, n=28) is **too small to inform the threshold** and is ignored.

## Pre-declared dispositions

- **PASS** → run the lag-fragility probe **only** on the frozen, fully-eligible PIT population;
  supports a narrow claim (method usable *within* the eligible universe). Still no global lag freeze.
- **Coverage high but recency/density imbalance remains** → do **not** run the probe; current method
  inadequate → PIID-level or source-restricted research.
- **Eligible sample too small (n<100)** → `INSUFFICIENT_STRATEGY_COVERAGE_EVIDENCE`; decide between
  expanding the sample and PIID-level reconciliation.
- **Coverage fails materially (rate < 0.90)** → fork (b): **b1** PIID/transaction-level reconciliation
  (if GOVCONTRACT-001 stays strategically important) or **b2** a formally restricted scope.

## Recorded corrections / status (carried into the artifact)

- **Recency hypothesis** — "recent awards reconcile worst because USAspending has not backfilled them"
  is the **primary hypothesis**; status: **association demonstrated, not yet causally confirmed.**
  Alternatives: query-window behaviour, award aggregation semantics, identifier drift, agency-specific
  submission practices, Quiver event-capture differences. Adjudicator: the Level-B publication-cycle
  cross-check.
- **Run C** = authoritative complete rate estimate. **Run D** = `replication_diagnostic` (80%
  operational completion); it supports stability of the semantic estimate but does **not** supersede
  Run C or get pooled with it.

No change to the global lag constant or the 890k-event history is justified before this gate resolves.
