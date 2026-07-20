# MR-002 Workstream C — SPQ-1 Phase 1 — Synthetic Implementation Qualification (submission v1.0)

**Status: submitted for review.** A deterministic, synthetic-only signal & data-production
implementation of the CLOSED SPQ-1 Phase-0 specification (census `87602e7c`, owner-rulings
`d8a9071d`, schema `49c0e550`). Qualifies implementation correctness only — no performance metric,
no real data, no vendor/broker/order-path integration. Independent of the Stage-3-frozen
`app.research.mr002.signal` module (not imported or modified).

## Package

Code: `apps/backend/app/research/mr002/spq1/` (18 modules) · Tests:
`apps/backend/tests/research/spq1/` (44 cases) · Artifacts + generator:
`docs/review/mr002/spq1/phase1/`.

Responsibilities separated per §1: `refusals` · `identities` · `constants` · `calendar` · `returns`
· `stock_regression` · `sector_factor` · `residuals` · `normalization` · `sector_pit` ·
`security_identity` · `eligibility` · `liquidity` · `models` · `execution_enrichment` ·
`publication` · `producer`. No signal math in strategy templates / OrderRouter / risk / UI / broker
adapters / Increment-3 modules.

## What it implements (all closed Phase-0 rules)

- **Registered solver, preregistered (§5/§6, SIG-10):** `numpy.linalg.lstsq` (LAPACK gelsd / SVD,
  float64), rank tolerance `rcond = 1e-10`, intercept, no regularization/ridge/pseudodata/factor
  dropping; rank-deficient design → `INTEGRITY_STOP:OLS_DESIGN_SINGULAR`.
- **Two-stage regression:** Step-1 PIT-recursive sector factor `u_sector`; Step-2 day-t residual
  from t−1 coefficients; emitted `beta = β̂_m` (market coefficient of the same regression).
- **R5 + single-pass z/σ (SIG-14/16/17):** 5 consecutive residuals; one deterministic pass over the
  60 overlapping R5 ending t−1 (current R5 excluded); z and σ share one normalization-window and one
  computation-record identity.
- **Warm-up boundary (SIG-32 / OWNER-A):** encoded exactly as **125 return / 126 price**; one
  session too early → ineligible (no approximate-day logic).
- **Missing-input taxonomy (Correction 2):** the four dispositions are distinct and cannot collapse;
  `RETURN_INPUT_MISSING` is retired non-emittable (asserts if raised).
- **PIT sector / security identity (SIG-18/19/28/29):** latest accepted record ≤ close t;
  same-timestamp → registered supersession, else conflict stop; successor does not inherit
  predecessor history unless the governed lineage authorizes it.
- **Eligibility (SIG-20/23 / Correction 3):** fixed precedence 1..6; `decision_eligibility_status`
  carries no z-threshold / percentile / gap filter; each outcome carries rule_id / observed_value /
  threshold / source_identity / availability_timestamp / decision_cutoff / precedence_rank; no fact
  published after close t is used.
- **ADV (SIG-25 / OWNER-B):** MEDIAN of raw close × raw volume; 20-session median =
  `trailing_adv_dollars`, 60-session median = universe/liquidity screen; exactly-N, ending t−1.
- **Decision/execution seam (SIG-27):** `SignalDecisionRecord` structurally rejects
  `official_next_open_price` / `actual_execution_session` / `gap_filter_result` /
  `execution_admissibility_status` / unknown keys → `INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED`;
  `ExecutionEnrichedCandidateRecord` binds the decision record by canonical embedding + SHA-256 and
  appends only t+1 execution facts; `verify_decision_unchanged` proves no mutation.
- **Immutable publication (§14):** deterministically ordered, canonicalized, SHA-256-bound, atomic,
  non-overwriting, fail-closed on partial output; no S3 / DB / broker adapter.

## Qualification results

| item | result |
|---|---|
| SPQ-1 Phase-1 tests | **44 passed** (`apps/backend/tests/research/spq1`) |
| branch coverage (spq1 package) | **96%** |
| ruff | clean |
| mypy (repo config) | clean (18 source files) |
| evaluator + Increment 1–3 + OQ-1 suites | **152 passed** (unchanged) |
| Increment-3 accepted output hash | `42c5cee0…` **unchanged** |
| deterministic output SHA-256 | `c9ebd7f9c88a7d9c73ca391245f0b4305ffe721fdbf13731271d003aa8d40d6f` (stable across repeat runs) |
| Stage-3 `signal.py` imported/modified | no |

Every emittable refusal code (17) is reachable **only** from its governed condition (see
`RefusalCoverage`); the deprecated code is proven never-emittable; no real-data / network /
order-path import exists (scanned).

## Artifacts (this directory)

`MR002_SPQ1_Phase1_ImplementationManifest_v1.0.json` (module hashes, solver identity, constants,
bound identities) · `RuleTraceability_v1.0.json` (SIG rule → impl → tests → outputs → refusals) ·
`RefusalCoverage_v1.0.json` · `DeterminismReport_v1.0.json` · `QualificationReport_v1.0.json` ·
`PublicationManifest_v1.0.json` · this submission. Generator: `_gen_phase1_artifacts.py`.

## Boundary held

No development / validation / OOS / vendor / broker data opened; no performance, Sharpe, or DSR
computed; no parameter tuned; no Increment-3 or OQ-1 modification; no EC2/ECS, scheduling, paper
trading, or production. Commit / tree / parent SHAs, changed-file list, and a clean-tree
confirmation accompany this submission.
