# ADR 0034 — Per-account daily-loss halt

| Field | Value |
|---|---|
| Date | 2026-07-02 |
| Status | Accepted |
| Phase | Cross-phase (risk engine; P5 §5 circuit breaker) |
| Supersedes | The *global-halt* behavior of ADR 0004 (daily-loss circuit breaker) |
| Related | 0002 (single OrderRouter), 0004 (daily-loss circuit breaker as hard halt), 0032 (single-armed-host paper stack) |

## Context

The platform runs multiple independent accounts on a single armed host (ADR 0032) — as of this writing, seven paper accounts, each with its own strategy, capital, and risk limits. The daily-loss circuit breaker (ADR 0004) was designed for a single-account world and implemented as **two** mechanisms:

1. A **per-account** breaker (`accounts.circuit_breaker_tripped_at`) that halts one account's strategies, enforced on every order via `CircuitBreakerService.check()` and by the periodic `breaker_monitor`.
2. A **global** hard-halt flag (`system_config.trading.halted`), set at `RiskEngine` step 9 when any account's `AccountState.day_change ≤ -max_daily_loss`, which rejects **every order from every account** system-wide until an operator clears it.

On 2026-07-01, momentum-conservative (one account) breached its $2000 daily-loss cap on a normal −3.88% down day and, via step 9, set the **global** flag — halting all seven accounts, including the healthy range trader, for ~1.5 trading days until noticed. The blast radius is the problem: **one account's ordinary daily loss should not stop every other account from trading.** The per-account breaker already provides exactly the containment we want; the global auto-halt is a redundant, coarser mechanism whose only effect here was collateral damage.

A separate but related failure mode: the `breaker_monitor` evaluated daily loss **pre-market** (03:13 ET) on stale/thin overnight prints and tripped a per-account breaker on noise that had recovered by the open.

## Decision

1. **A daily-loss breach trips only the breaching account's circuit breaker — never a global halt.** `RiskEngine` step 9 now calls `CircuitBreakerService.trip()` for `req.account_id` (halting that account's active strategies and auditing, atomically) and rejects the order with `CIRCUIT_BREAKER`, instead of calling `set_halted()` and rejecting with `HALT_REACHED`.
2. **The global `trading.halted` flag is retained as a manual operator kill switch only.** It is still checked first on every order (`RiskEngine` step 0) and still settable via `set_halted()`, but nothing in the automated daily-loss path sets it anymore.
3. **The `breaker_monitor` evaluates only during the REGULAR session.** Outside RTH it returns early (recorded as `outcome="skipped"`), because unrealized P&L computed from pre-/post-market prints is unreliable; a genuine overnight gap is caught at the first post-open run.

## Rationale

- **The per-account breaker already does the right thing.** It halts the breaching account's strategies and blocks its further orders, leaving every other account untouched. Routing daily loss through it (rather than the global flag) is the minimal change that fixes the blast radius while preserving every protection ADR 0004 intended for the account that actually lost money.
- **Daily-loss is inherently per-account.** Each account has its own capital, limit, and P&L. A system-wide halt conflates them: it punishes six healthy accounts for one account's day. In a single-account world the distinction was invisible; on a multi-account armed host it is the whole game.
- **The manual global halt still has value** — an operator "stop everything now" control during an incident — so we keep it, just not on a hair-trigger fed by one account's routine drawdown.
- **RTH-gating the monitor** matches how the daily-loss metric is defined (an intraday figure against the start-of-day baseline) and removes a class of false trips without weakening real protection: the first evaluation after the open still sees any overnight gap as day-change.

### Alternatives considered

- **Keep the global halt, only raise the caps.** Rejected: it treats the symptom (caps too tight) not the cause (blast radius). Even with looser caps, a genuine bad day on one account would still halt all accounts.
- **Keep the global halt but require N accounts to breach before halting.** Rejected: arbitrary threshold, and still couples independent accounts that should not be coupled.
- **Delete step 9 entirely and rely solely on step 13's `check()`.** Rejected: step 13 computes daily loss from the positions table (realized+unrealized), which is the computation ADR 0004 v2 / PR #144 is still correcting; step 9 uses the start-of-day baseline (`day_change`), which is the intended definition. Keeping step 9 (re-scoped to per-account) preserves the correct baseline computation.

## Implementation notes

- `app/risk/engine.py` step 9: `set_halted(...)` → `CircuitBreakerService(session=session, bus=self._bus).trip(account_id=req.account_id, reason="daily_loss_exceeded", payload={...})`; reject reason `HALT_REACHED` → `CIRCUIT_BREAKER`. `set_halted` import dropped (no longer used in the engine); `is_halted` retained for step 0.
- `app/jobs/breaker_monitor.py`: new optional `market_session` param (defaults to `default_market_session()`); returns early with `outcome="skipped"` when `classify().is_regular` is false; fails toward *not* evaluating on a classification error.
- No schema change. No new CI invariant. Coverage: `app/risk/` stays ≥95% (`check_risk_coverage.py`).
- Recovery of a tripped account is unchanged: `POST /accounts/{id}/risk/reset-circuit-breaker` with the account label as confirmation, then restore the strategy status.

## Consequences

- **Positive**: one account's daily-loss breach halts only that account; the other six keep trading. Removes the recurring system-wide halt. Removes pre-market false trips. The recovery surface shrinks to the one affected account.
- **Negative**: there is no longer an *automatic* system-wide stop when a single account has a very bad day — an operator who wants "halt everything" must set the manual flag deliberately. This is the intended trade-off (automatic global halt was doing more harm than good), but it means a genuine multi-account correlated drawdown is handled account-by-account, not in one stroke.
- **Neutral**: the daily-loss computation itself (start-of-day baseline via `day_change`) is unchanged; only the *scope* of the resulting halt changes. Composes with ADR 0004 v2 / PR #144 (which refines the per-account breaker's own P&L computation).

## Re-evaluation triggers

- If a correlated multi-account drawdown occurs where per-account halting proves insufficient and an automatic system-wide brake would have helped, revisit whether a deliberate, multi-account-aware global trip (e.g. "≥K accounts breached within T minutes") is warranted.
- If accounts stop being independent (shared capital, cross-account strategies), the per-account scoping assumption breaks and this decision should be revisited.
- If the `breaker_monitor`'s RTH gate is found to miss a genuine overnight-gap halt that materially mattered before the first post-open evaluation, reconsider a bounded pre-open evaluation against validated prior-close prices.
