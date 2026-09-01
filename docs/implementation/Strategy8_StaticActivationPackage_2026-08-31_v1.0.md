# Strategy 8 / LOW-001 — controlled PAPER restoration package

```
STRATEGY-8 STATIC ACTIVATION PACKAGE = READY FOR OWNER AUTHORIZATION
                                     / IMPLEMENTATION UNCHANGED / RISK LIMITS BOUND
                                     / PRE-STATE SEALED / STOP CONDITIONS DEFINED
                                     / NO POST-SEAL TUNING / NO EXECUTION YET
```

```
STRATEGY-8 RESTORATION-CANARY = MONDAY 2026-09-07 10:32 ET / NORMAL GOVERNED SCHEDULE
                              / NO TUESDAY EXCEPTION / NO MANUAL DISPATCH
                              / NO TEMPORARY CRON MUTATION
```

⛔ **PREPARED, NOT EXECUTED.** Nothing in this package has been performed. It grants no authority;
it is the artifact an owner activation ruling would act on.

⛔ **No economic parameter changes. No manual cash deployment. No Dynamic-PIT code. No
liquidation-to-clean-state.** The static strategy is used **unchanged**.

---

## 1. Runtime and code identity

| leg | value |
|---|---|
| deployed repository commit | `b94838b6aa611e02982b3d1ae5ca5333b5f1d80e` |
| runtime-derived code digest | `sha256:a52823f3bf4e7c919c0a549508230d9de66700042837ab4e9eb02fb98e320a7a` |
| strategy template | `strategies_user/templates/low_volatility.py`, DB `version = 1.0.3` |
| risk engine | `app/risk/engine.py` blob `d409d000fc2129f76aef4e15d9281b1510212472` — byte-identical at `b94838b6` and `origin/main`; carries the ADR-0055 / #683 repair |

⚠ Byte identity proves the **repair content** is deployed. It does not by itself prove every other
prerequisite — those are enumerated separately below.

## 2. Account-6 binding — measured, not inferred

| element | value |
|---|---|
| workbench account | **6** (user 6) |
| broker `account_number` | **`PA30T0I3JJV9`** — broker self-reported |
| credential key fingerprint | **`5da9c9d59a45`** (`sha256(key)[:12]`; ⛔ never the secret) |
| mode | `paper`, broker `alpaca` |

⭐ Consistent with the 2026-08-31 credential census, which recorded account 6 at the same
fingerprint and account number.

## 3. Effective risk limits — VERIFIED / BOUND

⭐ Binding is by **`user_id` + `scope_type=GLOBAL` + `broker_mode`**, *not* by
`strategies.risk_limits_id` (which is a control-plane field the engine never reads). Absence
**fails closed** — `REJECT` / `NO_LIMITS_CONFIGURED`.

`risk_limits id = 8` (user 6, GLOBAL, paper):

| limit | value |
|---|---|
| `max_position_qty` | 1,000 |
| `max_position_notional` | 25,000 |
| `max_gross_exposure` | **110,000** |
| `max_daily_loss` | 5,000 |
| `max_orders_per_minute` | 200 |
| `allow_short` | 0 |
| `allowed_symbols` / `denied_symbols` | null / null |

## 4. Pre-state seal — captured 2026-08-31 21:51 EDT

| item | value |
|---|---|
| equity | **103,414.12** |
| cash | **5,917.25** (5.72%) |
| long market value | **97,496.87** |
| nonzero positions | **34** |
| **book digest** | **`71a6ab2a80f8f6195d4c4965fd9ba17276c28c717d18ebebe660b0eebbb69a91`** |
| open orders | **0** · lifetime orders 259 |

Book digest = `sha256` over `ticker|qty` sorted by ticker. Holdings:

`AAPL:9.629027, ABBV:10, BAC:48.113623, BRK.B:6.000135, CME:10.795795, COST:3.13177, CVX:14.782138,
DIS:24, HD:8.865717, JNJ:11.120622, JPM:8.438068, KO:32.651694, LIN:6.155451, MA:5.051414,
MCD:11.102394, MDT:32.218898, MO:44.266088, NEE:36.111878, PEP:20.71816, PFE:107.81892,
PG:20.564786, PH:2, ROST:10, RTX:11, SCHW:26.369885, SHEL:32.294845, T:118.245505, TJX:21.589269,
UNP:9.745152, V:7.931471, VZ:60.675952, WELL:12.528902, WMT:22, XOM:18.374042`

⛔ **This book is the transition origin.** No flatten, no manual reshaping, no forcing toward the 2%
cash target.

## 5. Scheduler and rebalance state

| item | value |
|---|---|
| status | **`IDLE`** |
| schedule | `32 10 * * mon` → Mondays 10:32 America/New_York |
| `cooldown_until` | `2026-08-24 14:33:56` — **elapsed** |
| `has_pending_reload` | `1` — ⛔ informational only; not an activation gate, **do not clear** |
| last durable marker | `rebalance_completed`, `iso_week [2026, 35]`, written `2026-08-24 14:33:03` |
| next window | **2026-09-07 10:32 EDT**, `iso_week (2026, 37)` |

### ⚠ A material observation about the 2026-08-24 marker

The three signals immediately preceding that `rebalance_completed` are `rebalance_entry` records each
carrying **`"rejected": "STRATEGY_COOLDOWN"`**. The week was marked **complete even though its entry
orders were refused**.

⇒ **The durable marker records that a rebalance RAN, not that it SUCCEEDED.** A first restored
dispatch that is refused would still consume its ISO week and not retry until the following Monday.
That is not a defect to repair here, but it **must** shape the stop conditions and the reading of
first-dispatch evidence.

## 6. Expected first allowed action

1. Owner activation ruling (separate — this package does not grant it).
2. Strategy 8 `IDLE → PAPER`. **Activation crosses the factor-readiness interlock**, which is
   currently GREEN and proven; the engine re-evaluates it at `register`.
3. **First governed dispatch: 2026-09-07 10:32 EDT**, ISO week `(2026, 37)` — not marked complete, so
   `_week_completed` will not short-circuit it.
4. It computes a target book from current factor data and trades the **delta** from the sealed
   34-position origin. Expected shape: holds, small reductions/additions. ⛔ Not a rebuild.

⛔ **No canary order, no manual dispatch, no scheduler re-arm beyond the existing weekly cron.**

### 🚨 `STRATEGY8-MANUAL-DISPATCH-SEAM-001 = ABSENT BY DESIGN / PER-STRATEGY CRON IS SOLE NORMAL DISPATCH PATH / NO EXCEPTION AUTHORIZED`

The engine arms **one APScheduler job per strategy** from that strategy's own `schedule`:

```python
cron = CronTrigger.from_crontab(_normalize_crontab_dow(schedule), timezone=_STRATEGY_SCHEDULE_TZ)
self._scheduler.add_job(self._dispatch_bar_tick, cron, kwargs={"strategy_id": strategy_id}, ...)
```

`_dispatch_bar_tick` is **per-strategy**. Strategy 8's cron is `32 10 * * mon`, so **its next fire is
2026-09-07 10:32 ET and no other day produces a dispatch.** ⚠ The `*/5` ticks visible in the logs
belong to the **Range Trader** (schedule `*/5 * * * *`) — they are not a shared bus.

**There is no explicit dispatch seam.** `api/v1/strategies.py` exposes no rebalance / run-now /
dispatch-now / trigger endpoint. The only "rebalance" scripts are PORT-001 *check* scripts.

⇒ An out-of-cadence dispatch would require one of three things, **all withdrawn and none authorized**:

| mechanism | why refused |
|---|---|
| edit `strategies.schedule` | rewrites the recurring scheduler; ungoverned config mutation on a live 34-position book |
| call `_dispatch_bar_tick` directly | scheduler **bypass** — the "just for this one case" pattern `CLAUDE.md` lists as proven costly |
| temporary `*/5` then revert | same prohibition, plus two extra mutations and a revert to verify |

⭐ **The absence is the design, not a gap.** It is consistent with the single-dispatch-point
invariant, and it is why no Tuesday canary is possible without weakening a control.

### Week accounting

**ISO week 36 remains UNCONSUMED** — no dispatch occurs this week. **Week 37's normal Monday event is
the canary.** No exception to document, no schedule to restore, no weekly-guard bypass.

### Activation ≠ dispatch

Arming makes the **existing** scheduler live. It creates no execution. Activating early is
deliberate: it buys time to verify the arming itself, days before any order can be produced.

## 7. Stop conditions — any one halts and reports

1. Runtime identity at activation ≠ `b94838b6…` / `sha256:a52823f3…`.
2. Broker `account_number` ≠ `PA30T0I3JJV9` or credential fp ≠ `5da9c9d59a45`.
3. Effective limits resolve to anything other than `risk_limits id=8`, or resolve to **none**.
4. Pre-dispatch book digest ≠ `71a6ab2a…` without an explained, governed cause.
5. Factor readiness not GREEN at dispatch — the interlock must refuse, and a refusal is a stop.
6. Any order rejected by the **risk** engine (`ORDER_REJECTED_BY_RISK`) — investigate before the
   next window rather than letting the week consume itself.
7. Gross exposure projected above **110,000**, or any single position above **25,000** notional.
8. More than **one** `rebalance_completed` marker for the same ISO week.
9. Any short order (`allow_short = 0`).
10. Realized daily loss approaching **5,000**.
11. Any position mutation on Accounts 5 or 7, or any strategy other than 8 changing state.

## 7a. Pre-canary proofs — collected immediately AFTER activation, days BEFORE any dispatch

These verify the arming without touching the dispatch architecture:

1. Strategy 8 status is the activated/eligible state, not `IDLE`.
2. The APScheduler job for strategy 8 exists and is armed.
3. **Its next-run time resolves to `2026-09-07 10:32 America/New_York`** — not sooner, not another day.
4. Broker binding still `PA30T0I3JJV9` / fp `5da9c9d59a45`.
5. Effective limits still resolve to `risk_limits id = 8` with unchanged values.
6. **Zero orders produced by activation** — arming must not emit anything.
7. **Book unchanged**: digest still `71a6ab2a…` allowing for market-driven value moves but **no
   quantity, position-count, or order-state change**.
8. No state change on Accounts 5 or 7.

⛔ Any failure here is a stop-and-report, and it happens with days of margin before the canary.

## 8. Post-canary evidence collection

**Immediately pre-dispatch (2026-09-07, before 10:32 ET)** — re-measure, and ⚠ **distinguish normal
market movement from mutation**: equity and dollar values will legitimately differ from the Monday
seal; **quantities, position count, and order state must not**: runtime identity · broker binding ·
effective limits · book digest · open orders · factor readiness verdict · strategy row.

**Post-dispatch (after 10:45 ET):** strategy status · every order with status and rejection reason ·
fills · resulting book digest and delta vs `71a6ab2a…` · equity/cash/long-market-value before and
after · `rebalance_started` / `rebalance_completed` markers and their ISO week · risk decisions ·
gross exposure vs cap · audit rows.

**Adjudication:** normal weekly scheduling is re-armed **only** if that evidence passes. ⛔ A first
dispatch that is refused, partial, or ambiguous does **not** earn unattended operation.

## 9. Carried rulings — reproduced verbatim

```
STRATEGY8-CASH-DRAG-001 = OPEN / NON-BLOCKING / OBSERVE UNDER RESTORED STATIC OPERATION
                        / NO PRE-ACTIVATION CAPITAL-DEPLOYMENT REPAIR AUTHORIZED

STRATEGY8-SPY200-001    = OPEN / NON-BLOCKING / LATENT WHILE use_vol_scaling=false
                        / NO REPAIR REQUIRED FOR STATIC RESTORATION
```

⭐ On cash: 5.72% is **not** declared desirable. If ordinary governed rebalance logic later moves cash
toward the existing 2% target **without changing parameters or rules**, that is normal operation.
⛔ **Do not manually force the book toward 2% as part of activation.**

⛔ `no_post_seal_tuning = true`. The sealed 2026-08-12…08-21 window must not be used to retune
LOW-001 economics, and the strategy concept must not change.

## 10. Explicitly out of scope

⛔ No Dynamic-PIT code or gates (G2/G3/G5/G6/G7, S8.6 — HISTORICAL / NON-GOVERNING) · no S8.6 rerun ·
no strategy parameter change · no `risk_limits` edit · no clearing `has_pending_reload` · no
liquidation · no Account 5 or 7 action · no live-money path.
