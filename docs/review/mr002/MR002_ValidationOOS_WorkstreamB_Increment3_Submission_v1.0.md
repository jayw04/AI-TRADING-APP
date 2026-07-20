# MR-002 Workstream B — Increment 3 submission (synthetic portfolio construction → metrics replay)

**Status: submitted for review.** Implements the authorized Increment 3 (build-plan verdict
2026-07-20) with all four mandatory clarifications incorporated. **Synthetic-only; reads no real
dataset; computes no residual/z/sigma; validation/OOS never opened; no performance interpretation.**
Binds the implementation-binding registry `edb7ff22` + Phase-0 resolution `860c8cde`.

## Modules (`docs/review/mr002/evaluator/`)

Eight new modules (identity / candidates / construction / state / exposure / replay / nav / pipeline);
Increment-1 (`report`, `metrics`) and Increment-2 (`costmodel`, `execution`) reused. Increment-2 was
**refactored** to expose the shared `preview_entry_fill` clip primitive (behavior-preserving —
Increment-2 still 35/35, ledger data unchanged) so Increment 3 never reimplements the ADV/NAV/cost
formulas (clarification #4).

- **`portfolio_identity`** — hash-binds registry + resolution + governing sources; `NAV_IDENTITY_MISMATCH` (RC-4).
- **`candidates`** — strict `SyntheticCandidate`; `registered_sigma_resid` fail-closed (`CANDIDATE_SIGMA_RESID_INVALID`); evidence-only inverse cross-checked at frozen `rel_tol 1e-12` (`CANDIDATE_INVERSE_VOL_MISMATCH`); A/B/C `configuration_id`; `CANDIDATE_EXECUTION_INPUT_MISMATCH` (clarification #2).
- **`construction`** — side-eligible 10% selection + |z|≥Z_entry; inverse-vol weights normalized **once** within side; entry dollar-neutral sizing; position-cap **clip→cash**; sector→beta removal cascade with smallest-|z| + signal-age/permanent-id tie-breaks and **no upward renormalization** (freed→cash).
- **`portfolio_state`** — immutable `HeldPosition` (now carrying `entry_registered_signal_value` + `originating_candidate_id` + `eligibility_evidence_identity`, clarification #1) / `PendingExit` (dedup) / cash / one-position occupancy.
- **`exposure`** — three states RAW/INTENDED/REALIZED; per-name/gross/net/sector/beta; empty-portfolio `N_A_EMPTY_PORTFOLIO` (no div-by-zero/inf).
- **`replay`** — full-session **PREVIEW → VERIFY → COMMIT** (clarification #3): due exits → provisional post-exit state → construct entries against it → preview entries → verify complete realized session → commit atomically. Held positions are grandfathered (PR-16); a hard-cap breach fails closed **only when caused by clipping** (present in REALIZED but not INTENDED), with the distinct `REALIZED_SINGLE_NAME/GROSS/SECTOR/BETA_CONSTRAINT` codes. Net-dollar drift → `DriftRepairInstruction` (not a stop).
- **`nav`** — official open-to-open valuation; `HELD_POSITION_OPEN_MARK_MISSING`; daily return series.
- **`pipeline`** — orchestration + Increment-1 metric handoff (the **portfolio** return series) + canonical exact-float report.

## Qualification

- **Increment 3: 27 tests; full evaluator suite: 121 passed** (Inc 1: 59, Inc 2: 35, Inc 3: 27); **ruff clean**.
- Maps to `MR002_Increment3_QualificationMatrix_v1.0` (T3-01..T3-33; consolidated). Independently
  derived expectations. Notable adversarial coverage: real asymmetric-ADV clip → realized
  sector breach (fail-closed); realized beta breach; net-drift repair (commit, not stop); atomicity
  (refused session leaves cash/positions/pending/ledger/NAV byte-unchanged); realized single-name/gross
  via adversarial seam; no-duplicate-execution-formula scan; no-real-data-import scan.
- **Determinism:** replay report byte-identical across runs; `output_hash` =
  `53ffca3d2e40a8a024bf8c20ad3c8e3bc264662de80d1fb49bfa2ceccdb18d54`; self-hash verifies; the metric
  input is proven to be the portfolio return series (`metric_input_is_portfolio_series = true`); 4/4
  synthetic sessions committed; `synthetic_fixture_only = true`, `validation_data_read = false`.
- Evidence: `MR002_Increment3_ReplayReport.json` (`37032cb4…`), `MR002_Increment3_Qualification.json`
  (`3b6aca76…`), `MR002_Increment3_TestLog.txt`; dependency lock reused from Increment 1 (`17a73ede…`).

## A finding surfaced during the build

The frozen sector-**net** cap (5% of gross) enforces **sector-neutrality** — a valid book pairs long
and short within each sector; combined with the 10% side-selection, the smallest viable book is
~10 names across ≥5 sectors. This is the strategy's defining property, not a defect; it shaped the
synthetic fixtures (sub-functions unit-tested directly; integration uses a 50/50 sector-paired pool).

## Boundary

Validation/OOS **SEALED AND UNREAD**. **NOT authorized / not implemented:** real residual/z/sigma,
PIT sector reconstruction, real vendor/sealed adapters, validation/OOS access, development
performance, performance interpretation, production promotion. Stops at the synthetic
portfolio-to-metrics replay + qualification evidence.
