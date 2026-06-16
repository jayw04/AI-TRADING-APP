# Range Trader — Paper-Activation Plan

| Field | Value |
|---|---|
| Document version | v0.1 (plan) |
| Date | 2026-06-15 |
| Strategy | `range-trader` (`apps/backend/strategies_user/templates/range_trader.py`, v0.1.0) |
| Goal | Put a **second, diversifying** strategy — a single-symbol intraday **mean-reversion** book — into paper trading shortly, alongside the live momentum-portfolio, validated by backtest first. |
| Predecessor work | PR #92 (RangeTrader backtest harness — Jay's, OPEN); the P10 risk fixes already merged/deployed (#114 daily-loss, #120 breaker monitor) apply to it too. |
| Estimated wall time | 2–4 hours (mostly level-selection + backtest validation; activation itself is minutes) |
| Out of scope | LIVE (real money); multi-symbol books; automatic level derivation; any change to momentum-portfolio. |

---

## 1. Why this session exists

momentum-portfolio is the only active paper strategy. Range Trader adds a **second, deliberately *different*** sleeve:

| | momentum-portfolio | range-trader |
|---|---|---|
| Style | trend-following (buy strength) | **mean-reversion** (fade the range) |
| Cadence | weekly (Mon) | **intraday** (every 5 min) |
| Breadth | ~200-name systematic book | **single symbol**, manual levels |
| Risk | portfolio-level, no per-name stop | **per-trade hard stop**, intraday-flat |

Running a mean-reversion intraday book next to a weekly momentum book diversifies *style* and *horizon* — they tend to perform in different conditions. This session gets Range Trader from "template + backtest harness" to a validated, paper-active strategy.

---

## 2. What this session ships

- A `range-trader` strategy **registered and PAPER-active** on the BFY6 paper account, for **one chosen symbol** with reviewed entry/exit/stop levels.
- A **backtest record** (via the PR #92 harness) validating those levels/params before activation (ADR 0014 — backtests are the eval ground truth).
- A short verification that the live 5-min dispatch fires, the levels trigger entries/exits, the hard stop and end-of-day flatten work, and orders are audited `source_type=STRATEGY`.

---

## 3. How Range Trader works (the logic to validate)

"Fade the range" mean reversion on one symbol, on 5-minute bars:

- **Buy** when price dips **to/below `entry_price`** (near support / the lower band).
- **Sell (take profit)** when price rises **to/above `exit_price`** (near resistance / the upper band).
- **Hard stop:** sell when price falls **to/below `stop_price`** (below support) — and the range is then treated as **broken**: no further entries that ET day.
- **Sizing:** risk-based — `risk_per_trade_pct` (default 1%) of equity ÷ (entry − stop) distance, capped at `max_position_qty`.
- **Guards:** no entries in the first `no_trade_open_minutes` (default 5) after the open; **force-flat** in the last `hard_exit_before_close_minutes` (default 5) before the close; at most `max_trades_per_day` (default 4) entries.

Key parameters to set/review: `entry_price`, `exit_price`, `stop_price`, `risk_per_trade_pct`, `max_position_qty`, `max_trades_per_day`, `timeframe` (5Min).

---

## 4. Prerequisites

1. **A symbol + a recent, well-defined range.** Range trading needs a sideways/range-bound name with identifiable support/resistance — *not* a trending one. Pick the symbol and read its support/resistance (the "80% bands" of the recent range) to set `entry_price` / `exit_price` / `stop_price`. (The idle id=1 row was "Range Trader NVDA" — NVDA is a candidate, but only if it's currently range-bound; otherwise choose a better-suited name.)
2. **PR #92's backtest harness** available (`scripts/backtest_range_trader_{synthetic,alpaca,sweep}.py`). Review/merge it, or run it from its branch, to validate the chosen levels.
3. **The deployed risk fixes** (already on `main`/live): the daily-loss-on-buys fix (#114) and the continuous breaker monitor (#120) apply to range-trader exactly as to momentum.
4. **Stack up**, paper account wired (same as the momentum drive).

---

## 5. Detailed work

### 5a. Select symbol + levels
Choose a range-bound symbol; set `entry_price` (support), `exit_price` (resistance), `stop_price` (below support). The strategy validates `entry < exit` and `stop < entry` (`_levels_ok`); bad levels are logged and no-op, so confirm they pass.

### 5b. Backtest validation (PR #92 harness)
Run the harness on the chosen symbol/levels:
- `backtest_range_trader_synthetic.py` — sanity on a constructed range.
- `backtest_range_trader_alpaca.py` — real recent bars for the symbol.
- `backtest_range_trader_sweep.py` — walk-forward sweep over level/param choices.
Confirm the levels produce sensible entries/exits and acceptable risk before activating. Record the result.

### 5c. Register + activate to PAPER
Same API path as momentum: `POST /api/v1/strategies` (create IDLE — `code_path templates/range_trader.py`, the chosen `symbols`=[the one symbol], params with the levels, `schedule="*/5 * * * *"`) → `POST /strategies/{id}/start` (→ PAPER). No cooldown for PAPER (that gates LIVE only).

### 5d. Coexistence with momentum-portfolio (★ the important new consideration)
Both strategies run on the **same paper account**, so they **share account-level risk gates**:
- **Circuit breaker is account-wide.** If the *combined* daily P&L breaches `max_daily_loss`, the breaker trips and **HALTs both** strategies (the breaker maps by account, not strategy). The continuous monitor (#120) now catches this even between orders.
- **Order-rate caps are per-strategy** (STRATEGY scope), so range-trader's ≤4 trades/day won't crowd out momentum's weekly burst.
- **Decide:** is one shared daily-loss limit acceptable for two strategies, or should the account's `max_daily_loss` be revisited now that two books contribute to it? (Surface to the owner; the breaker is account-scoped by design — P5 §7 will add per-strategy account mapping.)

### 5e. Verify live
Over a paper session: confirm the 5-min dispatch fires `on_bar`; a dip to `entry_price` opens a sized position; a rise to `exit_price` (or the stop) exits; the end-of-day flatten fires; `max_trades_per_day` caps entries; orders show `source_type=STRATEGY` in the audit log and pass the risk engine.

---

## 6. Manual smoke

1. Stack up, login.
2. Create + start range-trader on the chosen symbol/levels → confirm `status=PAPER`, the 5-min job is scheduled.
3. During market hours, watch the signals/orders: an entry near support, an exit near resistance (or stop), and the pre-close flatten.
4. Confirm both strategies coexist (momentum still PAPER, breaker clear).

---

## 7. Walk-away discipline

The strategy code is unchanged (it already exists); this is activation + config. Any code change to `range_trader.py` follows the usual ≥1h walk-away; a risk-limits change (5d) is ≥2h. The live activation is owner-gated (market hours).

---

## 8. What this session does NOT do

- No LIVE (real-money) activation.
- No multi-symbol range books (one symbol now).
- No automatic support/resistance derivation (levels are set/reviewed manually this round).
- No change to momentum-portfolio or to the account-level risk limits (5d is a *decision to surface*, not a change to make blindly).
- No new strategy code — uses the existing template.

---

## 9. Notes & gotchas

1. **Pick a range-bound symbol.** Mean reversion loses in a strong trend (it keeps buying a falling knife into the stop). The symbol choice is the single biggest determinant of success — validate with the backtest, don't assume NVDA just because of the idle row.
2. **The cron day-of-week bug does NOT apply** — range-trader uses an interval schedule (`*/5 * * * *`), not a weekly day-of-week, so it's unaffected by the `0 14 * * mon` fix.
3. **It already sets `timeframe: "5Min"`** in its params, so the engine dispatch uses 5-min bars correctly (the momentum dispatch-timeframe issue doesn't recur here).
4. **The daily-loss fix (#114) matters here too** — range-trader opens positions (buys); pre-fix, those buys would have falsely tripped the breaker. Confirm the fix is deployed before activating.
5. **Account-level breaker is shared** (5d) — a bad day on either book can halt both. This is the main operational difference from running momentum alone.
6. **Agent-created path:** the template was designed to be instantiated via the agent ("Apply range template to {symbol}"), which derives levels. For this activation we set levels explicitly; the agent path is an alternative, not required.
