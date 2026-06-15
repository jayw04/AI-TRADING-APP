# momentum-portfolio — Strategy Status & Next Steps

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-15 |
| Strategy | `momentum-portfolio` (code `apps/backend/strategies_user/templates/momentum_portfolio.py`) |
| Code version | **v0.4.0** (⚠ the registered DB row `strategies.version` still reads `0.3.0` — cosmetic; the code file is what runs) |
| Live instance | strategy **id=2**, status **PAPER**, run_id=6, account **BFY6** (Alpaca paper, ~$10k) |
| Schedule | `0 14 * * mon` — weekly, Monday 14:00 UTC (≈10:00 ET, ~30 min after the 09:30 open) |
| Repository HEAD | `31ddfd6` (all of #111–#116 merged) |
| Related docs | P9 §1–§4 session docs; `TradingWorkbench_P10_PortfolioRisk_Roadmap_v0.1.md`; ADR 0014 (backtests = ground truth), 0004 (circuit breaker), 0002 (single OrderRouter), 0018 (Sharadar data) |

---

## 1. What the strategy is

A deterministic, long-only, **weekly cross-sectional price-momentum portfolio**. It selects the top-quintile names by a 6-1 month momentum z-score from a fixed top-N liquidity candidate universe, holds them equal-weight, and rebalances once per week. It reaches factor data only through the sandboxed read-only `ctx.factors` accessor and submits every order through `ctx.submit_order` → `OrderRouter` → risk engine (ADR 0002). No broker/DB/network/LLM access from the strategy file.

**MTG spec lens:** systematic cross-sectional equity factor · long-only momentum · ~1-week holding · top-quintile by 6-1 momentum (≥ `min_score`) · weekly rebalance with rank-hysteresis · equal target notional capped at `max_position_pct`, whole shares, market orders · no per-name stops · bail-outs: HOLD on missing factor data, risk-off to CASH when SPY < its 200d MA (fails open), risk-engine caps/breaker as the halt.

---

## 2. Current live configuration (id=2)

**Universe:** 201 symbols = top-200 PIT liquidity candidates + SPY (the regime/vol proxy; excluded from holdings).

**Stored params:**

| Param | Value | Notes |
|---|---|---|
| `max_names` | 5 | book cap (tuned for the ~$10k account) |
| `max_position_pct` | 0.20 | per-name cap (companion to max_names so per-name isn't capped at 10%) |
| `top_quantile` | 0.20 | top-quintile cut |
| `min_score` | 0.0 | z-score floor (no negative-momentum names) |
| `cash_buffer_pct` | 0.02 | keep 2% cash |
| `use_market_regime_filter` | true | SPY vs 200d MA → cash in downtrends |
| `market_filter_symbol` | SPY | must be in `symbols` |
| `pricing_timeframe` | 1Day | daily close for sizing |
| `timeframe` | 1Day | **engine dispatch** bar timeframe (fires `on_bar`) |
| `initial_equity_estimate` | 10000 | fallback only; live equity preferred |

**Inherited from defaults (not stored):** `market_ma_days`=200, `min_trade_pct`=0.03, `rebalance_buffer_rank_pct`=0.05, `order_pacing_seconds`=1.0, `use_vol_scaling`=**false**, `vol_target_annual`=0.15, `vol_ewma_span`=20.

**Current holdings (BFY6):** AAOI ×10, MU ×1, INTC ×15, BE ×7 (the live momentum book) + ADC ×6, MTDR ×9 (pre-existing, **outside** the universe → the strategy ignores them).

---

## 3. How a rebalance works

1. Engine fires `on_bar` per symbol on the cron tick (`StrategyEngine._dispatch_bar_tick`, fetching a `timeframe` bar).
2. `on_bar` marks the ISO week **at the start of the attempt** (≤1 rebalance/week; prevents the per-symbol-dispatch storm) and runs `_rebalance` once.
3. `_rebalance`: ① market-regime gate (SPY<200dMA → all-cash, fails open if SPY series missing) → ② momentum scores over the registered universe → ③ select top-quintile targets with rank hysteresis (SPY excluded) → ④ diff vs current holdings, sell leavers/trim then buy toward `investable_equity / k`.
4. Sizing: live account equity (`ctx.get_account_equity`, fallback to estimate) × (1 − cash_buffer) × `gross_scale` (vol-scaling, currently 1.0 = off), per-name = min(equity/k, equity·max_position_pct), whole shares.
5. Each order: `OrderRequest(source_type=STRATEGY)` → `ctx.submit_order` → OrderRouter + risk gates → Alpaca paper; submissions paced `order_pacing_seconds` apart.
6. Bail-outs: factor data unavailable → HOLD (logged); unexpected exception → log `rebalance_failed`, retry next **week** (not next tick).

---

## 4. What has been completed

### Build (P9 §1–§4, all tagged)
- **§1** Sharadar PIT survivorship-free price spine → local DuckDB store; `universe_asof` (PIT liquidity top-N).
- **§2** 6-1 month momentum factor (z-score of winsorized momentum) + sandboxed read-only `FactorAccessor` (`ctx.factors`), no look-ahead.
- **§3** Survivorship-free weekly cross-sectional backtest (final-price→cash delisting, equal-weight top-quintile, daily mark-to-market, ADR-0014 baseline).
- **§4** The `momentum-portfolio` Strategy template (PAPER-only), weekly cron + once-per-ISO-week rebalance.

### Review hardening → v0.3.0 (PR #106)
Live-equity sizing, turnover threshold (`min_trade_pct`), rank hysteresis, market-regime filter (fail-open), fail-hold on factor data, SPY excluded from holdings, MA over completed bars.

### Paper activation (2026-06-14)
Registered + activated to PAPER on the BFY6 ~$10k account; 201-symbol universe; auto-resumes on backend boot.

### First-rebalance day (2026-06-15) — four bugs found, fixed, merged, deployed
| Issue | Fix | PR |
|---|---|---|
| Weekly cron `0 14 * * 1` fired **Tuesday** (APScheduler dow 0=Mon, no remap) | engine `_normalize_crontab_dow` (systemic) + schedule → `0 14 * * mon` | #115, #116 |
| Circuit breaker tripped `daily_loss_exceeded` on **buys** (counted purchase notional as realized loss) | realize P&L only on closes (running avg cost) | #114 |
| Submission **storm**: engine dispatches `on_bar` ~200×/tick; v0.3.0 marked the week only after success → a failing rebalance re-ran 200× | mark the week on **attempt** (retry next week, not next tick) | #116 |
| Dispatch used the engine's `1Min` default timeframe | `timeframe: "1Day"` param | #116 |
| No order pacing under the per-strategy rate cap | `order_pacing_seconds` (default 1.0) | #116 |
| Crash risk (review Priority 1) | optional EWMA portfolio **vol-scaling** (default OFF) + backtest overlay | #112 |

### Live validation (2026-06-15, post-fix)
A clean manual rebalance bought **BE ×7 (FILLED, source=STRATEGY, no rejection)** — the *exact order* the buggy breaker rejected that morning — with **no daily-loss trip and no storm**. Proves the full path STRATEGY → OrderRouter → risk engine → Alpaca fill end-to-end, and completes the book to its 4-name target. Reverted to the weekly-Monday schedule. (The earlier 2026-06-15 backtest evidence for vol-scaling: max drawdown −38.8% → −15.9%, Sharpe 1.23 → 1.29 over the available window.)

---

## 5. Known limitations

1. **$10k + whole shares under-deploys.** Momentum clusters in pricey semis (e.g. SNDK ~$1980); names priced above the per-name budget floor to 0 shares → ~67% deployed across ~4 names. **Fractional shares** is the clean fix (deferred).
2. **Sector/correlation concentration.** The book skews semis/AI ("one AI-beta trade"); no sector cap yet (P10 §3, gated on sector classification data).
3. **Vol-scaling is OFF** by default — implemented but needs a broader-history backtest before enabling on the live book.
4. **Factor store is date-bounded** (~2024-06 onward for most names) → backtests cover a short, momentum-friendly window; broaden SEP history before drawing perf conclusions or promoting toward LIVE.
5. **Order-rate headroom.** The per-strategy cap is 5 orders/min (rolling); `order_pacing_seconds`=1.0 doesn't beat a rolling-minute cap for bursts >5 orders. Fine for the current 5-name book; raise the cap (or pacing) if the book grows. The once-per-week-attempt guard makes any rate rejection graceful (no storm; retry next week).
6. **Cosmetic:** the registered `strategies.version` row reads `0.3.0` while the code is `0.4.0` (the code file is authoritative).
7. **Pre-existing positions** ADC/MTDR sit in the paper account but are outside the universe and untouched by the strategy.

---

## 6. Next steps

**Immediate / monitoring**
- **Watch the Monday 2026-06-22 14:00 UTC cron rebalance** — the first fully-unattended scheduled fire on the fixed system. Expect a no-op or light adjustment unless the momentum ranking shifts. Confirm: fires Monday, no breaker trip, audit `source_type=STRATEGY`.
- (Optional cleanup) align the DB row `version` to `0.4.0`; rebuild the backend image to bake #112's `backtest.py` change (only matters for running backtests, not the live book).

**P10 portfolio-risk roadmap** (see `TradingWorkbench_P10_PortfolioRisk_Roadmap_v0.1.md`)
- **Priority 1 — enable vol-scaling** on the live book once a broader-history backtest supports it (already implemented, default off).
- **Priority 2 — daily exposure overlay** (keep weekly selection): needs a framework decision on dual cron cadence — own session doc + likely a small ADR.
- **Priority 3 — sector caps**: gated on ingesting sector classification (Sharadar TICKERS sector field, or the P9 §5 FMP layer).
- **Priority 4 — exposure smoothing** on top of #1/#2.
- **Data-dep ADRs**: VIX/breadth (for richer regime/vol inputs); sector data source.

**Capacity & realism**
- **Fractional shares** for full deployment on a ~$10k account (the biggest single under-deployment fix).
- Re-tune the per-strategy order-rate cap if `max_names` grows.

**Path toward LIVE (not yet scoped)**
- A framework `Backtester` run or an accepted external-reference eval (ADR 0014) is the prerequisite for LIVE promotion; plus the 24-h activation cooldown (ADR 0005). Broaden the factor history first.

---

## Notes & gotchas
1. **Re-activation needs the deployed image** — `app/` fixes (breaker, engine) are baked into the backend image; the strategy file is volume-mounted. After code changes to `app/`, `docker compose build backend` before relying on them live.
2. **Manual one-off rebalance recipe** (local-only, uncommitted helpers): `scripts/trigger_rebalance_once.py --mode trigger` (sets a near-term cron + daily dispatch, starts) then `--mode revert` (restores `0 14 * * mon`). Recovery from a breaker halt: reset breaker (`/accounts/{id}/risk/reset-circuit-breaker`, confirmation = account label) → `deactivate` (HALTED→IDLE; **not** `stop`, which leaves it HALTED) → PUT schedule → start.
3. **Use day NAMES in cron schedules** (`mon`, not `1`) — numeric dow is now normalized engine-side, but names are unambiguous.
