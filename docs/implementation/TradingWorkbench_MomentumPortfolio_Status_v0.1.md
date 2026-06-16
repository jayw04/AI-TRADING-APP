# momentum-portfolio — Strategy Status & Next Steps

| Field | Value |
|---|---|
| Document version | v0.4 (2026-06-15: +§5F–§5J from review comments — order lifecycle, source-of-truth, timestamp invariants, run schema, execution invariants) |
| Date | 2026-06-15 |
| Strategy | `momentum-portfolio` (code `apps/backend/strategies_user/templates/momentum_portfolio.py`) |
| Code version | **v0.5.0** — v0.4.0 (cron/dispatch/storm/pacing/vol-scaling) is merged & live; **v0.5.0 (sector caps, default off) is in PR #118, pending merge**. ⚠ the registered DB row `strategies.version` still reads `0.3.0` (cosmetic — the code file is what runs) |
| Live instance | strategy **id=2**, status **PAPER**, run_id=6, account **BFY6** (Alpaca paper, ~$10k) |
| Schedule | `0 14 * * mon` — weekly, Monday 14:00 UTC (≈10:00 ET, ~30 min after the 09:30 open) |
| Repository HEAD | `31ddfd6` (#111–#116 + #112 merged & deployed). Open PRs: **#117** (this doc), **#118** (sector caps) |
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

**Inherited from defaults (not stored):** `market_ma_days`=200, `min_trade_pct`=0.03, `rebalance_buffer_rank_pct`=0.05, `order_pacing_seconds`=1.0, `use_vol_scaling`=**false**, `vol_target_annual`=0.15, `vol_ewma_span`=20, `max_sector_pct`=**None** (sector cap disabled; #118).

**Current holdings (BFY6):** AAOI ×10, MU ×1, INTC ×15, BE ×7 (the live momentum book) + ADC ×6, MTDR ×9 (pre-existing, **outside** the universe → the strategy ignores them).

---

## 3. How a rebalance works

1. Engine fires `on_bar` per symbol on the cron tick (`StrategyEngine._dispatch_bar_tick`, fetching a `timeframe` bar).
2. `on_bar` marks the ISO week **at the start of the attempt** (≤1 rebalance/week; prevents the per-symbol-dispatch storm) and runs `_rebalance` once.
3. `_rebalance`: ① market-regime gate (SPY<200dMA → all-cash, fails open if SPY series missing) → ② momentum scores over the registered universe → ③ select top-quintile targets with rank hysteresis (SPY excluded), then an **optional per-sector cap** (`max_sector_pct`, off by default) that drops over-concentrated names and backfills from other sectors → ④ diff vs current holdings, sell leavers/trim then buy toward `investable_equity / k`.
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

### Sector caps built → v0.5.0 (PR #118, default off)
P10 §3 / review #7. Persists Sharadar `sector`/`industry` on the tickers table (additive idempotent migration); adds `FactorAccessor.sectors()` (read-only sandbox surface) and a `max_sector_pct` strategy param that caps names per sector and **backfills** from other sectors (diversify without shrinking), failing open if sector data is unavailable. **Default off** — no live behavior change until a deliberate, backtested enable. Tested (store/accessor/strategy); ruff + mypy clean; suites green. ⚠ Not yet *usable* on the live book — see limitations #2 / next-steps.

---

## 5. Known limitations

1. **$10k + whole shares under-deploys.** Momentum clusters in pricey semis (e.g. SNDK ~$1980); names priced above the per-name budget floor to 0 shares → ~67% deployed across ~4 names. **Fractional shares** is the clean fix (deferred).
2. **Sector/correlation concentration.** The book skews semis/AI ("one AI-beta trade"). The sector cap is now **built** (PR #118, default off) but **not yet usable on the live book**: the live tickers store has no sector data until a TICKERS re-ingest runs (after #118's schema deploys), and enabling `max_sector_pct` should follow a backtest.
3. **Vol-scaling is OFF** by default — implemented but needs a broader-history backtest before enabling on the live book.
4. **Factor store is date-bounded** (~2024-06 onward for most names) → backtests cover a short, momentum-friendly window; broaden SEP history before drawing perf conclusions or promoting toward LIVE.
5. **Order-rate headroom.** The per-strategy cap is 5 orders/min (rolling); `order_pacing_seconds`=1.0 doesn't beat a rolling-minute cap for bursts >5 orders. Fine for the current 5-name book; raise the cap (or pacing) if the book grows. The once-per-week-attempt guard makes any rate rejection graceful (no storm; retry next week).
6. **Cosmetic:** the registered `strategies.version` row reads `0.3.0` while the code is `0.4.0` live (`0.5.0` once #118 merges) — the code file is authoritative.
7. **Pre-existing positions** ADC/MTDR sit in the paper account but are outside the universe and untouched by the strategy.

---

## 5A. Expected failure modes

The single most important operational table: what the strategy does when a dependency fails. Every row is a **deliberate** choice; the bias is *fail toward inaction*, not toward an unintended trade.

| Failure | Behavior | Why |
|---|---|---|
| Factor data unavailable (whole universe) | **HOLD** — no rebalance this window; logged `rebalance_failed`, retry next **week** | A momentum decision without scores is a guess; doing nothing preserves the current book. |
| SPY (regime proxy) series unavailable | **Fail open** — skip the regime gate, run the deterministic momentum selection | A transient data gap should not silently flatten the book to cash (see §5C). |
| A single name's price missing at sizing | That name is **skipped** (0 shares); the rest of the book rebalances | One bad symbol shouldn't abort the whole rebalance. |
| Order rejected by risk engine (caps/notional) | **Logged, continue** — the remaining orders still submit; no retry storm | Risk gates are non-bypassable; a partial rebalance is the correct outcome. |
| Order-rate cap hit (>5/min) | **Graceful partial** — excess orders rejected this minute; once-per-week-attempt guard prevents re-storm | The book converges next attempt; no order storm (the #116 fix). |
| Broker disconnect / Alpaca outage | **No orders submitted**; submissions fail and are logged | Fail closed on execution — never assume a fill. |
| Strategy raises an unexpected exception | **Rebalance aborted for the current schedule window** (week marked on attempt) | Isolation: a strategy crash cannot wedge the engine or re-fire 200×. |
| Circuit breaker tripped (daily-loss/manual) | **HALTED** — no further orders until reset | The breaker is the last-resort halt (ADR 0004). |

---

## 5B. Turnover & holding period

Momentum systems can silently overtrade; these are the metrics to watch (rank hysteresis + `min_trade_pct` are the throttles).

| Metric | Current estimate | Notes |
|---|---|---|
| Avg weekly turnover | **~10–25%** of book (estimate) | Damped by `rebalance_buffer_rank_pct`=0.05 (hysteresis) and `min_trade_pct`=0.03 (no sub-3% trims). Needs measurement over ≥8 live weeks. |
| Annualized turnover | **~5–13×** (derived from weekly) | Confirm against actual fills, not the model. |
| Average holding period | **~4–10 weeks** (estimate) | A name held while it stays in the top quintile; hysteresis lengthens this. |

> ⚠ These are *modeled* estimates. Replace with **measured** turnover from the audit-logged fills once ≥8 scheduled rebalances have run — overtrading is the failure mode this table exists to catch.

---

## 5C. Benchmark

Performance statements are meaningless without a benchmark. For this strategy:

- **Primary benchmark: SPY total return** (the strategy already holds SPY as its regime proxy, and a long-only US-equity book is naturally measured against the S&P 500).
- **Secondary (style-aware): equal-weight large-cap** (e.g. RSP / equal-weight Russell 1000) — fairer for an equal-weight book that is not cap-weighted.
- Report **excess return vs SPY**, not just absolute, in all future performance discussions; drawdown and Sharpe are reported alongside SPY's over the same window.

---

## 5D. Why "fail open" on the regime filter (rationale)

The market-regime gate (SPY < 200d MA → all-cash) **fails open**: if the SPY series is unavailable, the gate is skipped and the deterministic momentum selection runs normally.

**Rationale:** silent strategy disablement from a *transient data outage* is operationally worse than continuing deterministic baseline trading. A data gap is not a market signal — flattening the entire book to cash because a price feed hiccupped would be an unintended, hard-to-diagnose action driven by infrastructure, not by the strategy's thesis. The risk engine and circuit breaker remain in force regardless, so "fail open" here never means "unbounded risk" — it means "don't let a feed glitch masquerade as a sell signal." (Contrast with execution failures, which **fail closed** — see §5A.)

---

## 5E. Minimum LIVE promotion criteria

Promotion from PAPER to LIVE is the expensive direction (ADR 0005 cooldown + ADR 0014 backtest ground truth). The bar — **all** must hold:

- [ ] **≥ 6 months** of paper runtime on the fixed system (post-#114/#116).
- [ ] A **broader-history backtest** (unbiased SEP, survivorship-free) supporting the live config — not just the 2024→ momentum-friendly window (limitation §5.4).
- [ ] **No unresolved reconciliation issues** between the DB, the audit log, and the Alpaca account.
- [ ] **Max drawdown within the expected envelope** (vs the backtested/vol-scaling envelope).
- [ ] **No uncontrolled order storms** across the full paper period (the #116 guard holds).
- [ ] **Successful broker reconnect/recovery** demonstrated at least once (disconnect → resume without duplicate or dropped orders).
- [ ] **Stable factor ingestion** (no silent gaps) over the paper period.
- [ ] The 24-h activation cooldown (ADR 0005) honored at promotion.

---

## 5F. Order lifecycle state model

> Review comments §1C. The canonical `OrderStatus` enum (`app/db/enums.py`) — every order, manual or strategy, moves through these states.

```
PENDING_RISK ──▶ PENDING_SUBMIT ──▶ SUBMITTED ──▶ PARTIALLY_FILLED ──▶ FILLED
     │                  │               │                 │
     └─▶ REJECTED       └─▶ REJECTED    ├─▶ CANCELED       └─▶ (more fills) ─▶ FILLED
        (risk gate)        (broker)     ├─▶ EXPIRED
                                        └─▶ REPLACED
```

- **`PENDING_RISK`** — created, awaiting the risk engine. A risk rejection → **`REJECTED`** (terminal, with a typed `RejectionReason`).
- **`PENDING_SUBMIT`** — risk-approved, handed to the broker adapter. A permanent broker error → **`REJECTED`**; a transient error leaves it `PENDING_SUBMIT` for retry (never silently marked rejected).
- **`SUBMITTED`** — accepted by Alpaca; live on the book.
- **`PARTIALLY_FILLED` → `FILLED`** — fills accumulate via the trade-updates stream.
- **`CANCELED` / `EXPIRED` / `REPLACED`** — terminal broker outcomes (DAY orders expire at the close).

**Invariant:** terminal states (`FILLED`, `REJECTED`, `CANCELED`, `EXPIRED`) never transition further; `terminal_at` is stamped once. (The reviewer's `NEW`/`RECONCILED` are not separate DB states — creation is `PENDING_RISK`; reconciliation updates an existing row from broker truth, see §5G.)

---

## 5G. Position & accounting source-of-truth

> Review comments §1B. The authoritative computation chain, to prevent drift bugs.

- **Positions are broker-authoritative intraday.** Alpaca is the source of truth for held quantity and cash.
- **The local `positions` table is derived state** — reconstructed from fills and periodically reconciled against the broker by `PositionSyncService` (`app/services/position_sync.py`). On boot and on reconnect, the DB is corrected to match Alpaca.
- **The audit log is authoritative for *decisions and actions*** (what the strategy/router decided and did), not for current holdings.
- Sizing reads **live account equity** (`ctx.get_account_equity`), not the DB snapshot, falling back to the estimate only if the broker is unreachable.

**Rule of thumb:** *holdings* → broker; *decisions* → audit log; *DB* → fast derived cache reconciled to the broker.

---

## 5H. Timestamp & session conventions

> Review comments §1D. Formalized to prevent timezone confusion.

- **All persisted timestamps are UTC** (models use `DateTime(timezone=True)`; the order path stamps `datetime.now(UTC)`).
- **Market-session logic uses `America/New_York`** (RTH, the Monday cron's ≈10:00 ET fire, end-of-day guards). Session determination source is the Market Session Model (design doc §9A): `pandas_market_calendars` (XNYS) + the Alpaca clock.
- **ISO week** (`%G-W%V`) keys the once-per-week rebalance guard.
- **The UI converts UTC → the user's local timezone** for display; storage is never local-time.

---

## 5I. Strategy run-state schema

> Review comments §1A. The run-state table exists today; the canonical fields:

```
strategy_runs (app/db/models/strategy_run.py)
- id            run identifier (the run_id surfaced in this doc, e.g. run_id=6)
- strategy_id   FK → strategies
- started_at    UTC
- ended_at      UTC | null (null while active)
- status        StrategyStatus (PAPER/LIVE/HALTED/…)
- error_text    str | null (failure detail when a run aborts)
```

Reviewer-proposed fields **not yet columns** (deferred enhancements, not blockers): `trigger_type`, `rebalance_week`, `rebalance_reason`, `exception_class` (currently folded into `error_text`). A **`portfolio_snapshots`** accounting table (ts, gross/net exposure, cash, equity, realized/unrealized PnL, leverage, drawdown, vol_scale) does **not** exist yet — it's a deferred analytics structure (tracked in the P10 roadmap); today the breaker computes those quantities on demand (§5J / circuit-breaker).

---

## 5J. Strategy execution invariants

> Review comments §1E. The guarantees the engine enforces around a rebalance.

- **At most one active rebalance per strategy per window** — the ISO-week guard marks the week on *attempt* (the #116 storm fix), so the ~200×/tick dispatch cannot launch concurrent rebalances.
- **No concurrent `_rebalance()`** — dispatch is serialized per strategy; a tick that arrives mid-rebalance is a no-op for that week.
- **Order submission is idempotent per rebalance window** — re-running a marked week does not re-submit.
- **Strategy exceptions cannot terminate the engine** — a raised exception aborts only that strategy's current window (logged `rebalance_failed`); isolation is a CI invariant (`check_strategy_isolation.sh`).
- **Failed orders never auto-retry blindly** — a rejection is logged and the window ends; recovery is the next scheduled window or an operator manual rebalance (never an automatic resubmit loop).

---

## 6. Next steps

**Immediate / monitoring**
- **Watch the Monday 2026-06-22 14:00 UTC cron rebalance** — the first fully-unattended scheduled fire on the fixed system. Expect a no-op or light adjustment unless the momentum ranking shifts. Confirm: fires Monday, no breaker trip, audit `source_type=STRATEGY`.
- **Merge the open PRs** when reviewed: **#117** (this status doc), **#118** (sector caps).
- (Optional cleanup) align the DB row `version`; rebuild the backend image to bake #112's `backtest.py` change (only matters for running backtests, not the live book).

**P10 portfolio-risk roadmap** (see `TradingWorkbench_P10_PortfolioRisk_Roadmap_v0.1.md`)
- **Priority 1 — enable vol-scaling** on the live book once a broader-history backtest supports it (implemented, default off).
- **Priority 2 — daily exposure overlay** (keep weekly selection): needs a framework decision on dual cron cadence — own session doc + likely a small ADR. (Not started.)
- **Priority 3 — sector caps: BUILT (PR #118, default off).** To make it usable: (1) merge #118 + deploy the store-schema change, (2) **re-ingest TICKERS to populate `sector`**, (3) set `max_sector_pct` (e.g. 0.40) and validate via backtest, (4) enable on the live book.
- **Priority 4 — exposure smoothing** on top of #1/#2. (Not started.)
- **Data-dep ADRs**: VIX/breadth (for richer regime/vol inputs) — sector source is resolved (Sharadar TICKERS, via #118).

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
