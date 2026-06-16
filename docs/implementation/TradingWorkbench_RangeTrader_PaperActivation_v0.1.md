# Range Trader — Paper-Activation Plan

| Field | Value |
|---|---|
| Document version | v0.2 (plan — dedicated-account decision folded in) |
| Date | 2026-06-15 |
| Strategy | `range-trader` (`apps/backend/strategies_user/templates/range_trader.py`, v0.1.0) |
| Account | **Dedicated paper account `ALPACA_PAPER_1`** (creds in `.env`), owned by a **second user** — fully isolated from momentum-portfolio's BFY6 account (separate user, account, credentials, **and circuit breaker**). |
| Goal | Put a **second, diversifying** strategy — a single-symbol intraday **mean-reversion** book — into paper trading shortly, on its **own** paper account, validated by backtest first. |
| Predecessor work | PR #92 (RangeTrader backtest harness — Jay's, OPEN); the P10 risk fixes already merged/deployed (#114 daily-loss, #120 breaker monitor) apply to it too. |
| Estimated wall time | 3–5 hours (second-user/account provisioning + level-selection + backtest validation; activation itself is minutes) |
| Out of scope | LIVE (real money); multi-symbol books; automatic level derivation; any change to momentum-portfolio; per-strategy `account_id` routing (P5 §7 — deliberately avoided via the second-user approach). |

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

- A **second user** + their **dedicated `ALPACA_PAPER_1` paper account** provisioned (credential store + `accounts` row + broker registry).
- A `range-trader` strategy **registered and PAPER-active under that second user / `ALPACA_PAPER_1`** (NOT the momentum account), for **one chosen symbol** with reviewed entry/exit/stop levels.
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

1. **Second user + `ALPACA_PAPER_1` paper account provisioned** (§5a) — the routing decision (below).
2. **A symbol + a recent, well-defined range.** Range trading needs a sideways/range-bound name with identifiable support/resistance — *not* a trending one. Pick the symbol and read its support/resistance (the "80% bands" of the recent range) to set `entry_price` / `exit_price` / `stop_price`. (The idle id=1 row was "Range Trader NVDA" — NVDA is a candidate, but only if it's currently range-bound; otherwise choose a better-suited name.)
3. **PR #92's backtest harness** available (`scripts/backtest_range_trader_{synthetic,alpaca,sweep}.py`). Review/merge it, or run it from its branch, to validate the chosen levels.
4. **The deployed risk fixes** (already on `main`/live): the daily-loss-on-buys fix (#114) and the continuous breaker monitor (#120) apply to range-trader exactly as to momentum.
5. **Stack up.**

### Account-routing decision (locked)
Strategies have **no `account_id`** (deferred to P5 §7); the engine resolves a strategy's account by **(user, broker, mode)**. So two paper accounts for *one* user would be ambiguous. **Decision: `ALPACA_PAPER_1` is owned by a SECOND USER**, and range-trader runs under that user — so `(second-user, alpaca, paper)` resolves cleanly to `ALPACA_PAPER_1` with **no engine change**. This also gives full isolation: separate user, account, credentials, and **circuit breaker** (a bad day on one book can't halt the other). The alternative (per-strategy `account_id` routing) is explicitly deferred.

---

## 5. Detailed work

### 5a. Provision the second user + `ALPACA_PAPER_1` paper account
The platform reads broker creds from the **encrypted credential store**, not `.env` directly (P5 §4) — so the second account must be provisioned, not just present in `.env`:
1. **Create a second user** (`apps/backend/scripts/create_user.py` with a new email + password/TOTP).
2. **Store the `ALPACA_PAPER_1` creds** under that user in the credential store (a variant of `rebootstrap_credentials.py` reading `ALPACA_PAPER_1_API_KEY` / `ALPACA_PAPER_1_API_SECRET` from `.env`). ⚠ note the env names: key is `ALPACA_PAPER_1_API_KEY` (len 26), secret is `ALPACA_PAPER_1_API_SECRET` (len 44) — *not* `_SECRET_KEY`.
3. **Create the `accounts` row** for the second user (broker `alpaca`, mode `paper`, label, credentials_ref).
4. ⚠ **Verify the broker registry loads it with its OWN credentials** — lifespan reuses the single startup paper adapter for "the user's paper account(s)"; a second paper account with *different* creds needs its own adapter (per-account creds), not the reused BFY6 one. Confirm `BrokerRegistry.load_all()` opens a distinct adapter for the second account, or extend it to. This is the one piece that may need code, not just data.

### 5b. Select symbol + levels
Choose a range-bound symbol; set `entry_price` (support), `exit_price` (resistance), `stop_price` (below support). The strategy validates `entry < exit` and `stop < entry` (`_levels_ok`); bad levels are logged and no-op, so confirm they pass.

### 5c. Backtest validation (PR #92 harness)
Run the harness on the chosen symbol/levels:
- `backtest_range_trader_synthetic.py` — sanity on a constructed range.
- `backtest_range_trader_alpaca.py` — real recent bars for the symbol.
- `backtest_range_trader_sweep.py` — walk-forward sweep over level/param choices.
Confirm the levels produce sensible entries/exits and acceptable risk before activating. Record the result.

### 5d. Register + activate to PAPER (under the second user)
**Logged in as the SECOND user** (so `(user, mode)` resolves to `ALPACA_PAPER_1`): `POST /api/v1/strategies` (create IDLE — `code_path templates/range_trader.py`, the chosen `symbols`=[the one symbol], params with the levels, `schedule="*/5 * * * *"`) → `POST /strategies/{id}/start` (→ PAPER). No cooldown for PAPER (that gates LIVE only). Confirm the engine resolved the **`ALPACA_PAPER_1`** account (not BFY6) in the registration log.

### 5e. Isolation from momentum-portfolio (✓ the second account resolves the old concern)
Because Range Trader runs on a **separate user + `ALPACA_PAPER_1` account**, it is **fully isolated** from momentum-portfolio:
- **Separate circuit breaker.** Each account has its own `circuit_breaker_tripped_at` and its own `max_daily_loss` — a bad day on one book **cannot halt** the other. (This is the clean resolution of the shared-breaker risk that a single shared account would have created.)
- **Separate risk limits** — `ALPACA_PAPER_1` gets its own `risk_limits` (daily-loss, order-rate, position caps) appropriate for an intraday mean-reversion book, independent of momentum's.
- **Separate equity / P&L** — each strategy sizes off its own account equity; no cross-contamination.
- The continuous breaker monitor (#120) runs per-account, so it covers both independently.

### 5f. Verify live
Over a paper session: confirm the 5-min dispatch fires `on_bar`; a dip to `entry_price` opens a sized position; a rise to `exit_price` (or the stop) exits; the end-of-day flatten fires; `max_trades_per_day` caps entries; orders show `source_type=STRATEGY` in the audit log and pass the risk engine.

---

## 6. Manual smoke

1. Stack up, login.
2. Create + start range-trader on the chosen symbol/levels → confirm `status=PAPER`, the 5-min job is scheduled.
3. During market hours, watch the signals/orders: an entry near support, an exit near resistance (or stop), and the pre-close flatten.
4. Confirm both strategies coexist on **separate accounts** — momentum still PAPER on BFY6, range-trader PAPER on `ALPACA_PAPER_1`, each account's breaker clear and independent.

---

## 7. Walk-away discipline

The strategy code is unchanged (it already exists); this is provisioning + config. If §5a's registry step needs a code change (per-account adapter creds), it follows the usual ≥1h walk-away (it touches the broker/credential path — treat as consequential). The live activation is owner-gated (market hours).

---

## 8. What this session does NOT do

- No LIVE (real-money) activation.
- No multi-symbol range books (one symbol now).
- No automatic support/resistance derivation (levels are set/reviewed manually this round).
- No change to momentum-portfolio or its BFY6 account (Range Trader is fully isolated on `ALPACA_PAPER_1`).
- No per-strategy `account_id` routing (P5 §7) — avoided via the second-user approach.
- No new strategy code — uses the existing template (unless §5a's registry per-account-creds step is needed).

---

## 9. Notes & gotchas

1. **Pick a range-bound symbol.** Mean reversion loses in a strong trend (it keeps buying a falling knife into the stop). The symbol choice is the single biggest determinant of success — validate with the backtest, don't assume NVDA just because of the idle row.
2. **The cron day-of-week bug does NOT apply** — range-trader uses an interval schedule (`*/5 * * * *`), not a weekly day-of-week, so it's unaffected by the `0 14 * * mon` fix.
3. **It already sets `timeframe: "5Min"`** in its params, so the engine dispatch uses 5-min bars correctly (the momentum dispatch-timeframe issue doesn't recur here).
4. **The daily-loss fix (#114) matters here too** — range-trader opens positions (buys); pre-fix, those buys would have falsely tripped the breaker. Confirm the fix is deployed before activating.
5. **Range Trader is on a SEPARATE account (`ALPACA_PAPER_1`, second user)** — so its circuit breaker, daily-loss limit, and equity are **isolated** from momentum-portfolio. A bad day on one book does **not** halt the other. The one wrinkle to verify is §5a step 4: the broker registry must load the second paper account with **its own credentials**, not reuse the BFY6 startup adapter.
6. **Agent-created path:** the template was designed to be instantiated via the agent ("Apply range template to {symbol}"), which derives levels. For this activation we set levels explicitly; the agent path is an alternative, not required.
