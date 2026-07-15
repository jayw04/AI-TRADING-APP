# GOVCONTRACT-001 — Disclosure-Lag Calibration: Disposition v1.0

**Date:** 2026-07-15
**Owner disposition:** accepted (this document records it verbatim in intent).
**PR:** #434 (`feat/govcontract-lag-calibration`).
**Primary artifact:** `data/govcontract_lag_calibration_runC.json` (`results_hash 805a412c…`).

---

## 1. What this calibration is (and is not)

It estimates a **USAspending reconciliation-based availability PROXY under imperfect
award-level matching** — *not* true first-public-disclosure lag. The purpose was to
pressure-test the 21-day `DISCLOSURE_LAG_DAYS` constant used in the GOVCONTRACT-001
pre-registration.

The load-bearing methodological result is **not** the 56-day p90. It is that the original
**37%** reconciliation rate was **operationally contaminated** — HTTP 429/5xx/timeout
transport failures were being counted as data-quality non-matches — and that after client
hardening the **defensible semantic reconciliation rate is 75.3% with 100% operational
completeness**. An infrastructure defect must never masquerade as a data-quality finding;
the new outcome taxonomy and retry-aware client enforce that.

## 2. Run taxonomy (authoritative vs diagnostic)

| Run | Client | Role | Use |
|-----|--------|------|-----|
| A / B | pre-hardening (`raise_for_status`, no retry) | `diagnostic_contaminated` | **failure-mode evidence only** |
| **C** | hardened (taxonomy + retry + adaptive limiter, seed 42, n=1000) | **`primary_representative`** | **authoritative calibration** |

Runs A/B **must never enter any pooled estimate.** They are retained as evidence that the
contamination was real and material (37% → 75.3%).

## 3. Run C result (authoritative)

- recipient reconciliation **75.3%**, 95% CI **[72.6%, 77.9%]**
- operational completeness **100.0%** (0 operational failures; outcomes RECONCILED 697 / VALID_NON_RECONCILIATION 247 / AMBIGUOUS_CANDIDATE 56)
- `reconciliation_lag_proxy_days` **p90 = 56**, 95% CI **[52, 59]**  (median 16, p75 40, p95 90)
- material year-based missingness (2018 reconciled share 0.79 → **2023 only 0.26**)

### Proxy policy status (frozen record)

```
reconciliation_lag_proxy_days p90 = 56
status        = descriptive_only
scope         = reconciled_subpopulation
policy_status = not_frozen
```

**`DISCLOSURE_LAG_DAYS` is NOT changed. The 890k events are NOT re-derived.** At 75.3% the
procedure does not support a broad-population claim; the proxy is estimated on a *selected*
reconciled subset and the missing 24.7% is too large to ignore without a missingness result.

## 4. Gate: differentiated component outcomes

A single undifferentiated FAIL under-reports what happened. The operational hardening
**succeeded**; the research-policy gate **correctly held FAIL**.

| Component | Status |
|-----------|--------|
| Operational completeness | **PASS** |
| Recipient reconciliation quality | **CONDITIONAL** (below broad-coverage 0.90 threshold) |
| Lag proxy computability (reconciled subset) | **PASS** |
| Missingness validity | **PENDING** |
| True-disclosure interpretation | **FAIL** |
| Global lag-policy freeze | **FAIL** |

The process behaved correctly: the infrastructure defect was fixed, the corrected result was
**materially less favorable** than the pilot, and the gate preserved that unfavorable evidence
rather than tuning it away.

## 5. Sensitivity / exceedance grid

Updated to include the measured proxy p90 alongside the conventional values:

```
21, 27, 30, 45, 56, 60   (+ bootstrap p90 CI upper endpoint IF materially above 60)
```

For Run C the p90 CI upper is **59** (not above 60), so **no extra grid point is added**. The
grid therefore spans: legacy assumption (21), prior pilot estimates (27/30), conventional
conservative values (45/60), and the representative proxy p90 (56).

## 6. Next steps (decision-gating analyses — do these before any lag decision)

### 6.1 Missingness & strategy-coverage analysis  *(tool built: `scripts/analyze_govcontract_missingness.py`)*

The Run C artifact holds **aggregates only**; the additional cuts require a re-run that
persists per-event reconciliation rows (now supported via `--events-out`, with full provenance:
`recipient_raw/_normalized`, `agency_raw/_normalized`, `award_amount`, `recency_bucket`,
`event_density`, `name_quality`, `candidate_count`, `failure_reason`, `source_request_key`,
`source_snapshot_or_retrieval_time`, `matcher_version`, `sample_event_id/_seed` — enough to
reproduce every cut without another source call). The analyzer compares reconciled vs
unreconciled across: **year, agency, award size, recipient-name quality, event recency, event
density** — reporting, per the disposition:

- categorical: absolute reconciliation-rate pp gaps **and** a global association test (chi² +
  Cramér's V), not p-values alone;
- continuous (amount, event density, candidate count): **standardized mean differences** + KS
  distributional comparison;
- `missingness_model_performance`: a multivariate logistic CV-AUC (AUC≈0.5 ⇒ missingness
  ~ignorable; high AUC ⇒ structured/MNAR).

**Material imbalance** is the pre-declared governance rule **|SMD| > 0.20 OR rate gap > 10pp**
(a rule, not proof smaller differences are harmless).

The decisive metric is **`strategy_eligible_reconciliation_rate`** — reserved and returned
**null** until the full PIT + 0.25%-of-mktcap join is applied. The computable down-payment is
now named **`material_award_reconciliation_rate_ge_250k`** ($-floor only), deliberately renamed
from the earlier provisional label so it is never mistaken for the fully-joined figure. A 75.3%
broad rate may still be usable if the eligible universe reconciles much better and failures
concentrate outside it — unusable if failure correlates with award size / agency / recency.

### 6.2 Lag-fragility probe  *(aggregator built: `scripts/aggregate_lag_fragility.py`)*

Re-run the identical study at each grid lag; the aggregator collapses the per-lag runs into
**one** comparison artifact aligned by lag (effect size, CI, n, survives) — never six
disconnected reports — records **un-run lags explicitly** (no silent pass), and classifies:

- Robust through 56–60d → `lag_not_decision_critical` (conclusion independent of calibration).
- Survives 30d but fails 45–56d → `pit_decision_critical` (PIT assumption load-bearing).
- Only survives 21–27d → `leakage_concern`.
- Fails at every lag → `economic_rejection_reachable` — recorded as an **economic** rejection,
  **separate** from the calibration-policy FAIL (distinct findings, never collapsed).

### 6.3 Then decide among

subset-valid research · PIID-level re-architecture · economic rejection.

---

## Disposition summary

1. Run C accepted as the authoritative calibration artifact.
2. PR #434 accepted as methodological hardening.
3. 56-day p90 retained as a **reconciled-subpopulation** proxy estimate (`descriptive_only`).
4. **No global lag frozen.**
5. Proceed next to: (1) missingness & strategy-coverage; (2) lag-fragility probe including 56d;
   (3) decision.
