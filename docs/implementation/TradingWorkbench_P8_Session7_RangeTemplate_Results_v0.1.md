# P8 Session 7 — Range-Trading Template + Apply Flow — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§7 of 7 — **closes P8**) |
| Plan doc | `TradingWorkbench_P8_Session7_RangeTemplate_v0_1.md` |
| Predecessor | `p8-session6-range-insight-panel-complete` (§6) |
| Tag | **`p8-session7-range-template-complete`** (moved onto the §7 todo commit) |
| Shipped as | PR **#80** — branch `feat/p8-session7-range-template`; squash-merged `a86fac2` |
| Verdict | **GO. P8 COMPLETE.** A trader can adopt a Range-Insight-tuned range-trading strategy in one click. Full backend suite + coverage + all 10 invariants + ADR-0002 green; frontend vitest + tsc + eslint; no migration. |

## What shipped

- **`apps/backend/strategies_user/templates/range_trader.py`** — `RangeTrader(Strategy)`, a regular deterministic strategy (Direction Decision 3): **fade-the-range mean reversion** — BUY when `price ≤ entry_price` (near support), SELL when `price ≥ exit_price` (near resistance), hard stop when `price ≤ stop_price`, plus a no-entry window after the open, a force-exit window before the close, a per-ET-day trade cap, and risk-based sizing (per-share risk = `entry − stop`). The price levels are **parameters** (default 0 = inert). `params_schema` ⇄ `default_params` parity holds. Orders route through `self.ctx.submit_order` only (ADR 0002 intact).
- **`POST /api/v1/range-template/apply`** (`app/api/v1/range_template.py`) — `{symbol, name?}` → compute Range Insight (when `app.state.bar_cache` exists) → `_range_trader_params`: status `ok` → `entry_price = low_band.high`, `exit_price = high_band.low`, `stop_price = max(0, support − 1.5×ATR)`, `prefilled=true`; else the static defaults, `prefilled=false` → register an **IDLE** Strategy row (`code_path="templates/range_trader.py"`, `params_json=…`, `symbols=[symbol]`, `authoring_method="template"`) → audit `STRATEGY_REGISTERED`. Auth-gated, user-scoped; returns `{id, name, status, code_path, authoring_method, symbol, prefilled_from_range_insight}`.
- **ADR-0002 invariant test** `ALLOWED` += `strategies_user/templates/range_trader.py` (the `self.ctx.submit_order` literal — the sanctioned context path, same as the rsi example). `check_strategy_isolation` scans only `app/strategies/`, so the template is out of its scope.
- **Frontend** — `src/api/strategyTemplates.ts` (`applyRange(symbol, name?)`); the §6 `RangeInsightPanel` gains an **"Apply range template"** button (footer, above the disclaimer) → `applyRange(symbol)` → `navigate('/strategies/{id}')`, with a busy + error state.

## Decisions settled (owner, 2026-06-08 — AskUserQuestion)

1. **Template logic: fade-the-range mean reversion** (buy support / sell resistance — the natural fit for the range-bound symbols Discovery + Range Insight surface).
2. **Prefill: from Range Insight when `ok`, else static defaults** (never blocks; zero levels → inert until edited; `prefilled_from_range_insight` flags which).
3. **Instantiation: one committed template file + per-row params** (each "Apply" is a Strategy row referencing the shared `code_path` with its own `params_json` + `authoring_method="template"`; edits go through the standard param form).
4. **Time-of-day (Direction Q5):** conservative defaults — `no_trade_open_minutes=5`, `hard_exit_before_close_minutes=5`, `max_trades_per_day=4`.

## Verification

- **Template** (8 tests): schema⇄params parity; entry buys at support; exit sells at resistance; stop sells below stop; no entry in the open window; force-exit in the close window; inert when levels unset; the daily trade cap.
- **Endpoint** (3 tests): apply with Range Insight prefills `entry 98 / exit 103 / stop 90.5` + `authoring_method=template` + IDLE + `symbols=[AAPL]`; apply without a bar cache → static defaults (`entry_price 0`) + `prefilled=false`; a `STRATEGY_REGISTERED` audit row.
- **Frontend** (1 new): "Apply range template" → `applyRange("AAPL")` → `navigate('/strategies/42')`.
- Backend full suite **exit 0** (2 known AAPL skips); ruff + mypy **(204)** clean; **ADR-0002 invariant test** passes (template ALLOWED entry); **all 10 shell invariants** + **3 coverage gates** (risk 0.904/P2/P3) green. **No migration / no new audit action.** Frontend vitest + tsc + eslint clean.
- A transient environment hiccup ran the verification jobs concurrently (Windows fork-retry / a vitest `ERR_IPC_CHANNEL_CLOSED` worker crash under load) — re-running each suite **alone** was clean; not a code failure.

## Notes / carry-forward

- **One file, many strategies** — N applied range strategies share the single template `code_path`; each row's `params_json` is its own. The param form derives from the shared class `params_schema` at GET-detail time.
- **Inert until configured** — applying with insufficient Range Insight creates a real IDLE strategy with zero levels that trades nothing until the trader sets them; `prefilled_from_range_insight=false` makes that explicit.
- **The template ships as a starting point, not advice** — like the rsi example, it's a reasonable default the trader is expected to review/backtest before going live (the standard backtest → paper → 24h-cooldown activation applies).
- Live confirmation (the template trading real bars; Range-Insight-derived levels against real prices) is **Norton-deferred**.

## P8 is complete

| § | Capability |
|---|---|
| §1 | Alpaca discovery feeds + caching (seed source) |
| §2 | Scanner engine — criteria evaluation |
| §3 | Discovery view UI |
| §4 | Scheduled scanning + Opportunities integration (**closes P8a**) |
| §5 | Range Insight computation |
| §6 | Range Insight panel UI |
| §7 | Range-trading template + Apply flow (**closes P8b / P8**) |

The full arc: a trader screens for range-bound symbols (Discovery), reads a symbol's recent behavior (Range Insight), and adopts a Range-Insight-tuned range-trading strategy in one click — into the standard backtest → paper → activation lifecycle.

## Deferred / next

- **Direction Q4** — a "scan + apply template" combined flow (optional post-§7 addition).
- The standing **live cross-session verification** on a non-Norton + credentialed stack: P6 (`§1b.12 → p6-session1-complete`, §2-variant smoke, the live LLM opt-in run), the §4 scan cron reaching `data.alpaca.markets` at 7:30 ET, Range Insight + the range template against real daily bars.
- Phases beyond P8 (P9+) per the master plan, when the developer directs.
