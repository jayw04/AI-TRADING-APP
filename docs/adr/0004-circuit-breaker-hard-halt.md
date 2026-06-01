# ADR 0004 — Daily-Loss Circuit Breaker as Hard Halt

| Field | Value |
|---|---|
| Date | 2026-05-31 |
| Status | Accepted |
| Phase | P5 §5 |
| Supersedes | — |
| Superseded by | — |

## Context

P5 introduces live trading. Live accounts can lose real money. The
workbench's existing P1 risk engine enforces per-order and per-minute
limits, plus a coarse *global* daily-loss halt (`app/risk/halt.py`,
keyed on `AccountState.day_change`) that stops **all** trading when any
account breaches its `max_daily_loss`. It does not have a precise,
*account-scoped* "this account isn't going well, stop it" state that also
pauses the strategies driving the losses.

We need a way to bound account-level loss in a single day. Three
candidate designs were considered:

1. **Hard halt** — when daily PnL crosses a configured threshold, every
   order on that account is rejected; every active strategy running in
   that account's mode is moved to a HALTED state; manual user action is
   required to resume.

2. **Soft warning** — surface a UI banner and an alert when daily PnL
   approaches the threshold, but continue trading.

3. **Adaptive sizing** — when daily PnL approaches the threshold, reduce
   subsequent order sizes proportionally to slow down further loss.

## Decision

**Hard halt, account-scoped.** `realized_pnl_today + unrealized_pnl_now ≤
-max_daily_loss` → every order on the account rejected, every active
strategy in that account's mode transitions to HALTED, manual reset
required (typed account-label confirmation).

The new account-scoped breaker is **additional** to — not a replacement
for — the existing global `system_config` halt. The two compose: a
daily-loss breach trips both. The global halt remains the blunt
system-wide backstop; the account breaker is the precise, strategy-aware
gate. (Consolidating the two into one mechanism is a future cleanup that
will carry its own ADR, per the risk-engine "removing a check requires an
ADR" rule.)

## Rationale

The choice between hard halt and the alternatives turns on what kind of
loss day-trading bugs typically produce.

- **A strategy that has gone wrong tends to keep being wrong.** A flaw in
  signal generation, position sizing, or exit logic produces correlated
  losses across many orders, not a single bad trade. Soft warnings let the
  bug keep losing money while the user is reading the banner.

- **Adaptive sizing assumes the bug has graceful failure modes.** A
  strategy submitting 100-share orders at 60% loss rate is no safer at
  50-share orders — it's losing the same percentage of buying power per
  trade, just slightly slower.

- **Manual reset forces the user to look.** The whole point of a circuit
  breaker is to interrupt the flow of damage long enough for a human to
  evaluate what's happening. Auto-reset (at midnight, after a cooling
  period) defeats this — it encodes the assumption that whatever caused
  the loss was transient. We assume the opposite by default.

- **Halting strategies, not just rejecting orders.** A strategy that
  submits an order, gets a CIRCUIT_BREAKER rejection, and tries again on
  the next bar tick is not actually stopped — it's spinning at maximum
  rate. The HALTED status is the engine-level signal that the strategy
  should not be dispatched, even if it would otherwise be active.

## Consequences

**Positive:**
- A single bug cannot lose more than `max_daily_loss` in one day per
  account (modulo open positions that drift between order submissions).
- The manual reset step creates a checkpoint where the user examines what
  happened before resuming.
- Halted strategies stay halted across backend restarts (status is
  persisted), so a flapping backend doesn't accidentally restart broken
  strategies.

**Negative:**
- A genuine market move that briefly crosses the threshold halts trading
  for the rest of the day even if the strategy would have recovered.
  Mitigation: the limit is conservative on LIVE accounts ($500 default);
  users can raise it if they have a higher risk tolerance.
- "Manual reset" friction during fast markets is a real cost. We consider
  it acceptable because the reset modal explicitly displays the loss state.
- Adds a code path on every order submission: a couple of indexed queries
  (today's fills, the account's positions). No broker round-trip — the
  engine stays DB-bound.

## Alternatives considered (not chosen)

- **Per-strategy circuit breakers.** Would localize damage to one
  strategy. Rejected: multiple strategies share the same account and
  buying power; protecting just one doesn't protect the account.
  Account-scope is the right unit.

- **Configurable hard-halt OR soft-warning.** Adds a setting the user has
  to think about. Rejected: a single defensible default beats an
  adjustable one when the cost of the wrong choice is high.

- **Auto-restart strategies on reset.** Convenient but undoes the "force
  the user to look" principle. Rejected.

## Implementation notes

- `accounts.circuit_breaker_tripped_at` is the source of truth (NULL =
  not tripped).
- `CircuitBreakerService.trip()` atomically (single commit): sets the
  timestamp, HALTs the account's active strategies, writes a
  CIRCUIT_BREAKER_TRIPPED audit row; then publishes `system.circuit_breaker`.
- Strategies have no `account_id` (the strategy↔account link is P5 §7);
  "the account's active strategies" are mapped via `(user_id, status↔mode)`
  — a PAPER-status strategy belongs to the paper account, LIVE to the live
  account.
- Realized PnL sums today's fills signed by the joined `Order.side`
  (`Fill` carries no signed direction); unrealized PnL is read from the
  local `positions` table.
- `CircuitBreakerService.reset()` requires the user to type the account
  label (server re-checks). It does NOT auto-restart HALTED strategies.
- Background PnL polling is out of scope. A position that drifts deep
  while no orders are submitted will not trip until the next order
  attempt. P5+ polish.
