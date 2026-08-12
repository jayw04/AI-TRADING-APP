# WP4 — Terminal Packaging Crash Consistency & Reconciliation

| Field | Value |
|-------|-------|
| Package | WP4 (CORR-04 / AMD-20; Controlling Design §6) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline contracts; broker HOLD) |
| Depends on | WP0–WP3 |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Define the **atomicity boundary** for Phase-0 terminal evidence so an interrupted run is
never forced into `DRIVER_TERMINAL` as though conclusively resolved (AMD-20):

- States: `DRIVER_RECOVERY_REQUIRED`, `DRIVER_RECONCILED`, `UNKNOWN_BROKER_OUTCOME`,
  and conclusive `DRIVER_TERMINAL` only when journal + broker truth agree.
- Evidence-completeness: a properly recorded `RECOVERY_REQUIRED` counts as **complete**;
  falsely declaring certainty is the violation.
- Terminal artifacts must be **idempotently reproducible** from the journal plus broker truth.

## Crash / atomicity cases (must fail closed or recover, never invent certainty)

1. Death before package creation
2. Death after broker submission but before local persistence
3. Package written but status update failed
4. Duplicate terminal write
5. Restart reconciliation
6. Object-store partial failure
7. Local / remote evidence disagreement

## In scope

- `app/risk/loss_control/phase0_crash_consistency.py` — pure classifier + package reproducer
- Hermetic unit tests for each atomicity case above
- Package doc (this file)

## Out of scope

- Live canary/churn wiring, OrderRouter, real object-store I/O
- WP3 path integration into production checkpoint files (separate deploy gate)
- CORR-06 account isolation; WP5+ dataset / estimator work
- Broker submission / formal canary (HOLD)

## Exit criteria

- [x] This package doc checked in
- [x] Driver reconciliation states defined and transitions fail-closed
- [x] Each AMD-20 atomicity case covered by a hermetic test
- [x] Properly recorded `DRIVER_RECOVERY_REQUIRED` → evidence complete
- [x] False `DRIVER_TERMINAL` under uncertainty → completeness violation
- [x] Duplicate terminal write idempotent
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_crash_consistency.py`
3. `apps/backend/tests/risk/test_phase0_crash_consistency.py`
