# ADR-0043 Live Canary Revalidation — Implementation Plan

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0 |
| Status | **APPROVED AS GOVERNING IMPLEMENTATION PLAN** |
| Date | 2026-07-31 |
| Supersedes | v0.1; v0.2 |
| Review input | `docs/design/review-comments.md` (v0.2 approved with non-blocking corrections folded herein) |
| Goal | One governed live canary on Alpaca paper **PA34USW0Q8UO** → independent qualification → owner-countersigned **GREEN** → only then ADR-0043 operationally validated |
| Prior programs | D-BOX / evidence-gap campaigns **CLOSED** (not canary evidence) |
| Prior canary contract | `ADR0043_Canary_Manifest_v1.1` (2026-07-21) — **superseded for execution**; retained as historical A1–A5 reference |
| Authorization ceiling of this plan | Planning sequence + preparation of the first three deliverables only |
| Broker / Phase 0 / live canary / D-WIRE / global ENFORCE | **HOLD** until separately authorized after those deliverables are approved |

This document is the **governing implementation plan**. It does **not** authorize provisioning, authoritative baseline capture, Phase 0 orders, live canary execution, D-WIRE, or global ENFORCE.

---

## 0. Standing stop rules

1. Under this plan, proceed **only** with: `REVALIDATION-001`, `BASELINE-DESIGN-001`, and the F1/F4/Q1/Q2 inventory. No provision/trade until those are separately approved.
2. **Do not** enable globally: `session_baseline_shadow_enabled`, `session_baseline_enforcement_enabled`.
3. Use **canary-specific, freeze-bound configuration** only.
4. Historical D-BOX / EVGAP failures **do not count** as canary evidence.
5. GREEN may authorize **cleanup and restoration** of the dedicated verification account; it does **not** authorize converting it into an ordinary strategy account, D-WIRE, global ENFORCE, deployment to all strategy accounts, or deletion of canary controls.
6. The canary **must not claim** timed re-arm to `NORMAL`.
7. Do **not** convert “unknown P&L” into a fabricated measured breach.
8. A partially completed run must never be restarted under a new run ID without adjudicating the first attempt.
9. After **RED** or **INCONCLUSIVE**: do not auto-clear loss-control state; do not reset breaker/account; preserve broker + DB state until adjudication; prohibit reuse for another run; require a separate remediation decision.

---

## 1. Program objective and bindings

### 1.1 Objective

Run **one** governed ADR-0043 live canary on **PA34USW0Q8UO**, obtain countersigned **GREEN**, and only then consider ADR-0043 **operationally validated**.

### 1.2 Fixed bindings

| Binding | Value |
|---------|-------|
| Broker identity | `PA34USW0Q8UO` |
| Account role | Dedicated permanent risk-engine **verification** account |
| Protected starting leg | `MSFT:19` (runtime-verified; no manufacture) |
| Workbench IDs | Resolved in **WS5**; bound in **WS6** — do not assume `account_id=3` |
| Assertions | **A1–A5** (§1.3) |
| Scope | One dedicated paper account |
| Evidence | New prospective population only |
| Q1 | Authoritative frozen session baseline **only** for control (§3.3) |

### 1.3 Assertions A1–A5

| # | Assertion | Pass criterion |
|---|-----------|----------------|
| **A1** | `state_authoritative` | Durable state is `REDUCTION_ONLY_DAILY_LOSS` (not breaker column alone, not inferred, not breaker-origin) |
| **A2** | `verified_reduction_allowed` | Frozen risk-reducing MSFT sell **admitted**; risk-reducing qty; no new exposure; durable trail; broker/local reconciliation |
| **A3** | `new_risk_refused` | Frozen new-risk BUY **rejected** with **`LOSS_CONTROL_STOP`** (not another gate); no broker order; no reservation leak; durable rejection + audit |
| **A4** | `reached_recovery_cooldown` | Frozen recovery → parent preflight PASSED; **exactly the frozen 12-check set**, all PASS; committed `PREFLIGHT_PASS`; state `RECOVERY_COOLDOWN` |
| **A5** | `evaluator_holds` | Evaluator returns exactly **`HOLD`**; remains in cooldown; no `NORMAL` / `COOLDOWN_COMPLETE` / `INTEGRITY_STOP` / ungoverned re-arm |

### 1.4 Frozen 12-check set identity (A4)

WS4A must freeze this set (registry order from `PREFLIGHT_CHECK_REGISTRY`). Qualifier verifies **set identity**, not merely a count of 12 rows.

| # | Check name |
|---|------------|
| 1 | `state_known_and_recoverable` |
| 2 | `recovery_origin_proven` |
| 3 | `broker_reachable` |
| 4 | `broker_account_active` |
| 5 | `positions_reconcile` |
| 6 | `open_orders_reconcile` |
| 7 | `reservations_reconcile` |
| 8 | `session_baseline_valid` |
| 9 | `daily_loss_recomputed` |
| 10 | `trip_cause_classified` |
| 11 | `control_state_consistent` |
| 12 | `no_unresolved_integrity_condition` |

Also freeze: schema/registry version; required PASS evidence; duplicates invalidate; unknown extra checks invalidate. Order follows registry; prerequisite graph is load-bearing.

### 1.5 Continuity boundary and freeze sequencing

**Governing sequence (corrected):**

```text
WS5 runtime readiness
  → WS6 freeze draft / readiness / seal + owner countersignature
  → boundary-opening record
  → Start A (authoritative baseline capture + Phase 0)
  → Start B (binds Phase 0 package hash)
  → live A1–A5 → seal → qualify → close
```

**Rule:** The immutable execution continuity boundary opens **after WS6 is sealed and countersigned**, and **immediately before** Start A’s authoritative baseline capture. The freeze binds the *rule* that the boundary will open then; the actual boundary-opening timestamp and state hashes are recorded under **Start A**.

| Phase | Allowed | Prohibited |
|-------|---------|------------|
| Before WS6 seal (provision + bootstrap + WS5) | Sanctioned audited setup; readiness validation of capture tooling | Authoritative baseline capture; Phase 0 orders |
| After WS6 seal, before Start A | Nothing operational beyond recording readiness | Baseline capture; any order |
| After boundary opens (Start A onward) | Frozen Start A / Start B / canary steps only | Image/config change; DB replace/migrate; credential rebind; limit mutation; scheduler change; broker rebind; process restart (default refuse) |

**WS5 and WS6 must not retrieve or persist the authoritative session baseline.** They may validate capture tooling, broker field contract, permissions, API connectivity, schema, and freshness-calculation logic only.

**WS6 seal and countersignature do not authorize baseline capture or Phase 0 activity.** Start A remains separately required.

---

## 2. Disposition classification (predetermined)

| Disposition | Meaning |
|-------------|---------|
| **GREEN** | All A1–A5 pass; evidence complete; qualification passes |
| **RED** | Assertion conclusively false (e.g. A3 reaches broker; A5 → `NORMAL`; A3 any fill) |
| **REFUSED** | Precondition/frozen identity fails before a valid assertion sequence begins |
| **INCONCLUSIVE** | Execution began, but evidence integrity / broker / continuity prevents valid determination |

Only **GREEN** proceeds to countersignature.

### 2.1 Partial-fill defaults (exact rules frozen in WS4A / WS6)

| Case | Disposition |
|------|-------------|
| **A2** partial fill | Reconcile; evaluate against frozen **minimum qualifying reduction** quantity; else **INCONCLUSIVE** or **RED** per manifest |
| **A3** partial fill or **any** fill | **RED** — new risk reached the broker |
| **Phase 0** partial fill | Reconcile cumulative loss and frozen capacity; **do not** resubmit blindly |
| Unknown partial status | **INCONCLUSIVE** after deterministic reconciliation is exhausted |

### 2.2 Broker ambiguity stop rules

Stop / classify on: API timeout after submission; local accept / unknown broker status; duplicate `client_order_id`; contradictory local/broker fields; partial fill; market closed; external cancel; API flapping.

**Posture:** Unknown submission outcome → reconcile by deterministic identity; **never resubmit** merely because the first response timed out.

---

## 3. Workstream plan

### Workstream 1 — Revalidation program

**Deliverable:** `ADR0043-LIVE-CANARY-REVALIDATION-001`

Confirm A1–A5; `PA34USW0Q8UO`; `MSFT:19`; new prospective evidence; D-BOX not canary evidence; no D-WIRE/broad activation; one paper account; GREEN cleanup ≠ strategy conversion.

**Exit:** owner approves.

---

### Workstream 2 — Baseline design

**Deliverable:** `ADR0043-CANARY-BASELINE-DESIGN-001`

Complete **before** code changes are finalized. Must define authoritative field, timing window, hash semantics, persistence contract, adjustment posture, and fail-closed behavior.

#### Baseline source

| Option | Description |
|--------|-------------|
| **A (required default)** | First successfully persisted **broker equity** snapshot for the trading session, via approved production mechanism, **before any canary-generated order**, within frozen freshness window — do **not** call it “session-open” unless timing meets that definition |
| **B** | Prior-session broker close (only if independently deterministic) |
| **C** | Another explicitly approved broker-derived baseline (named in freeze) |

**Authoritative API field (required definition in WS2):** broker **`equity`** (Alpaca account equity). `last_equity` is **telemetry only**, not control.

**Hash semantics (required):** preserve and hash the **complete raw broker response**; separately hash the **canonical baseline projection** used by control.

**Capital adjustments:** unexplained deposit/withdrawal/broker adjustment after baseline → **REFUSED** or **INCONCLUSIVE**; must **never** be treated as trading P&L; any adjustment-aware normalization must be explicitly designed and frozen.

#### Required fields, immutability, telemetry, fail-closed

As in approved v0.2 (one authoritative baseline per account/session/design version; no in-place update; same baseline ID/hash on all control paths; residual telemetry measurement-only; surface-specific fail-closed per table below).

| Context | Response |
|---------|----------|
| Before Phase 0 loss generation | **REFUSED**; no orders |
| New-risk admission under lock | **Reject** |
| Verified reduction under lock | **Permit** |
| Recovery preflight | **FAIL** / **INCOMPLETE**; never PASS on bad basis |
| Outside canary | Governed separately |
| Mid-run unverifiable | Stop; preserve; **RED** / **INCONCLUSIVE** per freeze |

**Exit:** design approved + tests pass.

---

### Workstream 3 — Deferred code package (canary-scoped)

**Deliverable:** one coherent PR when authorized (after WS1/WS2/inventory approval).

#### 3.1 Scope boundary

**In scope:** F1, F4, Q1, Q2, canary-only residual telemetry.  
**Out of scope:** separate legacy hardenings (F2/F3/F5-class). Byte-equivalent outside canary config. “No behavior change while flags off” applies to **this package only**.

#### 3.2 Deferred inventory

| ID | Required correction |
|----|---------------------|
| **F1** | Under canary config: one basis contract on breaker, engine, lock-state; fail closed; no silent cumulative; structured provenance |
| **F4** | Preflight `daily_loss_recomputed` aligns with Q1; no PASS on non-authoritative basis; frozen 12-check set |
| **Q1** | §3.3 required policy |
| **Q2** | Re-countersign recovery expectations under new basis (12/12 set identity, `HOLD`, no `NORMAL`) |
| **Telemetry** | Canary-only; cannot affect admission; global flags stay off |

#### 3.3 Q1 ruling (canary ENFORCE only)

| Basis | Control use |
|-------|-------------|
| Frozen authoritative session baseline (`equity`) | **Authorized** |
| `LEGACY_LAST_EQUITY` | **Telemetry only** |
| `LEGACY_CUMULATIVE_FALLBACK` | **Not authorized** |
| Missing / stale / unverifiable | **Fail closed** / Phase 0 **REFUSED** |

#### 3.4 Package invariants

Governed basis semantics under canary config; surface-specific fail-closed; no cumulative under canary ENFORCE; provenance everywhere; telemetry non-admitting; production defaults unchanged.

#### 3.5 Required tests

Missing account state; missing/valid/stale baseline; session mismatch; hash mismatch; breaker-origin vs daily-loss-origin; reduction allowed; new risk refused; recovery 12/12 **set identity**; evaluator `HOLD`; no `NORMAL`; no behavior change with canary config off.

**Exit:** focused + full backend + risk coverage/invariants green. Tier 3; validate locally first.

---

### Workstream 4 — Contract manifest (WS4A)

**Deliverable:** `ADR0043_Canary_Manifest_v1.2.md` (contract layer)

Freeze: broker identity; protected starting leg policy; A1–A5; code/harness/runbook version pins; baseline design ref; telemetry version; config **keys** + permitted values; risk-limit **policy**; Phase 0 budget **rules**; A2/A3 order contracts; post-A2 state; **12-check set identity**; partial-fill rules; A3 must prove `LOSS_CONTROL_STOP` only; stop conditions; evidence schema; dispositions. No placeholders. No runtime-unknown facts.

#### A3 authority proof (required)

Before the run, establish the frozen A3 order would otherwise pass: buying power, security eligibility, concentration, price availability, order sizing, market-hours, duplicate-order rules. Rejection reason must be **loss-control authority**, not another risk gate. Prefer a different frozen symbol if it does not introduce unrelated dependencies.

**Exit:** contract complete.

---

### Workstream 5 — Runtime readiness (no authoritative baseline capture)

Provision/bootstrap; resolve Workbench IDs, effective limits, image/env digests, positions, host identity; validate capture tooling/connectivity/schema/freshness logic; compute Phase 0 budget reachability. Publish **runtime-opening readiness record**.

**Exit:** readiness PASS; **no** authoritative baseline persisted.

---

### Workstream 6 — Execution freeze seal

**Deliverable:** `ADR0043-LIVE-CANARY-FREEZE-001`

Bind WS4A ⊕ WS5. Seal body hash; owner countersignature.

**Explicit:** seal/countersignature **does not** authorize baseline capture or Phase 0 — Start A required separately.

**Exit:** sealed + countersigned.

---

### Workstream 7 — Separate starts

**Start A** (`ADR0043-LIVE-CANARY-PHASE0-START-001`): opens boundary; captures authoritative baseline; generates daily-loss breach within budget; establishes `REDUCTION_ONLY_DAILY_LOSS`; readiness inspection. Must not run A2/A3, recovery, lower limits, buy legs, DB repair, or manufacture breaker. Result `READY_FOR_ADR0043_CANARY` or **REFUSED**. Publish Phase 0 package + hash; owner acceptance required.

**Start B** (`ADR0043-LIVE-CANARY-START-001`): binds Phase 0 package hash + state version; A1–A5 only. Any intervening mutation voids Start B.

---

### Workstream 8 — Live canary

Isolated box; deterministic identities; A1→A5 continuous.

#### 3.6 Phase 0 quantity budget

Freeze before Start A: expected baseline; daily-loss threshold; max Phase 0 loss qty; MSFT reserved for A2; order/round-trip capacity for A2/A3/recovery; buying-power/concentration; reachability. Unreachable while preserving A2+later capacity → `BREACH_UNREACHABLE` / **REFUSED**.

#### 3.7 A2/A3 order contracts

Freeze symbol/side/qty/type/price rule/TIF/extended-hours/`client_order_id`/timeout/retry/reconciliation/terminal states for each.

#### 3.8 Post-A2 state

Freeze expected remaining MSFT; A4 permission for reduced qty; readiness compare original vs post-A2; default **do not** fully flatten; partial-fill rules (§2.1).

#### 3.9 Broker ambiguity

Per §2.2.

---

### Workstream 9 — Evidence seal and qualification

Evidence includes Phase 0 hash, baseline raw+projection hashes, 12-check **set identity**, residual telemetry, post-A2 qty, A3 rejection reason code. Qualifier verifies `LOSS_CONTROL_STOP` authority for A3 and frozen check names — not row count alone.

---

### Workstream 10 — Close, cleanup, non-GREEN preservation

**GREEN closeout** (`ADR0043-LIVE-CANARY-CLOSE-001`): evidence/qualification SHAs; A1–A5; limits digest; post-state; telemetry; countersignature; cleanup checklist (SSH ingress revoke; credential archive/remove; stop runtime; preserve digests/evidence; final DB/broker hashes; reconcile orders/reservations; final MSFT qty; cooldown vs audited restore; schedulers disabled).

**Non-GREEN:** preserve loss-control state, breaker, positions, DB; no auto-reset; no account reuse; separate remediation decision required.

---

## 4. Authorized immediate work

1. `ADR0043-LIVE-CANARY-REVALIDATION-001`
2. `ADR0043-CANARY-BASELINE-DESIGN-001`
3. Detailed F1/F4/Q1/Q2 implementation inventory

Baseline design before code finalization.

---

## 5. Dependency graph

```text
WS1 + WS2 + inventory ──► owner approval ──► WS3 canary code
                                              │
                                         WS4A contract
                                              │
                                         WS5 readiness (no baseline capture)
                                              │
                                         WS6 freeze seal + countersign
                                              │
                                    [boundary opens under Start A]
                                              │
                                         Start A (baseline + Phase 0)
                                              │
                                         Start B (binds Phase 0 hash)
                                              │
                                         A1–A5 → qualify → close/cleanup
```

---

## 6. Explicit non-authorizations / HOLD

Until the three deliverables are separately approved: no runtime provisioning for execution; no authoritative baseline capture; no Phase 0 loss generation; no A1–A5; no broker orders; no canary-specific ENFORCE activation; no global flag changes; no D-WIRE.

---

## 7. Document control

| Version | Date | Change |
|---------|------|--------|
| v0.1 | 2026-07-31 | Initial draft |
| v0.2 | 2026-07-31 | Conditional-approval corrections |
| v1.0 | 2026-07-31 | Approved governing plan; folds non-blocking clarifications: section renumber; WS5→WS6→boundary→Start A; freeze ≠ Start A; no baseline in WS5/WS6; raw+projection hashes; adjustment posture; partial-fill dispositions; A3 authority proof; 12-check set identity; non-GREEN preservation |

*End of ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0.*
