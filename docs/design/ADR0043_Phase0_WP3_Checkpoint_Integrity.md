# WP3 — Checkpoint Integrity & Binding-Tuple Completion

| Field | Value |
|-------|-------|
| Package | WP3 (CORR-07 / AMD-07; Controlling Design §3.5) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline integrity; broker HOLD) |
| Depends on | WP0 seal; WP1 contracts; WP2 verdict vocabulary |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Make checkpoint acceptance **fail closed** before any Phase-0 retry treats a file as
authoritative evidence (owner freeze: AMD-07 is **BLOCKING**):

1. Binding tuple includes **`loss_control_state_version`** (and the other frozen fields).
2. Every sealed checkpoint carries a **content hash**; optional **HMAC-SHA256** when a key
   is configured.
3. Tampered or corrupted contents with a valid filename → **refused** at load.
4. Cross-session reuse of a sealed checkpoint under a different `session_id` → refused.

## In scope

- `app/risk/loss_control/phase0_checkpoint.py` — pure seal / verify / load helpers
- Hermetic unit tests including `tampered contents, valid filename → refused`
- Package doc (this file)

## Out of scope

- Wiring into live `adr0043_canary_lib.Checkpoint` / churn driver (deferred until broker
  HOLD lifts and WP4 crash-consistency contracts exist)
- OrderRouter, broker APIs, ENFORCE flips, account 1–7 mutation
- WP4 terminal packaging / DRIVER_RECOVERY_REQUIRED (AMD-20)

## Exit criteria

- [x] This package doc checked in
- [x] Binding tuple requires `loss_control_state_version`
- [x] Content hash always present; HMAC when key supplied
- [x] Tampered contents + valid filename → refuse
- [x] Incomplete binding / missing integrity → refuse
- [x] Cross-session reuse → refuse
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_checkpoint.py`
3. `apps/backend/tests/risk/test_phase0_checkpoint.py`
