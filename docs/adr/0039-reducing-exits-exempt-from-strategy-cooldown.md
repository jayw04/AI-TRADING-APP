# ADR 0039 — Position-reducing exits are exempt from the per-strategy cooldown

| Field | Value |
|---|---|
| Date | 2026-07-08 |
| Status | Accepted (2026-07-08) |
| Phase | Cross-phase (OrderRouter; P5 §6 per-strategy cooldown) |
| Related | 0002 (single OrderRouter), **0038** (reducing exits exempt from the gross-exposure gate — the same principle, one layer down), P5 §6 (per-strategy cooldown) |

> **Principle (shared with ADR 0038): an operational gate must never block a risk-*reducing* exit.**
> The per-strategy cooldown is an anti-spin control, not a risk gate — and a de-risking exit is the
> opposite of the harm it guards against.

## Context

The per-strategy cooldown (P5 §6, in `OrderRouter._submit_inner`) is an **anti-spin** control: when a
strategy's order fails to reach the broker (risk rejection, broker error), the strategy enters a 60-second
cooldown; subsequent STRATEGY-sourced orders for that strategy are rejected `STRATEGY_COOLDOWN` *before*
the (expensive) risk engine runs. It rejects orders of **any side**.

Consequently it also blocks a **de-risking exit**, and it *compounds* the exit-trap ADR 0038 addressed:
a rejected exit (e.g. the pre-0038 gross-exposure rejection) itself **sets** the cooldown, so the *next*
stop-loss attempt within 60 s was rejected `STRATEGY_COOLDOWN`. This was observed on 2026-07-07: Range
Trader Top-5's stop-loss SELLs were rejected by both `GROSS_EXPOSURE` and `STRATEGY_COOLDOWN` across
consecutive 5-minute cycles, and the strategy could not stop out. ADR 0038 fixed the gross gate; this
decision closes the same trap at the cooldown layer.

## Decision

1. **A position-reducing exit is exempt from the cooldown *check*.** A SELL fully covered by the current
   long position (`current_qty >= req.qty` — the *same* reducing-sell definition as ADR 0038) proceeds
   past the cooldown to the risk engine, which remains the final gate.
2. **Short-opening sells are NOT exempt** (qty beyond the held long): they stay subject to the cooldown,
   consistent with ADR 0038.
3. **The cooldown is still *set* by any failed submit** (unchanged) — a failed exit still cools the
   strategy, so its future *entries* remain gated. Only the *check* is relaxed for reducing exits.
4. No new rejection reason, no schema change.

## Rationale

- **The cooldown guards against a spinning strategy flooding failed *entries*.** A de-risking exit is the
  opposite of that harm — and exits are *self-limiting*: a strategy can only sell what it holds, and once
  flat there are no more exits to attempt. Letting a reducing exit through cannot flood.
- **The risk engine remains the final gate for the exit** (short restriction, gross exposure with the
  0038 exemption, daily-loss/circuit-breaker, etc.), so relaxing the anti-spin *timer* does not weaken
  risk enforcement — it only removes a time-based delay in front of the real gate.
- **Consistent with established treatment of de-risking sells** — ADR 0038 (gross gate) and the LIVE
  pre-trade buying-power gate ("SELL: always passes"). This makes the cooldown layer consistent rather
  than introducing a new concept.
- **Keeping the cooldown *set* on a failed exit** preserves the operational signal: the strategy is
  having trouble, so its *entries* should still wait. The narrow relaxation is only "an already-cooled
  strategy may still stop out."

### Alternatives considered

- **Exempt all sells, not just reducing ones.** Rejected: a short-*opening* sell increases exposure and
  should keep the anti-spin gate; scoping to `current_qty >= req.qty` is precise and matches ADR 0038.
- **Stop setting the cooldown on a failed exit.** Rejected: broader behavioral change; the failure
  signal is still useful for gating *entries*. Relaxing only the *check* is the minimal fix.
- **Move the cooldown check after the risk engine.** Rejected: the cooldown is deliberately pre-risk
  (don't run the expensive engine for a cooled strategy). A cheap position lookup on the rare
  STRATEGY-SELL-in-cooldown path preserves that while allowing the exit.

## Implementation notes

- `app/orders/router.py` §6 cooldown: skip the `STRATEGY_COOLDOWN` rejection when
  `await self._is_reducing_exit(session, req)` is true — a SELL whose `req.qty <= current_qty` for the
  order's symbol on the account. Reuses the session already opened for `is_in_cooldown`; a position
  lookup happens only on the STRATEGY-SELL-in-cooldown path (rare). New imports: `Position`, `OrderSide`.
- No new `ReasonCode`; no audit-log change (cooldown rejections are already unaudited); no schema change.
- Tests in `tests/orders/test_p5_live_order_safety.py`: a reducing exit in cooldown passes; a BUY in
  cooldown is still rejected; a short-opening sell in cooldown is still rejected.

## Consequences

- **A strategy in cooldown can still stop out / de-risk.** Combined with ADR 0038 (gross gate), the
  2026-07-07 exit-trap is now closed at *both* layers that caused it.
- **The cooldown remains fully in force for entries and short-opening sells** — the anti-spin protection
  is intact for the flooding case it was designed for.
- **Remaining follow-up (separate, as noted in ADR 0038):** the NULL-`estimated_notional` entry path
  lets market BUYs over-fill past the gross cap in the first place — a distinct fix.
