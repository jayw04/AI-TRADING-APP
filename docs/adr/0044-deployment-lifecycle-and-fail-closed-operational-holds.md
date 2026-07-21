# ADR 0044 — Deployment Lifecycle and Fail-Closed Operational Holds

| Field | Value |
|---|---|
| Date | 2026-07-21 |
| Status | **Accepted** (owner accepted 2026-07-21 after four adjudicated invariant refinements) |
| Phase | Cross-phase (P7 §7-A/§7-B — strategy deployment lifecycle; extends the operational-hold discipline of ADR 0043) |
| Supersedes | — |
| Related | 0043 (*loss-control architecture* — the account-level control state machine this ADR's holds sit alongside), 0035 (*operational self-healing* — hold-clear authority), 0005 (*24-hour activation cooldown*), 0002 (*single OrderRouter* — the seed and every order still route through it) |

## Context

On 2026-07-20 the momentum-daily book (account 4) executed its first live rebalance and placed **zero** orders. Investigation found a **cold-start defect**: the strategy's six pre-registered triggers are all *holdings-relative*, and the backstop defers on the first review, so a never-deployed flat book cannot deploy until the backstop matures (~10 trading days) — even though the regime model wants ~98% gross. The book was paused pending a fix.

Fixing the trigger (an explicit one-shot `initial_seed`) forced three deeper questions that are not momentum-daily-specific and that will recur for every governed strategy:

1. **What is the authoritative source of "has this strategy ever deployed"?** The obvious answer — "does it hold positions?" — is wrong on a shared account (a position can come from another strategy, a manual order, or delayed reconciliation) and wrong across restarts (positions lag fills). Inferring inception from holdings is exactly how a re-seed could fire against a book that already deployed, or a deployment could be missed.

2. **How is a paused strategy kept paused?** When the book was paused, the pause was recorded as an operational marker but **not enforced** — any activation path (`/start`, the engine's boot-resume, a provisioning script) could have re-registered it. A hold that is displayed but not enforced is not a hold.

3. **Was the thing we validated the thing we run?** The Stage 2-4 validation drove a *reimplementation* of the selection logic, not the live strategy class. The template's own docstring warns "the two must not drift" — and the cold-start gap is proof that they had. A validation that does not exercise the production code path can certify behavior the production path does not have.

This ADR answers those three questions as **durable invariants** that apply to governed strategies generally, so that the next strategy inherits the discipline rather than rediscovering it after an incident. It governs *what must be true*; the momentum-daily implementation detail (schema, function names, migrations, the acceptance matrix) lives in `docs/review/momentum_daily/` and is out of scope here.

## Decision

Adopt a **persisted, authoritative deployment lifecycle** and **fail-closed operational holds** for governed strategies, with the following invariants:

1. **The persisted deployment lifecycle is authoritative.** A strategy's inception state (`NEVER_DEPLOYED | DEPLOYMENT_PENDING | DEPLOYED | INTENTIONALLY_FLAT`) lives in durable state and is the single source of truth. **Holdings alone must not determine inception state** — positions corroborate, they never prove.

2. **Deployment requires an attributed qualifying fill; positions corroborate but never prove.** A strategy transitions to `DEPLOYED` only on a fill attributable to that strategy and account (via the fills→orders relationship, not a caller-supplied tag) with positive executed quantity. Positions may corroborate deployment but may not independently establish it: a **position without an attributed fill** cannot establish deployment and is reconciliation-required; a **qualifying fill without currently observable exposure** is surfaced as a reconciliation anomaly — a non-blocking alert when shared-account netting or observation lag plausibly explains it, and handled **fail-closed only where attribution or economic exposure remains genuinely ambiguous**. Deployment is never established by position alone.

3. **`has_ever_deployed` is monotonic** (`false → true` only). Once a strategy has ever established attributable exposure, that fact is permanent. A later flat state (regime-to-cash, full exit, liquidation) does **not** reset it.

4. **Inception seeding is one-shot and inception-only.** The `initial_seed` transition may fire only from `NEVER_DEPLOYED` with `has_ever_deployed = false`; it may never re-establish a book that has ever deployed. A later flat book re-enters only through the strategy's ordinary maintenance triggers, never through inception seeding.

5. **Operational holds are enforced fail-closed at every activation boundary — defined by capability, not a fixed list.** A hold must be checked, fail-closed, at every code path capable of **registering, resuming, provisioning, or otherwise enabling strategy execution** (current examples: `/start`, `engine.register`, boot/resume, the live-activation service, provisioning/admin utilities). The two state domains fail closed **distinctly**: **invalid deployment-lifecycle state** (missing, unsupported, malformed, or internally inconsistent) prevents governed evaluation or inception; **missing or unreadable operational-hold state** prevents activation whenever the hold's *absence* cannot be established authoritatively (an unreadable hold store is never read as "no hold" — but a strategy is not required to carry a hold record forever). Neither domain self-repairs.

6. **Clearing a hold and activating are separate audited operations.** `STRATEGY_HOLD_CLEARED` removes the prohibition and asserts nothing about activation; activation is the subsequent, separately-audited `/start` (still subject to the ADR 0005 cooldown). Neither is implied by the other.

7. **Activation paths are protected by a CI-enforced invariant.** A `check_*` invariant asserts that every activation path consults the hold guard, so the enforcement cannot silently regress the way ADR 0004's halt semantics went documented-but-unenforced for months.

8. **A governed strategy is validated using its production implementation (validation-production equivalence).** When a validation replica is unavoidable, CI must prove decision-equivalence between the replica and the production implementation across all governed decision seams. Three tiers:
   - **Preferred** — validation invokes the production strategy class directly.
   - **Permitted exception** — a replicated harness is permitted **only** when automated CI proves decision-equivalence to the production implementation across **all governed decision seams using common inputs**: semantic mismatches (candidate set, selected names, whether a trade is initiated) fail with **zero tolerance**; numeric differences (unavoidable floating-point) must be **explicitly registered** as tolerances; and CI **fails when equivalence cannot be established**.
   - **Not permitted** — an independently-maintained replica whose equivalence is asserted only by documentation.
   A second CI invariant enforces this: a governed-strategy replica must have a registered production-equivalence test, or validation must invoke the production class directly.

9. **This lifecycle model applies to future governed strategies unless a strategy-specific ADR explicitly overrides it.**

10. **Lifecycle transitions and hold changes are auditable, monotonic where specified, and never silently repaired.** Where an invariant specifies monotonicity (`has_ever_deployed` false→true) it holds; there is no reflexive reset; a corrupted or internally-contradictory authoritative state **fails loudly rather than being auto-corrected** (automatic repair must never conceal contradictory authoritative evidence); and a retrospective hold formalization records **real** timestamps (actual `event_time`, original `effective_at`) — it never fabricates history.

## Rationale

- **Why persisted lifecycle authority (invariant 1) rather than inferring from holdings?** The whole class of cold-start bugs — miss a deployment, or reseed one that already happened — comes from treating positions as the state. Positions are a *projection* of orders and fills that lags them and, on a shared account, is not even uniquely attributable to one strategy. A durable, explicitly-transitioned lifecycle is the only thing that survives restarts and shared accounts. (Same reasoning ADR 0043 §D1.1 applied to loss-control state: transitions are persisted, projections are derived.)

- **Why the fill is the deployment authority, not the position (invariant 2)?** A qualifying fill is a durable, attributable fact of execution. On a shared account, a required position could be netted to zero by another source, so requiring `positions > 0` to confirm deployment would fail spuriously; a position we cannot attribute could belong to someone else, so treating it as deployment would be wrong in the other direction. Making the fill the authority and the position a corroboration (with anomalies surfaced as non-blocking alerts, and genuine ambiguity as fail-closed reconciliation-required) is the only formulation that is correct in both directions.

- **Why monotonic `has_ever_deployed` and one-shot seeding (invariants 3-4)?** The cost of a wrong reseed is real money: a book that already deployed, then went flat for a legitimate reason, must not be re-seeded as if fresh — that would double a position or fight the strategy's own exit. Monotonicity plus inception-only seeding makes "already deployed once" an absorbing fact that permanently disables the inception path.

- **Why fail-closed holds at every boundary plus a CI invariant (invariants 5-7)?** The incident showed a hold that was recorded but not enforced. A hold enforced at only *some* activation paths is a hold with a bypass, and bypasses are exactly what the 2026-07-13 loss-control incident taught us compound into attack surface. Enforcing at every boundary, and asserting that enforcement in CI, is the difference between a rule and a wish. Separating clear-hold from activate (invariant 6) prevents the "reset it and it comes right back" reflex the loss-control incident also forbade.

- **Why the validation-production equivalence invariant (invariant 8)?** The cold-start defect shipped because the validated behavior (a reimplemented harness that seeded day-1) and the live behavior (the template's triggers that did not) were different code. A validation that certifies a replica certifies the replica, not the product. Requiring the production class — or a CI-proven equivalence contract when a replica is genuinely unavoidable — closes the gap that let this defect reach production wearing a "validated" label.

- **Trade-offs accepted:** durable lifecycle state becomes part of the trading-safety boundary (the store must be readable to act); fail-closed defaults will sometimes hold a strategy that a more permissive design would have run; and the equivalence requirement raises the cost of every validation harness. These are the safe directions, and they are real costs — see Consequences.

## Implementation notes

- **Governing artifacts, not code.** The concrete schema (the versioned deployment blob), the reconciliation state machine, the `ctx` seams, the migration, and the acceptance matrix are specified and implemented under `docs/review/momentum_daily/` (the P7 §7-A implementation plan) and the `fix/momentum-daily-cold-start-seed` branch — `app/strategies/{seed_reconciliation,deployment_state}.py`, `app/strategies/context.py`, `strategies_user/templates/momentum_daily.py`. This ADR deliberately holds none of those specifics so the invariants can outlive the first implementation.
- **CI invariants introduced (2), to be authored in §7-B:** (a) *every activation path consults the operational-hold guard before registering a strategy*; (b) *a governed-strategy validation replica has a registered production-equivalence test, or validation invokes the production class directly*. ⟨`check_*` scripts + guard module — future governed work.⟩
- **Audit actions:** `STRATEGY_HOLD_PLACED` and `STRATEGY_HOLD_CLEARED` (strategy-scoped, distinct from account/trading holds). The current momentum-daily hold predates these actions; its formalization is a **retrospective** `STRATEGY_HOLD_PLACED` whose `event_time` is the actual creation time and whose `effective_at` is the original marker timestamp — recording, not manufacturing, history.
- **Cooldown unchanged.** Reactivation after a cleared hold remains subject to the ADR 0005 activation cooldown; this ADR neither shortens nor bypasses it.
- **Defaults conservative** (house convention): fail-closed on missing/invalid state; a hold blocks by default.

## Consequences

- **Positive.** The cold-start defect class (miss-a-deployment / reseed-what-already-deployed) cannot recur by construction; a paused strategy is genuinely un-activatable, not merely labeled paused; "already deployed" is an absorbing, auditable fact; clearing a hold is an evidenced decision separate from activation; and a "validated" strategy is provably the strategy that runs.
- **Negative.**
  - **Durable state availability becomes part of the trading-safety boundary** — if the lifecycle store cannot be read, a governed strategy fails closed and does not trade.
  - **Fail-closed defaults will sometimes hold a strategy** a more permissive design would have run (an over-conservative reconciliation-required, a hold that outlives its cause until a human clears it).
  - **Every validation harness costs more** — the production class must be driven, or an equivalence contract maintained; documentation-asserted replicas are no longer allowed.
  - **More audited operations** (place/clear hold, the equivalence check) mean more machinery to keep correct and more storage/retention (compounds ADR 0042/0043 ledger growth).
- **Neutral.** The strategy's own trading logic and the ADR 0002 order path are unchanged; this ADR governs *when a strategy may deploy and activate*, not *what it trades*.

## Alternatives considered (not chosen)

1. **Infer inception from holdings (no persisted lifecycle).** Rejected: fails on shared accounts and across restarts — the exact failure this ADR exists to prevent. Simpler, but wrong in both directions.
2. **Fix only momentum-daily's trigger, no general invariants.** Rejected: the next strategy would rediscover the cold-start, hold-enforcement, and validation-drift problems after its own incident. The cost of generalizing the invariants now is far below the cost of three more incidents.
3. **Position-based deployment confirmation** (DEPLOYED when `positions > 0`). Rejected: on a shared account a netted position spuriously blocks deployment, and an unattributed position spuriously confirms it. The fill-as-authority formulation is the only one correct in both directions.
4. **Hold enforced only at `/start` (the "front door").** Rejected: boot-resume, the activation service, and provisioning scripts are also activation paths; a hold with any bypass is not a hold. The 2026-07-13 loss-control incident is the precedent that bypasses compound.
5. **Accept the reimplementation-based validation as-is** (document the drift, don't require equivalence). Rejected: it is precisely how the cold-start defect reached production under a "validated" banner. Documentation is not a contract.
6. **Auto-clear holds on self-heal (ADR 0035) without a separate audited clear.** Rejected: recreates the reflexive-reset the loss-control incident forbade; clearing a hold is a decision that needs its own evidence and audit.

## Re-evaluation triggers

- A governed strategy **re-seeds a book that had ever deployed**, or **misses a deployment**, despite these invariants (the lifecycle authority failed its purpose).
- An **activation path is found that bypasses the hold guard** in a live event (the CI invariant has a gap).
- The **fail-closed default holds a strategy that should have traded** frequently enough that the reconciliation/hold bar is mis-tuned (the conservative direction is over-firing).
- A **production-vs-replica equivalence check proves impractical** to maintain for a strategy class, forcing a documentation-only replica (the equivalence bar needs a degraded-mode design, not removal).
- A future strategy needs **materially different inception semantics** (e.g., an always-invested book with no cold-start), warranting a strategy-specific ADR that overrides invariant 9 for that strategy.
