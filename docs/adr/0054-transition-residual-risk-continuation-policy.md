# ADR 0054 — Transition Residual-Risk Continuation Policy

**Status:** Accepted (owner rulings 2026-08-21) · **amended the same day — v2.1, see §10**
**Date:** 2026-08-21
**Scope:** The Strategy 9 / account 7 staged transition executor (v13). Governs stage
**continuation** only. It changes no order-level gate.
**Supersedes:** the stage-continuation clauses of frozen execution limits v5.
**Related:** ADR 0002 (single OrderRouter) · ADR 0005 (activation cooldowns) ·
ADR 0042 (risk gate trapping risk) · ADR 0053 (strategy performance epochs)

---

## Context

The v13 transition executes in three ordered stages — `A_exits` (de-risk), `B_cross_asset`
(build the sleeve), `C_equity` (build the equity book). Each order passes governed
market-data gates: a 300-second single-stock trade-age limit, a 10-second cross-asset
quote-age limit, a 25 bps half-spread cap, a 1.5 % manifest-price drift collar, a bounded
transient re-poll, K=2 attempts with a 120-second fill window, broker-authoritative
terminality, the identity latch and the risk engine.

Those gates work. On 2026-08-20 they correctly refused two thin single names.

What did not work was the rule deciding whether the **transition** continues after an
individual order is refused. Frozen limits v5 expressed it as:

```
more than 3 gate aborts within one stage
gates failing on more than 10% of a stage's TOTAL order count
cumulative stage residual exceeding the residual tolerance ($250/stage)
```

Three live events exposed three separate defects in that rule.

### D1 — the abort clauses mix units

`v13_transition_executor_v7.py:499–506` took its abort count from
`ResidualLedger.attempt_opportunities()`, which counts **attempt records**, and compared it
against `0.10 × stage_order_count`, an **order** count. `attempt_policy.max_attempts` is 2,
so one failing order contributed 2.

The practical meaning of `aborts > 3` was therefore **"more than 1.5 failing orders"** —
**two failing orders halted a stage of any size**, 6 orders or 80.

Measured live on 2026-08-20 (manifest `45082b68…`, Stage A, 36 planned orders): exactly
**two** orders failed — MS (seq 20) and PH (seq 34) — producing **four** abort records and
halting the stage at a **5.9 % order-level failure rate**, after 32 exits had filled. EBAY
(seq 35) and FN (seq 36) were **never attempted**; the stage stopped before reaching them.

### D1b — dry runs could not predict live decisions

Dry mode called `core.gate()` once per order and wrote nothing to the residual ledger. A
dry run therefore logged **1** abort per failing order where live logged **2**, and dry and
live could return *different* continuation decisions for *identical* failing orders. The
dry run 23 minutes before the halt reported one abort and adjudicated admissible.

### D2 — stage-denominator collapse

The 10 % clause is denominated on the current manifest's stage. After a partial transition,
a fail-closed re-plan regenerates from the post-fill book, so the stage shrinks and the
tolerance shrinks with it. `A_exits` went 36 → 4 → 5 orders; at 5 orders the first failing
order is 20 % and stage-fatal. Waiting a day for fresh data added one name and restored no
tolerance. On 2026-08-21, **$757.28 of residual exits gated ~$27,941 of construction**.

### D3 — small stages inherited zero tolerance by arithmetic

`B_cross_asset` is structurally 6 orders. `6 × 10 % = 0.6 < 1`, so it had always tolerated
zero aborts. That may be the right policy, but it was an accident of integer arithmetic,
written down nowhere and therefore unreviewable.

### The conflation underneath all three

The protocol answered one question where there are two:

1. *Is this individual order safe enough to submit?* — the order-level gates. Working.
2. *Does the failure of this individual order make continuing the whole transition unsafe?*
   — answered by counting aborts. Not working.

A thin single name can correctly fail (1) without making $24 k of cross-asset construction
unsafe.

---

## Decision

Adopt a **per-stage continuation policy, declared in the sealed limits file and resolved
into every manifest at plan time**, so the owner approves the *rule* together with the
*orders* it governs.

### 1. Counting unit

Continuation counts **failed logical orders**, never attempt records. One order × two
failed attempts is **one** failed order. Retries are execution mechanics and must not
multiply the economic failure count.

Dry-run adjudication evaluates the **same** logical-order semantics as live: dry mode
records an imputed order disposition per gate-refused order, valued at the reviewed
manifest reference and flagged `imputed: true`, into the `.dryrun` ledger. A dry
adjudication that would continue where live would halt, or the reverse, is a defect.

### 2. Failure taxonomy

| class | codes | rule |
|---|---|---|
| **HARD** | `risk_refusal`, `broker_http_error`, `identity_mismatch`, `terminality_unestablished`, `reconciliation_mismatch`, `unknown_order_state` | Immediate `HALTED_REQUIRES_REVIEW`, regardless of economics. Never receives a residual budget — one is enough. |
| **EXECUTABILITY** | `stale_reference`, `spread_failure`, `manifest_drift_failure`, `no_usable_print_or_quote`, `other_governed_gate` | The individual order is **refused and never force-submitted**. Continuation is decided on the economic residual left behind. |

An unrecognised abort code classifies as **HARD** — fail closed. A failure nobody has
adjudicated is never budget-eligible.

**Taxonomy governance.** An `EXECUTABILITY` code is *budget-eligible*: it is the class that
lets a transition continue on the economics of what it left behind. Adding a code to that
class therefore requires a governed change — a new limits version and an ADR-compatible
amendment — never a silent edit. Widening the class one code at a time is how a fail-closed
taxonomy quietly becomes fail-open.

This is enforced, not merely stated: the limits **declare** both code sets, the executor
**holds** them as code, and it refuses any limits file whose declaration differs from what
it applies. Changing either side without the other is a refusal, so the declaration and the
behaviour cannot drift.

### 3. Residual-risk budget

```
effective budget = max(R_ABS, R_PCT × pre-run equity)
R_ABS = $250        R_PCT = 0.0
```

**`R_PCT = 0` for Protocol v2.x unless changed by a later owner ruling and a new limits
version.** No percentage threshold is invented without evidence. A later calibration may
introduce one; the decision is not v2.0's alone, and restating it here keeps the governing
document from reading as though it belonged to a superseded version.

`R_ABS = $250` has two independent anchors that both **predate** the 2026-08-20 incident:
it is the frozen `residual_policy.tolerance_usd_per_stage` ratified 2026-07-29 (itself
≈ 2× the ~$127 modelled worst-stage residual at K=2 in `v13_reattempt_simulation.json`),
and it is exactly 5.0 % of account 7's $5,000 `max_daily_loss` limit. It is not read off
either of the residuals it now governs.

### 4. Concentration trigger

When a **joint-construction** stage's largest single order is **≥ 50 %** of stage notional,
that stage is declared `completeness_required = true` in the hashed manifest: any failed
logical order halts it. Its legs are sized against one another, so a partial stage is a
*different* allocation, not a smaller one.

> **Amended the same day (v2.1, §10).** As first ruled, the trigger applied to all three
> stages. It is now scoped to stages declared `joint_construction: true`, which in v2.1 is
> `B_cross_asset` alone. The share is still measured and disclosed for every stage, for
> observability; only the completeness *consequence* is scoped.

**Stage B is not hard-coded to 6/6.** The trigger derives it: UUP was 65.4 % of Stage B on
2026-08-21. If the sleeve ever grows to a dozen names with no dominant leg, the policy
adapts on its stated reason instead of silently flipping when `12 × 10 % ≥ 1`.

**`joint_construction: true` alone does not imply completeness.** Completeness is activated
only when the declared concentration trigger is also met. A joint-construction stage whose
largest leg is below the threshold falls back to the residual budget and the backstop like
any other stage — being an interdependent sleeve does not, by itself, make a stage
all-or-nothing.

### 5. Per-stage policy

| stage | joint construction | mode | budget | backstop | count rule |
|---|---|---|---|---|---|
| `A_exits` | no | residual budget | $250 | 2 failed orders | — |
| `B_cross_asset` | **yes** | residual budget, + completeness when concentration ≥ 50 % | $250 | 2 failed orders | — |
| `C_equity` | no | residual budget **and** count | $250 | 3 failed orders | `max(floor 2, ⌊10 % × n⌋)` |

**Every applicable condition must hold; a backstop is never an allowance on its own.**
For `A_exits`, continuation requires both residual exposure ≤ $250 **and** failed logical
orders ≤ 2; neither condition overrides the other. Two failures totalling $260 halt on the
budget even though the count is within tolerance, and three failures totalling $150 halt on
the backstop even though the residual is within budget. The table above is what an operator
reads first, so it must not be read as "2 failures are allowed".

Stage C keeps the 10 % rule and takes backstop **3** rather than 2 so the count rule stays
meaningful: with 36 orders, three economically small failures may continue and the fourth
halts.

### 6. Evaluation order

1. HARD failure → halt (raised at the point of failure)
2. `completeness_required` → halt if any logical order failed (**joint-construction stages only**)
3. residual budget → halt if the stage residual exceeds the budget
4. absolute backstop → halt if too many logical orders failed
5. count rule (`residual_budget_and_count` only)
6. stage timeout — unchanged from v5

**All applicable conditions must remain satisfied.** The first binding condition names the
halt; no rule is subordinate to, or disabled by, another. Where two overlap the stricter
binds — at a 36-order Stage C the backstop (3) and the count rule (`max(2, ⌊0.10 × 36⌋)` = 3)
coincide, while on a five-order Stage C the count rule (2) is stricter and binds first. The
manifest must disclose every applicable threshold per stage and the executor must report the
actual binding clause.

### 7. Residual operational debt

A **permitted** residual creates a first-class `RESIDUAL_CLEANUP_REQUIRED` obligation
carrying: strategy and account, originating manifest run-id and SHA-256, symbol, residual
quantity, governed residual valuation and valuation price, abort reason and failure class,
originating stage, timestamp, target disposition and status.

The obligation is **keyed by the originating manifest, never by the symbol's current
status**, and is carried into subsequent planning. It must never disappear because the
symbol later re-enters the target universe — the planner sizes from *current* holdings, so
without this a name that failed to exit is indistinguishable from a name we still want.
The conflict is not hypothetical: TSM was exited 2026-08-20 and bought back 2026-08-21. The
planner therefore emits an explicit `conflicts_with_this_target` list.

Cleanup rule: re-evaluate at the next eligible trading session and incorporate explicitly
into the next governed rebalance or cleanup plan. It may remain outstanding only while it
continues to satisfy the residual-risk budget. It must **not** trigger an ungoverned manual
trade, and must **not** automatically block `/start` when the amended protocol explicitly
permits that residual. The C40 epoch-boundary record (ADR 0053) must **disclose** any
residual operational debt present at activation.

**Lifecycle.** An obligation starts `OPEN` and leaves it only into an explicit terminal
status, and only by an appended event — the `OPEN` event is never rewritten:

| status | meaning |
|---|---|
| `RESOLVED_FILLED` | the intended trade completed under a later governed plan |
| `RESOLVED_TARGET_REENTERED_WITH_OWNER_ACCEPTANCE` | the symbol re-entered the target universe and the owner accepted keeping it |
| `SUPERSEDED_BY_NEW_GOVERNED_PLAN` | a later governed plan replaced the obligation |
| `ESCALATED` | raised for a decision rather than discharged |

**Target re-entry does not close an obligation.** It requires the explicit
`RESOLVED_TARGET_REENTERED_WITH_OWNER_ACCEPTANCE` status *and* a recorded owner-acceptance
reference. Silent closure on re-entry is exactly the disappearance this ledger exists to
prevent: the position stops being a residual we owe a decision on and starts looking like a
position we chose. `close()` has no default status and refuses that status without an
acceptance reference; the planner reports the conflict and never closes it.

A **halted** stage mints no obligation: its residual is disclosed in the receipt and goes to
owner review, which is a stronger control. Minting debt for a run under review would imply
the residual had been accepted when it has not.

### 8. The "every individual gate must PASS" owner override is retired

Replaced by: hard/global gates must all PASS · order-level HARD failure halts immediately ·
EXECUTABILITY failure refuses that order, with continuation decided by this policy.

Consequence: a single ~$65 stale-reference failure no longer burns a manifest when the
stage remains admissible. On 2026-08-20 manifest `30a53127…` was retired over one ALAB
abort worth $65.07 — the executor's own stop conditions were never tripped. The override
layered an undocumented zero-tolerance rule above the governed executor; this aligns the two.

### 9. The manifest discloses the rule; it never confers it

The planner resolves the policy from the sealed limits into the hashed manifest body
(`continuation_policy_resolved`), including each stage's order count, notional, largest
order and its share, the derived `completeness_required`, the budget and the tolerated
failure count. **The executor re-derives that block from the sealed limits and refuses any
manifest whose disclosed rule differs from the rule it would apply.**

The same principle extends to the limits document itself. It is not enough to compare
derived values: the executor verifies the **sealed limits identity** the manifest claims —
the embedded SHA must equal the sealed file on disk, **and** the embedded content must be
identical to that file — and it then applies the **disk copy**. The SHA is over file bytes
while the embedded content is parsed JSON, so matching one never implied the other. The
binding between manifest, limits version and execution policy is therefore explicit: a
manifest *discloses* the limits it was reviewed under, and can never *supply* the policy
that governs it. The receipt records the limits identity actually applied.

---

## Consequences

### Protocol v2 does not rewrite history

The 2026-08-20 halt **still halts** under v2: Stage A residual reached **$257.27** against
the pre-existing **$250** budget, so the economic clause halts it on its own, independent of
any count. This is asserted as a permanent regression test
(`test_v13_continuation_policy_v1.py`, section H). An amendment that retroactively permitted
the run it was written in response to would be worthless.

### What changes in practice

| case | v1 | v2 |
|---|---|---|
| 2026-08-21 Stage A, 1 failed order ($124–$170) | HALT | CONTINUE |
| 2026-08-21 Stage A, 2 failed orders ($257.04) | HALT | HALT (budget) |
| 2026-08-21 Stage B, SPY fails ($173.96) | HALT (arithmetic) | HALT (**completeness**, declared) |
| 2026-08-21 Stage C, 2 trivial entries ($108.46) | HALT | CONTINUE |
| 2026-08-21 Stage C, 4 trivial entries ($224.94) | HALT | HALT (backstop, inside budget) |
| 2026-08-20 Stage C, ALAB ($65.07) | CONTINUE (but the override burned the manifest) | CONTINUE |
| same 2 failures, dry vs live | HALT live / CONTINUE dry | identical decision and clause |

### What does not change

Every order-level gate. Limits v6 is byte-identical to v5 across `quote_gates`,
`attempt_policy`, `transient_staleness_repoll`, `order_policy`, `residual_policy`,
`stage_limits`, `market_data_regime`, `attempt_states`, `rollback_doctrine`,
`stop_conditions_halt_requires_review`, `evidence_basis_and_limitations`, `amendment_v4`,
`amendment_v5` and `ratification_language` — asserted by the builder and re-asserted by
executor v8 at load. **The 300-second stale-reference rule is not changed.**

The five fixes forbidden on 2026-08-20 remain forbidden: changing the 10 % denominator as a
point fix, reordering stages, excluding names, extending the 300 s threshold, and manually
forcing the downstream buys.

### The v2.1 correction — the concentration trigger is scoped

The version of this ADR accepted earlier the same day declared the 50 % trigger for all
three stages. That re-created the pathology the ADR exists to remove: a Stage A collapsing
to one or two residual exits became `completeness_required` and zero-tolerance again, and a
one-order Stage A halted on a **$124.47** residual — half the budget — purely because one
order is, mathematically, 100 % of its own stage.

**Owner ruling, same day:** *"Concentration-triggered completeness applies only to stages
whose semantics are joint-construction completeness sensitive; for v2.0 that means
`B_cross_asset` only. It does not apply to `A_exits` or `C_equity`."*

The reasoning is the ADR's own: `A_exits` is a de-risking stage governed by a residual-risk
budget, while the concentration trigger was justified because a joint construction becomes a
materially different allocation when one dominant leg is missing. Exits are independent — a
refused exit leaves one measurable legacy position; it does not make the remaining exits a
different plan.

Behaviour after the correction, for a one-order Stage A with a $124 residual: the
stale-reference gate still **refuses** the order · the residual is **recorded** · $124 < $250
· failed logical orders 1 ≤ backstop 2 · therefore Stage A may **complete with disclosed
operational debt**. Two failed Stage-A orders totalling more than $250 still halt on the
economic budget. Stage B is unaffected: UUP at 65.4 % still makes it completeness-required.

Enforcement: `joint_construction` is a per-stage declaration in the sealed limits, and the
executor **refuses any limits file in which the joint-construction set is not exactly
`["stage_B_cross_asset"]`** — widening it is what re-creates the pathology, so it is a
refusal rather than a configuration choice. A limits file lacking `joint_construction` or
`precedence_rule` is the v2.0 shape and is refused.

### Stage C precedence — declared, not emergent

`N_BACKSTOP` and the Stage C count rule overlap. Per the same ruling, both apply: all
applicable conditions must remain satisfied, the first binding one names the halt, and no
rule is subordinate to or disabled by another. At 36 orders they coincide at 3 tolerated
failures; on a five-order Stage C the count rule allows 2 against a backstop of 3, and the
count rule binds and is named as the binding clause. The manifest discloses both thresholds.

---

## Implementation

| artifact | status |
|---|---|
| `v13_frozen_execution_limits_v8.json` | **governing** — `continuation_policy` v2.1 + taxonomy governance, debt lifecycle, activation invariants; no numeric order-level gate moved from v5 |
| `v13_continuation_policy.py` | one implementation, imported by planner and executor; v1 bytes preserved as `RETIRED__v13_continuation_policy_v1.py` |
| `v13_residual_debt.py` | append-only ledger with terminal statuses, the re-entry guard and `health()`; v1 preserved as `RETIRED__v13_residual_debt_v1.py` |
| `v13_execution_core_v3.py` | core v2 + failure taxonomy, logical-order counting, dry-parity recording |
| `v13_transition_executor_v10.py` | **governing** — v9 + taxonomy binding, limits identity binding, activation invariants |
| `v13_transition_planner_v8.py` | **governing** — v7 bound to limits v8; discloses every applicable threshold |

Limits v5/v6/v7, executor v7/v8/v9, planner v5/v6/v7 and core v2 are preserved
byte-identical. The identity latch is unchanged.

**Reconformance 2026-08-21 (v2.1 hardened) — all six suites green:** feed-explicit v10
15/15 · executor v10 78/78 · live-fill v10 34/34 · CA re-poll v5 65/65 · regressions ALL
PASS · continuation policy v3 89/89.

Stack identities sealed at
`ws1_evidence/v13/gate_20260821/PROTOCOL_V21_STACK_SEAL_20260821.json`; the superseded v2.0
stack remains sealed at `PROTOCOL_V2_STACK_SEAL_20260821.json`
(body-self `8fed03a3852ae1c5259822e97a54a957697bc8412cd89d43b8c16ca0ddcc257a`).

Evidence: `PROTOCOL_V2_POLICY_REPLAY_20260821.json` ·
`PROTOCOL_V2_THRESHOLD_SWEEP_20260821.json` ·
`docs/design/Transition_Protocol_v2_Residual_Risk_Design_Proposal_v0.1.md`.

---

## 9. Activation invariants

The sections above are design semantics. This is the gate between them and a live run. **No
live transition may begin unless all of the following hold**, and each is fail-closed — an
invariant that cannot be *evaluated* counts as failed:

1. the manifest's `continuation_policy_resolved` matches the policy re-derived from the
   sealed limits;
2. the manifest's embedded limits are identical in content to the sealed limits file, and
   the sealed file is the authority the executor applies;
3. dry-run and live evaluate the same logical-order continuation semantics;
4. the residual-debt ledger is present-or-creatable, append-only and parseable;
5. broker and platform ledger state reconcile, with no unexpected open orders and no drift
   from the manifest's `pre_run_state`;
6. no earlier halted transition remains unresolved — every run whose stage status reached
   `HALTED_REQUIRES_REVIEW` has a sealed disposition record.

These are preconditions for *beginning* a run, not additional stage-continuation rules. They
are declared in `continuation_policy.activation_invariants` and checked in the executor's
preflight; this section states the contract without restating the implementation. Resuming
the *same* run is the sanctioned path and is not blocked by (6).

**Expected side effect — a zero-byte `residual_debt.jsonl`.** Invariant (4) is
*present-or-creatable*, so evaluating it creates the ledger if it does not exist. A 0-byte
`data/ops/acct7/residual_debt.jsonl` with 0 obligations is therefore **normal and healthy**,
and is positive evidence that the executor could establish a writable debt ledger before
execution. It is not unexplained state, and it must not be "cleaned up". The file first
appeared on 2026-08-21 when the invariant was first evaluated, before any live run.

**Owner-visible proof of the limits binding.** The first manifest review under this protocol
must print, side by side, the limits SHA the manifest actually embeds and the sealed limits
SHA the executor expects. They must be equal, and equal to
`3f59ad7143418a926c8110d59c1519c99508b7fc9878c298b1eedb7339306948` (limits v8). That single
comparison is the owner-visible form of invariant (2), and it belongs in the hash-review step
before approval — not after.

---

## 10. Amendment log

| version | date | change |
|---|---|---|
| v2.0 | 2026-08-21 | Initial acceptance. Limits v6, core v3, executor v8, planner v6. Concentration trigger declared for all three stages. |
| **v2.1** | **2026-08-21** | Concentration-triggered completeness **scoped to joint-construction stages** (`B_cross_asset` alone), and Stage C precedence **declared** rather than emergent. Limits v7, continuation policy v2, executor v9, planner v7. No order-level gate, counting unit, taxonomy, budget or threshold value changed; Stage B's outcome is unchanged. |
| **v2.1 hardened** | **2026-08-21** | Owner review pass. Documentation: R_PCT scoped to v2.x, the A_exits dual-condition sentence, `joint_construction` alone ≠ completeness. Enforcement: taxonomy governance, explicit manifest↔limits identity binding, residual-debt terminal statuses with the target-re-entry guard, and the activation invariants (§9). Limits v8, residual debt v2, executor v10, planner v8. **No policy value changed.** |

v2.1 was found by the v2.0 conformance suite itself: an assertion written against a
one-order Stage A fixture failed, which is how the collapsed-stage consequence surfaced
before any live run rather than after one.

---

**No live execution was performed under Protocol v2 or v2.1.** Account 7 remains frozen: 51-position
reconciled book, strategy 9 IDLE v1.4.0, gross cap $100,000, no reload, no `/start`, no C40
epoch, no manual sale of residual names, zero orders. The next live attempt begins in a new
trading session with fresh readiness, fresh reconciliation, and a manifest generated
natively under the frozen v2.1 policy.
