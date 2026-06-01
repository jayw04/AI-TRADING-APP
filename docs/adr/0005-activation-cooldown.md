# ADR 0005 — 24-Hour Activation Cooldown

| Field | Value |
|---|---|
| Date | 2026-05-31 |
| Status | Accepted |
| Phase | P5 §7 |
| Related | ADR 0004 (circuit breaker hard halt) |

## Context

P5 §7 opens the live order path: a strategy that's been validated in paper can
now submit live orders. The activation gesture has to be explicit (typed
strategy name, TOTP code, prerequisites checklist) — but the question is whether
the LIVE state is effective immediately on wizard completion or after a delay.

Three candidates:

1. **Immediate** — wizard completes; next bar dispatched can submit live.
2. **Short cooldown** (e.g., 1 hour) — wizard completes; strategy waits an hour
   before live order flow, during which the user can cancel.
3. **Long cooldown** (24 hours) — same as (2), but the window spans a full
   overnight/next-morning review cycle.

## Decision

**24-hour cooldown.** Strategy transitions PAPER/IDLE → PENDING_LIVE on wizard
completion. A scheduled job 24 hours later transitions PENDING_LIVE → LIVE.
During PENDING_LIVE, no orders flow; the user can cancel without TOTP at any
time.

## Rationale

- **Cognitive bias of "feeling ready."** Traders complete validation in paper and
  feel ready to go live — but humans systematically underestimate how different
  live execution is from paper. A 24-hour pause means the user re-encounters the
  decision in a cooler state. If the conviction holds 24 hours later (and the
  user doesn't cancel), they almost certainly meant it.
- **The wizard is fast; the consequences are slow.** The wizard takes 2-3
  minutes. The cooldown is ~500x that. The asymmetry matches "easy to start" vs
  "hard to undo a bad trading day."
- **The cooldown is not gated by user action.** No "click here to activate after
  24 hours" — the scheduler flips the bit automatically. This avoids the user
  forgetting and the strategy sitting dormant. The only friction is the wait.
- **Cancellation during cooldown is frictionless.** No TOTP, no typed
  confirmation. Activation is the expensive action; cancellation is the safe one.
- **Why not 1 hour, why not 7 days.** 1 hour doesn't span the overnight reset that
  catches most impulse decisions. 7 days is too long — the market conditions the
  user validated against may have moved. 24 hours is the sweet spot.

## Consequences

**Positive:**
- Filters impulse activations. The user has to want it twice (during the wizard
  AND by not canceling 24 hours later).
- Forces the user to live with the decision overnight.
- The countdown is a useful UX surface — the user can watch paper signals during
  the cooldown and confirm/cancel before live.

**Negative:**
- Genuine "I want to start now" cases must wait. This is the intended friction.
- A scheduler bug that fails the PENDING_LIVE → LIVE transition leaves the
  strategy stuck. Defense: structured logs every minute; no manual override
  endpoint in §7 (P5+ polish if needed).
- 24h is a magic number; revisit if real users demand a different value.

## Alternatives considered (not chosen)

- **No cooldown, but require TOTP on every live order.** Defeats the purpose —
  the activation gesture IS the explicit step.
- **Per-account cooldown.** Bad UX — once one strategy is live, others skip the
  cooldown. It should attach to the individual strategy decision.
- **Configurable duration.** Defers the design call to the user. We make the
  call: 24h.
- **No cancellation during PENDING_LIVE.** Would force the user to wait out a
  regretted decision. Bad design.

## Implementation notes

- `strategies.live_activation_initiated_at` is the source of truth. When set and
  status=PENDING_LIVE, the strategy is in cooldown.
- The transition PENDING_LIVE → LIVE happens via the APScheduler job
  `activation_completion`, running every 60s. The job is idempotent — if the
  backend was down when 24h elapsed, the first run after restart completes it.
- Cancellation is permitted at any time during PENDING_LIVE. It clears
  `live_activation_initiated_at` and sets status=IDLE; audit-logged with
  `STRATEGY_ACTIVATION_CANCELED`.
- After completion (status=LIVE), `live_activation_initiated_at` is retained for
  forensic / "when did this go live" queries.
