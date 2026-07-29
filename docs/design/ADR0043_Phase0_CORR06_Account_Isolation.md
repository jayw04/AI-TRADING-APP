# CORR-06 — Account Isolation (AMD-12)

| Field | Value |
|-------|-------|
| Package | CORR-06 (AMD-12; Controlling Design §6) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline gate; broker HOLD) |
| Depends on | WP0–WP4 |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Own numbered package + **exit gate** (AMD-12), sequenced after WP4 and before O1/O2
structural approval on the box:

1. **Phase-0 retry:** targeted account resolution required; **no trading or risk-state
   mutation outside account 3**.
2. **Formal canary acceptance:** **zero account-1 credential-metadata mutation**; any
   unavoidable shared read must be documented and proven side-effect-free.

## In scope

- `app/risk/loss_control/phase0_account_isolation.py` — pure authorize / audit helpers
- Hermetic tests for cross-account trade/risk mutation refuse; account-1 credential
  metadata mutation refuse; declared side-effect-free shared read allow; canary
  acceptance over an operation log
- Package doc (this file)

## Out of scope

- Wiring into live canary/churn drivers (HOLD)
- OrderRouter / broker adapters
- WP5+ dataset / estimator / O4 harness
- ENFORCE flips on accounts 1–7

## Exit criteria

- [x] This package doc checked in
- [x] Frozen retry account id = 3
- [x] Trade / risk-state mutation outside account 3 → refuse
- [x] Account-1 credential-metadata mutation → refuse (canary acceptance fail)
- [x] Undeclared or side-effecting shared read → refuse
- [x] Declared side-effect-free shared read → allow with disclosure
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_account_isolation.py`
3. `apps/backend/tests/risk/test_phase0_account_isolation.py`
