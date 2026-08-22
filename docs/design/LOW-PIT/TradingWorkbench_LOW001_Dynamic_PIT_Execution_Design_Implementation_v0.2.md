# Trading Workbench — LOW-001 Dynamic PIT Execution
## Design & Implementation Specification v0.2

**Strategy:** LOW-001 (`low-volatility`)  
**Current implementation:** v1.0.1 working tree / conformance repair  
**Planned dynamic-PIT implementation:** v1.0.2 candidate  
**Strategy ID:** 8  
**Paper account:** Account 6 / user 6  
**Status:** IMPLEMENTATION-READY DESIGN — ENGINEERING MAY START; ACCOUNT 6 ACTIVATION REMAINS GATED  
**Date:** 2026-08-22

---

## Version 0.2 change summary

v0.2 promotes the document from design-only guidance to an **implementation-ready developer contract**. It does not change LOW-001 economics or the v1.0.2 target behavior. Relative to v0.1, it adds:

1. Explicit authorization to begin engineering now while keeping Account 6 activation gated behind the v1.0.1 boundary.
2. Concrete component/function contracts so dynamic eligibility cannot leak into ranking logic.
3. A ticket-level backlog with priority, dependencies, deliverables, and completion criteria.
4. Persistence/migration rules, including idempotency and stable rebalance identity requirements.
5. A recommended PR/branch merge sequence designed to avoid mixing strategy-economics changes with execution-conformance work.
6. A first implementation tranche that tells developers exactly what to do before writing the execution bypass.
7. A developer handoff checklist and stop conditions for ambiguous or unsafe behavior.

**v0.2 does not authorize live-money trading, does not upgrade LOW-001 above Diversifier (B), and does not make post-repair P&L an economic-validation dataset.**

---

## 1. Executive decision

LOW-001 remains **KEEP / REPAIR**. The strategy economics are not being changed. The next engineering work is to remove the remaining execution drift between the frozen research construction and the live runtime: research reconstructs the point-in-time top-200 universe on every rebalance, but execution is still limited by the strategy's statically registered symbol list.

Dynamic PIT execution **is authorized to start now as a separate engineering workstream**, but it must **not be folded into v1.0.1**. v1.0.1 is the current conformance repair and must retain a clean deployment/evidence boundary. Dynamic PIT should be delivered as a separate version (proposed: **v1.0.2**) after isolated verification.

### Decision summary

| Decision | Ruling |
|---|---|
| Change LOW-001 economics? | **No** |
| Change lookback / quintile / weighting / weekly cadence? | **No** |
| Keep v1.0.1 separate? | **Yes** |
| Start dynamic PIT engineering now? | **Yes** |
| Permit new PIT names to trade without strategy re-registration? | **Yes, through a governed dynamic-enrollment path** |
| Remove static registration globally? | **No** |
| Preserve sell capability for held names that leave the PIT universe? | **Mandatory** |
| Treat missing/untradable names by substitution? | **No — fail explicit, do not substitute** |
| Upgrade LOW-001 above Diversifier (B) because of recent paper P&L? | **No** |

---

## 2. Governing evidence and boundaries

The following pre-remediation paper window is already sealed and is an input to this implementation program, not something this change may rewrite:

- `docs/implementation/TradingWorkbench_LOW001_PaperWindow_2026-08-12_2026-08-21_v1.0.md`
- `docs/implementation/low001_paper_window_20260812_20260821.json`
- SHA-256: `81be681c6c3d1766a0098dbf7b82fdb199aef86c8076ff51dd5ec07ed244566b`
- Classification: `OBSERVATION_ONLY`

The sealed window must remain immutable after post-repair P&L is observed. It is not economic validation and is not a basis for upgrading LOW-001's research verdict from **B (Diversifier)**.

### v1.0.1 boundary

The dynamic-PIT work assumes v1.0.1 independently addresses the already identified implementation defects:

1. SPY 200-day cash gate removed for LOW-001 V1.
2. Fractional sizing restored, with the existing OrderRouter responsible for flooring non-fractionable quantities.
3. Unpriced names removed before equal-weight allocation so dead legs do not reserve cash.
4. Session-aware factor-staleness HOLD behavior added.
5. Durable `rebalance_started` -> `rebalance_completed` state via signals, with restart retry of an incomplete week.
6. Research PIT universe is scored even when names are not in the registered list; such names are currently logged as `pit_name_not_registered` and omitted from execution.

Dynamic PIT addresses item 6's remaining execution gap only. HON / 2026-07-27 cost-basis reconciliation remains a separate operations task. Engineering may branch and implement dynamic PIT before v1.0.1 is deployed, but **G0 blocks Account 6 activation until the v1.0.1 deployment/evidence boundary is established**.

---

## 3. Problem statement

### 3.1 Research behavior

At each weekly rebalance, frozen LOW-001 research conceptually performs:

```text
rebalance_date
    -> universe_asof(rebalance_date, n=200)
    -> valid 252-session realized-vol scores
    -> sort ascending by realized volatility
    -> select lowest quintile (~40 names)
    -> equal-weight executable names
    -> rebalance weekly
```

The key property is that the 200-name universe is **point-in-time**. Membership may change from week to week.

### 3.2 Current live limitation after v1.0.1

v1.0.1 can identify and score the correct research PIT universe, but execution still behaves like:

```text
PIT selected names
    -> intersect with statically registered strategy symbols
    -> execute only the intersection
```

A newly eligible liquid name can therefore be correctly selected by research logic but still fail to enter the live book because it was not registered when the strategy instance was created.

This is **construction drift**, not a new research question.

### 3.3 Required target behavior

The runtime must instead behave like:

```text
PIT universe
    -> factor eligibility
    -> LOW-001 selection
    -> governed dynamic symbol enrollment
    -> broker-asset validation
    -> price validation
    -> target sizing
    -> order plan
    -> execution + reconciliation
```

Static strategy registration remains the strategy-level safety boundary. Dynamic symbol enrollment becomes an explicit, auditable capability used only by strategies authorized for a changing PIT universe.

---

## 4. Design principles and non-negotiable invariants

### 4.1 Strategy economics are frozen

Dynamic PIT must not alter:

- 252-session realized-volatility factor definition.
- Lowest-quintile selection rule.
- Equal-weight construction.
- Weekly rebalance cadence.
- Always-invested LOW-001 V1 economic intent, subject to explicit fail-closed data/execution conditions.
- Existing risk controls that are independent of universe membership.

### 4.2 Static and dynamic universe modes must be explicit

Do not weaken registration behavior globally. Introduce an explicit strategy capability. Naming is implementation-dependent; a recommended model is:

```text
universe_mode = STATIC | DYNAMIC_PIT
```

- `STATIC`: existing behavior. Only explicitly registered symbols may become new targets.
- `DYNAMIC_PIT`: strategy may enroll PIT-selected symbols through the governed resolver described in this document.

Default must be `STATIC` for backward compatibility and safety.

### 4.3 Held positions must always be reducible

A symbol leaving the current PIT universe or current selected quintile **must remain sellable** while the strategy holds it.

This invariant is more important than buy eligibility. No universe-membership check may block a risk-reducing sell, liquidation, or rebalance exit of an existing LOW-001 position.

### 4.4 No silent substitution

If a PIT-selected name is unavailable because it is inactive, untradable, unpriced, factor-invalid, or broker-unresolvable:

- log the exact exclusion reason;
- omit it from the executable selected set;
- recompute equal weights across the remaining executable names;
- do **not** replace it with the next-ranked name unless the frozen research specification explicitly requires that behavior and a separate conformance decision authorizes it.

### 4.5 Evidence must be reproducible

Every rebalance must make it possible to reconstruct:

- PIT universe date / as-of session;
- PIT-200 membership;
- factor as-of date;
- valid/invalid factor set;
- selected lowest quintile;
- newly dynamically enrolled names;
- broker eligibility decisions;
- price eligibility decisions;
- final executable selected set;
- target weights / quantities;
- orders submitted;
- fills/rejections;
- final broker reconciliation;
- rebalance state (`started`, `completed`, or incomplete/recovering).

---

## 5. Proposed architecture

### 5.1 Separation of concerns

The design should use five logical components. These can be separate classes/modules or clearly separated functions depending on the existing codebase.

| Component | Responsibility | Must not do |
|---|---|---|
| `PITUniverseProvider` | Return `universe_asof(date, n=200)` with evidence metadata | Place orders |
| `LowVolSelector` | Apply 252-session vol eligibility, rank, select lowest quintile | Know broker registration rules |
| `DynamicSymbolResolver` | Convert selected symbols into governed execution eligibility | Change factor ranking |
| `TargetBuilder` | Price executable names and build equal-weight targets | Invent substitute symbols |
| `ExecutionReconciler` | Submit/recover orders and reconcile target vs broker state | Change research selection |

### 5.2 Dynamic symbol enrollment model

Dynamic enrollment should not rewrite the strategy registration record every week. Treat registration as the stable strategy identity/configuration and maintain a runtime-permitted symbol set for the rebalance.

Recommended data concept:

```text
strategy registration
    + current held symbols
    + dynamic PIT enrollment for this rebalance
    = permitted execution context
```

A dynamically enrolled symbol should carry at least:

```text
strategy_id
rebalance_id / rebalance_week
symbol
source = "pit_universe"
pit_as_of
selected_rank / score metadata
broker_asset_status
fractionable
price_status
enrollment_status
created_at
```

If the system already has an equivalent signal/evidence framework, reuse it rather than creating a duplicate persistence subsystem.

### 5.3 Buy eligibility

A new PIT-selected symbol is buy-eligible only if all applicable checks pass:

```text
selected_by_LOW001
AND dynamic_PIT_authorized_for_strategy
AND broker_asset_resolved
AND asset_active
AND asset_tradable
AND required_price_available
AND factor_freshness_gate_passed
AND strategy/risk gates_passed
```

Fractionability is not a buy/no-buy gate by itself. If the asset is non-fractionable, sizing should fall through to the existing whole-share behavior in OrderRouter.

### 5.4 Sell eligibility

Sell/reduce eligibility must be broader:

```text
currently_held_by_strategy
AND risk-reducing_or_rebalance_exit
```

The symbol does not need to be in the current PIT universe, current selected quintile, or current dynamic-enrollment set in order to exit.

---

## 6. Detailed rebalance flow

### Step 1 — Establish rebalance identity

Create/load the durable weekly rebalance state. The rebalance must have a stable identifier so retries reconcile the same logical attempt rather than generating an unrelated second attempt.

Expected state progression:

```text
not_started
    -> rebalance_started
    -> plan_built
    -> orders_dispatched / recovering
    -> reconciled
    -> rebalance_completed
```

Exact signal names may differ, but `rebalance_started` and `rebalance_completed` semantics from v1.0.1 must remain intact.

### Step 2 — Resolve the expected PIT session

Use the session/calendar logic already adopted for v1.0.1 freshness checks. Do not approximate this with raw weekday arithmetic when exchange holidays matter.

Persist:

- rebalance timestamp;
- expected latest completed factor session;
- actual factor `as_of`;
- pass/HOLD result.

If factor freshness fails, emit `factor_stale_hold`, make no selection/order changes, and leave evidence sufficient to explain the HOLD.

### Step 3 — Build PIT-200

Call the same governed `universe_asof(..., n=200)` behavior used by research/conformance reconstruction.

Persist the full PIT membership and its effective date/hash if available.

### Step 4 — Compute factor-eligible universe

For each PIT member, resolve the 252-session realized-vol factor using the required factor as-of date. Explicitly separate:

- valid factor;
- missing factor;
- stale factor;
- invalid/non-finite factor.

No name with invalid factor data may enter the ranked set.

### Step 5 — Select LOW-001 quintile

Sort valid factor names from lowest to highest realized volatility and apply the frozen quintile rule.

Persist selected symbols, scores, ranks, and selection count.

### Step 6 — Resolve dynamic execution eligibility

For every selected symbol not already statically known/registered for the strategy:

1. Resolve broker asset metadata.
2. Confirm symbol is active and tradable.
3. Enroll it into the rebalance's permitted execution context if valid.
4. Emit a durable audit record indicating dynamic enrollment.

For selected symbols that cannot be enrolled, emit a specific reason such as:

```text
pit_asset_not_found
pit_asset_inactive
pit_asset_not_tradable
pit_asset_resolution_error
```

Do not use the old generic `pit_name_not_registered` as the terminal outcome once dynamic PIT is enabled. It may remain useful as an observation before resolver processing.

### Step 7 — Price and construct executable equal-weight book

Resolve prices for the dynamically executable selected set. Drop names without an acceptable price **before** equal-weight sizing.

Emit explicit exclusion signals such as:

```text
pit_price_unavailable
pit_price_invalid
```

Then compute:

```text
allocatable_equity = equity * (1 - configured_cash_buffer)
weight_per_name = 1 / executable_name_count
notional_per_name = allocatable_equity / executable_name_count
```

Use the existing order sizing/router behavior for fractional vs non-fractionable assets.

### Step 8 — Build deterministic target plan

The order plan must clearly identify:

- positions to exit;
- positions to reduce;
- positions unchanged / within tolerance;
- positions to increase;
- new PIT entrants to buy.

The plan should be deterministic for identical inputs.

### Step 9 — Execute with recovery semantics

Preserve existing sell-before-buy behavior if that is the governed runtime behavior, but retries must inspect broker/current state and continue an incomplete rebalance rather than blindly replaying every original order.

A restart after `rebalance_started` and before `rebalance_completed` must enter recovery/reconciliation mode.

### Step 10 — Reconcile and complete

Before emitting `rebalance_completed`, compare:

```text
research_selected_set
executable_selected_set
final_target_set
broker_position_set
```

Every difference must be explained by a recorded reason (e.g., untradable, missing price, quantity rounding, pending/rejected order). There must be **zero unexplained symbol discrepancies**.

---

## 7. Required persistence / evidence schema

Use existing platform tables/signals where possible. The following is a logical minimum, not a mandate to create new tables with these exact names.

### 7.1 Rebalance summary

| Field | Purpose |
|---|---|
| `rebalance_id` | Stable logical attempt ID |
| `strategy_id` / version | Bind evidence to LOW-001 runtime identity |
| `week` | Week-once/recovery key |
| `started_at` / `completed_at` | Operational boundary |
| `pit_as_of` | Universe effective session |
| `factor_as_of` | Factor session |
| `pit_count` | Expected ~200 |
| `valid_factor_count` | Ranking input count |
| `selected_count` | Research-selected quintile count |
| `executable_count` | Selected names after broker/price checks |
| `dynamic_enrollment_count` | Newly permitted PIT symbols |
| `exclusion_count` | Explicitly excluded selected names |
| `status` | started/completed/hold/recovering/failed |

### 7.2 Per-symbol evidence

At minimum, each selected or held symbol should be traceable through:

```text
symbol
in_pit_universe
factor_value
factor_rank
research_selected
was_registered
was_already_held
dynamic_enrollment_status
broker_active
broker_tradable
fractionable
price
price_status
target_weight
target_qty
current_qty
planned_action
order_id(s)
fill_status
exclusion_reason
```

---

## 8. Engineering task breakdown

The tasks below should be tracked individually. Do not combine all work into one opaque PR if the codebase allows clean separation.

### EPIC LOW-PIT-01 — Characterize current registration boundary

**Goal:** determine exactly what static symbol registration controls today before bypassing it for dynamic PIT names.

Tasks:

- [ ] Identify the strategy registration model and all call sites that consume registered symbols.
- [ ] Identify whether registration initializes per-symbol state, subscriptions, callbacks, risk controls, position attribution, price feeds, or broker permissions.
- [ ] Identify every execution-layer check that rejects or omits an unregistered symbol.
- [ ] Confirm held-position sells are not blocked by registration membership.
- [ ] Write a short dependency map in the PR/design notes.

**Acceptance criteria:** developers can state precisely which safety/services must be recreated for a dynamically enrolled symbol. No dynamic-bypass code is written until this is known.

### EPIC LOW-PIT-02 — Add explicit universe capability

**Goal:** make changing-universe behavior opt-in and backward compatible.

Tasks:

- [ ] Add explicit strategy universe mode/capability (`STATIC` vs `DYNAMIC_PIT`, or equivalent).
- [ ] Default all existing strategies to `STATIC`.
- [ ] Authorize LOW-001 v1.0.2 only for `DYNAMIC_PIT`.
- [ ] Add configuration validation so unknown mode values fail closed.
- [ ] Add tests proving static strategies retain current behavior.

**Acceptance criteria:** enabling dynamic PIT for LOW-001 cannot implicitly enable it for Account 5 or any momentum strategy.

### EPIC LOW-PIT-03 — Implement DynamicSymbolResolver

**Goal:** allow a research-selected PIT name to become execution-eligible without permanent re-registration.

Tasks:

- [ ] Accept the selected LOW-001 symbol set and rebalance context.
- [ ] Resolve broker asset metadata in bounded batches where supported.
- [ ] Validate asset existence, active status, tradability, and required routing metadata.
- [ ] Record fractionability for sizing but do not reject solely because fractional trading is unavailable.
- [ ] Create durable dynamic-enrollment evidence.
- [ ] Emit explicit failure reasons for unresolvable/inactive/untradable names.
- [ ] Ensure resolver failure for one symbol does not silently drop evidence for other symbols.

**Acceptance criteria:** a selected symbol absent from the static registration list can reach the target builder when broker-valid.

### EPIC LOW-PIT-04 — Preserve unconditional risk-reducing exits

**Goal:** guarantee that a held name can leave the book even when it is no longer PIT-selected or enrolled.

Tasks:

- [ ] Trace all sell/reduce routing checks.
- [ ] Remove/avoid any current-universe membership requirement for reducing a held strategy position.
- [ ] Add explicit tests for a name that was dynamically added in week N and removed from PIT-200 in week N+1.
- [ ] Add test for inactive/untradable transitions and document broker-dependent behavior.

**Acceptance criteria:** no registration/PIT gate blocks a valid sell of an existing position.

### EPIC LOW-PIT-05 — Build executable book after eligibility checks

**Goal:** preserve equal weighting without reserving capital for dead legs.

Tasks:

- [ ] Resolve acceptable prices for all broker-eligible selected symbols.
- [ ] Drop unpriced/invalid-price names before equal-weight sizing.
- [ ] Recompute equal weights using only the executable selected set.
- [ ] Send fractionable/non-fractionable quantity handling through the existing OrderRouter.
- [ ] Preserve configured cash buffer.
- [ ] Emit selected->executable reconciliation evidence.

**Acceptance criteria:** no target cash is reserved for an unpriced or non-executable name; all omissions have explicit reasons.

### EPIC LOW-PIT-06 — Durable rebalance evidence and reconciliation

**Goal:** make every PIT rebalance reproducible and explainable.

Tasks:

- [ ] Persist PIT universe/as-of and factor as-of.
- [ ] Persist research selection and factor ranks.
- [ ] Persist dynamic-enrollment outcomes.
- [ ] Persist executable set and targets.
- [ ] Tie orders/fills to the stable rebalance ID where supported.
- [ ] Produce end-of-rebalance reconciliation: research selected vs executable vs broker positions.
- [ ] Block `rebalance_completed` if unexplained discrepancies remain.

**Acceptance criteria:** an operator can explain every symbol difference using stored evidence only.

### EPIC LOW-PIT-07 — Historical / deterministic conformance harness

**Goal:** prove the new resolver changes only execution eligibility, not research selection.

Tasks:

- [ ] Choose multiple historical LOW-001 rebalance dates, including at least one date where PIT membership differs from the static registration list.
- [ ] Reconstruct PIT-200 and research-selected quintile for each date.
- [ ] Run the new code in dry-run mode with broker metadata stubbed/frozen.
- [ ] Assert research selection is byte-/set-equivalent to the pre-change selection logic.
- [ ] Assert newly eligible unregistered names enter the executable set when broker-valid.
- [ ] Assert existing statically registered names behave unchanged.
- [ ] Assert no symbol outside the research-selected set becomes a buy target.

**Acceptance criteria:** zero unexplained differences across all test dates.

### EPIC LOW-PIT-08 — Failure and restart tests

**Goal:** prove dynamic PIT does not weaken v1.0.1 recovery behavior.

Tasks:

- [ ] Restart after `rebalance_started` before plan completion.
- [ ] Restart after sells but before buys.
- [ ] Restart after partial fills.
- [ ] Simulate broker asset lookup failure.
- [ ] Simulate missing price for a selected new PIT name.
- [ ] Simulate order rejection for a dynamically enrolled name.
- [ ] Prove retry reconciles broker state and does not duplicate completed orders.

**Acceptance criteria:** no test leaves an unexplained partial book or falsely marks the week complete.

### EPIC LOW-PIT-09 — Paper deployment and observation

**Goal:** enable v1.0.2 on Account 6 only after conformance gates pass.

Tasks:

- [ ] Capture pre-deploy Account 6 version/config/equity/positions and current week state.
- [ ] Deploy v1.0.2 without modifying Account 5.
- [ ] Confirm runtime identity/version after restart.
- [ ] Confirm no spurious rebalance is triggered outside authorized recovery/rebalance conditions.
- [ ] On the first governed weekly rebalance, capture PIT-200, selected set, dynamic enrollments, orders, fills, and final broker positions.
- [ ] Reconcile final positions to the executable target set with zero unexplained differences.
- [ ] Mark the post-v1.0.2 performance window as observation only unless a separate research protocol says otherwise.

**Acceptance criteria:** Account 6 executes a true PIT-derived book; every deviation is evidence-backed; Account 5 is untouched.

---

## 9. Test matrix

| Test ID | Scenario | Required result |
|---|---|---|
| PIT-T01 | Selected symbol is statically registered | Same behavior as current execution |
| PIT-T02 | Selected symbol is unregistered but active/tradable | Dynamically enroll and allow buy target |
| PIT-T03 | Selected symbol is unregistered and non-fractionable | Allow target; OrderRouter floors quantity |
| PIT-T04 | Selected symbol cannot be resolved at broker | Exclude with explicit reason; no substitution |
| PIT-T05 | Selected symbol is inactive/untradable | Exclude with explicit reason; no substitution |
| PIT-T06 | Selected symbol has no valid price | Drop before equal weighting; reweight remaining executable set |
| PIT-T07 | Held symbol leaves selected quintile | Sell/reduce remains allowed |
| PIT-T08 | Held symbol leaves PIT-200 entirely | Sell/reduce remains allowed |
| PIT-T09 | Factor store stale | `factor_stale_hold`; no new orders |
| PIT-T10 | Backend restarts after rebalance start | Resume/reconcile same rebalance |
| PIT-T11 | Backend restarts after sells before buys | Recover without duplicate sells and finish/record failure explicitly |
| PIT-T12 | Two dispatch callbacks in same process/week | Storm guard prevents duplicate logical rebalance |
| PIT-T13 | Static strategy sees unregistered symbol | Existing static safety behavior unchanged |
| PIT-T14 | Same inputs run twice in dry-run | Identical selected set and target plan |
| PIT-T15 | Final broker set differs from target | Completion blocked or discrepancy explicitly unresolved/failed |

---

## 10. Pull request structure

Preferred implementation is a small series of reviewable PRs. If repository mechanics require one PR, preserve these commits/sections logically.

### PR A — Capability and resolver scaffolding

- Universe mode/capability.
- Registration-boundary characterization.
- Resolver interface and evidence types.
- No Account 6 activation.

### PR B — Dynamic eligibility + exit invariants

- Broker asset resolution.
- Dynamic enrollment.
- Held-position sell invariant.
- Static-strategy regression tests.

### PR C — Target/reconciliation integration

- Executable-set construction.
- Dynamic PIT target planning.
- Evidence/reconciliation.
- Restart/failure tests.

### PR D — LOW-001 v1.0.2 activation record

- Version bump/config authorization for LOW-001 only.
- Deployment/runbook updates.
- No economic parameter changes.

Each PR must explicitly state that LOW-001 remains **Diversifier (B)** and that this work is conformance/execution engineering, not strategy optimization.

---

## 11. Deployment gates

Dynamic PIT must not deploy to Account 6 until all gates below are satisfied.

### G0 — v1.0.1 boundary is established

- v1.0.1 merged/deployed independently.
- Account 6 runtime identity is proven.
- Stale live `params_json` cleanup is completed/recorded as planned.

### G1 — Static-strategy regression

- All static-universe strategies preserve current registration enforcement.
- Account 5 behavior/code path is unchanged.

### G2 — Research-selection conformance

- Historical dry-runs prove the selected LOW-001 quintile is unchanged by the dynamic execution work.

### G3 — Dynamic enrollment correctness

- At least one test fixture contains an unregistered but PIT-selected valid name and proves it becomes executable.

### G4 — Exit safety

- Held names remain sellable after leaving both the selected set and PIT universe.

### G5 — Failure/restart safety

- Restart, broker lookup failure, missing price, rejection, and partial-fill cases pass.

### G6 — Reconciliation

- Dry-run/test broker target reconciliation has zero unexplained symbol differences.

### G7 — Paper-only first activation

- v1.0.2 is activated on Account 6 PAPER only.
- No production/live-money authorization is implied.

---

## 12. Rollback plan

Rollback must restore **execution eligibility behavior**, not rewrite observed evidence.

If v1.0.2 shows a correctness defect:

1. Stop new LOW-001 rebalance dispatch if needed.
2. Preserve broker positions and all v1.0.2 evidence.
3. Roll strategy runtime back to the last known-good v1.0.1 artifact/config.
4. Keep risk-reducing sells available for any positions introduced by v1.0.2.
5. Do not delete dynamically introduced positions merely to recreate the old static universe; reconcile them explicitly.
6. Record rollback reason and affected rebalance ID/week.
7. Resume only after the defect is reproduced and corrected.

A rollback must never make a dynamically introduced held symbol unsellable.

---

## 13. Operational observability

At minimum, add or preserve counters/log fields sufficient to answer:

- How many PIT names were considered?
- How many had valid factors?
- How many were selected?
- How many selected names were not statically registered?
- How many were dynamically enrolled?
- How many failed broker validation, and why?
- How many failed price validation?
- How many target names were executable?
- How many exits/additions occurred?
- Was the rebalance completed or recovered after restart?
- Are there any unexplained target-vs-broker discrepancies?

Suggested event names (adapt to existing signal conventions):

```text
pit_universe_resolved
pit_dynamic_enrolled
pit_asset_not_found
pit_asset_inactive
pit_asset_not_tradable
pit_price_unavailable
pit_execution_set_built
pit_reconciliation_complete
pit_reconciliation_mismatch
```

Avoid excessive per-dispatch-loop duplication; events should be associated with the stable rebalance ID.

---

## 14. Explicit non-goals

This work must **not** include:

- news/catalyst inputs;
- SIP-driven intraday selection;
- mid-week rotation;
- changes to 252-day realized-vol calculation;
- changes to the lowest-quintile rule;
- volatility targeting;
- sector tilts/caps unless already part of frozen LOW-001 V1;
- adding a new SPY regime filter;
- optimization based on August paper P&L;
- repair of HON / 7/27 historical cost basis;
- changes to Account 5 sector rotation;
- upgrading LOW-001's research verdict.

Any such proposal is a separate research/design decision and must not ride inside the dynamic-PIT conformance PR.

---

## 15. Definition of Done

Dynamic PIT execution is complete only when **all** of the following are true:

- [ ] LOW-001 explicitly declares/uses the approved dynamic-PIT universe capability.
- [ ] Existing strategies remain static by default.
- [ ] PIT-200 is reconstructed from the governed point-in-time universe each rebalance.
- [ ] The 252-session realized-vol selection is unchanged from frozen LOW-001 V1.
- [ ] A selected, broker-valid symbol can be bought even if absent from the original registered list.
- [ ] A held symbol can be sold after leaving the selected set or PIT universe.
- [ ] No missing/inactive/untradable/unpriced name is silently substituted.
- [ ] Dead legs are excluded before equal-weight sizing.
- [ ] Factor freshness and durable week/restart controls remain enforced.
- [ ] Every selected-to-executable difference is recorded with a reason.
- [ ] Final broker positions reconcile to the executable target set with zero unexplained discrepancies.
- [ ] Historical/dry-run tests pass.
- [ ] Restart/failure tests pass.
- [ ] Static-strategy regression tests pass.
- [ ] v1.0.2 deployment is isolated to Account 6 PAPER.
- [ ] Post-deploy observation is clearly separated from the sealed pre-remediation benchmark.
- [ ] LOW-001 remains classified **B (Diversifier)** unless a separate governed research process changes that verdict.

---

## 16. Developer execution order

Developers should work in this order:

1. **Map registration dependencies** (`LOW-PIT-01`).
2. **Add opt-in universe capability** (`LOW-PIT-02`).
3. **Implement dynamic broker symbol resolution/enrollment** (`LOW-PIT-03`).
4. **Prove held-position exits cannot be blocked** (`LOW-PIT-04`).
5. **Integrate executable-set equal weighting** (`LOW-PIT-05`).
6. **Add evidence/reconciliation** (`LOW-PIT-06`).
7. **Run historical deterministic conformance tests** (`LOW-PIT-07`).
8. **Run restart/failure tests** (`LOW-PIT-08`).
9. **Only after G0-G7 pass, activate v1.0.2 on Account 6 PAPER** (`LOW-PIT-09`).

The first developer deliverable should therefore be **the registration dependency map plus a proposed code touch-point list**, not an immediate bypass of the registration check.

---

## 17. Implementation contracts and code boundaries

The names below are recommended interfaces, not mandatory filenames. Developers may adapt them to the existing architecture, but the **direction of dependencies is mandatory**: ranking may not depend on broker registration, and execution eligibility may not change the research-selected set.

### 17.1 Core data contracts

Recommended immutable records:

```text
PITUniverseSnapshot
  rebalance_id
  pit_as_of
  members[]
  source_version / source_hash (when available)

LowVolSelection
  rebalance_id
  factor_as_of
  ranked[] = {symbol, realized_vol, rank}
  selected[]

ExecutionEligibility
  symbol
  selected = true
  was_registered
  was_held
  broker_resolved
  active
  tradable
  fractionable
  price_status
  enrollment_status
  exclusion_reason

TargetPlan
  rebalance_id
  executable_symbols[]
  target_weight_by_symbol
  target_qty_by_symbol
  planned_actions[]
```

These records should be immutable once the corresponding rebalance reaches `rebalance_completed`. Corrections should be additive evidence, not destructive rewrites.

### 17.2 Required function boundaries

Equivalent behavior should exist for the following interfaces:

```python
pit = pit_universe_provider.universe_asof(
    as_of=expected_pit_session,
    n=200,
)

selection = low_vol_selector.select(
    pit_universe=pit,
    factor_as_of=expected_factor_session,
)

eligibility = dynamic_symbol_resolver.resolve(
    strategy_id=8,
    rebalance_id=rebalance_id,
    selected_symbols=selection.selected,
    held_symbols=current_positions,
    universe_mode="DYNAMIC_PIT",
)

target = target_builder.build_equal_weight(
    selected=selection.selected,
    eligibility=eligibility,
    equity=current_equity,
    cash_buffer=configured_cash_buffer,
)

result = execution_reconciler.execute_or_recover(
    rebalance_id=rebalance_id,
    target=target,
    broker_state=current_broker_state,
)
```

### 17.3 Forbidden dependency directions

The following are implementation errors:

```text
LowVolSelector -> registered symbol list
LowVolSelector -> broker asset status
PITUniverseProvider -> current broker holdings
DynamicSymbolResolver -> change factor rank
DynamicSymbolResolver -> choose next-ranked substitute
OrderRouter -> infer research selection
```

The selector answers **what LOW-001 wants**. The resolver/target builder answers **what can safely be executed**. Evidence must preserve both sets.

### 17.4 Idempotency contract

For the same `rebalance_id` and unchanged governed inputs:

- PIT universe reconstruction must be deterministic.
- Research selection must be deterministic.
- Dynamic enrollment must not create duplicate durable rows/signals.
- A retry may reconcile changed broker state, but must not create a second logical weekly rebalance.
- `rebalance_completed` must be emitted at most once for a successful logical rebalance.

---

## 18. Ticket-level implementation backlog

The epics in section 8 define the workstream. The table below is the recommended developer ticket breakdown and execution order.

| Ticket | Priority | Depends on | Developer deliverable | Done when |
|---|---:|---|---|---|
| `LOW-PIT-00` | P0 | None | Freeze v0.2 design reference and branch from the intended base commit | PR/branch records exact base SHA; no v1.0.1 code is accidentally rebased away |
| `LOW-PIT-01A` | P0 | 00 | Registration dependency map | All consumers of registered symbols are identified |
| `LOW-PIT-01B` | P0 | 01A | Sell-path audit | Proves held-position reduce/sell path and every membership check on it |
| `LOW-PIT-02A` | P0 | 01A | `STATIC` / `DYNAMIC_PIT` capability | Default is `STATIC`; LOW-001 candidate explicitly opts in |
| `LOW-PIT-02B` | P0 | 02A | Static-strategy regression tests | Account 5 and other static strategies show no changed eligibility behavior |
| `LOW-PIT-03A` | P0 | 01A,02A | Dynamic resolver with broker metadata lookup | Valid unregistered selected symbol resolves to eligible |
| `LOW-PIT-03B` | P0 | 03A | Durable enrollment/exclusion evidence | Every selected symbol has an explicit execution outcome |
| `LOW-PIT-04A` | P0 | 01B,03A | Exit invariant implementation | Held symbol remains sellable after leaving PIT/selection |
| `LOW-PIT-05A` | P1 | 03A | Price eligibility stage | Unpriced selected names are explicitly excluded before sizing |
| `LOW-PIT-05B` | P1 | 05A | Equal-weight executable target builder | Weights are recomputed across executable names only |
| `LOW-PIT-06A` | P1 | 03B,05B | Stable rebalance evidence model | PIT -> selection -> eligibility -> target is reconstructable |
| `LOW-PIT-06B` | P1 | 06A | End-state reconciliation | Zero unexplained target/broker symbol differences before completion |
| `LOW-PIT-07A` | P1 | 05B,06A | Historical dry-run fixtures | Includes dates with unregistered PIT entrants |
| `LOW-PIT-07B` | P1 | 07A | Determinism/conformance assertions | Research-selected sets unchanged; only execution eligibility differs |
| `LOW-PIT-08A` | P1 | 06B | Restart/partial-fill fault tests | Recovery does not duplicate orders or strand unexplained partial books |
| `LOW-PIT-09A` | P1 | G0-G6 | LOW-001 v1.0.2 activation change | Account 6 only; PAPER only; exact runtime identity captured |
| `LOW-PIT-09B` | P1 | 09A | First governed paper-rebalance closeout | PIT-selected, executable, orders/fills, and broker positions reconcile |

### Ticket rules

- A P0 ticket may block all later implementation even if tests are green elsewhere.
- `LOW-PIT-09A` must not merge into an Account 6 deployment path until G0-G6 are recorded as satisfied.
- A ticket may be split further, but its acceptance condition may not be weakened.
- Any discovery that dynamic symbol enrollment requires changing factor/ranking economics is a **STOP** and requires a new design decision.

---

## 19. Persistence, migration, and compatibility rules

### 19.1 Reuse before creating new tables

Prefer existing strategy signal/evidence and order-reconciliation tables if they can represent the required fields without ambiguity. Create a schema migration only when the current persistence model cannot durably answer the required reconstruction questions.

### 19.2 If a new persistence object is required

Use a stable key equivalent to:

```text
(strategy_id, rebalance_id, symbol)
```

and make dynamic enrollment/upsert idempotent. Recommended logical fields:

```text
strategy_id
strategy_version
rebalance_id
rebalance_week
pit_as_of
factor_as_of
symbol
research_selected
was_registered
was_held
broker_status
fractionable
price_status
enrollment_status
exclusion_reason
created_at
updated_at
```

Do not use mutable symbol-registration rows as the only evidence that a symbol was dynamically eligible for a historical rebalance.

### 19.3 Backward compatibility

- Missing `universe_mode` on an existing strategy must resolve to `STATIC`.
- No database migration may auto-convert existing strategies to `DYNAMIC_PIT`.
- Dynamic enrollment records must not alter ownership/attribution of positions held by other strategies/accounts.
- Existing order-router handling for non-fractionable assets remains authoritative unless a separate router defect is found.

### 19.4 Evidence immutability

After `rebalance_completed`, do not rewrite the historical selected/executable sets merely because a later broker sync or P&L observation changes. Reconciliation corrections must be separate, timestamped evidence.

---

## 20. Recommended branch / PR / merge sequence

The safest implementation sequence is:

```text
main / approved base
  |
  +-- LOW-001 v1.0.1 conformance repair -----------------> merge/deploy boundary
  |
  +-- dynamic-pit/scaffold
       -> PR A: capability + dependency map + static regressions
       -> PR B: resolver + exit safety
       -> PR C: target/reconciliation + fault tests
       -> PR D: LOW-001 v1.0.2 activation record
```

Dynamic-PIT engineering may begin before the v1.0.1 paper deployment is complete, but developers must keep the branches/reviews separable. Before PR D activates Account 6, rebase/retarget against the exact approved post-v1.0.1 base and rerun all conformance tests.

### Merge protection requirements

Every PR should state:

- no LOW-001 economics changed;
- no Account 5 change;
- no live-money authorization;
- whether persistence schema changed;
- static-strategy regression status;
- exact test commands/results;
- any new event/signal names;
- any remaining open drift.

---

## 21. First implementation tranche — start here

Developers should begin immediately with the following bounded tranche. **Do not begin by removing the registration check.**

### Task 1 — Establish exact code touch points

Produce a one-page dependency map covering:

1. where LOW-001 obtains `symbols` / registered universe;
2. where `universe_asof(n=200)` is called;
3. where factor scores are joined to symbols;
4. where buy targets are filtered by registration;
5. where held-position sells are authorized;
6. where price subscriptions/quotes are initialized;
7. where broker asset metadata is fetched/cached;
8. where order ownership/strategy attribution is enforced;
9. where `_last_rebalance_week` / durable signals participate in dispatch/recovery;
10. where end-of-rebalance completion is recorded.

**Deliverable:** code-path document plus file/function list attached to PR A.

### Task 2 — Write characterization tests before behavior change

Add tests that reproduce the current gap:

```text
Given: XYZ is in PIT-200 and selected by LOW-001
And: XYZ is absent from static registration
And: XYZ is active/tradable at the broker
Current expected behavior: selection contains XYZ, execution omits XYZ and records pit_name_not_registered
```

Also add the safety control:

```text
Given: ABC is currently held by LOW-001
And: ABC is no longer in PIT-200
Expected behavior: sell/reduce remains permitted
```

These tests become the before/after proof for the resolver change.

### Task 3 — Add universe capability with no activation

Introduce `STATIC` / `DYNAMIC_PIT` (or equivalent), default `STATIC`, with tests. **Do not yet switch Account 6 to dynamic mode in the same commit.**

### Task 4 — Review checkpoint

Before implementing dynamic enrollment, reviewer must confirm:

- registration is not secretly required for position attribution or risk controls in a way the proposed resolver would bypass;
- the sell path is understood;
- static strategies remain isolated;
- no new research-selection logic has appeared.

Only after this checkpoint should `LOW-PIT-03A` begin.

---

## 22. Developer handoff checklist and stop conditions

Before claiming the work implementation-ready for Account 6, the developer/reviewer pair must be able to answer **yes** to all of these:

- [ ] Can we show the exact PIT-200 membership used for a rebalance?
- [ ] Can we show the exact LOW-001 research-selected quintile before execution filtering?
- [ ] Can a newly selected valid symbol be bought without permanent strategy re-registration?
- [ ] Can a held symbol always be reduced/sold after it leaves PIT membership?
- [ ] Does every selected-but-not-executed symbol have one explicit reason?
- [ ] Are equal weights calculated only after broker/price eligibility is known?
- [ ] Is the logical weekly rebalance idempotent across process restart?
- [ ] Are static strategies behaviorally unchanged?
- [ ] Can we reconstruct the final broker book from stored target/order/fill evidence?
- [ ] Is Account 6 activation still PAPER-only and version-bound?

### Mandatory STOP conditions

Stop implementation and escalate for design review if any of the following is discovered:

1. Dynamic enrollment would require changing the 252-session factor, quintile rule, weighting, or weekly cadence.
2. The only way to buy a dynamic symbol would bypass strategy ownership/risk attribution globally.
3. A held symbol can become unsellable because it left registration/PIT membership.
4. The system cannot distinguish a retry of the same rebalance from a new rebalance.
5. The resolver would need to silently substitute a different symbol to keep the book near 40 names.
6. A schema migration would overwrite or reinterpret sealed pre-remediation evidence.
7. Dynamic behavior cannot be restricted to LOW-001/explicit `DYNAMIC_PIT` strategies.

---

## 23. Final implementation ruling
**Authorized engineering direction:** Begin dynamic PIT implementation now as a separate LOW-001 conformance workstream under this v0.2 developer contract. Keep v1.0.1 isolated and deployable on its own. Build v1.0.2 so the weekly LOW-001 research-selected PIT universe can become the true execution universe through an explicit, auditable, fail-closed dynamic enrollment mechanism.

**Do not change the strategy economics. Do not weaken static registration for other strategies. Do not treat post-change P&L as validation.**
