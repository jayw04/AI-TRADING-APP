# Review — momentum-daily cold-start repair

Review package for the momentum-daily (id=11, acct 4 / user 4) cold-start defect and its governed repair.
Branch: `fix/momentum-daily-cold-start-seed` (off `origin/main`, contains PR #435 / `f8f079c`).

## Status (2026-07-20)
- **Book state:** PAUSED (`AWAITING_COLD_START_FIX`), status IDLE, dispatch job removed. Reactivation gated.
- **Plan:** v1.0 approved; classification **ratified 2026-07-20**.
- **Classification:** **Case C-structural → Case A-behavioral** (NOT Case B) — the Stage 2-4 harness reimplemented selection and seeded on day 1, so validated inception was day-one deployment; the live ~10-session cold-start delay is a divergence, and `initial_seed` **restores conformance** (adopt day-1; do not preserve the delay). RATIFIED.
- **Drift-audit requirement:** because validation ran a *reimplementation* the template warns "must not drift," the §8 equivalence work must drive the **actual live `MomentumDaily` class** through history and compare **through `_evaluate`** at every decision seam (zero tolerance for semantic mismatches). A validation-production equivalence invariant is folded into ADR 0044 + a second CI invariant.
- **Next:** step 5 — Policy M (≥0.60) vs Policy H (=0.98) inception-threshold analysis → lock threshold → implement.

## Contents
- `momentum_daily_coldstart_repair_plan_v1.0.md` — implementation plan (lifecycle state machine, idempotency/crash-recovery, `initial_seed` gating, migration, evidence-clock split, ADR 0044, fail-closed hold enforcement, drift audit, reactivation checklist, validation matrix, ratified decisions).
- `harness_inception_reconstruction_findings_v1.0.md` — step-3 gate: evidence-cited reconstruction of the Stage 2-4 harness inception semantics (basis for the classification).
- `acct4_prepause_evidence_20260720T223216Z.json` — immutable pre-pause containment snapshot; **canonical SHA-256 `8fa766f39e289c9925e7295f434b7887abd4d91ce1d802eb21b30d626fd8c054`** (recorded in `strategy_state.operational_hold.evidence_snapshot_sha256`).

## Key governed facts
- Deactivation: audited via `POST /strategies/11/stop` (actor user 4), audit `STRATEGY_UNREGISTERED` id=5733, run 605 closed.
- Deployed image at pause: `sha256:064490a5…`.
- Reactivation requirements: approved plan · lifecycle migration verified · acceptance suite passed · inception-equivalence rerun adjudicated · production deployment verified.
