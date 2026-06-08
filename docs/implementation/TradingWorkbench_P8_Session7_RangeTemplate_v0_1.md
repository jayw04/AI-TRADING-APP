# Trading Workbench — P8 §7: Range-Trading Template + Apply Flow (closes P8)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§7 of 7 — **closes P8**) |
| Predecessor | `p8-session6-range-insight-panel-complete` (§6) |
| Successor | — (P8 complete) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (Decision 3, 4; Q5; Q6 from P7) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | A committed range-trading strategy template + an "Apply range template to {symbol}" flow that creates an IDLE strategy referencing the template with params prefilled from the symbol's Range Insight, tagged `authoring_method="template"`. Picks up P7's reserved value (Direction Q6). |
| Estimated wall time | 4–6 hours |
| Tag on completion | `p8-session7-range-template-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

§7 closes P8 and connects the whole arc: the trader finds a range-bound symbol (Discovery), reads its behavior (Range Insight), and now **adopts a tradable strategy for it in one click** — the template prefilled with that symbol's statistics. It's a regular deterministic Strategy file (Direction Decision 3), saved IDLE into the standard backtest → paper → activation lifecycle (Decision 4). It picks up `authoring_method="template"`, the value P7 §8 reserved (Direction Q6).

## What this session ships

1. `apps/backend/strategies_user/templates/range_trader.py` — `RangeTrader(Strategy)`: fade-the-range mean reversion (buy near support / the 80% low band, exit near resistance / the 80% high band, ATR-based hard stop below support), with conservative time-of-day + trade-count gates. Levels are **parameters** (set from Range Insight at apply time; editable via the standard param form).
2. `app/api/v1/range_template.py` + `schemas` — `POST /api/v1/range-template/apply {symbol, name?}`: compute Range Insight, derive params (or static defaults), register an IDLE Strategy row (`code_path="templates/range_trader.py"`, `authoring_method="template"`, `symbols=[symbol]`), audit `STRATEGY_REGISTERED`.
3. `strategies_user/templates/range_trader.py` added to the ADR-0002 invariant test's ALLOWED set (`self.ctx.submit_order` literal).
4. Frontend — `src/api/strategyTemplates.ts` + an "Apply range template" button on the §6 `RangeInsightPanel` → navigates to the new strategy.
5. Tests: template loads + schema/params parity; the prefill mapping (ok → derived, insufficient → static); the endpoint (creates IDLE template strategy + audit; no-bar-cache → static defaults); a focused `on_bar` behavior test; frontend (apply button → api + navigate).

## Prerequisites

- §5 (`compute_range_insight`) + §6 (`RangeInsightPanel`). The Strategy framework (`app/strategies/base.py`, `StrategyLoader`, `_strategies_root()` = `strategies_user/`), `authoring_method` (`String(16)`, "template" needs no migration), the §8/§4 generic create pattern.

## Decisions settled for §7 (owner, 2026-06-08 — AskUserQuestion)

- **Template logic: fade-the-range mean reversion.** Buy near support / the 80% low band, exit near resistance / the 80% high band, ATR-based hard stop below support. The classic intraday range setup; the natural fit for the range-bound symbols Discovery + Range Insight surface.
- **Prefill: from Range Insight when `ok`, else static defaults.** `ok` → `entry_price = low_band.high`, `exit_price = high_band.low`, `stop_price = support − 1.5×ATR`. `insufficient_data` / no bar cache → the template's conservative static defaults (zero levels → the strategy is inert until the trader sets them); never blocks. The response flags `prefilled_from_range_insight`.
- **Instantiation: one template file + per-row params.** A single committed `range_trader.py`; each "Apply" creates a Strategy row referencing it with its own `params_json` + `authoring_method="template"`. The framework already supports shared `code_path` + distinct `params_json`; edits go through the standard param form; forking the `.py` stays the manual path.
- **Time-of-day (Direction Q5):** conservative defaults — `no_trade_open_minutes=5` (no entries in the first 5 min after 09:30 ET), `hard_exit_before_close_minutes=5` (force-exit any position in the last 5 min before 16:00 ET). Plus a `max_trades_per_day` cap (default 4).

## Detailed work

### §7.1 — `range_trader.py`

`RangeTrader(Strategy)` — `name="range-trader"`, `schedule="*/5 * * * *"`, `symbols=[]` (set per apply). `default_params` + a matching `params_schema` (typed form) for: `timeframe` (enum, default 5Min), `entry_price` / `exit_price` / `stop_price` (number, default 0 = unset), `risk_per_trade_pct` (0.01), `initial_equity_estimate` (100000), `max_position_qty` (100), `max_trades_per_day` (4), `no_trade_open_minutes` (5), `hard_exit_before_close_minutes` (5). Schema keys == default_params keys (no drift).

`on_bar`: convert `bar.t` to ET. (1) in the close-exit window → SELL if long, return. (2) long + `price ≤ stop_price` → SELL (stop). (3) long + `price ≥ exit_price` → SELL (range exit). (4) in the open no-trade window → return. (5) flat + `price ≤ entry_price` + under the daily trade cap → risk-sized BUY (per-share risk = `entry − stop`). Zero/unset levels make every branch a no-op (inert until configured). `_submit` mirrors `rsi_meanreversion._submit` (`OrderRequest` → `ctx.submit_order` → `ctx.log_signal`); ADR 0002 intact (orders via the context).

### §7.2 — `POST /api/v1/range-template/apply`

`{symbol, name?}` → `bar_cache = app.state.bar_cache` (may be None) → `insight = compute_range_insight(symbol, …)` when a cache exists → `params, prefilled = _range_trader_params(cls.default_params, insight)` → `StrategyLoader(_strategies_root()).load("templates/range_trader.py")` (400 if the template won't load) → `StrategyRow(status=IDLE, code_path, params_json=params, symbols_json=[symbol], schedule=cls.schedule, authoring_method="template", version=str(cls.version))` → audit `STRATEGY_REGISTERED` (payload `authoring_method="template"`, symbol, `prefilled`) → returns `{id, name, status, code_path, authoring_method, symbol, prefilled_from_range_insight}`. Auth-gated, user-scoped. Registered after `range_insight.router`.

### §7.3 — Frontend

`src/api/strategyTemplates.ts` — `strategyTemplatesApi.applyRange(symbol, name?)`. `RangeInsightPanel` gains an "Apply range template" button (footer, above the disclaimer) → `applyRange(symbol)` → `navigate('/strategies/{id}')`; a busy state + an error line. Reuses the symbol the panel already shows.

## Manual smoke

1. Charts → Range Insight panel for AAPL → "Apply range template" → lands on the new IDLE strategy `/strategies/{id}` with `authoring_method=template`, `symbols=[AAPL]`, params prefilled (entry/exit/stop from the panel's levels).
2. Open the strategy's Params tab → the typed form (from the template's `params_schema`) shows the prefilled levels; edit + save.
3. Backtest → paper → activation: the standard lifecycle (nothing auto-activates; Decision 4).

## Walk-away discipline

A new committed strategy + an apply endpoint, but it only *registers* an IDLE strategy (no live path) → **≥1 hour**.

## What this session does NOT do

- **No auto-activation** — saved IDLE (Decision 4); the trader runs backtest → paper → 24h-cooldown activation.
- **No "scan + apply" combined flow** (Direction Q4) — an optional post-§7 addition; §7 is per-symbol from the panel.
- **No live-updating levels** — `entry/exit/stop` are params set at apply time (from daily Range Insight), edited via the form; they don't recompute each bar (the "fork the .py" path is for custom logic).
- **No migration** — `authoring_method="template"` fits the existing `String(16)`; no schema change.
- **No new audit action** — reuses `STRATEGY_REGISTERED`; **no order-path / risk / new CI invariant change; no LLM.**

## Notes & gotchas

1. **The template calls `self.ctx.submit_order`** → add `strategies_user/templates/range_trader.py` to the ADR-0002 invariant test's `ALLOWED` set (the regex matches the literal; the *context* is the sanctioned router path, same as `rsi_meanreversion.py`). `check_strategy_isolation` scans only `app/strategies/`, so the template is out of its scope.
2. **Schema⇄params parity** — every `params_schema` key is in `default_params` and used by `on_bar` (the P4 §7 form invariant); a test asserts the key sets match.
3. **Zero levels = inert** — applying with insufficient Range Insight creates a real IDLE strategy whose levels are 0, so it trades nothing until the trader sets them; the response's `prefilled_from_range_insight=false` + the UI note make that explicit.
4. **One file, many strategies** — N applied strategies share `code_path="templates/range_trader.py"`; each row's `params_json` is its own. The param form derives from the shared class `params_schema` at GET-detail time.
5. **Per-share risk = entry − stop** — sizing falls back to a 2%-of-price stop distance when `stop_price` is unset, so sizing never divides by zero.
