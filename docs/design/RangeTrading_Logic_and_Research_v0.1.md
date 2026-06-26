# Range Trading — Logic, Trigger Rules & Improvement Research (v0.1)

| Field | Value |
|---|---|
| Date | 2026-06-26 |
| Scope | The TradingWorkbench **RangeTrader** template (`apps/backend/strategies_user/templates/range_trader.py`) — the *fade-the-range* intraday mean-reversion strategy. (Distinct from the sibling system's "Combined Book.") |
| Status | Working doc — documents current behavior + a prioritized research plan to fix the "no trades for days" problem. |
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

## 8. Research plan — improve results & reduce dry spells

Prioritized; lead with selection (biggest lever, lowest risk), then trigger widening, then structural changes. **Each change must be backtested** (`scripts/backtest_range_trader_{sweep,alpaca,synthetic}.py`) before any live param change — and judged on **risk-adjusted P&L**, not trade count.

### A. Symbol selection — pick range-suitable names *(highest leverage, shippable now)*
Use the **Range Candidates ranker** (PR #281): rank a universe by **normalized ATR% × `range_bound` classification** and trade the best range-bound, wide-range names instead of a fixed NVDA. Live example today: **AMD (6.6%, range_bound) > NVDA (4.0%)**. A wider, genuinely range-bound symbol produces more clean support touches → fewer dry days *and* better setups. **Experiment:** backtest the fade strategy on the top-5 ranked names vs NVDA; measure trades/day, win-rate, Sharpe.

### B. Entry as a *zone*, not a point *(directly attacks the dry-spell)*
Today entry fires only at `price ≤ opening-range low` — an exact touch. Widen to an **entry band** (e.g., buy anywhere in the lower X% of the day's range, or at the 25th percentile of the opening range), or place a **resting limit** at the level. This fires on *near*-misses that currently produce nothing. **Experiment:** sweep an `entry_band_pct` (0 / 0.25% / 0.5% / lower-quartile) on the backtest; watch trades/day vs win-rate (wider band = more trades but worse average entry — find the knee).

### C. Two-sided range trading *(structural; more opportunity)*
Add **fade-the-resistance** (short the opening-range high) or a symmetric buy-low/sell-high so the strategy trades **both edges**, roughly doubling setups and covering up-from-the-open days. Requires shorting permission + risk design (the platform is long-only today for this template). **Experiment:** backtest a long+short variant; confirm the short edge isn't negative (shorts often behave differently).

### D. Adaptive / rolling levels *(reduces frozen-range staleness)*
Instead of a single frozen opening range, derive levels from a **rolling intraday window** (last N bars' high/low) or re-derive midday. Levels then track a drifting range and fire more often in a slow grind. **Experiment:** sweep `opening_range_minutes` (15/30/60) and a rolling-window variant; shorter/earlier ranges give tighter, earlier levels (more touches) at the cost of noise.

### E. Regime gating — *trade only when it should* *(quality over quantity)*
Add a daily filter: **skip days classified `trending`**, trade only `range_bound`/`mixed`. This *reduces* trades but raises their quality (avoids the NVDA-trend losses). Pair with (A): on a trending day for the held symbol, the ranker may point to a different, range-bound name. **Experiment:** compare P&L with/without the regime gate; confirm the skipped days were net-negative.

### F. Parameter sweep matrix *(do this first to calibrate B/D/E)*
Backtest grid over: `opening_range_minutes` {15,30,60} × `stop_buffer_pct` {0.25%,0.5%,1%} × entry-band {0,0.25%,0.5%} × `timeframe` {1Min,5Min} × `max_trades_per_day` {2,4,8}. Output trades/day, win-rate, Sharpe, maxDD per cell → pick the efficient frontier (not the most-trades cell).

### Out of scope / explicitly *not* the goal
- **Manufacturing trades for their own sake.** A flat day on a trending symbol is correct. The fix is *better symbols + better triggers*, validated, not loosening until it trades.
- Hot-swapping the live strategy's symbol daily (collides with the activation-cooldown invariant, ADR 0005). The ranker's "Use" creates an **IDLE** strategy you then activate — the cooldown-safe path. A true auto-daily universe strategy is a separate, larger design.

---

## 9. Immediate next steps (recommended order)

1. **Confirm the operational fix held** — with the MarketHours task + dispatch monitor live, verify the engine is up pre-open and `on_bar` is dispatching (the dispatch-liveness endpoint / WARN logs).
2. **Run the symbol study (A)** — backtest the fade on the top range-candidates vs NVDA; if AAPL/AMD clearly trade more and better, that alone fixes most dry spells.
3. **Run the param sweep (F)** + the entry-band study (B) — calibrate the trigger.
4. Only then consider the structural changes (C/D/E), each gated on backtest evidence.
