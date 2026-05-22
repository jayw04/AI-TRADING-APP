# Trading Workbench — P2 Strategy MVP Checklist

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-21 |
| Phase | **P2 — Strategy MVP** |
| Predecessor | *TradingWorkbench_P1_Checklist_v0.1.md* (closed at tag `p1-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Phase numbering | **Design Doc §13** (todo.md-aligned). See P1 Checklist §0.3 for the canonical mapping vs. Implementation Plan v0.2. |
| Estimated effort | 3–4 weeks FTE-equivalent (6–9 weeks evenings/weekends) |
| Goal | One reference systematic strategy runs end-to-end on Alpaca paper with a working backtest harness, per-strategy risk caps, and a basic Strategies UI page. (Design Doc §2.3 criterion **S3**.) |

---

## 0. Pre-flight

### 0.1 P1 hygiene check (carry-overs)

Before any P2 code, confirm:

- [ ] `git describe --tags --abbrev=0` on `main` returns `p1-complete`.
- [ ] CI is green on the commit `p1-complete` points to.
- [ ] `docs/runbook/p1-smoke-log.md` exists with all six steps recorded.
- [ ] Alpaca paper account: open positions count = 0, open orders count = 0.
  ```bash
  ./scripts/dev.sh
  sleep 25
  curl -s http://127.0.0.1:8000/api/v1/positions | jq '.count'   # expect 0
  curl -s http://127.0.0.1:8000/api/v1/orders?status=open | jq '.count'  # expect 0
  docker compose down
  ```
- [ ] ADR 0002 grep tripwire still passes: `bash apps/backend/scripts/check_adr0002.sh`.
- [ ] Risk engine branch coverage still at the gate set in P1 Session 7.

If anything is amber, fix in a `chore/p1-hygiene-...` PR before P2 starts.

### 0.2 P2 prereqs (one-time reads + decisions)

- [ ] Re-read **Design Doc §11** (Strategy framework) and **Implementation Plan v0.2 §9 + §15** (strategy interface, reference RSI strategy). Anything that contradicts this checklist, this checklist wins for P2.
- [ ] Re-read **ADR 0002** (single order entry point). Strategies submit through `OrderRouter` like everyone else; the engine cannot fast-path past the risk gate.
- [ ] Confirm the **reference strategy decision**: P2 ships **one** Python strategy — RSI mean-reversion on a small symbol set (default `[AAPL, MSFT, SPY]`). This is a *reference implementation*, not a recommended trading strategy. Calling it out so we don't accidentally promote it.
- [ ] Confirm **strategy types in P2 scope**: Python only. `pine` and `agent` enum values exist in the schema (so we don't migrate twice), but the engine only dispatches Python strategies. Pine arrives in P4; Agent in P6.
- [ ] Confirm **backtest scope**: market-order strategies fill at next bar's open with a configurable slippage in basis points. Limit/stop simulation lands when the first strategy needs it (not P2).
- [ ] Create a GitHub milestone "P2 — Strategy MVP" linking to this checklist:
  ```bash
  gh api repos/jayw04/AI-TRADING-APP/milestones \
    -f title="P2 - Strategy MVP" \
    -f description="See docs/implementation/TradingWorkbench_P2_Checklist_v0.1.md"
  ```

### 0.3 Phase-numbering reminder

This P2 follows **todo.md / Design Doc §13** numbering, same as the P1 Checklist:

| This doc | Design Doc §13 | Implementation Plan v0.2 §17 |
|---|---|---|
| **P2 — Strategy MVP** ← *you are here* | P2 Strategy MVP | **P3** Strategy Engine + Reference Strategy |
| P3 — Agent MVP (B1+B2) | P3 Agent MVP | P5 Agent B1+B2 |
| P4 — Polish & extend | P4 Polish | P2+P4+P8 (Opportunities, TV webhooks, polish) |
| P5 — Live trading | P5 Live | P9 Live Mode Toggle |
| P6 — Agent autonomy (B3) | P6 Agent autonomy | P6 Agent Strategy |
| P7 — NL → Python (B′) | (stretch) | P7 NL → Python |

**Acceptance for §0:** P1 hygiene green; prereqs read; reference-strategy choice + backtest scope confirmed; milestone created.

---

## 1. Server-side Indicators + Bar Cache (P2.A)

The foundation for everything else: a deterministic, fast source of OHLCV bars and computed indicators. Backtest needs it; the runtime strategy engine needs it; future Opportunities-page indicators (P4) will reuse it.

### 1.1 Bar cache (parquet, per Implementation Plan v0.2 §19 #1)

- [ ] `apps/backend/app/market_data/bar_cache.py` — `BarCache` class.
  - Storage layout: `apps/backend/bars_cache/{symbol}/{timeframe}/{YYYY-MM-DD}.parquet`.
  - Read API: `get_bars(symbol, timeframe, start, end)` returns a pandas DataFrame; cache hits served from disk, misses fetched from Alpaca and written.
  - Write API: append-only; never rewrites existing days.
- [ ] LRU eviction: configurable size cap (default 5 GB per v0.2 §19 #4). Track total cache size; evict oldest-accessed full-day files when over.
- [ ] `BarCacheConfig` in `app.config` with cap size + cache root path.

### 1.2 Indicator computer (`pandas-ta` wrapper)

- [ ] `apps/backend/app/indicators/computer.py` — `IndicatorComputer` class.
- [ ] Core set (P1 Checklist §13 already listed these as P2 dependencies):
  - Trend: SMA 20/50/200, EMA 9/21
  - Momentum: RSI(14), MACD(12,26,9)
  - Volatility / level: ATR(14), VWAP, Bollinger Bands(20,2)
  - Volume: relative volume vs. 20-day average
- [ ] Public surface: `compute(bars: pd.DataFrame, names: list[str]) -> dict[str, pd.Series]`.
- [ ] Caching: indicator values memoized on `(symbol, timeframe, end_ts, indicator_name)` — same call twice in the same minute returns the cached series.

### 1.3 REST endpoint

- [ ] `GET /api/v1/indicators/{symbol}` — query: `set=core|extended` or `names=RSI,MACD,...`, plus `timeframe`. Returns the latest values + last N points for sparklining. (Will be consumed by the Strategies detail UI in §7; later by Opportunities in P4.)

### 1.4 Tests

- [ ] Golden test: cache the same fixture bars in `tests/fixtures/bars/`; assert `IndicatorComputer.compute` produces identical RSI/MACD values across runs (catches pandas-ta version regressions).
- [ ] Cache test: write a day, read it back, confirm bytes-equal.
- [ ] LRU eviction test: write past the cap, confirm oldest file is gone.

**Acceptance:** `/api/v1/indicators/AAPL?names=RSI,MACD` returns sensible values during market hours; bar cache fills `apps/backend/bars_cache/` on first use and serves from disk on subsequent calls; indicator golden test passes.

---

## 2. Strategies DB Schema (P2.B)

Add the four tables that hold strategy state. Schema is per Implementation Plan v0.2 §6.4 with one note: the `agent_strategy_configs` table and the `pine_alerts_raw` table are **not** created in P2 — they're P3 and P4 work respectively. The `strategies.type` enum still includes `agent` and `pine` values so we don't have to migrate the enum twice.

### 2.1 New enums

- [ ] Extend `apps/backend/app/db/enums.py`:
  - `StrategyType`: `python`, `pine`, `agent` (Python only used in P2).
  - `StrategyStatus`: `idle`, `backtest`, `paper`, `live`, `error`, `halted`.
  - `SignalType`: `entry`, `exit`, `flat`, `info`, `agent_action`, `pine_alert`.

### 2.2 Models

- [ ] `apps/backend/app/db/models/strategy.py` — `Strategy(id, user_id, name, version, type, status, code_path, params_json, symbols_json, schedule, risk_limits_id NULL, created_at, updated_at)`.
- [ ] `apps/backend/app/db/models/strategy_run.py` — `StrategyRun(id, strategy_id, started_at, ended_at NULL, status, error_text NULL)`.
- [ ] `apps/backend/app/db/models/signal.py` — `Signal(id, user_id, strategy_id NULL, symbol_id, type, payload_json, received_at, processed_at NULL)`.
- [ ] `apps/backend/app/db/models/backtest_result.py` — `BacktestResult(id, strategy_id, run_id, params_json, metrics_json, equity_curve_json, trades_json, created_at)`.

### 2.3 Migration

- [ ] `alembic revision --autogenerate -m "P2: strategies, strategy_runs, signals, backtest_results"`.
- [ ] Review: foreign keys to `users`, `symbols`, `risk_limits` (FK to `risk_limits.id` for strategy-scoped caps). Indices: `signals(strategy_id, received_at)`, `signals(symbol_id, received_at)`, `strategy_runs(strategy_id, started_at)`.
- [ ] Round-trip downgrade/upgrade clean.

### 2.4 Seed: per-strategy risk_limits row for the reference strategy

- [ ] Extend `scripts/seed_dev_data.py`: add a `risk_limits` row at `STRATEGY` scope (scope_id = the reference strategy's id) with tighter caps than GLOBAL — max_position_notional $5000, max_orders_per_minute 5. Idempotent.

**Acceptance:** Four new tables present after migrate; `strategies.type` enum includes the future-reserved values; STRATEGY-scope risk_limits row exists with tighter caps than GLOBAL.

---

## 3. Strategy Framework (P2.C)

The interface every strategy implements + the context object handed to user code + the engine that hosts them.

### 3.1 Strategy interface

- [ ] `apps/backend/app/strategies/base.py` — abstract `Strategy` class per IP v0.2 §9.1:
  ```python
  class Strategy:
      name: ClassVar[str]
      version: ClassVar[str]
      symbols: ClassVar[list[str]]
      schedule: ClassVar[str]               # cron string or 'event'
      default_params: ClassVar[dict]

      def __init__(self, ctx: StrategyContext, params: dict): ...
      def on_bar(self, bar): ...
      def on_signal(self, signal): ...
      def on_fill(self, fill): ...
  ```
- [ ] Default no-op implementations of `on_bar` / `on_signal` / `on_fill` so a strategy only overrides what it needs.

### 3.2 Strategy context

- [ ] `apps/backend/app/strategies/context.py` — `StrategyContext` exposing **safe** accessors:
  - `get_positions()` — current open positions for the strategy's allowed symbols only.
  - `get_recent_bars(symbol, timeframe, n)` — via `BarCache`.
  - `get_indicators(symbol, names, timeframe)` — via `IndicatorComputer`.
  - `submit_order(order_request)` — dispatches to `OrderRouter.submit` with `source_type=STRATEGY` and `source_id=<strategy_id>`. **No direct adapter access.**
  - `log_signal(symbol, type, payload)` — writes to `signals` table.
  - `journal(text)` — writes a `journal_entries` row attributed to this strategy (table from P0).

### 3.3 Strategy engine

- [ ] `apps/backend/app/strategies/engine.py` — `StrategyEngine` class.
  - **Lifecycle:** `register(strategy_id) -> running task`, `unregister(strategy_id) -> halt task`.
  - **Scheduling:** APScheduler integration (re-using Session 2's scheduler), one cron job per registered strategy whose `schedule != 'event'`.
  - **Event dispatch:** subscribes to the event bus for `fill.created` and `signal.new`; dispatches to `strategy.on_fill` / `strategy.on_signal` only when the relevant strategy's symbol set matches.
  - **Bar dispatch (P2 polling-based, see §3.5 below):** every N seconds during market hours, fetch latest bars for active strategies' symbols, call `strategy.on_bar(bar)`.
  - **Error containment:** any uncaught exception inside user strategy code is caught, the strategy is transitioned to `error` status, and an audit row is written. The engine keeps running.

### 3.4 Strategy loader

- [ ] `apps/backend/app/strategies/loader.py` — `load_strategy_class(code_path)` reads a Python file under `apps/backend/strategies_user/` and returns the strategy class. Module name derived from path; classes that don't subclass `Strategy` are rejected.
- [ ] Safety: the loader does NOT trust paths from request bodies. For P2, only paths under `strategies_user/` registered at startup are loadable. Arbitrary file-load via API is a P3+ concern when the agent might propose strategies.

### 3.5 Bar dispatch cadence — polling for MVP

P2 polls bars rather than subscribing to Alpaca's market-data WS. Rationale:

- Polling is deterministic, easy to test, easy to throttle for free-tier rate limits.
- The reference RSI strategy reacts at 1-minute granularity; a 30-second poll is fast enough.
- WS-driven dispatch lands in P4 when the universe of subscribed symbols matters more (Opportunities page, multiple concurrent strategies).

Defaults:
- Poll interval: 30s during regular session, 5min off-hours (configurable per strategy via `schedule`).
- Per poll: fetch the latest 100 bars for each strategy's symbols (covers all P2 indicator lookback needs).

### 3.6 Strategy submission goes through OrderRouter (ADR 0002)

- [ ] `StrategyContext.submit_order` calls `OrderRouter.submit(req, source=STRATEGY, source_id=strategy_id)`.
- [ ] Extend the ADR 0002 grep tripwire to permit `app/strategies/context.py` if it ever needs to import `OrderRouter` (most likely it imports via FastAPI app state, no allowed-files change needed).
- [ ] Verify: a strategy that tries to `import alpaca_trade_api` directly and bypass OrderRouter is caught by the existing grep check (no new tripwire needed; the existing one already covers `app/`).

**Acceptance:** A no-op strategy registers, gets dispatched `on_bar` at the configured cadence, can call `ctx.submit_order` which lands an `Order` row with `source_type='strategy'` and `source_id` set, and unregisters cleanly.

---

## 4. Reference Strategy: RSI Mean Reversion (P2.D)

Per IP v0.2 §15. Lives at `apps/backend/strategies_user/examples/rsi_meanreversion.py`.

### 4.1 Logic (spec)

- Universe: `default_params['symbols']` (default `["AAPL", "MSFT", "SPY"]`).
- On each 1-minute bar for each symbol:
  - Compute RSI(14).
  - If `RSI < 30` and no current long position: **enter long** with fixed sizing (1% of account equity / ATR distance to stop, rounded down to whole shares).
  - If long position open and `RSI > 55`: **exit long** (market).
  - Hard stop: 2 × ATR below entry; managed by submitting a STOP order when the entry fills (`on_fill` handler).
  - Time stop: at end-of-day, exit any remaining position.
- Strategy-scope risk envelope (from the seed row in §2.4): max 3 concurrent positions, max position notional $5000, no shorts.

### 4.2 Tests

- [ ] Unit: with hand-constructed bars driving RSI through 30 → exit threshold 55, verify the strategy emits exactly one entry signal and one exit signal.
- [ ] Determinism: same bars + same seed + same params → same signals and same orders.
- [ ] Risk integration: with max_position_notional set to $5 (artificial), verify the strategy's `ctx.submit_order` call is rejected by the risk engine and the strategy logs the rejection but keeps running.

**Acceptance:** Strategy file exists, conforms to the interface, passes unit tests. Not yet running on paper — that's Session 4.

---

## 5. Backtest Harness (P2.E)

Same `Strategy` interface, different `ctx`. Per IP v0.2 §9.3.

### 5.1 Harness internals

- [ ] `apps/backend/app/strategies/backtest.py` — `Backtester` class.
  - Loads bars from `BarCache` for the requested date range.
  - Iterates bar-by-bar (per symbol; for multi-symbol strategies, interleave by bar timestamp).
  - At each bar: build a synthetic `Bar` event, hand to `strategy.on_bar`.
  - When the strategy calls `ctx.submit_order` (intercepted in the backtest ctx, not real `OrderRouter`): simulate fill at next bar's open price ± slippage_bps.
  - Maintain in-memory positions, equity curve, trade log.

### 5.2 Metrics

- [ ] Compute and return: total return, Sharpe ratio (daily, annualized), max drawdown, win rate, profit factor, trade count, average win, average loss, average trade duration.
- [ ] Equity curve as a list of `(ts, equity)` points.
- [ ] Trade list: enter/exit ts + price + side + pnl + duration.

### 5.3 Slippage + commission

- [ ] Constants (configurable per backtest run): `slippage_bps` (default 5), `commission_per_share` (default 0; Alpaca paper has no commissions).

### 5.4 Persistence

- [ ] `BacktestResult` row written on every run with `metrics_json` + `equity_curve_json` + `trades_json`. Large; OK to inline in SQLite for MVP.

### 5.5 Reproducibility test

- [ ] Run the reference strategy backtest twice with the same bars and same params: assert metrics identical (within 1e-9 for floats).

**Acceptance:** `POST /api/v1/strategies/{id}/backtest` with a date range runs the strategy over cached bars, returns metrics + equity curve + trade list, and a `BacktestResult` row is persisted.

---

## 6. REST API + WebSocket Topics (P2.F)

Schemas + endpoints + WS topics for the new domain.

### 6.1 Pydantic schemas

- [ ] `apps/backend/app/api/v1/schemas/strategies.py` — `StrategyCreateRequest`, `StrategyUpdateRequest`, `StrategyResponse`, `StrategyListResponse`, `BacktestRequest`, `BacktestResultResponse`, `SignalResponse`.

### 6.2 REST endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/strategies` | List strategies (filter by status, type). |
| POST | `/api/v1/strategies` | Register a strategy by code_path + initial params. |
| GET | `/api/v1/strategies/{id}` | Detail with embedded recent runs + recent signals. |
| PUT | `/api/v1/strategies/{id}` | Update params + risk_limits_id. Only when status is `idle`. |
| POST | `/api/v1/strategies/{id}/start` | Transition `idle → paper`. Engine picks up. |
| POST | `/api/v1/strategies/{id}/stop` | Transition to `idle` or `halted`. Engine releases. |
| POST | `/api/v1/strategies/{id}/backtest` | Body: `{start, end, params?}`. Runs synchronously; returns BacktestResultResponse. |
| GET | `/api/v1/strategies/{id}/runs` | History of strategy runs. |
| GET | `/api/v1/strategies/{id}/signals` | Signals emitted by this strategy. |
| GET | `/api/v1/strategies/{id}/backtests` | List BacktestResults for this strategy. |
| GET | `/api/v1/signals` | Cross-strategy signal view; filter by strategy, symbol, since. |

### 6.3 WebSocket topics

Map onto the existing gateway. Per IP v0.2 §8 replay windows:

- `strategies` — `strategy.status_changed`, `strategy.run_started`, `strategy.run_ended`, `strategy.error`. Replay 60 min.
- `signals` — `signal.new`. Replay 60 min.
- `backtests` — `backtest.completed`. Replay 60 min (low volume).

**Acceptance:** Every endpoint returns expected status codes. OpenAPI docs render. Live WS subscribers see strategy status transitions and signal emissions in real time.

---

## 7. Frontend Strategies Page (P2.G)

Bare-bones in P2: list view, detail view, backtest results view. Parameter editing is a JSON form (no fancy dynamic schema in MVP).

### 7.1 Strategies list page

- [ ] `apps/frontend/src/pages/Strategies/index.tsx` — table with name, version, type, status, last-run-at, today's signals count, today's P&L attributed. Status badge color-coded. Click a row → strategy detail.
- [ ] Row action: "Start" / "Stop" button per strategy.
- [ ] Polls `/api/v1/strategies` every 5s; subscribes to `strategies` WS topic for instant status changes.

### 7.2 Strategy detail page

- [ ] `apps/frontend/src/pages/Strategies/$id.tsx` — tabs: Overview, Signals, Orders, Backtests, Params.
  - **Overview:** equity curve sparkline (from latest backtest if no live run), recent signals list, recent orders attributed to this strategy.
  - **Signals:** table of all signals, filterable by type.
  - **Orders:** reuse the same row component as the Orders page but pre-filtered by `source_id=strategy_id`.
  - **Backtests:** list of past BacktestResults; click → results detail.
  - **Params:** JSON textarea + Save button. Only enabled when status=`idle`.

### 7.3 Backtest detail view

- [ ] Modal or sub-page showing: parameters used, all metrics, equity curve (line chart via recharts), trade list (table).

### 7.4 Strategy run flow

- [ ] Start button → POST `/start` → status changes to `paper` → engine picks up → on_bar fires.
- [ ] Stop button → POST `/stop` → engine releases → status `idle`.
- [ ] Halted by risk (e.g. daily-loss): UI shows red banner on the strategy row + a "Resume" button that calls `/start`.

**Acceptance:** Trader can register the reference strategy, start it, watch signals stream in (or run a backtest), inspect orders attributed to it, stop it. No fancy charts beyond recharts equity curve.

---

## 8. Tests + Smoke Matrix (P2.H)

Mirror the P1 §10 structure.

### 8.1 Backend unit tests

- [ ] `IndicatorComputer`: golden test against fixture bars.
- [ ] `BarCache`: write/read round-trip, LRU eviction, gap-filling.
- [ ] `StrategyEngine`: register/unregister, error containment, dispatch routing.
- [ ] `StrategyContext.submit_order`: dispatches through `OrderRouter` with correct `source_type`/`source_id`.
- [ ] `Backtester`: determinism, slippage application, metrics correctness.
- [ ] Reference strategy: signal emission on RSI threshold crossing.

### 8.2 Integration test

- [ ] End-to-end: register reference strategy → start → simulate bar dispatch → strategy emits entry signal → order goes through risk → mocked Alpaca returns broker_id → trade-update fill arrives → strategy `on_fill` fires → stop order is submitted. Assert: full audit chain, fills attributed to strategy, position attributed.

### 8.3 Backtest reproducibility test

- [ ] Run reference RSI strategy twice on identical fixture bars; assert all metrics identical.

### 8.4 Frontend Vitest

- [ ] Strategies list page renders, start/stop actions hit the right endpoints.
- [ ] Backtest detail renders metrics + equity curve from a mock response.

### 8.5 Manual smoke matrix (mirrors P1 §10.4)

Six steps against Alpaca paper, recorded in `docs/runbook/p2-smoke-log.md`:

1. Register the reference RSI strategy, leave it `idle`.
2. Run a 30-day backtest. Confirm metrics appear in UI; row count > 0.
3. Start the strategy on paper during market hours.
4. Wait for an entry signal (or force one by editing params to a loose threshold). Confirm: signal row, Order row with `source_type=strategy`, fill arrives, position attributed.
5. Force a risk rejection by lowering the per-strategy `max_position_notional` to $1. Confirm: strategy keeps running, audit row records the reject.
6. Stop the strategy, confirm any open position is left in place (closing on stop is *not* default behavior; document this), close manually via Positions page.

### 8.6 CI gates

- [ ] Coverage ratchet: overall ≥ 80% maintained; new code (indicators, strategy engine, backtester) targeted at ≥ 85%.
- [ ] ADR 0002 tripwire continues to pass.
- [ ] Add a new check: `bash apps/backend/scripts/check_strategy_isolation.sh` — greps `app/strategies/` for any direct import of `app.brokers` (allowed only in `context.py` if we ever need it; ideally never).

**Acceptance:** All test suites green; manual smoke matrix recorded with results; coverage gates green.

---

## 9. Documentation

- [ ] `docs/runbook/strategy-authoring.md` — how to write a Python strategy: file location, class structure, ctx accessors, registration, error handling, common pitfalls.
- [ ] `docs/runbook/backtesting.md` — how to run a backtest, what the metrics mean, slippage / commission assumptions, data source.
- [ ] `docs/runbook/p2-smoke-log.md` — the smoke log (created during §8.5).
- [ ] Update `docs/runbook/risk-limits.md` — add a section on STRATEGY-scope risk_limits and how they layer over GLOBAL.
- [ ] Update `README.md` — Quickstart mentions the Strategies page and the reference strategy.
- [ ] Update `todo.md` — P2 in-progress markers as sessions land.

---

## 10. P2 Exit Gate

Before tagging `p2-complete`:

- [ ] All §0 hygiene items closed.
- [ ] Every checkbox above ticked or explicitly deferred (with rationale).
- [ ] Design Doc §2.3 success criterion green: **S3** — "At least one systematic strategy runs end-to-end: signal → risk check → paper order → fill → journal entry."
- [ ] ADR 0002 + strategy-isolation grep checks green.
- [ ] Coverage gates green.
- [ ] Reference strategy backtest produces deterministic metrics on a committed fixture.
- [ ] All six manual smoke steps green; log committed.
- [ ] `docker compose up` from a clean checkout still brings up a working system.
- [ ] `git tag -a p2-complete -m "P2 Strategy MVP complete: reference RSI strategy on paper + backtest"`.
- [ ] `todo.md` updated.

**On all green → P2 is done. Move to P3 (Agent MVP — B1+B2 chat panel).**

---

## 11. Session Breakdown (sketch — refined per session)

The detailed session docs follow the pattern from P1. Suggested split:

| Session | Theme | Sections from this checklist |
|---|---|---|
| **P2 Session 1** | Bar cache + indicators | §1 entirely |
| **P2 Session 2** | Strategies schema + framework skeleton | §2 + §3 (no real strategy yet) |
| **P2 Session 3** | Reference RSI strategy + backtest harness | §4 + §5 |
| **P2 Session 4** | REST + WS + paper deploy lifecycle | §6 + connect §3's engine to live paper run |
| **P2 Session 5** | Frontend Strategies pages | §7 |
| **P2 Session 6** | Tests + smoke + runbooks + exit gate | §8 + §9 + §10 |

Six sessions, roughly mirroring P1's seven (P1 had an extra session for the trade-update consumer because trading is inherently messier than strategies).

---

## 12. Deferred to later phases (so we don't lose them)

- **Pine strategy type (webhook from TradingView).** Enum value reserved; webhook receiver + Pine signal parser → **P4**.
- **Agent Strategy type (B3).** Enum value reserved; agent_strategy_configs table + invocation engine → **P6**.
- **Live deployment of strategies.** Per-strategy live-mode toggle, separate audit, daily cost cap (Implementation Plan v0.2 §13.3 $2/day) → **P5 + P6**.
- **Multi-strategy resource contention.** P2 assumes few concurrent strategies; rate-limit / fair-share across strategies → **P4**.
- **Strategy parameter optimization** (grid / walk-forward) → not in MVP scope at all.
- **Order types beyond market + stop in backtest** (limit / stop-limit / bracket simulation) → land per-strategy as needed.
- **WS-driven bar dispatch** (replace 30s polling with Alpaca market-data WS subscription) → **P4** alongside Opportunities page work.
- **Hot-reload of strategy files** without restart → **P4**; for MVP, restart on changes.
- **Visual strategy backtest charting** beyond a recharts equity curve → **P4**.

---

## 13. Notes for Claude Code execution

Same pattern as P0 and P1:

1. **One section at a time per PR.** §1 is its own PR. §2 + §3 land together (schema + framework couple too tightly to separate). §4 + §5 land together (the reference strategy is the first consumer of the backtester). §6 is its own PR. §7 is its own PR. §8 + §9 + §10 are the closer PR.
2. **Acceptance-first.** Each session doc will define explicit acceptance per group; verify before merging the PR.
3. **ADR 0002 still rules.** `StrategyContext.submit_order` is the strategy-side equivalent of an order ticket; it dispatches through `OrderRouter.submit`. No exception.
4. **Don't sprawl.** If a session starts feeling like "while I'm here let me also build Pine support" — stop. Pine is P4 work in this numbering scheme.
5. **Commit message convention (continuing from P0 / P1):**
   - `feat(market-data): bar cache + indicator computer`
   - `feat(db): strategies / strategy_runs / signals / backtest_results schema`
   - `feat(strategies): strategy framework + engine`
   - `feat(strategies): reference RSI mean-reversion + backtest harness`
   - `feat(api): strategies and signals endpoints + ws topics`
   - `feat(frontend): strategies list + detail + backtest views`
   - `test(p2): coverage gates, integration test, smoke, runbooks`

---

*End of P2 Checklist v0.1.*
