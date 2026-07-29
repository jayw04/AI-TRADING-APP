# WP8 — Canonical Loss-Accounting Formula (AMD-18)

| Field | Value |
|-------|-------|
| Package | WP8 (AMD-18; Sections 4.3 / 7 / 8.1 Cost / Appendix B) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline formula + O2 reconciliation; broker HOLD) |
| Depends on | WP2/WP6/WP7 loss sign conventions |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

One **authoritative** loss formula shared by the model, reachability, loss-control,
replay, and terminal adjudication — so feasibility and control state cannot silently
diverge. Includes an **O2 reconciliation test**: model-computed vs control-engine-computed
loss on identical inputs must match.

## Frozen Phase-0 policy

| Topic | Frozen rule |
|-------|-------------|
| Fill-to-fill realized P&L | Σ (sell proceeds − buy cost) per matched fill pair / FIFO legs |
| Commissions | Subtracted from realized (increase loss / decrease gain) |
| Exchange / regulatory fees | Subtracted (same sign convention) |
| Rebates | Added (reduce loss) |
| Inter-leg unrealized movement | **Does not count** toward canonical round-trip loss |
| Baseline for control day-change | Prefer session / broker equity baseline (provenance elsewhere); model round-trip uses **realized-only** |
| Partial fills | Prorate notional; open residual tracked explicitly |
| Settlement timing | **Trade date** (not settlement date) for Phase-0 |
| Rounding | Quantize to **0.01** after each monetary aggregate |
| Corporate actions | If flagged on a leg → **refuse** canonical compute (no silent adjust) |
| Residual fractional positions | Included at provided mark; `has_residual_fractional=True` |

Canonical quantity for reachability remains non-negative
`round_trip_loss_amount` = `max(0, −realized_net)` when expressing loss magnitude.

## In scope

- `phase0_loss_accounting.py` — policy, compute, reconcile
- Hermetic tests including model↔control mismatch detection
- This package doc

## Out of scope

- Wiring into live `daily_loss_basis` / OrderRouter
- AMD-19 quote provenance (WP9)
- Broker submission (HOLD)

## Exit criteria

- [x] Package doc with frozen policy table
- [x] Single compute path for model and control
- [x] Reconciliation helper (match / mismatch)
- [x] Corporate-action refuse; partial-fill residual tracked
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_loss_accounting.py`
3. `apps/backend/tests/risk/test_phase0_loss_accounting.py`
