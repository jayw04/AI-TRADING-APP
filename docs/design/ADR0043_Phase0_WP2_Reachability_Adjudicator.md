# WP2 — Decision Adjudicator / Reachability Verdict Engine

| Field | Value |
|-------|-------|
| Package | WP2 (Section 4.1 adjudicator; AMD-13/14; Controlling Design §3.2/§4) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline adjudicator; broker HOLD) |
| Depends on | WP0 seal; WP1 contracts |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Why this is WP2

AMD r2 names WP1 (ExecutionPlan), WP3 (checkpoints), WP4 (crash consistency), WP5–WP9,
but not WP2 explicitly. Sequenced after plan authority and before checkpoint integrity,
WP2 is the **reachability / decision-adjudicator** that produces v1.1 verdicts + reason
codes from evidence — the gate-facing layer that WP1 authorizations bind to.

## Goal

Replace / supersede the diagnostic displayed-spread assessor’s **binding** semantics with
Controlling Design v1.1 rules:

- Canonical verdicts: `REACHABLE` / `UNREACHABLE_WITHIN_CAPS` / `INDETERMINATE`
- Mandatory reason codes
- Non-negative loss amounts
- Evidence-tier gating: **Tier D (displayed spread) never yields a binding verdict**
- Preserve the operational “do not widen caps” diagnostic when projection shows
  infeasibility (non-binding `UNREACHABLE_WITHIN_CAPS`)

## In scope

- `app/risk/loss_control/phase0_reachability.py` — pure adjudicator
- Thin compatibility wrapper in `scripts/adr0043_reachability.py`
- Unit tests for Tier-D non-binding REACHABLE → INDETERMINATE; projection UNREACHABLE;
  unknown baseline; vacuous quotes; legacy alias

## Out of scope

- Broker quotes live fetch, OrderRouter, canary, WP3 checkpoints
- Estimator E0–E2 graduation (WP6)
- O4 replay harness (WP7)

## Exit criteria

- [x] This package doc checked in
- [x] Adjudicator emits reason codes + evidence tier
- [x] Tier D cannot produce `binding=True`
- [x] Tier D “would-be REACHABLE” → `INDETERMINATE` + `INSUFFICIENT_EXECUTION_COST`
- [x] Legacy script tests updated / still hermetic
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_reachability.py`
3. `apps/backend/scripts/adr0043_reachability.py` (thin façade)
4. `apps/backend/tests/scripts/test_adr0043_reachability.py`
