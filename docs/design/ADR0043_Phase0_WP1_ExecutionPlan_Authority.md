# WP1 — ExecutionPlan Authority & Authorization Lifecycle

| Field | Value |
|-------|-------|
| Package | WP1 (AMD-15, AMD-16; Gate O1) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` §5 |
| Status | **COMPLETE** (offline Gate O1 matrix green; broker HOLD) |
| Depends on | WP0 seal complete |
| Broker submission | **HOLD** (this package is offline-only) |
| Created | 2026-07-29 |

## Goal

Make reachability an **enforceable authorization contract**: once a plan is authorized,
the driver may only execute that frozen plan (or reduce/terminate for safety). Enforce
the authorization lifecycle and owner-adjudicated expiry / fresh-data rules **without**
submitting broker orders.

## In scope

- Immutable `ExecutionPlan` + `plan_hash` (already in `phase0_contracts.py`; extend as needed).
- Authorization record lifecycle: `ISSUED → CLAIMED → ACTIVE → CONSUMED` (+ terminals).
- Refusal rules from AMD-15/16 and owner freeze mods:
  - no quantity increase, symbol substitution, route/order-type change, expiry extension,
    or plan regeneration under the same authorization;
  - fresh quotes/broker/risk reads allowed for safety only;
  - expiry before submission → refuse; after partial fill → risk-reducing / flatten only;
  - no second independent run after any broker submission under the same authorization.
- Offline Gate O1 test matrix (pure unit tests).

## Out of scope

- Wiring into `OrderRouter` / live churn driver / canary.
- Broker API calls, ENFORCE flips, account 1–7 mutations.
- WP2+ (estimator, dataset seal, Option C threshold tests, etc.).

## Exit criteria

- [x] WP1 package doc (this file) checked in.
- [x] `phase0_authority` module enforces lifecycle + mutation refusals.
- [x] Unit tests cover: reuse after simulated broker submission → refused; reuse after
      local refusal without governed retry → refused; expiry mid-plan → risk-increasing
      blocked, risk-reducing allowed; fresh data cannot extend/expand plan; hash mismatch
      → refuse.
- [x] No import of order-path / broker adapter modules from the authority package
      (structural grep or import test).
- [x] HOLD posture unchanged.

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_authority.py`
3. `apps/backend/tests/risk/test_phase0_authority.py`
