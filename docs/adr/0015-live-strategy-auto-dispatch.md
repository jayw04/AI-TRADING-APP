# ADR 0015 — Live strategy auto-dispatch

| Field | Value |
|---|---|
| Date | 2026-06-05 |
| Status | Accepted (2026-06-05; envelope decided by the owner via the 2026-06-05 decision turn, this record reviewed and accepted) |
| Phase | P6b §4.5 |
| Supersedes | — |
| Related | 0002 (single OrderRouter), 0004 (daily-loss circuit breaker), 0005 (24-hour activation cooldown), 0006 v2 (LLM in order path — §5 depends on this path existing), 0007 |

## Context

P5 §7 shipped the "live trading toggle." A strategy can be activated to `LIVE` only through a deliberate ceremony — a 24-hour activation cooldown, a typed confirmation of the strategy's name, and a TOTP re-entry (ADR 0005) — and the `OrderRouter` was extended to *accept* strategy-sourced orders on a live account (its live guard requires `strategy.status == LIVE`, rejecting `PENDING_LIVE` and everything else).

But the strategy engine was never wired to *produce* those orders. `StrategyEngine.register()` resolves the user's **paper** account unconditionally (`Account.mode == AccountMode.paper`, with no branch on status) and binds that paper `account_id` into the `StrategyContext` for the strategy's lifetime. The activation-completion job (`complete_pending`) flips `PENDING_LIVE → LIVE` but does not register the strategy for dispatch. The consequences are concrete and current:

- A `LIVE` strategy's automatic orders carry the **paper** `account_id`, so they route to the paper broker.
- A strategy that becomes `LIVE` mid-session is never registered, so it does not dispatch at all until the next process boot.
- The `OrderRouter`'s STRATEGY-on-LIVE guard is effectively dead code for engine-dispatched orders — it only fires for an order that already carries a live `account_id`, which only a manually constructed request (the Trade page, or a test) produces.

So "going live" does not actually make a strategy trade live automatically. P6b §5 (LLM-driven live trading opt-in, ADR 0006 v2) presupposes a real live-dispatch path to gate. We must decide whether — and under what safety envelope — strategies place real-money orders automatically.

This is the first capability in the platform where **software places a live order without a human confirming that specific order**. Manual live trading (Trade page) requires a typed-ticker confirmation per order; auto-dispatch removes the per-order human. That is a categorically larger trust step and demands an explicit decision and an explicit envelope, not a quiet wiring fix.

## Decision

1. **A strategy with `status == LIVE` auto-dispatches its engine-generated orders to the user's live account.** The engine resolves the dispatch account by status: `LIVE` → the user's live account; `PAPER` and `PAPER_VARIANT` → the paper account. A `LIVE` strategy with no live account is an error state (it cannot dispatch).

2. **Reaching `LIVE` is the authorization — no separate per-strategy auto-dispatch gate is introduced.** Activation already requires the 24-hour cooldown, the typed strategy-name confirmation, and TOTP re-entry (ADR 0005, P5 §7); that ceremony is the authorization to trade live automatically. Every order, paper or live, continues to pass the risk engine and the circuit breaker (ADR 0002, ADR 0004); those remain non-bypassable.

3. **A global master switch `LIVE_AUTODISPATCH_ENABLED` defaults OFF.** While off, `LIVE` strategies do not auto-dispatch — their automatic orders are suppressed at the engine boundary, manual live orders (Trade page) are unaffected, and paper behavior is byte-identical. Turning it on is an operator action that is audit-logged. It is both the staged-rollout gate and the single instant halt for all live auto-dispatch, distinct from the per-account, loss-triggered circuit breaker.

4. **The activation → registration lifecycle is made coherent.** Entering `LIVE` (re-)registers the strategy so it binds the live account; leaving `LIVE` (deactivate/halt) or entering `PENDING_LIVE` unregisters or rebinds it, so a strategy never dispatches against the wrong account or during its cooldown.

## Rationale

**Why `LIVE`-status is the authorization (decision 2), not a second per-strategy gate.** The activation flow was built for exactly this purpose — its 24-hour "sleep on it" cooldown, typed name, and TOTP are the deliberate, account-protecting gate for *live trading*. The only reason a separate gate looked plausible is that the engine never wired dispatch, so over time "LIVE" had degenerated to "live orders permitted but never actually produced." Restoring the wiring completes the original intent of the toggle rather than inventing a second ceremony. A separate per-strategy auto-dispatch flag would double the friction, split the meaning of `LIVE` across two states that every status consumer must now track, and add no safety the risk engine and circuit breaker do not already provide on every order.

**Why a global master switch defaulting off (decision 3).** This is the platform's first software-places-real-money capability, and the house rules are "conservative defaults, configurable extremes" and "friction is the feature." Both argue for a deliberate, auditable enable step and a single operator-level breaker that halts *everything* at once. That breaker is genuinely distinct from the per-account circuit breaker, which is loss-triggered and per-account rather than an operator choice over the whole capability. Default-off means merging §4.5 changes nothing in production until an operator consciously turns it on — the correct blast-radius posture for a change this consequential. The cost is exactly one config flip before live auto-dispatch works, and that cost is the point.

**Why resolve the account by status inside the engine (decision 1).** The alternative — keep the engine paper-only and rewrite `account_id` for `LIVE` strategies somewhere downstream — scatters the live/paper decision across layers and invites mode-leak (a paper-bound context emitting a live order, or vice versa). Resolving the account once, at registration, from the authoritative `status`, keeps a single source of truth and preserves the load-bearing "paper byte-identical" property: a `PAPER` strategy takes the identical code path it does today.

## Implementation notes

- **Engine `register()`** (`app/strategies/engine.py`): branch the account query on `row.status` — `AccountMode.live` for `LIVE`, `AccountMode.paper` for `PAPER` / `PAPER_VARIANT`. A `LIVE` strategy with no live account transitions to `ERROR` (it cannot dispatch).
- **Master switch** `LIVE_AUTODISPATCH_ENABLED` (default `false`) in `app/config.py` settings. When false, a `LIVE` strategy is registered but its automatic submit is bound to a suppressing wrapper (the order is dropped before the broker, with an operational log and/or audit signal). Manual live orders (`OrderSourceType.MANUAL`, Trade page) never consult this switch — they are human-confirmed. The exact suppression seam is settled in the §4.5 session doc.
- **Activation completion** (`app/services/activation.py::complete_pending` + `app/jobs/activation_completion.py`): after flipping to `LIVE`, call `engine.register(strategy_id)` so the live account binds. **Initiate** (`PAPER → PENDING_LIVE`): unregister a paper-running instance so it stops paper-dispatching during the cooldown (`PENDING_LIVE` is not engine-runnable).
- **Audit**: a new action `LIVE_AUTODISPATCH_ENABLED_CHANGED` for the operator flip (with the new value + actor). Suppressed live orders (switch off) are logged operationally; whether they also audit is settled in the session doc.
- **CI / tests**: a test (or invariant) asserting the engine resolves the account by status (`LIVE → live`, `PAPER → paper`) and that `LIVE_AUTODISPATCH_ENABLED` defaults off. The P5 §7 "paper smoke byte-identical" assertion carries forward.
- **Default values**: master switch `false`; account-by-status resolution has no configurable override (it is structural).

## Consequences

**Positive.** Live trading works end-to-end for the first time: a `LIVE` strategy actually trades live. The `OrderRouter` live guard stops being dead code. P6b §5 (LLM opt-in, ADR 0006 v2) gains the real live path it presupposes. The master switch provides a staged rollout and an instant, operator-level halt.

**Negative.** Real-money orders now flow without per-order human confirmation — the single largest increase in the platform's blast radius to date. A bug in a `LIVE` strategy now loses real money automatically. This is mitigated, not eliminated, by the risk engine, the circuit breaker, the default-off master switch, and the 24-hour activation cooldown. The engine's account resolution becomes status-dependent, so any future `StrategyStatus` must explicitly decide its dispatch mode. Operators must remember to enable the master switch (intended friction).

**Neutral.** The meaning of `LIVE` sharpens from "live orders permitted" to "trades live automatically." Every consumer of `StrategyStatus` that implicitly assumed paper dispatch must be reviewed against the new semantics.

## Alternatives considered (not chosen)

- **A separate per-strategy auto-dispatch enablement, distinct from `LIVE`.** Rejected: it doubles the activation ceremony, splits the meaning of `LIVE` into two tracked states, and adds friction without adding safety the risk engine + circuit breaker do not already provide. *Reconsider if* real-world use shows users reaching `LIVE` without intending automatic dispatch.
- **No global master switch** (rely on the per-account circuit breaker + per-strategy deactivate). Rejected: there would be no single operator-level halt distinct from the loss-triggered per-account breaker, and nothing to stage the rollout of the platform's first auto-real-money capability behind. *Reconsider* once live auto-dispatch has a long, safe track record.
- **Master switch defaulting ON.** Rejected: live-by-default the moment §4.5 merges is the wrong blast-radius posture for this capability.
- **Keep the engine paper-only and rewrite `account_id` downstream for `LIVE` strategies.** Rejected: scatters the live/paper decision across layers and risks mode-leak; violates the single-source-of-truth shape that ADR 0002 establishes for the order path.

## Re-evaluation triggers

- A `LIVE` strategy auto-dispatches an order the user did not anticipate and it causes a material loss → revisit whether `LIVE`-status alone is sufficient authorization, or a per-strategy confirmation is warranted after all.
- Operators routinely leave `LIVE_AUTODISPATCH_ENABLED` on in every environment with no staged use → the default-off may be friction without value; revisit the default.
- The risk engine / circuit breaker prove insufficient as the per-order safety net for auto-dispatched live orders (a runaway strategy slips past the caps) → revisit the envelope, likely adding live-scoped rate/exposure limits before re-enabling.
- A later phase changes what "live dispatch" means (e.g., multiple live accounts per user, or §5's LLM gate altering the submit path) → revisit the account-resolution-by-status decision.
