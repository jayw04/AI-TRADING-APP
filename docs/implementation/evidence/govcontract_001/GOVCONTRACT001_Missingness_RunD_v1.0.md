# GOVCONTRACT-001 — Run D + Reconciliation Missingness: Evidence v1.0

**Date:** 2026-07-15
**Run D artifact:** `data/govcontract_lag_calibration_runD.json` (`results_hash 30aadedaca9f04ef`)
**Missingness artifact:** `data/govcontract_missingness_runD.json`
**Per-event source:** `data/govcontract_events_runD.jsonl` (1000 rows, seed 42, hardened client)
**PR:** #434.

---

## 1. Run D — the events-persisting re-run (owner next-step 1)

Re-ran the calibration with `--events-out` (seed 42, n=1000, workers 4) to persist per-event
provenance for the missingness analysis. **Run D was operationally INCOMPLETE: 80% completion,
200 `NETWORK_ERROR` transport failures** (transient USAspending connection drops this evening).

Critically, the taxonomy handled this exactly as designed — the 200 failures were classified
**operational**, not counted as non-reconciliations — so the semantic findings **replicated Run C**:

| Metric | Run C (100% complete) | Run D (80% complete) |
|---|---|---|
| recipient reconciliation | 75.3% | **74.9%** CI [71.9, 77.9] |
| lag proxy p90 | 56d | **57d** CI [52, 62] |
| operational completeness | 100% | 80% (200 NETWORK_ERROR) |

Two runs with very different operational completeness producing the **same** semantic rate and
p90 is a clean confirmation that the operational/semantic split works. Run C remains the
authoritative **complete** artifact; Run D is authoritative for the **per-event missingness**
(on its 800 adjudicated rows). A fully-complete re-run would strengthen the missingness n.

## 2. Missingness & coverage — **VERDICT: MATERIAL_IMBALANCE**

The reconciled subpopulation is **not** a representative basis. Reconciliation depends on
pre-event covariates that are connected to expected returns:

| Covariate | Signal | Material? |
|---|---|---|
| **year** | reconciled share 2018=0.75 → **2024=0.15, 2025=0.39**; gap 32pp, p=2.4e-5 | **YES** |
| **recency_bucket** | gap 25pp, p=3e-4 | **YES** |
| **agency** | gap 43pp, Cramér's V 0.25, p≈0 | **YES** |
| **name_quality** | gap 27pp, p=2e-4 (poor names match worse) | YES (matching artifact) |
| **event_density** | SMD −0.78 (high-density tickers reconcile worse) | YES |
| **award_amount / size** | SMD **0.09**; size gap 11.6pp but p=0.09 | **NO** (weak) |

Honest **missingness-model CV-AUC = 0.82** (pre-event covariates only) ⇒ **structured (MNAR)
missingness**. `material_award_reconciliation_rate_ge_250k = 92.9%` but **n=28** (too small; this
is the $-floor down-payment, NOT the full `strategy_eligible_reconciliation_rate`).

### Interpretation

The dominant driver is **recency**: recent awards reconcile far worse because **USAspending has
not yet backfilled them** into the official record — not because Quiver is wrong. So the reconciled
subset **over-represents old events**, and the lag proxy is computed only on events where the
official record has already caught up (**survivorship**). Recency is exactly the return-relevant
axis (recent = tradeable), so per the pre-declared rule — *"even 75.3% is unusable if
reconciliation failure is related to award size, agency, recency, or another variable connected to
expected returns"* — **the reconciled subset is not a defensible basis for a broad-population lag
claim.** (The feared *award-size* confound is largely **absent**: SMD 0.09.)

## 3. Methodological note — target leakage caught and fixed

The first analyzer pass reported CV-AUC **0.998**. That was **target leakage**, not a real signal:
(a) `candidate_count` is **outcome-derived** (0 by construction for a non-reconciliation), and
(b) high-cardinality `agency_normalized` one-hot let logistic regression **memorise identity**.
Both were removed from the model (candidate_count → labelled diagnostic; categoricals one-hot only
when ≤12 levels — agency's association is still measured honestly by chi²/Cramér's V). The honest
AUC is **0.82**. This is the same operational-integrity discipline applied to the analysis layer:
an artifact of the method must not masquerade as a finding.

## 4. Disposition (updates the fragility-probe gate)

Per the disposition tree: **missingness is materially biased AND strategy coverage is not yet
established** (n=28 material-award subset is too small; the full PIT + mktcap join is not done).
Therefore:

- **Do NOT spend EC2 on a broad-population lag-fragility probe** — a broad verdict run over a
  recency-biased subpopulation would not be interpretable.
- **Next, choose:** (a) build the targeted **strategy-eligible** reconciliation (material universe
  + 0.25%-of-mktcap PIT join) to establish whether the *eligible* universe reconciles well enough
  to run the probe on that predeclared population; or (b) accept the recency bias as structural and
  move to **PIID-level reconciliation** or a **restricted research scope**.
- **Reinforces the v1.0 disposition:** the 56–57d proxy stays `descriptive_only` / `not_frozen`;
  the recency bias is a concrete additional reason **not** to promote it into `DISCLOSURE_LAG_DAYS`.

No change to the global lag constant or the 890k-event history is justified.
