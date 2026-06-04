# P6b Session 2b-variant — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — Direction v0.2 deferred capabilities, §2b-variant |
| Plan doc | `TradingWorkbench_P6b_Session2b_variant_v0_1.md` (with the 2026-06-03 review-corrections section) |
| Predecessor | `p6b-session2a-variant-complete` |
| Successor | `TradingWorkbench_P6b_Session2c_variant_v0.1.md` (UI surfaces — draft against THIS doc) |
| Tag on completion | `p6b-session2b-variant-complete` |
| Outcome | Shipped: equity-curve primitive, variant-vs-live comparison, read endpoint, MCP tool (count 18→19), D5 auto-spawn + D8 invalidation hooks. Full backend suite green; ruff/mypy clean; no-LLM / mcp-readonly / agent-no-db / audit-immutability invariants green. |

---

## What shipped

- **`app/services/equity_curve.py`** (new) — `reconstruct_equity_curve(session, strategy_id, start, end, capital_base, *, bar_cache=None) → list[(datetime, Decimal)]`. Daily EOD marks on NYSE business days; `E(t) = capital_base + realized_pnl + unrealized_pnl_at_close`. Closes via the injected `BarCache.get_bars(ticker, "1Day", …)` (`_close_on_day`); days with a missing close are skipped. `DEFAULT_CAPITAL_BASE = $100k`. NYSE calendar via `pandas_market_calendars` when present, else a curated weekday/holiday fallback (the package is not a dep — fallback is the live path; matches the Norton posture).
- **`app/services/paper_variant.py`** (+comparison) — `VariantSideMetrics` + `VariantComparison` dataclasses; `find_in_flight_variant(session, parent_id)` (module-level promotion of the §2a private lookup); `_read_capital_base`, `_pct_delta`; `compare_variant_to_parent(session, variant_id, bar_cache=None)`. Both sides share one `capital_base` and the window `[variant.created_at, now]`. Metrics come from the §1a-drift functions (`win_rate`, `avg_return_per_trade`, `sharpe_ratio`, `max_drawdown`) — no `compute_metrics`/`BacktestMetrics`.
- **`GET /api/v1/strategies/{id}/variant-comparison`** (proposals.py `strategies_router`) — read-only; `{"status":"no_active_variant"}` or `{"status":"variant_active", "comparison": {…}}`. Pulls `bar_cache` from `app.state` (getattr-guarded).
- **MCP `workbench_paper_variant_metrics(strategy_id)`** — positional, added to the `_TOOLS` list literal; build-server count 18 → 19; CLAUDE.md decision-tree row + header count updated.
- **D5 auto-spawn** — `_maybe_auto_validate_proposal` fires on PATCH `…/proposals/{id}` → ACCEPTED when `agent_envelope_json.auto_validate_proposals` is set and the parent is LIVE. Best-effort: `spawn` self-guards (plain `ValueError`), which is swallowed so the ACCEPT never fails.
- **D8 invalidation** — terminate the in-flight variant when a parent leaves `ACTIVE_STRATEGY_STATUSES` (`stop_strategy` + `deactivate_strategy` endpoints) and on `apply_proposal`. All call `PaperVariantService.terminate_for_parent(...)` (no-op if none; commits internally).
- **Tests** — 35 new (equity-curve algorithm, comparison, find-in-flight, endpoint, D5 auto-spawn, D8 invalidation, MCP passthrough/count).

## Deviations from the plan sketch

1. **D8 hook placement = endpoint layer, not `ActivationService.deactivate`.** `ActivationService` has no engine handle; the variant's running job must be `unregister`ed, so the hook lives in the `stop_strategy` and `deactivate_strategy` **endpoints** (where `app.state.strategy_engine` is available). Functionally identical to "in the deactivate path," but correct re: engine ownership.
2. **`find_in_flight_variant` is a new module-level helper** (the §2a service only had a private `_in_flight_variant_for`). The read endpoint and tests use it; the service still uses its own private method.
3. **Two SQLite tz coercions** (not in the sketch): SQLite returns `DateTime(tz=True)` columns naive. `equity_curve` coerces `fill.filled_at` (`_aware`) before comparing to aware EODs; `compare_variant_to_parent` coerces `variant.created_at` for the window. Without these, `TypeError: can't compare offset-naive and offset-aware datetimes`.
4. **Fill horizon = end-day EOD, not the `end` instant.** Each business day is marked at its EOD, so the fill query bounds on `end_inclusive = EOD(end.date())` rather than `<= end`. Otherwise a fill later on the end day is dropped though that day is still marked. Production passes `end=now` (no future fills), so this only matters for mid-day `end` callers/tests.
5. **D5 hook needed `request: Request`** added to `patch_proposal`; **D8-on-apply** needed `request: Request` added to `apply_proposal` (to reach the engine handle).

## Norton / deferred gates

- The live close path (`BarCache.get_bars` → `data.alpaca.markets`) is Norton-blocked locally and not exercised in dev. Tests mock the fetch; equity curves with open positions and a real broker are a deferred (non-Norton) gate.
- `pandas_market_calendars` is not installed (Norton-blocked install) → the curated-holiday fallback is the active calendar path. Swapping in the package later is a drop-in.

## Out of scope (→ §2c / §3)

Variant UI surfaces (card, overview, comparison viz) → §2c. EVALUATING→…→PROMOTED lifecycle + the 4-criterion promotion gate → §3. Drift lifting its live-Sharpe deferral via this primitive → P6+.
