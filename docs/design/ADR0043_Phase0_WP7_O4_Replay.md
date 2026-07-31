# WP7 — Gate O4 Split: Decision-Time vs Forensic Replay (AMD-17 / D1)

| Field | Value |
|-------|-------|
| Package | WP7 (AMD-17; Gate O4; owner D1) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` §2 D1 |
| Status | **COMPLETE** (offline replay harness; broker HOLD) |
| Depends on | WP2 reachability; WP5/WP6 contracts |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Enforce the O4 split so decision-time and forensic evidence **are never mixed**:

| Gate | Evidence | Expected verdict |
|------|----------|------------------|
| **O4-A** | Only evidence available **before** first broker submission | `INDETERMINATE` + `INSUFFICIENT_EXECUTION_COST` (or `MODEL_UNAVAILABLE` if model absent) |
| **O4-B** | Complete terminal evidence including fills | `UNREACHABLE_WITHIN_CAPS` |

Safety property O4-A must prove: with only the evidence that existed, the corrected system
**refuses to trade**. INDETERMINATE is that refusal — not a back-door UNREACHABLE from Tier D.

Both replays preserve **original instrument termination** separately from counterfactual
adjudication. **Both O4-A and O4-B must pass** for Gate O4.

## In scope

- `phase0_o4_replay.py` — evidence bundles, mix detection, O4-A/O4-B runners, combined gate
- Hermetic tests (look-ahead refuse; expected verdicts; both-required)
- This package doc

## Out of scope

- Live broker replay against account 3
- AMD-18 loss-accounting formula (WP8 candidate)
- Sealed dataset open (AMD-08)
- Formal canary (HOLD)

## Exit criteria

- [x] Package doc
- [x] Mixing decision-time + forensic evidence → refuse
- [x] O4-A expected INDETERMINATE (+ reason)
- [x] O4-B expected UNREACHABLE_WITHIN_CAPS
- [x] Combined gate requires both PASS
- [x] Original termination preserved separately from counterfactual
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_o4_replay.py`
3. `apps/backend/tests/risk/test_phase0_o4_replay.py`
