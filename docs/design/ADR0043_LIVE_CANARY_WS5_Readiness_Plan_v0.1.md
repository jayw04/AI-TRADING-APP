# ADR0043 Live Canary — WS5 Runtime Readiness Plan (Non-Executable Draft)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-WS5-READINESS-PLAN-001 v0.1 |
| Status | **CONDITIONALLY APPROVED — NON-EXECUTABLE DRAFT** (owner clarification folded; drafting authority only) |
| Date | 2026-08-02 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0 (WS5) |
| Contract layer | ADR0043-CANARY-MANIFEST-v1.2 (WS4A — pending owner ruling) |
| Baseline design | ADR0043-CANARY-BASELINE-DESIGN-001 v0.2.1 (Model A) |
| Code capability | WS3 merge SHA `92cbd30…` (PR #591) |
| Execution authority | **NONE.** This draft carries no authority to touch any runtime, broker, or database. |

> **Standing constraint.** This document may be drafted while WS4A is under owner review, **provided it remains non-executable**. Under drafting authority alone: **no provisioning, no broker reads, no database access, no migration application, no capture (not even dry-run).** Every action described here is gated behind a separate, narrow start ruling (§6). WS5 must **never** retrieve or persist the authoritative session baseline.

---

## 1. Purpose

Enumerate the **runtime facts that must be resolved** before an ADR-0043 canary can be sealed (WS6) and started (Start A), and the readiness checks that resolve them. WS5 turns the WS4A **[WS5/WS6-BOUND]** fields into verified values, without capturing the authoritative baseline and without executing any assertion.

## 2. Runtime facts to resolve (currently unknown — do not assume)

| # | Runtime fact | How it is resolved (under WS5 start ruling) | Notes |
|---|--------------|---------------------------------------------|-------|
| 1 | Workbench **account ID** and **user ID** for `PA34USW0Q8UO` | Read-only DB reconciliation on the isolated runtime | `account_id=3` is **not** authoritative until verified |
| 2 | **Broker → Workbench mapping** | Read-only account/credential-metadata reconciliation | Must map to `PA34USW0Q8UO` exactly |
| 3 | Current **MSFT:19** condition | Read-only broker position + local position reconciliation | Verify presence and qty; no manufacture; no flatten |
| 4 | **Open orders** and **reservations** | Read-only broker + local reconciliation | Must be clean before seal; leaks void readiness |
| 5 | **Exact risk limits** (applied daily-loss limit, etc.) | Read effective `risk_limits` rows on the runtime | Values are **runtime facts**; bound into WS6 seal, never guessed in WS4A |
| 6 | **Schema head** | `alembic current` on the isolated runtime DB | Must equal the single governed Alembic head named in the eventual WS5 start ruling and WS6 freeze; **currently `b2d8f4c6a901`** (successor governed migrations may land first without amending this plan) |
| 7 | **Code / image identity** | Image digest + commit SHA of the deployed canary image | Must correspond to WS3 capability at `92cbd30…` or an approved successor |
| 8 | **Configuration digest** | Compute over the sealed canary configuration set | Value is runtime-derived; bound in WS6 |
| 9 | **Scheduler and strategy state** | Read-only inspection | Schedulers/strategies must be in the frozen, non-arming state |
| 10 | **Broker connectivity** | Connectivity + permissions probe (no orders) | API reachable; account active; read scopes verified |
| 11 | **Dry-run capture validation** | Exercise Model A capture tooling **without** authoritative persist | Validates field contract, window logic, freshness calc, dual-hash + canonical serialization — persists **nothing** authoritative |

## 3. Readiness checks (map to WS4A §14 and the frozen 12-check inputs)

1. Isolated runtime provisioned and reachable (SSH ingress scoped, revocable).
2. Migrations applied to the **isolated** runtime DB → the single governed Alembic head named in the WS5 start ruling / WS6 freeze (currently `b2d8f4c6a901`).
3. Read-only identity reconciliation (facts 1–4) reconciles deterministically.
4. Effective risk limits read and recorded (fact 5).
5. Image/commit/config identity captured (facts 7, 8).
6. Broker connectivity + account-active + read-scope probe passes (fact 10), **no orders**.
7. Scheduler/strategy state confirmed non-arming (fact 9).
8. Capture tooling dry-run passes the baseline field/window/freshness/hash contract with **no authoritative row** written (fact 11).
9. Phase 0 **planning reachability** computed against a clearly labeled *non-authoritative* baseline estimate (§3.1) — **not** an authoritative baseline. This may show the mechanism is plausibly reachable; it cannot certify final reachability.

### 3.1 Planning reachability vs. Start A authoritative reachability (frozen distinction)

The actual Model A baseline **cannot be known** until Start A captures broker `equity` inside `[09:30, 09:35) ET`. WS5 must **never** retrieve or persist that authoritative baseline. Two separate calculations exist:

**WS5 planning reachability (non-authoritative).** Uses a clearly labeled estimate / bounded range:

| Field | Meaning |
|-------|---------|
| `planning_baseline_estimate` | Best non-authoritative estimate of session-open equity |
| `planning_baseline_source` | How the estimate was derived (e.g. prior-close telemetry) — **not** an authoritative capture |
| `planning_baseline_timestamp` | When the estimate was formed |
| `planning_baseline_uncertainty_band` | Explicit ± range around the estimate |

**Start A authoritative reachability (executed only under Start A, not WS5).** Immediately after the Model A baseline commits and **before** the first Phase 0 order: load the exact baseline; load the frozen daily-loss limit and available capacities; recompute the Phase 0 quantity budget; prove breach reachability while preserving A2 and recovery capacity; if unreachable, return `BREACH_UNREACHABLE` / **REFUSED** and submit no Phase 0 order.

**A WS5 planning-reachability PASS cannot override a Start A authoritative reachability failure.** The planning number is advisory only.

## 3.2 WS5 stages (distinct, separately recorded)

The future WS5 start ruling must state whether the isolated runtime already exists or may be created, and WS5 records these as **distinct stages** (a later stage does not begin until the prior one is recorded PASS):

1. **Isolated runtime provisioning** (create-or-attach; the start ruling says which is permitted).
2. **Migration** to the governed head on the isolated DB.
3. **Identity resolution** (facts 1, 2, 7, 8).
4. **Read-only broker reconciliation** (facts 3, 4, 10).
5. **Dry-run capture validation** (fact 11; non-persistence proof per §5.1).
6. **Readiness closeout** (output artifact §4, including pre/post mutation proof §4.1).

## 4. Output artifact

A **runtime-opening readiness record** that:

- populates every WS4A **[WS5/WS6-BOUND]** field with a verified value;
- records reconciliation snapshots (positions, orders, reservations, limits, identities);
- records the **planning reachability** calculation (§3.1) as explicitly non-authoritative;
- attaches the dry-run capture validation result (no authoritative baseline);
- states explicitly that **no authoritative baseline was persisted** and **no order was submitted**.

### 4.1 Pre/post mutation proof (required in the readiness package)

Record pre- and post-exercise hashes or snapshots for each of the following and prove they are unchanged (or changed only in an explicitly sanctioned, recorded way), demonstrating the readiness exercise did **not** open the execution boundary:

- broker positions;
- broker open orders;
- local positions;
- reservations;
- effective risk limits;
- Start A authorization table (`risk_canary_start_a_authorizations`);
- Model A baseline table (`risk_canary_session_baselines`).

## 5. Explicit prohibitions under WS5 (even after the start ruling)

- Authoritative baseline capture / persistence (Start A only).
- Any broker **order** (Phase 0, A2, A3, or otherwise).
- Migration application to anything other than the **isolated** runtime.
- Start A / Phase 0 / Start B.
- Canary ENFORCE activation; global session-baseline flags stay OFF.
- D-WIRE.
- Converting the verification account into a strategy account.

### 5.1 Dry-run non-persistence proof (technical, required)

The capture-tooling dry-run must prove, by inspection after it runs, that it created **none** of the following:

- no `risk_canary_session_baselines` row;
- no EFFECTIVE Start A authorization (`risk_canary_start_a_authorizations` with `authorization_status = EFFECTIVE`);
- no `CANARY_MODEL_A_BASELINE_CAPTURE` audit event;
- no raw object-store evidence object labeled authoritative;
- no risk-state mutation;
- no broker order.

## 6. Gating — separate start ruling required

WS5 execution begins **only** under a narrow authorization such as:

```
ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001
```

That ruling may authorize: isolated runtime preparation; migration application to that isolated runtime; read-only identity/account reconciliation; dry-run capture validation; readiness evidence. It must still prohibit: authoritative baseline capture; Start A; Phase 0; broker orders; ENFORCE; D-WIRE.

**This draft does not request or constitute that ruling.** It exists to make the runtime-fact resolution plan reviewable in parallel with the WS4A ruling.

## 7. Sequencing (reminder)

```
WS4A manifest ruling
  → WS5 start ruling → WS5 readiness (no baseline capture)
  → WS6 freeze seal + owner countersignature
  → boundary opens under Start A → Start A (baseline + Phase 0)
  → Start B → A1–A5 → qualify → close
```

## 8. Document control

| Rev | Date | Change |
|-----|------|--------|
| draft-1 | 2026-08-02 | Initial non-executable readiness plan |
| draft-2 | 2026-08-02 | Owner **CONDITIONALLY APPROVED**; clarifications folded: split planning-reachability (§3.1, non-authoritative estimate) from Start A authoritative reachability, with "planning PASS cannot override Start A failure"; distinct WS5 stages (§3.2); dry-run non-persistence proof (§5.1); pre/post mutation proof (§4.1); governed-head successor handling (fact 6, check 2). Remains non-executable; no WS5 start ruling issued. |

*End of ADR0043-LIVE-CANARY-WS5-READINESS-PLAN-001 v0.1 (non-executable draft).*
