# ADR 0035 — Operational self-healing policy

| Field | Value |
|---|---|
| Date | 2026-07-02 |
| Status | Accepted |
| Phase | Cross-phase (operations; scheduler, strategy engine, daily setup) |
| Supersedes | — |
| Related | 0002 (single OrderRouter), 0004/0034 (daily-loss halt), 0005 (activation cooldown), 0032 (single-armed-host paper stack) |

## Context

Daily strategy operation depends on a chain of *operational* setup steps that are
not themselves trading decisions: the scheduler must be armed, the strategy must
be registered and dispatching, the day's opportunity set (e.g. the range Top-5)
must be assigned, the day's price levels must initialize, caches must be fresh.
When one of these silently fails, the strategy produces no signals and no trades
— a "quiet" outage that is easy to miss until a day is lost. The Range Trader's
opening-range levels are the motivating case: if the strategy is not dispatching
at 09:30 ET, no levels form and nothing trades, yet nothing is *wrong* with the
trading logic or risk gates.

The tempting fix — "just auto-correct everything" — is dangerous, because the
same platform also runs **risk controls** (daily-loss breaker, halts, position
caps) whose entire value is that they are *not* bypassable. An automation that
cleared a halt or resized a position to "keep things running" would silently
defeat the governance the platform exists to provide.

We need a single, explicit policy that says **what may self-heal, what may only
be retried, what may only be recommended, and what may never be auto-corrected** —
so operational reliability and risk governance reinforce each other instead of
colliding.

## Decision

Adopt an **Operational Self-Healing Policy**: every automatically-detectable
condition is classified into one of four action levels, and automation may only
take the action its level permits.

- **Level 1 — Auto-correct (safe operational failures).** Deterministic setup
  failures with a single correct fix, involving **no trading decision**. The
  system corrects them automatically and audits the recovery. Examples: strategy
  not started before the open, dispatch loop not running, scheduler missed a
  cycle, opportunity set not assigned, daily price levels not initialized, cached
  daily levels missing, a strategy accidentally stopped.
- **Level 2 — Auto-retry (transient faults).** Operations that failed for a
  transient reason are retried with backoff before escalating. Examples: broker/
  data API timeout, transient network error, stale cache, database lock.
- **Level 3 — Alert + recommend (needs judgment).** Conditions that are not
  obviously wrong but warrant a human look. The system **changes nothing** and
  emits an alert with a concrete recommendation. Examples: price levels look
  abnormal, candidate score unusually low, range far wider than historical, no
  qualified candidates, an opportunity set with only one symbol.
- **Level 4 — Never auto-correct (risk controls).** Risk-governance state is
  never altered by automation; it always requires human approval. The system may
  only **alert with a recommendation**. Examples: daily-loss breaker, risk halt,
  position-size violation, max-drawdown, manual trading pause, broker order
  rejection.

Three invariants bind the policy:

1. **Self-heal operational failures; never self-heal trading decisions** (entries,
   exits, order submission) **or risk gates** (halts, breakers, caps).
2. **Every automatic recovery is audited** — an append-only record of what was
   detected, what action was taken, and the before/after state.
3. **Escalate when safety can't be proven.** If the system cannot establish that a
   correction is *operationally* safe (Level 1/2), it drops to alert-only (Level 3).

Each self-healed subsystem also reports an explicit **health state**:

| State | Meaning |
|---|---|
| 🟢 GREEN | healthy — all checks pass |
| 🟡 YELLOW | recovered automatically (a Level 1/2 action fixed it) |
| 🟠 ORANGE | needs an operator (Level 3 alert, or a correction that failed) |
| 🔴 RED | trading disabled for this subsystem (unsafe to proceed) |

## Rationale

- **The operational/trading boundary is the whole point.** The platform already
  separates *what should be traded* (Evidence Engineering) from *what is allowed
  to be traded* (Risk Governance). This policy adds a third, subordinate layer —
  *ensuring the machinery runs* (Operational Self-Healing) — that must never
  override the other two. Encoding that boundary as an action-level classification
  makes "may I auto-fix this?" answerable mechanically rather than case-by-case.
- **Aggressive where it's safe, conservative where it isn't.** Before any trade,
  re-initializing the day's setup has no risk downside, so Level 1 can be
  aggressive (recompute, re-arm, re-assign, then verify). After a trade, or on any
  risk state, the downside is real, so the policy forbids automation. The daily
  price-setting is squarely pre-trade, so it self-heals aggressively; the halt is
  squarely risk, so it never does.
- **"Provably spurious" is not a safe trigger for a risk action.** A halt that
  today looks inconsistent with account P&L may, tomorrow, be inconsistent because
  the *checker* is wrong, not the halt. Auto-clearing on "looks spurious" makes the
  risk gate only as trustworthy as the least-tested inference in the checker. The
  policy therefore keeps Level 4 alert-only, emitting e.g. *"daily-loss breaker
  appears inconsistent with account P&L — verify account state before clearing."*
- **Health states make quiet outages loud.** A per-strategy GREEN/YELLOW/ORANGE/
  RED surfaced each morning turns "it silently didn't trade" into a visible,
  triageable status, and distinguishes "recovered on its own" (YELLOW) from "needs
  you" (ORANGE) so attention goes where it's needed.

### Alternatives considered

- **Single global policy (auto-correct everything / alert-only everything).**
  Rejected. "Auto-correct everything" would automate risk-gate bypasses;
  "alert-only everything" would page an operator for a trivially-fixable unstarted
  scheduler every morning. Neither matches the fact that *risk of the action*
  varies enormously by condition.
- **Auto-clear provably-spurious halts (a fourth global option).** Rejected on the
  owner's reasoning above: risk gates stay sacred; the platform recommends, a human
  clears.
- **Bake self-healing into each subsystem ad hoc.** Rejected: without a shared
  classification, each new automation re-litigates "is this safe to auto-fix?" and
  the operational/risk boundary erodes by a thousand small exceptions.

## Implementation notes

- A subsystem opts in by mapping its detectable conditions to levels and running a
  scheduled health-check that (a) auto-corrects Level 1, (b) retries Level 2,
  (c) alerts+recommends Level 3/4, (d) audits every action, (e) reports a health
  state.
- **First implementation: the Range Trader daily price-setting** (this PR).
  - Level 1 (auto-correct): **pre-open**, if the strategy is registered but not
    dispatching, re-arm it — safe because the opening range has not started, so it
    rebuilds cleanly from 09:30. (A *mid-day* re-arm is explicitly **not** Level 1:
    reloading after 10:00 would rebuild the opening range from the wrong window and
    corrupt the levels — so mid-day dispatch inertness is Level 3 alert-only.)
  - Level 2 (auto-retry): transient data/broker fetches inside the check.
  - Level 3 (alert): post-open, missing or invalid levels; abnormal range; no/thin
    candidates; dispatch inert mid-day.
  - Level 4 (alert-only): the account halted / breaker tripped blocking the range
    account — recommend verification, never clear.
  - Health state emitted to the operator (SNS) and reusable by a dashboard widget.
- **Audit trail.** Level 1/2 recoveries write an `AuditLogger` entry (a new
  `AuditAction` value, e.g. `OPERATIONAL_SELF_HEAL`) with the condition, action,
  and before/after — extending the existing hash-chained log. This keeps the
  on-call playbook and the audit chain aware of automated recoveries (see the
  "new audit action ⇒ update the runbook" convention).
- No change to the OrderRouter, risk engine, or any Level 4 state.

## Consequences

- **Positive.** Quiet operational outages self-heal or page early; the
  operational/risk boundary is explicit and mechanically checkable; health states
  make daily status legible; every automated action is auditable; new automations
  inherit a ready-made safety classification.
- **Negative.** The classification is a judgment that must be maintained — a
  mis-filed condition (calling a risk action "operational") is exactly the failure
  the policy exists to prevent, so *changes to the level of any condition are
  themselves consequential* and should be reviewed like risk changes. Self-healing
  can also mask a recurring operational defect (it keeps recovering instead of
  being fixed) — the YELLOW state and the audit trail are the mitigations, but
  someone must actually read them.
- **Neutral.** Adds a scheduled health-check and an audit action per self-healed
  subsystem; more moving parts, but each is small and independently testable.

## Re-evaluation triggers

- A Level 1 auto-correction is found to have caused a bad trade or corrupted state
  (e.g. a re-arm that recomputed levels from the wrong window) — tighten the level
  definition or demote the condition to Level 3.
- Repeated YELLOW on the same condition (self-healing is papering over a defect
  that should be fixed at the source).
- Pressure to move any Level 4 condition to auto-correct — that is a risk-governance
  change and must go through its own ADR, not this one.
- The health-state taxonomy proves too coarse/fine in practice.
