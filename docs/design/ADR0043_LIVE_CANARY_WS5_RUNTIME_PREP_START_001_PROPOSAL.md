# ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 (PROPOSAL)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 |
| Status | **PROPOSAL PUBLISHED FOR OWNER COMPLETION — NOT EFFECTIVE** (owner ruling 2026-08-02: *APPROVED FOR PUBLICATION ONLY — NOT YET EFFECTIVE*) |
| Date | 2026-08-02 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0 (WS5) |
| Contract layer | ADR0043-CANARY-MANIFEST-v1.2 — **APPROVED — WS4A CONTRACT FREEZE** (2026-08-02) |
| Readiness plan | ADR0043-LIVE-CANARY-WS5-READINESS-PLAN-001 v0.1 — **APPROVED AS NON-EXECUTABLE PLAN** (2026-08-02) |
| Baseline design | ADR0043-CANARY-BASELINE-DESIGN-001 v0.2.1 (Model A) |
| Code capability | WS3 on `main` at merge `0462c25…` (WS3 code `92cbd30…`, PR #591) |
| Prerequisite | This document carries **no** authority until the owner issues the ruling in §9. Drafting it does not start WS5. |

> **Purpose of this document.** It is the *proposed* narrow start ruling that would authorize **WS5 runtime preparation only**. It is returned for a **separate authorization ruling**. Until the owner signs §9, nothing in WS5 may execute — no provisioning, no migration, no database or broker access, and no dry-run capture.

> ⚠ **PUBLICATION STATUS — NOT EFFECTIVE.** This document is published (owner ruling 2026-08-02, *APPROVED FOR PUBLICATION ONLY — NOT YET EFFECTIVE*) **solely to place the draft record in `main` for owner completion**. Publication does **not** authorize WS5 execution. §9 remains **PENDING**. No runtime mode and no isolated-runtime identity have been approved. **No** provisioning, database access, broker access, migration, or dry-run capture may begin. A later revision (§10) and a **separate** owner ruling (*APPROVED FOR AUTHORIZATION*) are required before this document becomes effective.

---

## 1. What this ruling would authorize (if signed)

Scoped strictly to preparing an **isolated** canary runtime and resolving the WS4A **[WS5/WS6-BOUND]** facts, with **no authoritative baseline capture**:

1. **Isolated runtime provisioning** — create-or-attach the isolated canary runtime (the ruling selects which; see §3).
2. **Migration application to that isolated runtime only** — bring its DB to the single governed Alembic head (currently `b2d8f4c6a901`).
3. **Read-only identity and account reconciliation** — resolve Workbench account/user IDs, broker→Workbench mapping, MSFT:19 condition, open orders, reservations, effective risk limits, image/commit/config identity, scheduler/strategy state, broker connectivity.
4. **Dry-run capture validation** — exercise Model A capture tooling **without** authoritative persistence (field/window/freshness/hash contract), proving non-persistence per §5.
5. **Readiness evidence** — publish the runtime-opening readiness record (WS5 plan §4), including planning reachability (§4) and pre/post mutation proof (§6).

## 2. What this ruling would still prohibit (non-negotiable)

- authoritative session-baseline capture / persistence (Start A only);
- Start A / Phase 0 / Start B;
- any broker **order** (Phase 0, A2, A3, or otherwise);
- canary-specific ENFORCE activation; global session-baseline flags stay OFF;
- D-WIRE;
- migration application to anything other than the isolated runtime;
- converting the verification account into an ordinary strategy account.

## 3. Runtime-existence decision (owner to specify in §9)

The ruling must state **one**:

- **(a) Attach-only** — the isolated runtime already exists; WS5 attaches read-only + applies migration to it; **or**
- **(b) Create-and-attach** — WS5 may provision a fresh isolated runtime, then migrate and attach.

Provisioning (stage 1) and readiness inspection (stages 3–6) are recorded as distinct stages regardless (WS5 plan §3.2).

## 4. Reachability handling (bound by WS5 plan §3.1)

WS5 computes **planning reachability** only, against a clearly labeled **non-authoritative** baseline estimate (`planning_baseline_estimate` + source + timestamp + uncertainty band). **Start A authoritative reachability** — recomputed from the exact captured baseline before the first Phase 0 order — is **out of scope** here. A WS5 planning PASS **cannot** override a later Start A reachability failure.

## 5. Dry-run non-persistence proof (required to close WS5)

The dry-run must demonstrate it created **none** of: a `risk_canary_session_baselines` row; an EFFECTIVE `risk_canary_start_a_authorizations` row; a `CANARY_MODEL_A_BASELINE_CAPTURE` audit event; a raw evidence object labeled authoritative; any risk-state mutation; any broker order.

## 6. Pre/post mutation proof (required to close WS5)

Pre- and post-exercise snapshots/hashes for broker positions, broker open orders, local positions, reservations, effective risk limits, the Start A authorization table, and the Model A baseline table — proving the exercise did not open the execution boundary.

## 7. Exit criteria (what a WS5 PASS produces)

- Every WS4A **[WS5/WS6-BOUND]** field populated with a verified value.
- Readiness record published; planning reachability recorded as non-authoritative.
- Dry-run non-persistence proof (§5) and pre/post mutation proof (§6) attached.
- Explicit statement that **no authoritative baseline was persisted and no order was submitted**.
- Result feeds **WS6** (freeze seal + owner countersignature). WS5 PASS does **not** authorize WS6 seal, Start A, or any capture.

## 8. Governed-head / continuity notes

- Runtime schema must equal the single governed Alembic head named here and in the WS6 freeze; **currently `b2d8f4c6a901`** (a later governed migration may supersede without amending this ruling).
- The execution continuity boundary does **not** open under WS5. It opens later, under Start A, after WS6 is sealed and countersigned.

## 9. Owner authorization ruling (to be completed by owner)

| Decision | Value |
|----------|-------|
| Authorize WS5 runtime preparation under this narrow scope (§1)? | **PENDING** |
| Runtime-existence mode (§3) | ☐ attach-only ☐ create-and-attach |
| Isolated-runtime identity / location | (owner to name) |
| Countersignature | |
| Date | |

**Until this block is signed, WS5 remains non-executable.** No provisioning, migration, database/broker access, or dry-run capture may occur.

## 10. Required before authorization (owner-completion checklist — currently unresolved)

This proposal is published as a **non-effective** record. Before the owner can issue *APPROVED FOR AUTHORIZATION*, a revision must **freeze** each of the following (all currently deferred):

1. Runtime mode — **attach-only** or **create-and-attach**.
2. Exact isolated-runtime identity and ownership.
3. Permitted **network, credential, image, database, and migration** mutations.
4. Exact **broker read endpoints** and credential restrictions.
5. Exact **database and schema access**, including any permitted writes.
6. **Technical dry-run incapacity** to create authoritative artifacts (baseline row, EFFECTIVE Start A authorization, capture audit event, execution state).
7. **Mechanical stop conditions** (identity mismatch, broker mismatch, schema conflict, unexpected position/order/reservation, any unauthorized mutation).
8. **WS5 dispositions** — `READY_FOR_WS6`, `REFUSED`, or `INCONCLUSIVE`.
9. **Expiration** — on completion, refusal, material identity change, or a fixed deadline.
10. **Explicit operator invocation bound to the final document hash** (no automatic execution on merge).

The §9 decision block must not remain open once the document is made effective.

## 11. Document control

| Rev | Date | Change |
|-----|------|--------|
| proposal | 2026-08-02 | Drafted and returned for owner ruling |
| published | 2026-08-02 | Owner ruling **APPROVED FOR PUBLICATION ONLY — NOT YET EFFECTIVE**; status set **PROPOSAL PUBLISHED FOR OWNER COMPLETION — NOT EFFECTIVE**; publication note + §10 owner-completion checklist added. Content otherwise unchanged; deferred items remain unresolved by design. |

*End of ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 (PUBLISHED — NOT EFFECTIVE; pending owner completion + separate authorization ruling).*
