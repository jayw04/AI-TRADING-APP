# Incident — 2026-07-13 — Halted-strategy dispatch, slot oscillation, and a risk gate that blocked its own risk reduction

**Status:** Open (P0 corrective merged; ADR 0042 / ADR 0043 pending)
**Accounts:** 1 (momentum-portfolio), 7 (combined-book) — **paper**
**Owner disposition:** stand down; no bypass; fix properly before the next eligible run
**Related:** ADR 0004, ADR 0020, ADR 0034, ADR 0038, ADR 0039 · ADR 0042 (fast-track), ADR 0043 (architecture) · PR #424

---

## Impact

**No capital was lost to a bug.** Every loss on the day was market loss. What was lost was
*control*: the account could not act on its own risk-reducing decision.

| | |
|---|---|
| momentum-portfolio, day P&L at breaker trip (09:30:25 ET) | **−$5,504** |
| day P&L at 12:45 ET, breaker still tripped | **−$7,501 (−6.97%)** |
| loss accrued **after** the breaker fired | **≈ −$2,000 (+36%)** |
| exposure throughout | **98.1% invested, 5 names** |
| risk-reducing orders the strategy proposed and was denied | **SNDK trim, LITE trim** |

The book was held at full exposure through a −7% day **by the control that exists to limit
loss**, against the strategy's own instruction to reduce.

---

## Timeline (ET)

| Time | Event |
|---|---|
| 06:04 | Backend restarts (factor-refresh). momentum-portfolio registered, status `PAPER`, enters `engine._running`. |
| 09:30:25 | Daily-loss monitor trips the breaker. `day_change −$5,504` vs `max_daily_loss $5,000`. `strategies.status → HALTED`. **Nothing evicts the strategy from `_running`.** |
| 10:00:03 | The 10:00 cron slot dispatches the **halted** strategy. |
| 10:00:03–10:00:52 | The slot runs **six times**. 18 order proposals: SNDK trim ×6, LITE trim ×6, BE entry ×6. |
| — | Every proposal rejected: `CIRCUIT_BREAKER` ×12, `STRATEGY_COOLDOWN` (the BE buys, correctly). |
| 12:45 | Day P&L −$7,501. Book still 98% invested. Owner declines to bypass. |

---

## Root causes

### 1. The daily-loss and circuit-breaker gates block risk-*reducing* orders (primary)

`app/risk/engine.py` step 9 rejects **every** order while `day_change ≤ −max_daily_loss`, and
step 13 rejects **every** order while the breaker is tripped. Neither consults
`is_reducing_sell`.

That exemption **already exists in this codebase** — ADR 0038 applied it to the gross-exposure
gate and ADR 0039 to the per-strategy cooldown. The loss gates were simply missed.

Consequence: once an account breaches its daily-loss limit, it is frozen to *all* order flow —
including the position-reducing sells that are the only way to contain the very loss the limit
is protecting. **The control locks in the exposure it exists to cap.**

> A risk control may stop trading, but it must not prevent verified reduction of the risk it is
> intended to control.

Note this is not merely "the breaker fails to de-risk." Resetting the breaker would not have
helped either: **step 9 sits before step 13**, so any order re-trips the breaker and is
rejected regardless. The account was structurally unable to reduce.

### 2. `HALTED` was never enforced at dispatch

ADR 0004 states the requirement explicitly:

> "A strategy that submits an order, gets a CIRCUIT_BREAKER rejection, and tries again on the
> next bar tick is not actually stopped — it's spinning at maximum rate. The HALTED status is
> the engine-level signal that the strategy should not be dispatched."

It was written down and never implemented. The breaker sets `strategies.status = HALTED` in the
database; `_dispatch_bar_tick` consulted only the in-memory `_running` map, and **nothing
removes a halted strategy from it** — no unregister call, no bus subscriber. So a halted
strategy dispatched normally and spun 18 proposals into the risk engine, which is precisely the
behaviour the ADR says HALTED exists to prevent.

### 3. The scheduled slot ran six times

The portfolio templates guarded the engine's per-symbol `on_bar` fan-out by remembering the ISO
week of `bar.t`. But `bar.t` is *data*: each call carries that symbol's own latest bar, and
symbols disagree on how recent that is. Friday is ISO week 28, Monday is week 29 — so one
lagging symbol flips the guard back and the whole run repeats. (Full analysis: PR #424.)

Compounding it: **a run whose every order was rejected produced no orders, and was therefore
indistinguishable from a run that never happened.** "No orders landed" was read as "nothing
happened, try again."

### 4. There is no durable record between "signal generated" and "order accepted"

**Rejected orders are not persisted.** The `orders` table showed *zero* rows for account 1 all
day, so the investigation reached the wrong conclusion twice — first "it ran and correctly did
nothing," then "it was halted and never ran." Both wrong. It ran six times and was refused
eighteen times. Only the `signals` table carried the truth, and only by accident.

An operational system cannot have a hole where its most important decisions are made.

---

## What was NOT done, and why

- **No risk-engine bypass.** Non-bypassable gates are an architectural invariant.
- **No raising of `max_daily_loss`.** An audited parameter change is still functionally a
  bypass when its purpose is to defeat the active protection condition — and it would have
  re-enabled buys, not only reductions.
- **No intraday hot-patch.** Deploying an inadequately tested risk-gate change to the live
  order path under time pressure trades a contained problem for an uncontained one.
- **No discretionary liquidation.** The strategy's *own* intent (trim SNDK, trim LITE) is
  recoverable; inventing new quantities under intraday pressure is not the same thing.

**Disposition:** no trade executed. Risk-reducing orders were blocked by a confirmed risk-gate
design defect. Existing positions were retained until a tested corrective release could be
deployed. *This is a controlled acceptance of residual paper risk to avoid creating a more
serious control failure — not an endorsement of holding the positions.*

---

## Corrective actions

| # | Action | Priority | Status |
|---|---|---|---|
| 1 | Enforce `HALTED` before dispatch — persisted status, fail closed, all dispatch paths | **P0** | this PR |
| 2 | Durable one-run-per-slot claim — `UNIQUE (account, strategy, slot, version, retry_generation)` | **P0** | this PR |
| 3 | Bar-keyed guard → dispatch-keyed guard (the oscillation itself) | P0 | PR #424 |
| 4 | **ADR 0042** — verified risk-reducing orders through active loss/breaker gates + durable risk-decision ledger | **P1** | pending |
| 5 | **ADR 0043** — loss-control architecture: separated controls, persisted session baseline, trip classification, reconciliation, recovery preflight, hysteresis | P1 | pending |
| 6 | Portfolio construction review — 3 of 5 names (SNDK/WDC/MU) are memory/storage: **59% of the book in one sub-industry**, and they produced **78% of the day's loss**. A per-name cap does not constrain a book whose names are the same trade. | P2 | pending |

### Release gate for ADR 0042 (owner-specified)

Unit tests for the risk-effect classifier and every gate-ordering case · integration through
the real OrderRouter → risk-engine path · **historical replay of today's exact SNDK and LITE
proposals** · negative tests (buys, oversells, reversals, unknown positions, stale snapshots,
short creation all still blocked) · a paper-account canary under a deliberately breached
daily-loss state · proof that `HALTED` prevents dispatch and a rejected run cannot execute six
times · evidence in the new decision ledger for every case.

Replay must demonstrate:

```
BEFORE   SNDK trim -> DAILY_LOSS reject        AFTER   SNDK trim -> ALLOW_VERIFIED_REDUCTION
         LITE trim -> DAILY_LOSS reject                LITE trim -> ALLOW_VERIFIED_REDUCTION
                                                       any buy   -> DAILY_LOSS reject
                                                       oversell  -> RISK_REDUCTION_CLASSIFICATION reject
                                                       2nd run   -> DUPLICATE_SLOT reject
                                                       halted    -> SKIPPED_HALTED
```

---

## Lessons

**The `orders` table is not a history of what the system did.** It records orders *accepted for
submission*. It is silent on everything refused, and it gets purged. Three separate wrong
conclusions on this incident trace to reading it as a ledger. Use `strategy_dispatch_runs` for
*did it run*, the (forthcoming) decision ledger for *what was proposed and why it was refused*,
and `audit_log` for *what was done*.

**A control that is written down but not enforced is worse than no control**, because everyone
plans around the version in the document. ADR 0004's halt semantics were correct, specific, and
absent from the code for months.

**"Halted" does not mean "safe."** It meant, here, 98% invested through a −7% day with the
de-risking path bolted shut.
