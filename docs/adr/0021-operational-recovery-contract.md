# ADR 0021 — Operational Recovery Contract for Automated Actions

| Field | Value |
|---|---|
| Date | 2026-06-19 |
| Status | Draft |
| Phase | P10 (cross-cutting; first exercised by §2 overlay) |
| Supersedes | — |
| Related | 0002 (single OrderRouter — recovery never bypasses it), 0004 (circuit breaker — the canonical fail-safe), 0015 (live auto-dispatch), 0020 (daily overlay — the first recurring automated re-sizer), 0019 (Research Engine — off the order path, excluded) |

## Context

The platform is moving from "built and gated" toward "operationally run." The
architecture (ADRs 0002/0004/0019/0020) defines *what each subsystem owns*; it does
**not** yet define how automated, recurring actions behave under operational failure —
scheduler crashes, backend restarts, broker/data outages, partial fills, duplicate
fires, and the reconciliation of local state against broker truth.

This was acceptable while the only automated actor was the weekly strategy rebalance.
But two recurring automated actors now exist or are imminent: the **§6 continuous
circuit-breaker monitor** (every 60 s) and the **§2 daily gross-exposure overlay**
(ADR 0020), which re-sizes a live book on a schedule and is therefore exposed to
partial fills and double-fires. Without a stated contract, each new automated action
re-invents (or forgets) idempotency, fail-safety, and restart behavior — and the
failure modes are precisely the ones that hurt under real capital.

The question: what operational guarantees must every automated, order-affecting action
satisfy — and what is the platform's posture on recovery, reconciliation, and replay?

## Decision

Adopt an **Operational Recovery Contract**: every automated, recurring, order-affecting
action (overlay re-size, breaker monitor, scheduled rebalance, and any future
automated actor) must satisfy these properties. They are testable per action and
enforced by review, not by a new subsystem.

1. **Idempotent within its period.** A re-fire for a period whose work is already
   applied is a no-op. Scheduler jobs run single-flight (`max_instances=1`, `coalesce`)
   plus an action-level already-applied guard. Double-fires never double-act.
2. **Fail-safe, never fail-dangerous.** On missing/invalid inputs or an external
   (broker/data) outage, the action degrades toward *less* action, never more: the
   overlay fails open to gross = 1.0 (no scaling); the breaker only ever halts. No
   automated action manufactures risk when it is degraded.
3. **Restart-recoverable.** All state an automated action needs lives in durable stores
   (DB), never in process memory. On restart the scheduler re-registers its jobs and
   each action resumes **without** duplicate side effects (guaranteed by property 1).
4. **Reconciled against broker truth.** Local position/order state is periodically
   reconciled against the broker; a discrepancy **alerts** and is surfaced — it never
   silently auto-corrects into new orders. (Reconciliation reads; remediation is an
   owner decision, mirroring ADR 0019's "monitor alerts, owner acts.")
5. **Replayable.** Every automated decision logs a structured, self-contained
   fingerprint (a unique event id + the inputs and outputs that produced it) so it can
   be reconstructed after the fact — extending the audit hash chain, not replacing it.
6. **Self-healing on partial application.** An action that may partially apply (e.g. a
   re-size where only some orders fill) must converge on a later tick rather than assume
   full application; the gap is observable (fingerprint records intended vs. achieved)
   and is never silently treated as complete.

Routing is unchanged: every order an automated action induces still flows through
`OrderRouter.submit()` (ADR 0002) and the full risk engine. Recovery never adds an
order path.

## Rationale

**Why a contract, not a subsystem (yet).** The properties above are achievable as
per-action discipline plus small shared helpers (single-flight scheduling, a fingerprint
schema). Building a standalone "Execution/Recovery Engine" now would be premature — there
is one overlay and one monitor. A contract makes the guarantees explicit and testable
without over-building; the subsystem can be extracted when a second consumer needs shared
order diffing/batching/retry (named as a trigger in ADR 0020).

**Why fail-safe asymmetry.** The platform's entire trust story (ADR 0004, the risk
engine, "conservative defaults") is that a false stop is cheap and a false action can be
ruinous. Automated actors must inherit that asymmetry; an overlay that fails *open* (no
scaling) is safe, an overlay that fails into a forced liquidation is not.

**Why reconcile-but-don't-auto-correct.** Silent auto-correction of a local/broker
discrepancy is itself an automated order path with no human in the loop — exactly what
the platform avoids. Alert-and-surface keeps the owner in control (same posture as the
Research Engine's revalidation alerts).

**Why replayability.** Non-deterministic or schedule-driven actions can't be reproduced
from code alone; a fingerprint of inputs+outputs is what makes "why did the book de-risk
at 14:32 on the 19th?" answerable months later. This is the same logic that makes
LLM decisions auditable (ADR 0006 v2) applied to automated risk actions.

## Implementation notes

- **No new subsystem, no new external dependency.** Shared helpers only: a single-flight
  scheduling convention (already used by §6 and §2) and a fingerprint payload schema.
- **Fingerprint schema (per automated action):** `{event_id, action, date, inputs{…},
  intended, achieved, reason}` written through `AuditLogger`; generated orders carry the
  `event_id` for end-to-end tracing (Action → Orders → Fills → Audit).
- **Reconciliation:** a periodic position/order reconcile job (broker vs. local)
  emitting a discrepancy alert; **phased** — not required for §2's first ship, but §2's
  partial-fill gap (ADR 0020) is its first concrete consumer.
- **Phasing:** §2 (overlay) implements properties 1, 2, 3, 5, 6 at ship; property 4
  (active reconciliation) and a generalized recovery surface are a **follow-on** (see
  Consequences / Re-evaluation).
- **CI:** no new invariant; the contract is reviewed per action. Existing
  `check_adr0002.sh` already guarantees automated actions don't bypass the router.

## Consequences

- **Positive.** Every automated actor inherits a known, testable safety posture;
  operational failure modes (double-fire, restart, outage, partial fill) are designed for
  rather than discovered in production. Replayable fingerprints make incident analysis
  tractable.
- **Negative.** It adds required test surface to every automated action (idempotency,
  restart, failure-injection), which slows shipping a new automated actor — deliberately.
  Some properties (active reconciliation) are stated here but only **partially**
  implemented at first, so the contract temporarily describes more than the code enforces
  (tracked as phased work, not as done).
- **Neutral.** Manual order flow and the Research Engine (off the order path, ADR 0019)
  are out of scope — this contract governs *automated, order-affecting* actions only.

## Alternatives considered (not chosen)

- **Build a full Execution/Recovery Engine now.** Rejected as premature (YAGNI) — one
  overlay + one monitor don't justify a subsystem; the contract delivers the guarantees
  at far lower cost. Reconsider when a second consumer needs shared order
  diffing/batching/retry (ADR 0020's Execution-Engine trigger).
- **Leave recovery to per-action ad-hoc handling.** Rejected — that is the status quo
  that lets each new actor forget idempotency or fail-safety; the inconsistency is the
  risk.
- **Auto-correct broker/local discrepancies.** Rejected — a no-human-in-the-loop
  automated order path contradicts the platform's control model; alert-and-surface keeps
  the owner deciding.

## Re-evaluation triggers

- **Second automated consumer** needing order diffing/batching/retry → extract a real
  Execution/Recovery Engine (compose with ADR 0020's trigger).
- **A real partial-fill or restart incident** that the phased implementation didn't
  cover → prioritize the deferred reconciliation property (4).
- **Live (real-capital) operation** of any automated actor → all six properties must be
  fully implemented and tested before that actor governs live orders (not just paper).
- **Reconciliation discrepancies recur** → revisit whether alert-only is sufficient or a
  bounded auto-remediation (still owner-gated) is warranted.
