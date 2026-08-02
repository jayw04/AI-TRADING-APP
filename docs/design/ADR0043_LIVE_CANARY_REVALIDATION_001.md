# ADR0043-LIVE-CANARY-REVALIDATION-001

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-REVALIDATION-001 |
| Status | **APPROVED / EFFECTIVE** for design and planning artifacts only — operational HOLD unchanged |
| Date | 2026-07-31 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 **v1.0** |
| Prior programs | D-BOX / evidence-gap campaigns **CLOSED** |
| Prior canary contract | `ADR0043_Canary_Manifest_v1.1` (2026-07-21) — historical A1–A5 reference only; **not** the execution contract |
| Broker / Phase 0 / live canary | **HOLD** — this document does not authorize them |

## 1. Purpose

Re-open the ADR-0043 live canary as a **new governed program**. Prior D-BOX and evidence-gap programs are closed, and the July 21 canary manifest predates the baseline-lineage findings. A fresh prospective evidence population is required before ADR-0043 can be considered operationally validated.

## 2. Confirmed bindings

| Binding | Confirmation |
|---------|--------------|
| Objective | Still **A1–A5** exactly as in IMPL-PLAN v1.0 §1.3 |
| Broker identity | **PA34USW0Q8UO** |
| Account role | Dedicated permanent risk-engine **verification** account |
| Protected starting leg | **MSFT:19** (runtime-verified; no manufacture of missing legs) |
| Workbench IDs | Resolved later in WS5; **not assumed** (`account_id=3` is not authoritative) |
| Evidence population | **New prospective** run only |
| Historical D-BOX / EVGAP | **Do not count** as canary evidence |
| D-WIRE / broad production activation | **Not authorized** |
| Scope | **One** dedicated paper account only |
| Timed re-arm to `NORMAL` | **Outside** canary claim |
| GREEN aftermath | Cleanup/restoration may be authorized separately; **not** conversion to an ordinary strategy account |

## 3. Why revalidation (not reuse)

1. D-BOX and evidence-gap campaigns closed without producing a countersigned live canary GREEN.
2. Stage-2 inventory showed insufficient per-episode baseline lineage (`risk_session_baselines` = 0 for the account; forensic baseline missing).
3. Manifest v1.1 predates Q1 fail-closed / authoritative-baseline rulings now required by IMPL-PLAN v1.0.
4. Continuity, freeze layering (WS4A/WS5/WS6), and Start A/B separation are now governing — the old single-manifest-as-execution model is insufficient.

## 4. Program ceiling

This revalidation authorizes **design and planning artifacts only** until further owner approvals under IMPL-PLAN v1.0. It does not authorize provisioning, baseline capture, Phase 0 loss generation, A1–A5 execution, canary-specific ENFORCE activation, global flag changes, or D-WIRE.

## 5. Successor artifacts (gated)

| Artifact | Role |
|----------|------|
| `ADR0043-CANARY-BASELINE-DESIGN-001` | Authoritative baseline semantics |
| F1/F4/Q1/Q2 inventory | Canary-scoped code package scope |
| `ADR0043_Canary_Manifest_v1.2` (WS4A) | Contract freeze |
| Later freeze / Start A / Start B / Close | Execution governance |

## 6. Exit criterion

Owner approves this revalidation design.

## 7. Owner decision block

| Decision | Value |
|----------|-------|
| Approve revalidation program? | **APPROVED / EFFECTIVE** for design and planning artifacts only |
| Countersignature | (owner review 2026-07-31 — recorded via `review-comments.md`) |
| Date | 2026-07-31 |

*End of ADR0043-LIVE-CANARY-REVALIDATION-001.*
