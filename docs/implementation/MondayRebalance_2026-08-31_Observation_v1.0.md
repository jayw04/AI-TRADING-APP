# MONDAY-REBALANCE-2026-08-31 — scheduled-window observation

Read-only observation of every governed rebalance window on Monday 2026-08-31, on accepted runtime
`b94838b6aa611e02982b3d1ae5ca5333b5f1d80e`. ⛔ **Observation only** — no strategy status, schedule,
reload flag, position, or order was changed to produce this record.

⚠ This record is **separate from** `FACTOR SYSTEM = GREEN / ACCEPTED / INTERLOCK PROVEN`. GREEN
removed a shared technical blocker; it activated nothing and selected nobody. The two facts are kept
apart deliberately.

---

## MORNING — `MORNING-REBALANCE-2026-08-31 = OBSERVED / STRATEGIES 2,4,5,7,8,9 REMAINED IDLE / ZERO REBALANCE DISPATCH / ZERO NEW AUTHORITY CREATED`

Windows verified from `strategies.schedule`, not assumed:

| window (ET) | strategy | user/acct | status after |
|---|---|---|---|
| 10:00 | 2 momentum-portfolio *(archived)* | 1 | IDLE |
| 10:08 | 4 momentum-conservative | 3 | IDLE |
| 10:16 | 5 momentum-growth | 4 | IDLE |
| **10:24** | **7 sector-rotation** | 5 | IDLE |
| 10:32 | 8 low-volatility | 6 | IDLE |
| 10:40 | 9 combined-book | 7 | IDLE |

⚠ **Strategy 7's 10:24 window was absent from the first status framing of the morning** and was
recovered only by reading the schedules directly. Enumerate windows from `strategies.schedule`; never
from a remembered list.

**Closing capture 2026-08-31 10:45:13 EDT / 14:45:13Z**, after every morning window:

- platform **open orders = 0**
- **orders today for users 3, 4, 5, 6, 7 = 0** — zero for every governed rebalance account
- nonzero positions: user 6 = **34** (unchanged), user 7 = **51** (unchanged)
- Account-6 and Account-7 position sync current (`14:45:13`) — ordinary read-only reconciliation
- journal scan **09:55–10:45**: no dispatch for any governed rebalance strategy

### The one live strategy — and why it does not contaminate the evidence

Strategy **1 Range Trader Top-5** (user 2, `PAPER`, `*/5 * * * *`) is the only live strategy and
operated normally: orders today **1 → 2**, positions **1 → 2**, open orders returned to **0**,
reconciliation clean. It is a **different strategy on a different account** from every governed
rebalance book, and its activity is disjoint from the windows above.

### Account boundaries preserved

- **Account 7 (strategy 9) — isolated by standing operating instruction.** 51-position book
  **observed untouched**; no transition rebalance, no cleanup, no reconciliation-driven mutation.
  Factor GREEN granted it nothing. ⚠ The "FROZEN / NO-GO" characterisation is an **operating boundary
  carried from working notes**, *not* a custodied governance ruling verified here — see the activation
  reconciliation, which classifies strategy 9 as `activation authority NOT ESTABLISHED`.
- **Account 4 (strategies 5, 11) — HELD.** The 10:16 window no-opped. Today's platform GREEN state is
  not a reason to reinterpret the HELD decision.
- **Account 6 (strategy 8) —** see `TrackB_2026-08-31_IdleThroughRebalance_Decision_v1.0.md`.

---

## AFTERNOON — `AFTERNOON-REBALANCE-2026-08-31 = OBSERVED / STRATEGY 11 REMAINED IDLE / ZERO REBALANCE DISPATCH / ZERO NEW AUTHORITY CREATED`

Independent read-only capture **2026-08-31 15:55:03 EDT / 19:55:03Z**, after the 15:50 window, on
runtime `b94838b6…`.

| item | observed |
|---|---|
| strategy 11 `momentum-daily` (user 4, v0.2.0) | **`IDLE`**, schedule `50 15 * * mon-fri` unchanged, `has_pending_reload=1` unchanged |
| Account 4 | **0 positions · 0 open orders · 0 orders today · 0 orders total** |
| platform open orders | **0** |
| orders today, users 3/4/5/6/7 | **0** |
| all strategy statuses | `1:PAPER` · 2,3,4,5,7,8,9,10,11 `IDLE` — identical to the morning |

**Dispatch evidence, 15:45–15:58:** the only scheduler activity is the engine's generic
`_dispatch_bar_tick` (`*/5` cron — the Range Trader's tick) and `_dispatch_health_monitor_tick`.
**No strategy-11 job ran and no rebalance job exists** — strategy 11 is IDLE and therefore not
registered with the scheduler.

⭐ **Account 4 has `orders total = 0`** — it has never traded. Its HELD status is not a pause on an
active book; there is no book.

⚠ Strategy 1 Range Trader continued normally (orders today 2 → 3), unrelated to the 15:50 window.

---

## 🏁 FULL-DAY ROLL-UP — both halves now observed

```
MONDAY-REBALANCE-2026-08-31 = OBSERVED / ALL GOVERNED REBALANCE WINDOWS PASSED
                            / ZERO REBALANCE DISPATCH / ZERO NEW AUTHORITY CREATED
```

Every governed rebalance window on 2026-08-31 — **10:00 s2 · 10:08 s4 · 10:16 s5 · 10:24 s7 ·
10:32 s8 · 10:40 s9 · 15:50 s11** — arrived and produced **no dispatch, no order, and no state
change**. Strategies 2, 4, 5, 7, 8, 9 and 11 all remained `IDLE` across the whole session. The only
live strategy, non-factor Range Trader (strategy 1, Account 2), operated normally throughout and is
disjoint from every window above.

⛔ **This roll-up creates no authority.** It records that scheduled opportunities passed without
action — which is what the governing decisions required. It is a **separate fact** from
`FACTOR SYSTEM = GREEN / ACCEPTED / INTERLOCK PROVEN`; GREEN removed a shared technical blocker and
**activated nothing and selected nobody**.

---

## 🐛 Observation refinement — `has_pending_reload` is PLATFORM-WIDE, not a 7/8/9 condition

The 10:45 capture shows **`has_pending_reload = 1` on all ten strategies**, including strategy 1,
which is `PAPER` and trading normally. An earlier note in this session observed the flag on 7/8/9 and
read it as a per-strategy activation prerequisite; that framing was **incomplete** — the flag does not
distinguish 7/8/9 from anything else, and it demonstrably does not prevent an already-running strategy
from operating.

⇒ Whether a reload predating the `2026-08-31T10:07:35Z` restart constitutes an **activation**
prerequisite is **unverified** and is exactly the "verify the applicability of the
one-runtime-epoch/reload rule" item in the read-only activation reconciliation.
⛔ **Do not clear `has_pending_reload` or perform a reload** on any strategy.

---

## 🏁 DAY CLOSE

```
2026-08-31 PAPER GOVERNANCE DAY = CLOSED
                                / NO GOVERNED IDLE STRATEGY ACTIVATED
                                / MORNING AND AFTERNOON REBALANCE WINDOWS OBSERVED
                                / ZERO NEW EXECUTION AUTHORITY CREATED
```
