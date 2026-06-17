# Range Trader — Paper-Activation Plan

> ## ⛔ ARCHIVED — RESEARCHED & REJECTED (2026-06-16)
>
> **Status: REJECTED. Do not activate.** **Reason: no robust out-of-sample edge.**
>
> The §5c backtest gate did its job. After fixing the trade-count constraint
> (intraday-oscillation screen + VWAP±σ dynamic levels + same-day re-entry took
> the book from ~20 INCONCLUSIVE trades to 63–98), **every configuration that
> cleared the in-sample bar collapsed out-of-sample** — best case PLTR
> partial-exit **IS PF 1.37 → OOS PF 0.92** (deep-entry IS 1.24 → OOS 0.85).
> That is the curve-fit signature the OOS criterion exists to catch.
>
> Full evidence: **`TradingWorkbench_RangeTrader_5c_TestResults_v0.1.md`** (v0.3).
>
> **Kept as reusable infrastructure** (merged): the §5c gate + bar-count drift
> metric, the intraday-oscillation screener, the VWAP±σ variant
> (`range_trader_vwap.py`), and the OOS/robustness/evidence pipeline. The
> provisioned `range@local.dev` / `ALPACA_PAPER_1` paper account stays unused.
> Effort redirected to the momentum portfolio / portfolio-risk roadmap.
>
> *The plan below is retained as the historical research record.*

| Field | Value |
|---|---|
| Document version | v0.4 (plan — +§5g execution/state semantics from review comments §3; §3B/§3D/§3E now implemented in #126) |
| Date | 2026-06-15 |
| Strategy | `range-trader` (`apps/backend/strategies_user/templates/range_trader.py`, v0.1.0 — **verify deployed version, §5.0**) |
| Account | **Dedicated paper account `ALPACA_PAPER_1`** (creds in `.env`), owned by a **second user** — fully isolated from momentum-portfolio's BFY6 account (separate user, account, credentials, **and circuit breaker**). |
| Goal | Put a **second, diversifying** strategy — a single-symbol intraday **mean-reversion** book — into paper trading shortly, on its **own** paper account, validated by a **pre-registered** backtest first. |
| Predecessor work | PR #92 (RangeTrader backtest harness — Jay's, OPEN — **merge + pin before §5c**); the P10 risk fixes already merged/deployed (#114 daily-loss, #120 breaker monitor) apply to it too. |
| Estimated wall time | 4–6 hours (the **lifespan per-user-adapter fix** in §5a is now in-scope code + tests; plus provisioning, level selection, backtest validation; activation itself is minutes) |
| Out of scope | LIVE (real money); multi-symbol books; automatic level derivation; any change to momentum-portfolio; per-strategy `account_id` routing (P5 §7 — deliberately avoided via the second-user approach). |

> **Review status (this revision).** Folds in Jay's review `TradingWorkbench_RangeTrader_PaperActivation_Review_v0.1.md`. Finding 1 (the isolated-vs-shared contradiction) was already resolved in v0.2 (commit `df9dd76`) — the review was against a pre-edit snapshot; no further action. Findings 2–10 are incorporated below. **Finding 2 is the load-bearing one and turned out to be sharper than stated: the per-user account/breaker model is sound, but a single line in the lifespan startup path silently clobbers it. That fix (§5a step 4) is now a hard prerequisite.**

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

- A **lifespan broker-registry fix** so a second paper account is served by an adapter built from **its own** credentials, not the reused startup (BFY6) adapter (§5a step 4 — **the blocker**, with tests).
- A **second user** + their **dedicated `ALPACA_PAPER_1` paper account** provisioned (credential store + `accounts` row + broker registry).
- A `range-trader` strategy **registered and PAPER-active under that second user / `ALPACA_PAPER_1`** (NOT the momentum account), for **one chosen symbol** with reviewed entry/exit/stop levels.
- A **pre-registered backtest record** (via the PR #92 harness) clearing the §5c acceptance criteria *before* activation (ADR 0014 — backtests are the eval ground truth).
- A short verification that the live 5-min dispatch fires, the levels trigger entries/exits, the hard stop and end-of-day flatten work, RTH gating holds, and orders are audited `source_type=STRATEGY`.

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

1. **The lifespan per-user-adapter fix merged + deployed** (§5a step 4). Until this lands, a second paper account's orders route to **BFY6**, not `ALPACA_PAPER_1` — see §5a. This gates everything else.
2. **Second user + `ALPACA_PAPER_1` paper account provisioned** (§5a).
3. **A symbol + a recent, well-defined range, selected by an explicit screen** (§5b / Finding 3) — *not* "NVDA because the idle row said so."
4. **PR #92's backtest harness merged + version-pinned** (Finding 7) before it is used as the §5c gate.
5. **The deployed risk fixes** (already on `main`/live): the daily-loss-on-buys fix (#114) and the continuous breaker monitor (#120).
6. **Stack up.**

### Account-routing decision (locked, and now *verified end-to-end*)
Strategies have **no `account_id`** (deferred to P5 §7); the engine resolves a strategy's account by **(user, broker, mode)**. So two paper accounts for *one* user would be ambiguous. **Decision: `ALPACA_PAPER_1` is owned by a SECOND USER**, and range-trader runs under that user — so `(second-user, alpaca, paper)` resolves cleanly to `ALPACA_PAPER_1`.

Verification of the three layers this depends on (Finding 2 — "verify the capability, don't assume it"):

| Layer | Where | Verdict |
|---|---|---|
| **(a)** Strategy → account routing | `engine.py` resolves by `Account.user_id == row.user_id, broker, mode` | ✅ Routes by the strategy's **owning user** — a 2nd user gets a separate account row. |
| **(b)** Per-account circuit breaker | breaker keyed by `account_id`; `trip()` halts by (user, mode) | ✅ Isolated — a bad day on one book can't halt the other. |
| **(c)** Per-account broker **credentials** | `credentials_for_mode(mode, user_id, …)` reads the **encrypted `CredentialStore` keyed by `user_id`** | ✅ The data model supports distinct creds per user — each user has their own `ALPACA_PAPER_KEY`/`_SECRET`. |
| **(c′)** Lifespan startup reuse | `app/lifespan.py` (the `for _aid in _paper_ids: broker_registry.register(_aid, adapter)` loop) | ❌ **BLOCKER** — see §5a step 4. |

So (a) and (b) hold as the v0.2 plan assumed. The catch is (c′): `BrokerRegistry.load_all()` *does* construct a correct per-user adapter for the second account — and then the lifespan reuse loop **overwrites every paper account's adapter** with the single env-creds startup (BFY6) adapter. Net: today, a second paper account would silently trade BFY6. The alternative (per-strategy `account_id` routing) remains deferred to P5 §7.

---

## 5. Detailed work

### 5.0 Verify the deployed strategy version (Finding 8)
`range_trader.py` lives under the **volume-mounted** `strategies_user/templates/`, not the baked image — but confirm the running container is serving the intended (fixed) `v0.1.0` and not a stale copy: read the version banner in the registration log (or `grep VERSION` the file the container actually mounts). Pin the exact version this activation validated so a later edit can't silently diverge from the backtested code.

### 5a. Provision the second user + `ALPACA_PAPER_1` paper account — **including the lifespan fix**
The platform reads broker creds from the **encrypted credential store**, not `.env` directly (P5 §4) — so the second account must be provisioned, not just present in `.env`:

1. **Create a second user** (`apps/backend/scripts/create_user.py` with a new email + password/TOTP).
2. **Store the `ALPACA_PAPER_1` creds** under that user in the credential store (a variant of `rebootstrap_credentials.py` reading `ALPACA_PAPER_1_API_KEY` / `ALPACA_PAPER_1_API_SECRET` from `.env`, writing them as that user's `CredentialKind.ALPACA_PAPER_KEY` / `ALPACA_PAPER_SECRET`). ⚠ note the env names: key is `ALPACA_PAPER_1_API_KEY` (len 26), secret is `ALPACA_PAPER_1_API_SECRET` (len 44) — *not* `_SECRET_KEY`. Read length only; never log the values (ADR 0018 §5).
3. **Create the `accounts` row** for the second user (broker `alpaca`, mode `paper`, label e.g. "Alpaca Paper (Range)", `credentials_ref`).
4. **⚠ FIX THE LIFESPAN STARTUP REUSE — the blocker.** Today `app/lifespan.py` connects **one** startup paper adapter from `load_credentials()` (the `.env` default `ALPACA_PAPER_API_KEY` = BFY6), then does:

   ```python
   _paper_ids = [...all accounts where mode == paper...]
   for _aid in _paper_ids:
       broker_registry.register(_aid, adapter)   # ← clobbers the per-user adapter
   ```

   `BrokerRegistry.load_all()` already built a *correct* per-user adapter for the second account (via `credentials_for_mode(..., user_id, ...)` → that user's `ALPACA_PAPER_1` creds), but this loop overwrites it with the single BFY6 startup adapter. So **`registry.get(second_account_id)` returns the BFY6 adapter** and the range-trader's orders hit the wrong Alpaca account, silently.

   **Fix:** reuse the startup adapter **only** for the account whose credentials it was built from (the startup user's paper account), and leave the `load_all()`-constructed per-user adapters in place for the others — connecting each at startup. Concretely, restrict the reuse loop to the startup user's account id (or compare the resolved creds), and `connect()` any remaining constructed paper adapters. This touches the **broker/credential startup path**, so it ships with tests (a two-paper-account fixture asserting `registry.get(acct_2)` carries `ALPACA_PAPER_1`'s key, not BFY6's) and the usual ≥1h walk-away (treat as consequential — §7).

5. **Confirm at boot:** the registration log shows the second account resolving its **own** adapter (assert on the api-key *length/fingerprint*, never the value), and a paper order placed as the second user appears in the `ALPACA_PAPER_1` Alpaca dashboard — not BFY6's.

### 5b. Select symbol + levels — by an explicit range screen (Finding 3)
Do **not** default to NVDA because of the idle row. Select a **range-bound** symbol by an explicit, written screen, e.g.:
- **ADX(14) < 20** on the daily (no strong trend), and
- price oscillating within a band: the last ~20 sessions' high/low define resistance/support, and price has **touched both** sides ≥2× without breaking out, and
- adequate liquidity (avg daily volume / tight spread) so 5-min fills are realistic.

From the chosen name set `entry_price` (support), `exit_price` (resistance), `stop_price` (below support). The strategy validates `entry < exit` and `stop < entry` (`_levels_ok`); bad levels are logged and no-op, so confirm they pass. **Record the screen output** (which names passed, why this one) alongside the levels.

### 5c. Backtest validation — **pre-registered** acceptance criteria (Finding 4)
Per ADR 0014 backtests are the eval ground truth. **Write the pass/fail thresholds down *before* running** (no post-hoc goalpost moving), then run the PR #92 harness on the chosen symbol/levels:
- `backtest_range_trader_synthetic.py` — sanity on a constructed range.
- `backtest_range_trader_alpaca.py` — real recent bars for the symbol.
- `backtest_range_trader_sweep.py` — walk-forward sweep over level/param choices.

**Pre-registered go/no-go (conservative defaults — tighten, don't loosen, after the fact):**

| Metric | Threshold to activate | Rationale |
|---|---|---|
| **# round-trip trades in the test window** | ≥ 30 | Below this the stats aren't meaningful; a "great" 5-trade backtest is noise. |
| **Profit factor** (gross win / gross loss) | ≥ 1.3 | Edge must survive costs; 1.0–1.3 is too thin for an intraday book. |
| **Win rate** | ≥ 45% | Mean-reversion can win <50% if winners ≥ losers, but pair with the payoff check below. |
| **Avg win / avg loss** | ≥ 1.0 | With the hard stop defining the loss, winners must at least match losers. |
| **Max drawdown** (test window) | ≤ 2× the per-trade risk budget × `max_trades_per_day` | Drawdown must be bounded by the stop discipline, not exceed it. |
| **Out-of-sample ≈ in-sample** | OOS profit factor ≥ 0.8 × IS | Guards against curve-fit levels (the sweep's walk-forward split). |
| **Stop behavior** | every modeled stop-out actually flattens; no "stuck long through a breakdown" | The stop is the whole risk story — verify it fires in the sim. |

If any metric misses, **do not activate**; re-select levels/symbol or shelve. Record the full backtest result (params, window, metrics) as the activation evidence.

### 5d. Register + activate to PAPER (under the second user)
**Logged in as the SECOND user** (so `(user, mode)` resolves to `ALPACA_PAPER_1`): `POST /api/v1/strategies` (create IDLE — `code_path templates/range_trader.py`, the chosen `symbols`=[the one symbol], params with the levels + `timeframe:"5Min"`, `schedule="*/5 * * * *"`) → `POST /strategies/{id}/start` (→ PAPER). No cooldown for PAPER (that gates LIVE only). **Confirm in the registration log that the engine resolved the `ALPACA_PAPER_1` account (by id/label), not BFY6** — this is the live proof that §5a step 4 worked.

State the **starting equity** of `ALPACA_PAPER_1` here (Finding 5) — the risk-based sizing (`risk_per_trade_pct` of equity) is meaningless without it. Set the account's `risk_limits` (daily-loss, order-rate, position caps) appropriate for an intraday mean-reversion book *before* start.

### 5e. Isolation from momentum-portfolio (✓ the second account resolves the old concern)
Because Range Trader runs on a **separate user + `ALPACA_PAPER_1` account** (and once §5a step 4 lands, a separate *adapter with its own creds*), it is **fully isolated** from momentum-portfolio:
- **Separate circuit breaker.** Each account has its own `circuit_breaker_tripped_at` and its own `max_daily_loss` — a bad day on one book **cannot halt** the other. (Verified: breaker is keyed by `account_id`; §4 layer (b).)
- **Separate credentials/adapter.** After §5a step 4, `registry.get(range_account_id)` carries the `ALPACA_PAPER_1` key, not BFY6's. (Before the fix, this is the one thing that would silently *break* isolation — hence the blocker.)
- **Separate risk limits** — `ALPACA_PAPER_1` gets its own `risk_limits` independent of momentum's.
- **Separate equity / P&L** — each strategy sizes off its own account equity; no cross-contamination.
- The continuous breaker monitor (#120) runs per-account, so it covers both independently.

### 5f. Verify live — bounded by behavior, not a vague "watch it" (Finding 6, Finding 9)
The verification window completes only when it has actually exercised the strategy's risk machinery — **≥ 5 trading days OR ≥ N completed round-trips that include at least one stop-out and at least one end-of-day forced flatten** (whichever the market provides first). Over that window confirm:
- the 5-min dispatch fires `on_bar` **only during regular trading hours** (Finding 9 — an intraday range book must not act pre-market/after-hours; confirm the engine/strategy gates on RTH, and if it does not, gate it before activation);
- a dip to `entry_price` opens a sized position; a rise to `exit_price` (or the stop) exits;
- a **stop-out** flattens and blocks further entries that day (range-broken);
- the **end-of-day forced flatten** fires in the last `hard_exit_before_close_minutes`;
- `max_trades_per_day` caps entries;
- orders show `source_type=STRATEGY` in the audit log and pass the risk engine.

---

## 5g. Execution & state semantics (review comments §3)

Five points the second-pass review asked to formalize. Several are now **implemented** in the range-trader safeguards (PR #126).

**(§3A) Market-hours source-of-truth.** Session determination is the platform Market Session Model (design doc **§9A**): `pandas_market_calendars` (XNYS calendar — holidays, early closes) cross-checked against the **Alpaca clock** (authoritative live open/close), with all session math in `America/New_York` (DST-correct). Until §9A.4's engine gate ships, the strategy's own `no_trade_open_minutes` / `hard_exit_before_close_minutes` guards are the interim RTH protection — which is exactly why §9A is a prerequisite for activation.

**(§3B) Duplicate-order protection.** ✅ Implemented (#126). A per-symbol **in-flight flag** (`_pending` = "entry"/"exit") ensures a single 5-min bar generates at most one entry decision and that a duplicate/redelivered bar cannot double-submit before the prior fill lands. The flag is cleared on fill (`on_fill`) and reconciled against actual position state every bar; DAY orders expire at the close so the flag resets each session. **Invariant:** *at most one entry per bar; redelivered bars never double-enter.*

**(§3C) Breaker realized/unrealized PnL definition.** The daily-loss breaker trips on **`realized_pnl_today + unrealized_pnl_now ≤ −max_daily_loss`** (`app/risk/circuit_breaker.py`):
- **Realized** = closes only (sells joined Fill→Order, signed by side; the #114 fix — buys no longer count as loss).
- **Unrealized** = summed from the local `positions` table (kept fresh by `PositionSyncService`), marked at the latest price.
- **Snapshot cadence:** evaluated on every order submission *and* continuously by the breaker monitor (#120, 60s). This matters more for range-trader than momentum because an intraday book carries unrealized swings within the day.

**(§3D) Stop-order execution semantics.** The stop is a **synthetic local stop → market sell**: the strategy evaluates `price ≤ stop_price` on each 5-min bar and, when breached, submits a **market SELL** through the risk engine (not a broker-native stop order). Implications to accept: (i) **no overnight/gap protection** between bars or after the close — the EOD force-flat (`hard_exit_before_close_minutes`) is the overnight guard; (ii) fills at the next available price, so a fast gap-down can fill below `stop_price`. A broker-native stop-market is a possible future enhancement, out of scope here.

**(§3E) `range_broken` reset rule.** ✅ Implemented (#126). Once the stop fires (or price is already at/below the stop level), `_stopped_today = True` halts **all further entries for the rest of that ET day** — the range is considered broken. **Reset:** at the **next ET trading-session open** (the per-ET-day rollover in `on_bar` clears `_stopped_today`, `_trades_today`, and stale `_pending`). No mid-session re-arming.

---

## 6. Manual smoke

1. Stack up, login **as the second user**.
2. Confirm boot log: second account served by its **own** adapter (`ALPACA_PAPER_1` key fingerprint, not BFY6).
3. Create + start range-trader on the chosen symbol/levels → confirm `status=PAPER`, the 5-min job is scheduled, and the registration log names the `ALPACA_PAPER_1` account.
4. During **regular trading hours**, watch the signals/orders: an entry near support, an exit near resistance (or stop), and the pre-close flatten. Confirm no dispatch acts outside RTH.
5. Confirm both strategies coexist on **separate accounts** — momentum still PAPER on BFY6, range-trader PAPER on `ALPACA_PAPER_1`, each account's breaker clear and independent — and a test paper order as the second user lands in the `ALPACA_PAPER_1` dashboard.

---

## 7. Walk-away discipline

The **§5a step 4 lifespan fix touches the broker/credential startup path** — treat as consequential: ≥1h walk-away minimum, with the two-paper-account regression test in the PR. Provisioning + config (§5a 1–3, §5b–5d) is lower-stakes but still merges through PR. The live activation is owner-gated (regular market hours).

---

## 8. What this session does NOT do

- No LIVE (real-money) activation.
- No multi-symbol range books (one symbol now).
- No automatic support/resistance derivation (levels are set/reviewed manually this round, via the §5b screen).
- No change to momentum-portfolio or its BFY6 account (Range Trader is fully isolated on `ALPACA_PAPER_1`).
- No per-strategy `account_id` routing (P5 §7) — avoided via the second-user approach.
- No new **strategy** code — uses the existing template. (The §5a step 4 **lifespan** change is infra, not strategy logic.)

---

## 9. Notes & gotchas

1. **The lifespan reuse loop is the whole ballgame for isolation.** Until §5a step 4 lands, the second account silently trades BFY6 — and nothing errors, so it would only surface as "why are range-trader's fills showing up in momentum's account?" Verify by api-key fingerprint at boot and by the Alpaca dashboard the first order lands in.
2. **Pick a range-bound symbol by the §5b screen.** Mean reversion loses in a strong trend (it keeps buying a falling knife into the stop). The symbol choice is the single biggest determinant of success — validate with the pre-registered backtest, don't assume NVDA just because of the idle row.
3. **The cron day-of-week bug does NOT apply** — range-trader uses an interval schedule (`*/5 * * * *`), not a weekly day-of-week, so it's unaffected by the `0 14 * * mon` fix.
4. **It already sets `timeframe: "5Min"`** in its params, so the engine dispatch uses 5-min bars correctly (the momentum dispatch-timeframe issue doesn't recur here).
5. **The daily-loss fix (#114) matters here too** — range-trader opens positions (buys); pre-fix, those buys would have falsely tripped the breaker. Confirm the fix is deployed before activating.
6. **RTH gating (Finding 9).** A 5-min interval schedule will fire 24/7 in principle; confirm the dispatch only *acts* during regular trading hours, or the open/close guards (`no_trade_open_minutes`, `hard_exit_before_close_minutes`) are meaningless. If RTH gating isn't already enforced, gate it before activation.
7. **Pre-register the backtest bar (Finding 4).** Write §5c's thresholds before you run the sweep; the sweep makes it trivially easy to find *some* level set that looks good in-sample. The OOS≈IS check is the guard.
8. **PR #92 sequencing (Finding 7).** Merge and version-pin the backtest harness before it's used as the activation gate — a moving harness can't be the ground truth.
9. **Agent-created path:** the template was designed to be instantiated via the agent ("Apply range template to {symbol}"), which derives levels. For this activation we set levels explicitly; the agent path is an alternative, not required.

---

## Appendix A — disposition of Jay's review (`..._Review_v0.1.md`)

| # | Finding | Disposition |
|---|---|---|
| 1 | Isolated-vs-shared §5e contradiction | **Stale** — already fixed in v0.2 (`df9dd76`); review was against a pre-edit snapshot. |
| 2 | Per-user routing is an unverified load-bearing assumption | **Valid, sharpened.** (a) engine routing + (b) per-account breaker **verified present**; (c) per-user creds **present in the store** but (c′) the lifespan reuse loop clobbers it → **blocker, now §5a step 4 + §4 table.** |
| 3 | Payload/symbol selection method (not "NVDA by default") | **Incorporated** — §5b explicit ADX<20 range screen. |
| 4 | Pre-registered backtest acceptance criteria | **Incorporated** — §5c thresholds table, pre-registered. |
| 5 | Account equity unstated | **Incorporated** — §5d states starting equity before sizing. |
| 6 | Verify-live window too vague | **Incorporated** — §5f: ≥5 days **or** ≥N round-trips incl. a stop-out and an EOD flatten. |
| 7 | PR #92 sequencing | **Incorporated** — prerequisite #4 + Note 8: merge/pin before §5c. |
| 8 | Version-bump verification | **Incorporated** — §5.0 verify deployed `range_trader.py` version. |
| 9 | RTH gating | **Incorporated** — §5f + Note 6. |
| 10 | Hygiene | **Incorporated** — fingerprint-not-value logging (§5a 5), recorded evidence (§5b/§5c). |
