# Strategy 8 / LOW-001 — static viability disposition

| Field | Value |
|---|---|
| Status | **READ-ONLY ADJUDICATION.** No mutation, rebalance, activation, or order. |
| Question | Repair prospectively into a worthwhile PAPER strategy, or retire and reclaim Account 6? |
| Method | Three bounded questions: B2 consumer characterization · static gate reconstruction · economic thesis |

## Disposition

```
STRATEGY-8 = REPAIR-TO-ACTIVATE
```

⭐ **Not because work was invested in it.** The economic thesis was independently owner-ruled
**SUPPORTED** on 2026-08-22 against sealed live evidence, and the remaining static engineering is
short. The Dynamic-PIT gate table that made it look expensive is **non-governing for static
operation**.

---

## Q1 — B2: platform-wide cost-basis consumer characterization

Complete census of `avg_entry_price` / `cost_basis` consumers on `origin/main`:

| module | role | post-ADR-0055 status |
|---|---|---|
| `app/orders/positions.py` (`PositionRecomputer`) | **writes** from fills | producer; not a gate input |
| `app/services/position_sync.py` | **writes** from broker-reported values | producer; broker is authoritative |
| `app/api/v1/positions.py` + schemas | **reads** for display | presentation only |
| `app/risk/engine.py` | **comments only** — deliberately excluded from the chain | **no consumption** |
| `app/strategies/backtest_context.py` | backtest plane | not the live order path |

⇒ **No live risk or order-path decision consumes `avg_entry_price`.** The residual is two *writers*
that can in principle disagree (fill-derived vs broker-derived) — a **data-consistency** question,
not a gate-bypass one, and the risk engine no longer depends on either.

⭐ This also explains *why* today's book is clean: `position_sync` overwrites from the broker, which
is why the HON row is gone. ⚠ **That is present sanity maintained by sync — NOT proof that every
historical position record was correct.**

**`B2 = CHARACTERIZED / NO RESIDUAL CONSUMPTION DEFECT / WRITER-CONSISTENCY IS A SEPARATE, NON-GATING QUESTION`**

---

## Q2 — the actual static gate set

The custodied v0.5 §9 table is **stale**: it predates ADR 0055 and the owner closure of Track C.
Marked historical below, never silently deleted.

### Static LOW-001 gates — governing

| gate | state |
|---|---|
| G-A risk allow/deny envelope | **CLOSED** |
| G-B ownership design | **RULED** |
| G-C startup readiness | **CLOSED** |
| **G1 static-strategy regression** | **CLOSED** — note the name: the static path had its own gate |
| G4 exit safety (normal path) | **CLOSED** in code |
| G4b capability | **CLOSED** in code |
| G4b operational reachability | **PASS** 2026-08-31 — 34/34 resolved, 0 excluded, 0 unaccounted |
| §21.5 cost-basis consumer | **REPAIRED + DEPLOYED** — ADR 0055 / #683 `07a9233`; `engine.py` blob `d409d000…` byte-identical at `b94838b6` and `origin/main` |
| Factor readiness | **SATISFIED** — GREEN, interlock proven |
| **G0 Account-6 boundary** | **COMPLETE** — see below |
| Final activation | **SEPARATE OWNER DECISION** (always was) |

**G0 verified complete:** `use_market_regime_filter` is **ABSENT** from strategy 8's params (orphan
removed); `fractional_shares = True` is consistent with the fractional book; and the surviving
`market_filter_symbol` / `market_ma_days` are **declared in `params_schema` and used in the code** —
no schema/code drift. Both are inert while `use_vol_scaling = False`, which the schema documents.

### ⚠ HISTORICAL — Dynamic-PIT gates, NON-GOVERNING for static operation

⛔ Retained for provenance. **Do not carry these into a static activation plan.**

| gate | v0.5 owner | why non-governing |
|---|---|---|
| G2 research-selection conformance | PR B/C | Track C |
| G3 dynamic enrollment correctness | PR B | Track C |
| G5 failure/restart safety | PR C | Track C |
| G6 reconciliation | PR C | Track C |
| G7 paper-only first activation | PR D | Track C |
| S8.6 deployment proof | A3 | consumer closed; procedure unsatisfiable as written |

**Track C / Dynamic PIT is owner-CLOSED.** These gate **Dynamic BUY**, not static operation.

### Static readiness items — RESOLVED 2026-08-31 (read-only)

#### 1. `risk_limits_id = NULL` — **NOT BLOCKING.** Traced, not inferred.

⭐⭐ **`strategies.risk_limits_id` is never read by the risk engine.** Its only readers are
`api/v1/strategies.py` (create/update) and its schemas — a control-plane field with **no gate
consumption**. NULL is therefore not a gate gap.

The engine binds limits by **`user_id` + `scope_type=GLOBAL` + `broker_mode`**
(`_load_global_limits`, `engine.py:614`). **Absence fails CLOSED:** no row ⇒ `REJECT` /
`ReasonCode.NO_LIMITS_CONFIGURED` (`engine.py:240–245`). "No limits" is never "unbounded".

**`ACCOUNT-6 EFFECTIVE RISK LIMITS = VERIFIED / BOUND`** — `risk_limits id=8`, user 6, GLOBAL, paper:

| limit | value |
|---|---|
| `max_position_qty` | 1,000 |
| `max_position_notional` | 25,000 |
| `max_gross_exposure` | 110,000 |
| `max_daily_loss` | 5,000 |
| `max_orders_per_minute` | 200 |
| `allow_short` | 0 |
| `allowed_symbols` / `denied_symbols` | null / null |
| `max_orders_per_day` | None |

Every user 1–7 holds a GLOBAL paper row — the pattern is platform-consistent, not a gap for user 6.
⭐ Current gross 97,481 against the 110,000 cap leaves **12,519 headroom** — not presently truncating.

#### 2. Carried paper-window defects — re-measured

| defect | disposition | evidence |
|---|---|---|
| **cash drag** | **OPEN / NON-BLOCKING** | equity 103,396.94, cash 5,917.25 ⇒ **5.72%** vs the declared `cash_buffer_pct = 2.00%` ⇒ **+3.72 pp**. Improved from the sealed 6.5% but still over target. No safety implication. |
| **in-memory weekly lock** | ✅ **CLOSED** | `_week_completed` reads **durable** `rebalance_completed` signals via `ctx.recent_payloads`; `_mark` writes them via `ctx.log_signal`. The in-memory `_last_rebalance_week` is only a secondary same-process dedup used when `dispatch_seq` is not an int. A restart no longer loses week state. |
| **SPY 200-day nonconformity** | **OPEN / NON-BLOCKING** | latent and **inert**: `use_vol_scaling = False` and the vol-scaling path returns early (`low_volatility.py:549`). `market_filter_symbol` is used only to **exclude** SPY from the tradable universe (`:396`); the schema documents it as *"Not a cash gate"* and `market_ma_days` as *"unused unless vol-scaling is on"*. |

⚠ **Residual observation on the weekly lock, not a defect claim:** `_week_completed` scans only the
**last 80 payloads**. That is a bounded window, not in-memory state; a week generating >80 signals
after the completion marker could scroll it out. Well clear at 34 names, but worth knowing.

⚠ **Tension to flag, not resolve:** repairing the cash drag moves delivered cash toward the
strategy's own declared 2% target, which reads as an **implementation repair**. But it also changes
deployed capital, which brushes against `no_post_seal_tuning = true`. ⛔ Needs an explicit ruling
before anyone touches it; this adjudication does not decide it.

---

## Q3 — economic thesis

Owner-frozen rulings, 2026-08-22, against the sealed paper window
(`81be681c6c3d1766a0098dbf7b82fdb199aef86c8076ff51dd5ec07ed244566b`):

> **LOW-001 research thesis — SUPPORTED / no adverse evidence**
> **Diversifier role — Strengthened by this live window**
> **Account 6 disposition — KEEP / REPAIR**
> Standalone alpha claim — **still not established** (six/seven weeks is too short)

Measured behaviour, Mon–Fri from last-snapshot-of-day equity:

| week | sector (acct 5) | low-vol (acct 6) |
|---|---:|---:|
| 8/10–8/14 | +3.23% | **+0.39%** |
| 8/17–8/21 | −4.05% | **+0.87%** |
| Fri→Fri | −3.76% | **−0.007% (flat)** |

Low-vol took neither the upside nor the drawdown — the diversification signature the thesis
predicts. On 8/17 sector took **78** fills and −3.0% the next day; low-vol took **14**.

⛔ **`no_post_seal_tuning = true`.** This window must not be used to retune LOW-001 economics, and
the concept must not be changed. It authorizes **implementation repairs only**.

⇒ **The economic case is already adjudicated and positive for the Diversifier (B) role.** Retiring
Strategy 8 would discard an owner-supported thesis with live corroboration — which is the opposite
of the "don't preserve it merely because work was invested" test.

---

## Remaining static work — short, and explicitly free of Dynamic-PIT gates

1. Resolve **`risk_limits_id = NULL`** — bind a limits row or establish that account defaults govern.
2. Establish current status of the three carried paper-window defects (cash drag, weekly lock,
   SPY-gate nonconformity).
3. Then a **separate owner activation decision**.

⛔ **Nothing here authorizes activation, rebalance, liquidation, order submission, or any mutation of
Account 6.** ⛔ Two cautions stand: the `engine.py` byte identity proves the *repair content* is
deployed, not that every other prerequisite is met; and the clean 34-position snapshot is *present*
data sanity, not historical correctness.
