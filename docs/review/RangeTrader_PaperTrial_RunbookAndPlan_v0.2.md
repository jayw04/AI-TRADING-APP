# Range Trader — Paper Trial Runbook & Implementation Plan (v0.2)

**Status:** DRAFT for owner review · **Date:** 2026-06-24 · **For:** trying the Range Trader live on paper tomorrow at market open.

> **v0.2 — owner review folded** (`Docs/review/comments.md`, 9.6/10 → target 9.9/10). Added: explicit operational success criteria (§2); the **mechanical-vs-trading** framing up front (§0.1); a four-level **failure classification** (§13); **expected evidence artifacts** (§9.1); a **pre-registered "what would surprise us"** list (§10); **Capability Maturity** for RNG-001 (§0.3); the **whitepaper / platform** connection (§0.4); **why we keep a rejected strategy** + the **three strategy classes** reframing (§0.2); **regression value** (§17); and **exit deliverables + Go/No-Go** (§18).

**Goal of this trial:** verify that the Range Trader's **daily, opening-range mechanics fire correctly on a live paper account during RTH** — entries near support, exits near resistance, stop/time-exit, per-day trade caps. This is an **execution / operations validation, not an edge test** (see §0). RNG-001 was researched and formally **REJECTED** (no robust OOS edge); we are validating that the *execution platform does what the code says*, live, on real intraday bars — not expecting profit.

Everything below was verified against the running code and the live DB (`data/workbench.sqlite`) on 2026-06-24; `file:line` references are included so you can trust each claim.

---

## 0. Framing — what this trial *is* (and is not)

### 0.1 Mechanical success ≠ trading success
A reader's instinct is "paper trial → did it make money?" That is **not** the objective. The trial evaluates **only the left column**:

| **Mechanical (this trial evaluates)** | **Trading (explicitly out of scope)** |
|---|---|
| Scheduler fires on cadence | P&L |
| Opening range + levels correct | Win rate |
| Orders correct & risk-gated | Sharpe |
| Audit / reconciliation clean | Edge |

A losing day, zero trades, or stop-outs are **not** failures of this trial. A missed scheduler tick, a wrong level, a duplicate order, or an audit gap **are**.

### 0.2 Why test a strategy we already rejected? — the three strategy classes
The platform runs three distinct classes of strategy:

| Class | Purpose | Example |
|---|---|---|
| **Production** | Earn returns | Momentum v1.1 (live paper) |
| **Candidate** | Collect evidence toward a verdict | a program under research |
| **Benchmark** | Validate the execution & operations platform | **Range Trader (RNG-001)** |

Range Trader is a **Reference Benchmark Strategy** (a.k.a. Execution Validation Strategy). Its purpose is **no longer alpha** — it is continuous validation of execution, broker integration, scheduler, audit, and regression, *without any risk of promotion to production*. Rejected strategies are retained as permanent reference implementations precisely because they exercise the full order path safely. That a rejected strategy can still have **production-quality execution** is a hallmark of a mature research platform — and a platform value worth demonstrating.

> **Proposed follow-up (beyond this doc):** formalize the three-class taxonomy in the platform + registry (a `strategy_class` field; rename "rejected" → "Reference Benchmark" in the registry/UI). Owner-gated; noted here, not implemented by this trial.

### 0.3 Capability Maturity for RNG-001
Maturity is tracked per lifecycle stage — a rejected research verdict and a production-grade execution capability coexist:

```
Research   → L2 Validated (a real, testable hypothesis, properly run)
Evidence   → REJECTED   (no robust OOS edge; the honest "no")
Execution  → L4 Operational  ← what THIS trial confirms, live
Production → Not Promoted (correctly — by governance)
```

### 0.4 Where this sits in the platform (whitepaper architecture)
This trial validates the **Execution Platform + Operations Platform**, not the Research Platform:

```
Research    ✓ completed
Governance  ✓ rejected (verdict of record)
Execution   ◻ under validation  ← this trial
Operations  ◻ under validation  ← this trial
```

---

## 1. TL;DR — what will actually happen tomorrow

If you start strategy **id 1 (NVDA)** and/or **id 3 (AAPL)** to PAPER:

1. A scheduler job fires **every 5 minutes**, but only **during regular hours (09:30–16:00 ET)** — out-of-session ticks are skipped (`engine.py:758 _dispatch_allowed` → `MarketSession.classify()`).
2. **09:30–10:00 ET** the strategy *builds* today's range (first `opening_range_minutes = 30` of bars) and **takes no entries** while it forms.
3. From **~10:00 ET** the day's levels freeze: **entry = opening-range low, exit = opening-range high, stop = range-low × (1 − 0.5%)** (`range_trader.py:329-346`).
4. It **buys** when price dips to/below the entry, **sells** at the exit or stop, force-exits any open position by **15:55 ET**, ≤ **4 entries/day (NVDA) / 3/day (AAPL)**.
5. Levels reset and rebuild **fresh next day**.

> **⚠ Most important catch (see §5):** the stored fixed `entry/exit/stop` prices **will NOT be used** — these run in **`opening_range` mode** and derive levels daily.

---

## 2. Operational Success Criteria

The trial is **successful** when all of the following hold (none concern profitability):

- [ ] Scheduler fires every 5 minutes during RTH (and is skipped outside it)
- [ ] Opening range completes correctly (built 09:30–10:00, then frozen)
- [ ] Dynamic levels calculated (entry/exit/stop set, `stop < entry < exit`)
- [ ] Orders pass the risk engine (or are rejected for a *correct*, logged reason)
- [ ] Entry generated when the trigger occurs (price ≤ entry, gates satisfied)
- [ ] Exit generated correctly (resistance / stop / 15:55 time-exit)
- [ ] Audit log complete (every order hash-chained)
- [ ] No duplicate orders (in-flight guard holds)
- [ ] No scheduler failures (no missed/stacked ticks; `max_instances=1` + coalesce)
- [ ] No reconciliation failures (broker ⇄ local consistent)
- [ ] Clean shutdown (Stop → IDLE, job removed, no orphaned state)

A clean run that produces **zero trades** still **passes** if the above hold and the no-trade outcome is explained (e.g., price never tapped the range low).

---

## 3. Verified current state

| Field | Range Trader **NVDA** (id 1) | Range Trader **AAPL** (id 3) |
|---|---|---|
| Status | `IDLE` | `IDLE` |
| User / Account | user 2 / account 2 "Alpaca Paper (Range)" (`mode=paper`) | same |
| Symbol | `NVDA` (fixed) | `AAPL` (fixed) |
| Schedule | `*/5 * * * *` (every 5 min) | `*/5 * * * *` |
| Timeframe | `5Min` | `5Min` |
| `level_mode` (effective) | **`opening_range`** (default; not stored) | **`opening_range`** |
| Stored fixed levels (IGNORED in opening_range) | entry 210.63 / exit 210.95 / stop 191.49 | entry 290.76 / exit 291.23 / stop 280.71 |
| `max_trades_per_day` | 4 | 3 |
| `risk_per_trade_pct` | 0.01 (1%) | 0.01 |
| `cooldown_until` | none | none |

**Risk limits in force** (user 2, paper, GLOBAL row id 6): `max_position_qty 1000`, `max_position_notional $10,000`, `max_gross_exposure $10,000`, `max_daily_loss $500`, `max_orders_per_minute 10`, `allow_short = no`. Every order still passes the central risk engine (non-bypassable).

---

## 4. How the strategy works (mechanics)

### 4.1 Ticker is **fixed per strategy**, not chosen daily
Each Range strategy instance trades exactly one symbol (`symbols` set when the template is applied — `range_trader.py:67`). There is **no universe scan / daily stock selection**; NVDA and AAPL are two separate rows. To trade another symbol you apply the template again.

### 4.2 Entry/exit/stop are **recomputed each day** (opening-range mode)
At each new ET day the engine resets the range and refreshes sizing equity from the live account (`range_trader.py:202-217`). Then (`_resolve_levels`, `range_trader.py:311-346`):
- **09:30 → +30 min:** accumulate each bar's high/low; return `(0,0,0)` → **no entries**.
- **after the window:** freeze `entry = range_low`, `exit = range_high`, `stop = range_low × (1 − 0.005)`.
- Size = `risk_per_trade_pct × equity / (entry − stop)`, capped at `max_position_qty` and the risk engine's notional caps (`range_trader.py:348-366`).

### 4.3 Dispatch path
`*/5` cron → `_dispatch_bar_tick` (`engine.py:777`) → **session gate** `_dispatch_allowed` (RTH only; `allow_extended_hours` off) → `ctx.get_recent_bars(symbol,"5Min",n=1)` → `on_bar(bar)` (`engine.py:786-813`).

---

## 5. ★ Critical clarification: stored fixed prices are ignored

Stored params contain `entry_price`/`exit_price`/`stop_price` but **no `level_mode`**. The engine merges class defaults under stored params:

```
merged_params = {**cls.default_params, **(row.params_json or {})}   # engine.py:286
```

`default_params["level_mode"] = "opening_range"` (`range_trader.py:75`) is not overridden, so the effective mode is **`opening_range`**, and `_resolve_levels` **never reads** the stored fixed prices (`range_trader.py:323-346`). Intended (review E5): the default was flipped so the strategy and its proposal-page eval simulate the live daily rules, not a frozen snapshot. **Consequence:** tomorrow both trade off *that day's* opening range regardless of the 210.63 / 290.76 numbers. See §16 to test fixed levels instead.

---

## 6. Pre-flight checklist (before / at open)

- [ ] **Stack up** with current code (`docker compose ps`). `range_trader.py` is mounted (E5 default already live, no rebuild); the engine merge is in the running image.
- [ ] **Market-data access for intraday bars (THE key risk).** `get_recent_bars` pulls 5-min bars from Alpaca data. Norton SSL has historically blocked `data.alpaca.markets`; the ADR 0017 / truststore fix (PR #91) is on main and should defeat it, but only *weekly* bars have been exercised live here. **Verify at open** (§11): `strategy_dispatch_get_bar_failed` = bars not arriving → nothing trades.
- [ ] **Paper risk-limits row present** — yes (user 2 paper GLOBAL id 6, §3).
- [ ] **Account / breaker** — account 2; confirm no `circuit_breaker_tripped_at`.
- [ ] **No cooldown** — both null; paper start is immediate (the 24h activation cooldown is **LIVE-only**, `activation.py:64`, `:4-6`).
- [ ] **Decide `level_mode` and symbol(s)** (§16) before starting.

---

## 7. Activation (IDLE → PAPER)

Paper activation = the **start** endpoint — immediate, no 24h wait (`strategies.py:9` "status -> PAPER"; `engine.register`).

**UI:** Strategies → Range Trader (NVDA/AAPL) → **Start**.
**API:** `POST /api/v1/strategies/1/start` (NVDA) / `POST /api/v1/strategies/3/start` (AAPL); auth required. Stop: `POST /api/v1/strategies/{id}/stop` → `IDLE`.

**Recommendation:** start **NVDA alone first** to watch mechanics cleanly; add AAPL once bars are confirmed flowing.

---

## 8. Tomorrow's timeline (all times ET)

| Time | What happens |
|---|---|
| before 09:30 | `*/5` ticks fire but the session gate **skips** them. No action. |
| **09:30** | New ET day → range reset, sizing equity refreshed from the live paper balance. Range starts building. |
| 09:30–10:00 | Range **forming**; **no entries** (levels return 0). |
| **~10:00** | Levels **frozen** (entry=low, exit=high, stop=low×0.995). Entries permitted. |
| 10:00–15:55 | **Entry** when price ≤ entry (valid ordering); **exit** at ≥ exit or ≤ stop; ≤ 4/3 entries; once stopped out, no re-entry that day. |
| **15:55** | Hard time-exit of any open position (`hard_exit_before_close_minutes = 5`). |
| 16:00 | Close; ticks skipped; DAY orders expire. |

---

## 9. What "working" looks like + expected evidence

- `strategy_registered` on start; a `strategy:{id}:on_bar` job present (`GET /api/v1/ops/state`).
- 09:30–10:00: bars arriving, **no** ENTRY signals.
- ~10:00: levels set; ENTRY + paper BUY when price taps the range low; matching EXIT at high/stop; `time_exit` near 15:55 if still in.

### 9.1 Expected evidence artifacts (produced regardless of profitability)
The trial's deliverable is **evidence**, not P&L. After the run these should exist:

- **Logs** — dispatch + lifecycle lines (per tick, per signal)
- **Signals** — ENTRY/EXIT with `reason` (`GET /api/v1/strategies/{id}/signals`)
- **Orders** — submitted/accepted/rejected
- **Positions** — paper account 2
- **Audit records** — every order, hash-chained
- **Risk checks** — each order's risk-gate result
- **Opening-range levels** — the day's entry/exit/stop actually used
- **Exit reasons** — `range_exit` / `stop_loss` / `time_exit`
- **Scheduler history** — job fire record (no missed/stacked runs)
- **Broker reconciliation** — broker ⇄ local consistent

---

## 10. Pre-registered: "what would surprise us?"

Defining surprises *before* the run prevents hindsight bias.

**Expected (NOT a problem):** zero trades · stop-outs · a losing day · no signal (price never tapped support).

**Unexpected (investigate — a mechanics bug):**
- an entry **before 10:00** (range window not respected)
- an **exit before any entry**
- **duplicate fills** for one decision (in-flight guard breached)
- the **range changing after it froze**
- **any trade after 16:00** or **in premarket** (session gate breached)
- an order that **bypassed** the risk engine / left no audit record

---

## 11. Monitoring (where to look)

- **Logs (backend container):** `strategy_registered`, then per tick. **Red flags:** `strategy_dispatch_get_bar_failed`, `on_bar` exceptions, `entry_skipped_invalid_levels`.
- **Signals:** `GET /api/v1/strategies/{id}/signals` (reasons + any `rejected`).
- **Positions / equity:** account 2.
- **Ops state:** `GET /api/v1/ops/state` (job health).
- **Audit log:** every order (hash-chained).

---

## 12. Safeguards already in the code (no action needed)

- No entries while the range forms; `stop < entry < exit` enforced (`_levels_ok`, `range_trader.py:424`); invalid → inert for entries, logged once/day.
- Stop-out halt: no re-entry after a stop that day (`_stopped_today`).
- In-flight order guard: per-symbol pending flag, reconciled each bar + on fill.
- Central risk engine gates every order (§3 caps); **no shorting**.
- Market-session gate prevents any out-of-RTH action.

---

## 13. Failure classification

Not every failure is equal. Classify by layer — and note that a **research** failure is *expected* while a **mechanics** failure is *not*:

| Level | Class | Examples | Expected? |
|---|---|---|---|
| **L1** | Infrastructure | scheduler down, broker unreachable, **market data blocked**, DB error | No — blocks the trial |
| **L2** | Strategy logic | wrong levels, wrong stop, duplicate entry, range mutates after freeze | **No — a bug to fix** |
| **L3** | Execution | order rejected (bad), timeout, reconciliation mismatch | No — investigate |
| **L4** | Research | edge absent / losing day / zero trades | **Yes — expected (RNG-001 is rejected)** |

If the only "failures" are L4, the trial **passed**: the execution platform worked and the strategy behaved exactly as a rejected edge should.

---

## 14. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Intraday bars blocked by Norton** (`data.alpaca.markets`) → nothing trades | Medium (untested intraday here) | Verify at open via logs; ADR 0017 truststore should handle it; else run from WSL (standing networking note) |
| Stored fixed prices assumed but mode is `opening_range` | High if unaware | §5 — decide `level_mode` up front |
| Thin open → tiny range → over-tight levels, instant stop | Low | `stop_buffer_pct` + `_levels_ok`; observe, tune next day |
| Expecting profit from a rejected strategy | — | §0 — this is execution validation, not alpha |

---

## 15. Rollback / deactivate

- **Stop:** `POST /api/v1/strategies/{id}/stop` (or UI **Stop**) → `IDLE`, job removed. Open paper position remains; flatten manually if desired.
- Paper only — no real capital; stopping mid-day is frictionless.

---

## 16. Decision points for you (before starting)

1. **`level_mode`** — keep **`opening_range`** (recommended: tests the real daily mechanics) **or** set **`fixed`** (uses stored 210.63/etc. — a static study with stale snapshots). To switch: set strategy param `level_mode = "fixed"` before Start.
2. **Which symbol(s)** — NVDA only first, or both.
3. **`opening_range_minutes`** — 30 (default, conservative) vs 15 (levels set earlier, longer trading window). Leave 30 for the first trial.

---

## 17. Regression value (why this outlives one trial)

Once validated, Range Trader becomes a **permanent execution-regression benchmark**. After any major execution/operations change, re-run the benchmark set to confirm no regression:

```
Major execution change → run { Momentum, Range, Discovery, … } → verify execution unchanged
```

This elevates the strategy from a one-time experiment to a standing part of the platform's test surface — alpha-free, low-risk, full-path coverage.

---

## 18. Exit deliverables + Go/No-Go

After tomorrow's run, produce (append to this doc or a sibling Results doc):

- **Operational Report** — pass/fail against §2 success criteria
- **Timeline** — what fired when (vs §8)
- **Logs** — dispatch + signal excerpts
- **Trade list** — entries/exits with reasons (or "zero trades — why")
- **Screenshots** — signals / positions / ops state (optional)
- **Issues found** — classified per §13
- **Recommendations** — params (e.g., `opening_range_minutes`), follow-ups
- **ADR updates** — if any execution behaviour needs recording
- **Capability status** — confirm/raise RNG-001 Execution maturity (§0.3)
- **Go / No-Go** — keep as a standing benchmark? promote the three-class taxonomy (§0.2)?

---

## 19. Open questions to confirm at open

- Does `get_recent_bars("NVDA","5Min",n=1)` return fresh bars on this machine during RTH? (the make-or-break check)
- Is the running image current enough that the session gate behaves as `main`? (long-merged — expected yes)
- Is account 2's paper balance enough for the sized position (1% risk on ~$100k est., capped at $10k notional)?

---

*Prepared from the live code + DB on 2026-06-24; owner review v0.1 → v0.2 folded. Append the §18 deliverables after the run to complete the evidence lifecycle.*
