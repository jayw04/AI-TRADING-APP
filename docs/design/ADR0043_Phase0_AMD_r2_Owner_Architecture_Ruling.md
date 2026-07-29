# Owner Architecture Review Ruling

| Field | Value |
|-------|-------|
| Document | ADR0043-PH0-CORR-001-AMD r2 |
| Companion review | `docs/design/design-review.md` |
| Approval scope | Architecture Review — Approval Sequence Step 1 |
| Decision | **APPROVED WITH MODIFICATIONS** |
| Ruling date | 2026-07-29 |
| Approving role | Owner (Architecture Review) |
| Sign-off | Jay Wang, Owner — Architecture Review Step 1 approved 2026-07-29 |

---

## Ruling

The consolidated amendment architecture (AMD r2) is **approved**. The Option A / Option C governance split, immutable evidence requirements, O1–O5 validation structure, ExecutionPlan authority boundary, authorization lifecycle, non-negative loss convention, estimator graduation ladder, replay separation, account-isolation requirements, canonical loss accounting, market-data provenance, and recovery/reconciliation design are accepted.

Implementation is permitted only after the **Required Modifications Before Freeze** below are incorporated into the controlling design and re-frozen. Nothing in this ruling authorizes broker submission, formal canary execution, cap widening, a limits-digest change, reuse of prior baselines or authorizations, or modification of the July 24 historical evidence chain.

| Posture | Status |
|---------|--------|
| Architecture review step 1 | APPROVED WITH AMENDMENTS |
| Phase-0 broker submission | **HOLD** |
| Formal canary | **HOLD** |
| July 24 limits digest | Unchanged |

---

## D1 Adjudication — ACCEPT

**O4-A** shall be a strict decision-time replay using only evidence available before the first broker submission. Its expected verdict is `INDETERMINATE`, normally with reason `INSUFFICIENT_EXECUTION_COST` (use `MODEL_UNAVAILABLE` only when the model artifact or runtime is actually absent).

**O4-B** shall use the complete forensic evidence and must produce `UNREACHABLE_WITHIN_CAPS`.

Decision-time and forensic evidence shall not be mixed. Neither test may substitute for the other.

---

## D2 Adjudication — ACCEPT WITH MODIFICATION

Provisional minimums of **59** pooled binding REACHABLE plans, **20** observations per intended-symbol stratum, and **10** shadow sessions are frozen as **planning floors**, not automatic sufficiency guarantees.

They may be replaced **once** through a documented statistical-design decision at **WP5 exit**, before model evaluation and sealed-set opening. Thereafter, they are frozen.

Every result must report the exact one-sided Clopper–Pearson upper bound, dependency / clustering / effective-sample assumptions, and achieved per-stratum coverage. The n ≥ 20 per-symbol floor is diagnostic only and is not by itself sufficient to demonstrate a 5% upper failure bound.

---

## Required Modifications Before Freeze

1. Define every binding REACHABLE plan that fails to attain **100%** of the remaining target within frozen caps as a false reachable. Retain the below-80% **CRITICAL** severity classification, but establish a frozen acceptance rule for 80%–below-100% **MARGINAL** cases (preferably zero for the initial sealed validation).
2. Replace the original execution-evidence hierarchy so paper fills cannot remain simultaneously classified as Tier A and Tier B; define whether current Alpaca paper-account fills count as real broker fills or paper fills.
3. Clarify authorization expiry after partial execution: expiry must block new risk-increasing activity but must not prevent governed risk-reducing completion or emergency flattening (consistent with ADR-0042 reduction-only behavior).
4. Clarify that fresh quotes and broker state may be read for safety checks but may not extend, expand, or regenerate the frozen plan under the same authorization.
5. Promote checkpoint integrity and tamper detection (**AMD-07**) to **blocking** status before any Phase-0 retry.
6. Record statistical independence, clustering, and effective-sample assumptions in the WP5 statistical-design artifact.

---

## Continuing Hold

Phase-0 broker submission and the formal canary remain on **HOLD** until the amended design is integrated, frozen, implemented, deployed through governance, and all applicable approval gates pass.

After the modifications above are incorporated, AMD r2 (as amended by this ruling) is the controlling architecture decision for implementation.
