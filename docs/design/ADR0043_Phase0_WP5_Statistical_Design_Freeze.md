# WP5 — Statistical Design Freeze (AMD-02 / D2)

| Field | Value |
|-------|-------|
| Package | WP5 (AMD-02; Controlling Design §2 D2 + §3.6) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline freeze artifact + gate scorer; broker HOLD) |
| Depends on | WP0–WP4; CORR-06 |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Freeze the **statistical-design artifact** before model evaluation / sealed-set opening:

1. Planning floors (D2): pooled binding REACHABLE ≥ 59; per-symbol stratum ≥ 20;
   shadow sessions ≥ 10 — **planning floors, not automatic sufficiency**.
2. One governed replacement allowed at WP5 exit; then **locked** until unseal.
3. Every gate result reports exact one-sided Clopper–Pearson upper bound, dependency /
   clustering / effective-sample assumptions, and stratum coverage.
4. Zero critical false-reachable is **necessary but not sufficient**; bound weaker than
   frozen threshold → **INCONCLUSIVE**, not PASS.
5. Per-symbol n≥20 is a **diagnostic floor** only (zero failures in 20 does not prove 5%).

## Recorded assumptions (§3.6)

| Topic | Frozen default (provisional) |
|-------|------------------------------|
| Independence unit | Binding REACHABLE **execution plan** |
| Multiple plans / session | Count separately toward pooled n |
| Clustering | Same-session plans treated as positively dependent; report `n_eff` |
| Same-symbol repeats | Allowed; stratum coverage still required |
| Pooled weighting | Equal weight per binding REACHABLE plan |
| Effective sample size | `n_eff ≤ n_raw`; gate may use `n_eff` for bound |

## In scope

- `phase0_statistical_design.py` — floors, lock/replace-once, CP bound, O5 sample gate
- Hermetic tests (including n=59 / n=20 bound behavior)
- This package doc

## Out of scope

- Sealed dataset open/unseal (AMD-08 / later WP)
- Estimator E0–E2 (WP6)
- Live O5 canary scoring on the box
- Broker submission (HOLD)

## Exit criteria

- [x] Package doc + assumptions table
- [x] Floors 59 / 20 / 10 frozen as planning defaults
- [x] One replacement then lock
- [x] Clopper–Pearson one-sided upper bound
- [x] Bound > threshold → INCONCLUSIVE
- [x] Zero failures necessary but not sufficient for PASS
- [x] Stratum diagnostic floor documented in code/tests
- [x] No order-path imports
- [x] HOLD unchanged

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_statistical_design.py`
3. `apps/backend/tests/risk/test_phase0_statistical_design.py`
