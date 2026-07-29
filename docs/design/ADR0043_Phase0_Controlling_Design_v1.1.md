# ADR-0043 Phase-0 Controlling Design v1.1

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-CTRL-001 v1.1 |
| Status | **FROZEN FOR IMPLEMENTATION** (Architecture Step 1 complete) |
| Freeze date | 2026-07-29 |
| Amends / integrates | ADR0043-PH0-CORR-001 v1.0; AMD r2 (`ADR0043-PH0-CORR-001-AMD r2`); owner ruling 2026-07-29 |
| Companion | `design-review.md`; `ADR0043_Phase0_AMD_r2_Owner_Architecture_Ruling.md` |
| Broker submission | **HOLD** |
| Formal canary | **HOLD** |
| July 24 limits digest | Unchanged |

This document is the **controlling architecture** for Phase-0 implementation after owner
sign-off. It does not restate the entire v1.0 CORR body; it freezes the amendment set and
the six owner-required modifications so implementers have one place to read the binding
rules. Where this document and AMD r2 conflict, **this document + the owner ruling win**.

---

## 1. Posture and non-authorization

- Architecture Review Step 1: **APPROVED WITH MODIFICATIONS** (signed 2026-07-29).
- Implementation of offline contracts, evidence sealing (WP0), Option C tests, and
  structural gates is **authorized**.
- Phase-0 **broker submission** and the **formal canary** remain **HOLD** until the
  amended design is integrated, frozen (this document), implemented, deployed through
  governance, and all applicable O-gates pass.
- Nothing here widens caps, changes the July 24 limits digest, reuses prior baselines or
  authorizations, or authorizes live trading.

---

## 2. Owner adjudications (binding)

### D1 — O4 split (ACCEPT)

| Gate | Evidence | Expected verdict |
|------|----------|------------------|
| **O4-A** decision-time | Only evidence available **before** first broker submission | `INDETERMINATE` with `INSUFFICIENT_EXECUTION_COST` (or `MODEL_UNAVAILABLE` only if model artifact/runtime absent) |
| **O4-B** forensic | Complete terminal evidence including fills | `UNREACHABLE_WITHIN_CAPS` |

Decision-time and forensic evidence **must not be mixed**. Neither test substitutes for the other.

### D2 — Sample floors (ACCEPT WITH MODIFICATION)

Frozen **planning floors** (not automatic sufficiency):

| Quantity | Provisional floor |
|----------|-------------------|
| Pooled binding REACHABLE plans | ≥ 59 |
| Per intended-symbol stratum | ≥ 20 |
| Shadow sessions | ≥ 10 |

One governed replacement allowed at **WP5 exit**, before model evaluation and sealed-set
opening; then locked. Every gate result reports exact one-sided Clopper–Pearson upper
bound, dependency/clustering/effective-sample assumptions, and achieved stratum coverage.
Per-symbol n≥20 is a diagnostic floor only (zero failures in 20 does **not** prove a 5%
upper bound).

---

## 3. Required modifications before freeze (incorporated here)

### 3.1 False-reachable (AMD-01 + owner mod)

A **plan-level false reachable** occurs whenever the exact authorized sequence cannot
achieve **100%** of the remaining target within all frozen caps.

| Severity | Achieved fraction of remaining target | Gate effect |
|----------|----------------------------------------|-------------|
| CRITICAL | &lt; 80% | Automatic **REJECT** |
| MARGINAL | 80% ≤ x &lt; 100% | Counts in false-reachable rate; permitted count/rate frozen before unseal — **initial sealed validation: zero marginal allowed** |

Evaluation unit = binding REACHABLE **execution plan**, not session. Exclude from
model-failure counts (separate reason codes): post-plan condition changes;
non-model execution failures (broker outage, halt).

### 3.2 Execution-evidence tiers (replaces contradictory v1.0 / AMD-04 language)

| Tier | Definition |
|------|------------|
| **A** | Matched **live-market** broker fills from the same or demonstrably equivalent execution path |
| **B** | Independently generated **paper** fills, or broker executable-price estimates |
| **C** | Quote-derived estimates with validated quote-to-fill mapping |
| **D** | Displayed spread alone (diagnostic only; never sufficient for a binding verdict) |

**Alpaca paper-account fills** (current Phase-0 paper stack): classified as **Tier B** —
broker-reported executions in a simulated account, **not** live-market Tier A fills.
Paper fills are **never** Tier A.

O5 may not rest solely on model–simulator agreement; at least one live-fill-anchored
comparison per gate cycle is mandatory, and the approval decision must still judge whether
the number and representativeness of anchors are sufficient.

### 3.3 Authorization expiry after partial execution (AMD-16 + owner mod)

| Situation | Required behavior |
|-----------|-------------------|
| Expiry before any broker submission | Refuse; fail closed |
| Expiry after one or more legs, before closing leg | **Prohibit** further risk-increasing submissions; **permit** only predefined risk-reducing completion or emergency flatten; record authorization-expiry exception; enter recovery/reconciliation as required |

Invariant: expiry must not prevent an already-authorized or emergency-governed
**risk-reducing** action needed to neutralize exposure created under that authorization
(consistent with ADR-0042 reduction-only).

### 3.4 Fresh market/broker reads vs plan mutation (AMD-15 + owner mod)

The driver **may** obtain fresh quotes, broker state, and risk state for **safety checks**.
Fresh data may cause refusal, quantity reduction, or termination. Fresh data **may not**
expand the plan, extend expiry, increase quantity, substitute the instrument, or
regenerate authority under the same authorization.

### 3.5 Checkpoint integrity (AMD-07 → blocking)

Checkpoint integrity (loss-control state version in binding tuple; HMAC/content hash;
tampered-contents refuse) is **BLOCKING** before any Phase-0 retry and before any
checkpoint is accepted as authoritative evidence.

### 3.6 Statistical design assumptions (WP5 artifact)

WP5 statistical-design must record: independence unit; whether multiple plans/session
count separately; clustering adjustments; same-symbol repeats; pooled weighting;
effective sample size vs raw plan count.

---

## 4. Verdicts, reason codes, and loss sign (AMD-13, AMD-14)

### Verdicts (canonical)

- `REACHABLE`
- `UNREACHABLE_WITHIN_CAPS` (replaces legacy `BREACH_UNREACHABLE` in new code paths;
  migration note: existing scripts may alias until cutover)
- `INDETERMINATE`

### Mandatory reason codes

`INSUFFICIENT_EXECUTION_COST`, `ROUND_TRIP_CAP`, `NOTIONAL_CAP`, `POSITION_CAP`,
`MARKET_CLOSED`, `STALE_EVIDENCE`, `TIMESTAMP_CONTRADICTION`, `MODEL_UNAVAILABLE`,
`ALREADY_BREACHED`, `CONDITIONS_CHANGED_POST_PLAN`, `EXECUTION_FAILURE_NON_MODEL`

Schema version is a frozen governed constant.

### Non-negative loss

Canonical quantity: `round_trip_loss_amount ≥ 0`. Preferred term: **conservative minimum
supported loss amount**. Signed-P&L “lower bound” meaning “more negative” is prohibited.

---

## 5. ExecutionPlan and authorization lifecycle (AMD-15, AMD-16)

### Plan immutability

Once authorized, the driver may only execute the exact frozen plan. It may reduce quantity
or terminate for safety; it may not increase quantity, substitute symbol, change
route/order type, extend validity, or regenerate the plan under the same authorization.

Required fields include: `plan_id`, `plan_schema_version`, `plan_hash`, `created_at`,
`expires_at`, `quote_evidence_hash`, `model_artifact_hash`, `authorization_scope`,
`maximum_authorized_legs`.

### Authorization lifecycle

`ISSUED → CLAIMED → ACTIVE → CONSUMED`, with terminals `REFUSED` / `ABORTED` / `EXPIRED`.

Invariant: no authorization that has produced a broker submission may authorize a second
independent run. Pre-broker refusal is retryable only via new owner-controlled
authorization or an explicitly governed same-plan retry rule.

---

## 6. Work-package sequence (AMD-12)

| Order | Package | Notes |
|-------|---------|-------|
| 1 | **WP0** Preserve and seal current evidence | First; exit gate before structural work that mutates evidence |
| 2 | **WP1** ExecutionPlan authority + auth lifecycle (Gate O1) | Offline contracts; no broker |
| 3 | **WP2** Reachability / decision adjudicator | Verdicts + reason codes; Tier D non-binding |
| 4 | **WP3** Checkpoint integrity | CORR-07 / AMD-07 |
| 5 | **WP4** Crash consistency | CORR-04 / AMD-20 |
| 6 | **CORR-06** account isolation (AMD-12) | Own numbered package + exit gate; after WP4, before O1/O2 structural approval on the box; retry = account 3 only; canary acceptance = zero account-1 credential-metadata mutation |
| 7 | **WP5** Statistical-design freeze (AMD-02 / D2) | Floors 59/20/10; one replacement then lock; CP bounds; §3.6 assumptions |
| 8 | **WP6** Estimator ladder E0–E2 (AMD-03) | Conservative loss bound; governed graduation; lower-tail q=0.10 |
| 9 | WP7–WP9 | Dataset / gates / remaining AMD packages |

Phase-0 retry: account-3 only; no trading or risk-state mutation outside account 3.
Formal canary acceptance: zero account-1 credential-metadata mutation.

---

## 7. Gates O1–O5 (summary; details in AMD pack)

Retain O1–O5 structure from v1.0 as amended. O4 is split per §2 D1. O5 requires sample
floors and confidence bounds per §2 D2. Option A validates threshold-independent
state-machine properties only; $3,000 threshold behavior requires Option C offline tests
(AMD-10).

---

## 8. Implementation carve-out (this increment)

Authorized **now** (offline only):

1. This controlling design freeze artifact.
2. WP0 seal procedure and exit criteria.
3. Pure Python contracts for verdicts, reason codes, ExecutionPlan hashing, and
   authorization lifecycle — **not** wired into `OrderRouter` / live broker submission.

**Not authorized in this increment:** broker submission, canary run, ENFORCE flip on
production accounts 1–7, cap changes, limits-digest edits.

---

## 9. Change control

Changes to frozen constants in §2–§5 require an explicit re-freeze and owner architecture
sign-off. Implementation PRs must cite this document ID and must not weaken HOLD posture
without a new ruling.
