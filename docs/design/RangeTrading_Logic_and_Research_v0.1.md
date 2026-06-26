# Range Trading — Logic, Trigger Rules & Improvement Research (v0.2)

| Field | Value |
|---|---|
| Date | 2026-06-26 |
| Scope | The TradingWorkbench **RangeTrader** template (`apps/backend/strategies_user/templates/range_trader.py`) — the *fade-the-range* intraday mean-reversion strategy. (Distinct from the sibling system's "Combined Book.") |
| Status | Working doc — current behavior + a prioritized research plan. **v0.2 folds the owner review (`design ideas.md`, 9.8/10):** the two-hypothesis split (H1 symbols / H2 entry, tested separately), a composite **Range Score** + **Range Efficiency**, the **support-zone** entry, **bounce confirmation**, and the **Candidate Engine** architecture (§8, §10). |
| Live instance | `Range Trader NVDA` (strategy id=1, user2 `range@local.dev`, account 2, PAPER). An IDLE `Range Trader AAPL` (id=3) also exists. |
| Related | Range Candidates ranker (PR #281) · dispatch-liveness monitor (PR #280) · the MarketHours autostart task. |

---

## 1. Thesis — fade the range

Intraday mean reversion: in a **range-bound** session, price oscillates between a support (low) and a resistance (high). The strategy **buys near support and sells near resistance**, with a hard stop just below support for when the range breaks. It is **long-only** (buys dips, sells the bounce) — it does not short the top of the range. The edge it bets on is *oscillation*; on a one-directional (trending) day it deliberately does little or nothing.

> ⚠ Honest framing (from the backtest, this session): range trading is a **marginal** edge even on well-suited names (NVDA 5-min fade: Sharpe −1.12, 25% win; AAPL: Sharpe +0.46, 62% win). The goal of the research below is **more *good* setups**, not simply "more trades" — being flat on a trending day is correct, not a bug.

---

## 2. Where it runs

| Component | Detail |
|---|---|
| Strategy file | `strategies_user/templates/range_trader.py` (a deterministic Strategy; no LLM). |
| Dispatch | The StrategyEngine fires `on_bar` on the strategy's schedule. The live NVDA strategy uses cron `*/5 * * * *` → **`on_bar` every 5 minutes during RTH** (`_dispatch_bar_tick` fetches the latest 5-min bar and calls `on_bar`). |
| Orders | Every order → `OrderRouter.submit()` → the risk engine (ADR 0002). Sizing/cooldowns/breakers all apply. |
| Sessions | The §9A market-session gate skips dispatch outside RTH (unless `allow_extended_hours`). |

---

## 3. Levels — where buy/sell/stop come from

Two modes (`level_mode`, default **`opening_range`**):

### 3.1 `opening_range` (default) — daily-adaptive
Each trading day the levels are derived from the **first `opening_range_minutes` (default 30)** of price action (09:30–10:00 ET):

- **entry (buy/support)** = the opening range's **low**
- **exit (sell/resistance)** = the opening range's **high**
- **stop** = `range_low × (1 − stop_buffer_pct)` (default 0.5% below the range low)

While the range is forming (09:30–10:00), levels are `(0,0,0)` and **no entries are taken**. After 10:00 ET the levels **freeze for the rest of the day**. Levels reset at the next day's first bar.

> This is why the engine **must be up before 09:30 ET** — if it starts after 10:00 the opening range never forms, `entry = 0`, and the strategy is **inert all day**. (Operationally fixed via the MarketHours autostart task + the dispatch-liveness monitor.)

### 3.2 `fixed` — static levels
Uses the `entry_price` / `exit_price` / `stop_price` params verbatim (frozen, don't track the day). Default 0 → inert until set. *(The live NVDA strategy is in `opening_range` mode; its stored fixed levels are vestigial — see the AAPL params we zeroed.)*

**Validity guard:** entries require `stop < entry < exit` (`_levels_ok`). An invalid ordering makes the strategy inert for entries (exits/stops still protect an open position) and is logged once per day.

---

## 4. Trigger rules (evaluated every `on_bar` ≈ every 5 min)

Order of checks in `on_bar`, given the current `price` and today's `(entry, exit, stop)`:

| # | Condition | Action |
|---|---|---|
| 1 | New ET day | reset `trades_today=0`, `stopped_today=False`, opening range; refresh sizing equity from the live account |
| 2 | `tod ≥ close − hard_exit_before_close_minutes` (last 5 min) **and in a position** | **SELL** (`time_exit`) — force-flat into the close |
| 3 | **In a position** and `price ≤ stop` | **SELL** (`stop_loss`) + set `stopped_today` → **no more entries today** (range broken) |
| 4 | **In a position** and `price ≥ exit` | **SELL** (`range_exit`) — take the bounce to resistance |
| 5 | `tod < open + no_trade_open_minutes` (first 5 min) | skip entries |
| 6 | flat, no pending order, **`price ≤ entry`**, levels valid, not stopped-out, `trades_today < max_trades_per_day` | **BUY** (`range_entry`), sized (§5) → `trades_today += 1` |

So in plain terms:
- **BUY** when price **dips to/below the support (opening-range low)** — after the range forms, outside the first 5 min, if not already stopped out and under the daily cap.
- **SELL** when price **reaches resistance** (`range_exit`), **hits the stop** (`stop_loss`, which also halts the day), or **the close approaches** (`time_exit`).

**In-flight guard:** a per-symbol `pending` flag prevents duplicate entry/exit submissions across consecutive bars before a fill lands (reconciled each bar + on fill).

---

## 5. Position sizing

`qty = floor( risk_per_trade_pct × equity / (entry − stop) )`, capped at `max_position_qty` (`_size_position`). Per-share risk = `entry − stop`. Equity is the live account balance (refreshed daily), falling back to `initial_equity_estimate`. An inverted stop (`stop ≥ entry`) sizes to **0** (fail-safe, not silently masked).

---

## 6. How many trades per day

| Parameter | Default | NVDA live |
|---|---|---|
| `max_trades_per_day` | 4 | 3 |

- **Cap:** at most `max_trades_per_day` **entries** (BUYs) per day. Exits (resistance/stop/time) do **not** consume slots; only **accepted** entries do (risk-rejections don't burn a slot).
- **Practical reality:** far below the cap. An entry requires price to **revisit the opening-range low**, and a single stop-out **halts entries for the rest of the day**. On most days the realistic count is **0–1**, not 4. The cap is a ceiling, not a target.

---

## 7. Why we see *no trades* (failure-mode analysis)

Observed: **0 orders for ~2 days** on the NVDA range strategy. Root causes, in order of impact:

1. **Price never returns to support (one-directional day).** The #1 cause. The strategy only buys at `price ≤ opening-range low`; if the session drifts up (or down through the stop without a bounce), there's no fade entry. **Verified 2026-06-26:** NVDA opening-range low **191.24**, lowest after 10:00 = **192.48** → it never came back → correctly no entry.
2. **Engine not up through RTH.** If the backend isn't running before 09:30 ET, the opening range can't form → `entry = 0` → inert all day. This was happening (logon-only autostart). *Fixed:* MarketHours healthcheck task (08:00 CT + 30-min self-heal) + the dispatch-liveness monitor (PR #280) that now alarms on silent inertness.
3. **Poorly-suited symbol.** NVDA trends rather than oscillating, and its **normalized** range (ATR% ≈ 4.0%) and absolute support distance are modest. A trending name gives few/no clean touches of support.
4. **Stop-out halt.** One stop ends entries for the day.
5. **Long-only.** It can't profit from the *upper* edge — a day that ranges but starts by going **up** from the open offers no support touch to buy.
6. **Daily cap / invalid levels** (secondary): cap reached, or `stop<entry<exit` violated → inert.

> Distinction that matters: (1), (3), (5) are *strategy-design* reasons (the setup didn't appear); (2) is an *operational* reason (the engine wasn't running). (2) is fixed. The research below targets (1)/(3)/(5).

---

## 8. Research plan — two independent hypotheses (owner review folded, 9.8/10)

> **Methodology fold (owner — the most important one):** split the research into **two independent
> hypotheses** and test them **separately**, or you'll never know which change actually mattered
> (clean Evidence-Engineering attribution):
> - **H1 — Can we pick better *symbols*?** → the Candidate Engine.
> - **H2 — Can we improve the *entry logic*?** → the strategy trigger.
>
> Every change is backtested (`scripts/backtest_range_trader_{sweep,alpaca,synthetic}.py`) and judged on
> **risk-adjusted P&L, not trade count.** A flat day on a trending symbol is *correct*; the goal is more
> *good* setups, not more trades.

### 8.1 H1 — Candidate selection (the #1 lever)
The single highest-value change — and it eliminates most "no-trade" days **without touching the strategy
logic**. The architecture should be `Candidate Engine → Range Candidate → Range Trader`, **not**
`Fixed Symbol → Range Trader` — the same evolution made with Discovery Lab (see §10).

**8.1a Rank by a composite Range Score, not ATR% alone.** ATR% is *necessary but not sufficient* (owner):
a high-ATR% **trender** (NVDA) should rank *below* a moderate-ATR% genuine **oscillator**. Proposed:

> **RangeScore = ATR% × RangeBoundProbability × IntradayOscillation × Liquidity × SpreadQuality**

- **IntradayOscillation = Range Efficiency** — `intraday_travel / |net_change|` (high travel, low net move
  ⇒ oscillating ⇒ good). *Stock A:* H−L $20 / Close−Open $18 ⇒ directional ⇒ **bad**. *Stock B:* H−L $20 /
  Close−Open $1 ⇒ oscillating ⇒ **excellent**. **Same ATR, opposite behavior.** ⭐ The platform **already
  computes a version of this — `RangeInsight.efficiency_ratio`** — so feature it in the score.
- Add the richer candidate dimensions the owner listed: **RVOL, average spread, liquidity, mean-reversion
  score, trend score, gap size, sector volatility** — then let the strategy filter.

The current ranker (PR #281) is **v1** (ATR% × `range_bound`); this extends it to the full Range Score.

**8.1b Experiment (H1, in isolation):** backtest the **unchanged** fade on the top-5 RangeScore names vs
NVDA; measure trades/day, win-rate, Sharpe. If selection alone lifts it, H1 is confirmed independent of any
trigger change.

### 8.2 H2 — Entry logic (kept separate from H1)
**8.2a Support ZONE, not an exact low *(Priority 2)*.** Markets rarely touch an exact level — support is
an *area*, not a point. Replace `BUY when price ≤ OR-low` with a **support zone = the lowest 20% of the
opening range**:

> **BUY when price ≤ OR-low + 0.20 × (OR-high − OR-low)**

Example: OR high 210 / low 200 → buy anywhere ≤ **202** (vs only ≤ 200). Many more legitimate entries while
preserving the mean-reversion concept. **Experiment:** sweep the zone fraction {0, 10%, 20%, 33%} — trades/day
vs win-rate/avg-entry; find the knee.

**8.2b Bounce confirmation *(optional, after 8.2a)*.** Instead of buying *at* support (catching a falling
knife), buy when price **crosses back up through** support — buying *confirmation*. **Experiment:** "first
touch" vs "cross-back-above" on win-rate + drawdown.

**8.2c VWAP confirmation.** Gate entries by VWAP (e.g., only fade support when price is near/above VWAP, or
use VWAP as a dynamic support). Usually filters bad entries. **Experiment:** add a VWAP gate; measure
false-entry reduction.

**8.2d Adaptive/rolling levels & two-sided *(structural, last)*.** A rolling intraday range instead of a
frozen opening range (fires more in a slow grind); and **fade-the-resistance** (short the OR high) to cover
up-from-the-open days (needs shorting + risk design — long-only today).

**8.2e Param-sweep matrix** (calibrates the above): `opening_range_minutes`{15,30,60} × zone-fraction
{0,10,20,33%} × `stop_buffer_pct`{0.25,0.5,1%} × `timeframe`{1Min,5Min} × `max_trades_per_day`{2,4,8} →
trades/day, win, Sharpe, maxDD per cell; pick the efficient frontier, **not** the most-trades cell.

### 8.3 Priority (owner)
| # | Improvement | Hypothesis | Why |
|---|---|---|---|
| **1** | Dynamic candidate selection | **H1** | Biggest expected lift; eliminates most no-trade days *without changing logic* |
| **2** | Support-zone entry (`≤ OR-low + 20%·range`) | **H2** | Realistic market behavior; more valid entries, preserves the concept |
| **3** | **Keep H1 and H2 separate** | method | Attribute which change mattered → clean Evidence Engineering |
| **4** | Richer **Range Score** (oscillation/trend/liquidity/RVOL/spread + Range Efficiency) | **H1** | ATR% alone is insufficient |
| **5** | Bounce confirmation | **H2** | Buy confirmation, not a falling knife — *after* 1 & 2 |

### Out of scope / explicitly *not* the goal
- **Manufacturing trades for their own sake.** A flat day on a trending symbol is correct.
- Hot-swapping the live strategy's symbol daily (collides with the activation-cooldown invariant, ADR 0005).
  The ranker's "Use" creates an **IDLE** strategy you then activate — the cooldown-safe path.

---

## 9. Immediate next steps (recommended order)

1. **Confirm the operational fix held** — engine up pre-open; `on_bar` dispatching (dispatch-liveness
   endpoint / WARN logs clean).
2. **Test H1 in isolation** — backtest the *unchanged* fade on the top RangeScore names vs NVDA. If AMD/AAPL
   trade more and better, selection alone fixes most dry spells.
3. **Then test H2 in isolation** — support-zone entry (8.2a) on a *fixed* symbol set, so the lift is
   attributable to the trigger, not the symbol.
4. **Combine only after each is independently attributed.** Structural changes (rolling levels / two-sided /
   VWAP) last, each gated on backtest evidence.

---

## 10. Strategic architecture — Range Trader as a Candidate-Engine consumer (owner)

The owner's headline recommendation: **Range Trader should stop being a standalone strategy and become the
*execution component* of a two-stage pipeline** — mirroring Discovery Lab:

> `Candidate Engine → Candidate Ranking → Strategy → Execution → Evidence Collection`  *(not `Strategy → Stock`)*

And the engine should be **generic**, not range-only: a single **Candidate Engine** produces
**Momentum / Range / Trend / Sector** candidate lists, and Range Trader is *one consumer* (the PR #281 ranker
is the seed of the *Range profile*). This turns candidate selection into a **reusable platform capability** —
far more valuable than relaxing a trigger, and consistent with the rest of TradingWorkbench (Discovery Lab,
Factor Lab). The cooldown-safe realization is a **universe range strategy** that picks intraday from the
ranked list (no daily symbol-swap → no re-activation).
