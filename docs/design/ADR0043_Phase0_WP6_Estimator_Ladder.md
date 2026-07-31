# WP6 — Estimator Objective & Graduation Ladder (AMD-03)

| Field | Value |
|-------|-------|
| Package | WP6 (AMD-03; Section 4.3) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline estimator ladder; broker HOLD) |
| Depends on | WP5 statistical-design freeze |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Governing objective

> Estimate a **conservative executable-loss bound** with demonstrated out-of-sample
> coverage. Model complexity must be justified by sample size and calibration performance.

Canonical quantity remains non-negative `round_trip_loss_amount` (AMD-13): the
**conservative minimum supported loss amount**.

## Ladder

| Level | Role |
|-------|------|
| **E0** (default) | Distribution-free **empirical lower-tail quantile** of realized non-negative loss per stratum. Governed default quantile = **0.10**. Below stratum minimum n → `INDETERMINATE`. |
| **E1** | E0 plus **monotone** quantity/notional adjustment; rule-based envelopes and broker executable-price bounds permitted. |
| **E2** | Conformal / bootstrap lower bound / bounded regression — only after frozen n threshold and OOS coverage **no worse than E0** on identical splits. |

Active level is recorded on every estimate. **Graduation is a governed decision, never automatic.**

## In scope

- `phase0_estimator.py` — E0/E1/E2 estimate + graduation gate
- Hermetic tests (quantile direction, stratum under-n, monotone E1, blocked auto-E2)
- This package doc

## Out of scope

- Training on sealed datasets / unseal (AMD-08)
- Live O5 wiring, broker submission (HOLD)
- WP7+ replay / Option C harness

## Exit criteria

- [x] Package doc with quantile direction stated
- [x] E0 lower-tail quantile (default 0.10); under-n → INDETERMINATE
- [x] E1 monotone size adjustment
- [x] E2 blocked unless governed graduation + n + OOS ≥ E0
- [x] Active level on every estimate package
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_estimator.py`
3. `apps/backend/tests/risk/test_phase0_estimator.py`
