# P6b Session 2b-variant — Comparison Metrics + MCP + Auto-Spawn/Invalidation Hooks

| Field | Value |
|---|---|
| Document version | **v0.1** (drafted against `TradingWorkbench_P6b_Session2a_variant_Results_v0.1.md` + the 10-question architecture-decision turn) |
| Date | 2026-06-03 |
| Phase | **P6b — Direction v0.2 deferred capabilities**, **§2b-variant** (data + integration half of P6b Session 2; §2c-variant adds the UI surfaces) |
| Predecessor | `TradingWorkbench_P6b_Session2a_variant_Results_v0.1.md` (tag `p6b-session2a-variant-complete` pending PR + walk-away) |
| Successor | `TradingWorkbench_P6b_Session2c_variant_v0.1.md` (drafted only after §2b-variant ships per Retrospective Rec #10) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **Equity-curve reconstruction service** at `app/services/equity_curve.py` (per Q1 settled (a)) — pure primitive `reconstruct_equity_curve(session, strategy_id, start, end, capital_base) → list[(datetime, Decimal)]`. Daily marks on NYSE business days (per Q2 lean); end-of-day equity = capital_base + realized_pnl + unrealized_pnl_at_close; reusable by drift (when it eventually lifts §1a's live-Sharpe deferral), variant comparison, §3 gate. **Variant-vs-live comparison service** — new `compare_variant_to_parent(session, variant_strategy_id) → VariantComparison` returning the Q4-settled dataclass: `live_metrics: BacktestMetrics, variant_metrics: BacktestMetrics, deltas, window_start, window_end, live_trade_count, variant_trade_count`. Match-windowed `[variant.created_at, now]` for both sides (per Q8 settled). **API endpoint** `GET /api/v1/strategies/{parent_id}/variant-comparison` returning serialized `VariantComparison` or `{"status": "no_active_variant"}`. **MCP tool** `workbench_paper_variant_metrics(strategy_id)` — read-only passthrough; keys by parent `strategy_id` per Q5 settled; build-server count 18 → 19. **D5 auto-spawn envelope flag** `agent_envelope_json.auto_validate_proposals: bool` (default `false`); hook fires on `PROPOSAL_TRANSITIONED to=ACCEPTED` when flag enabled + parent is LIVE + no in-flight variant. **D8 invalidation hooks (two trigger points, per Q7 settled (c))**: (i) on parent status transition out of `ACTIVE_STRATEGY_STATUSES` → terminate with `reason="parent_deactivated"`; (ii) on `apply_proposal` for parent → terminate with `reason="parent_proposal_applied"`. Both use existing `PaperVariantService.terminate(variant_id, reason=...)` from §2a. **No new audit action** (per Q10 — spawn/terminate use existing P6b actions). **No frontend** (§2c). **No new lifecycle states** (§3 owns EVALUATING+ states). Single PR. |
| Estimated wall time | 7-8h |
| Stopping point | `git tag p6b-session2b-variant-complete` |
| Tests added | ~22 backend (equity-curve + comparison + endpoint + MCP + hooks) |
| Out of scope | Variant UI surfaces — card on strategy detail, variants overview, comparison visualization (all §2c-variant). EVALUATING → EVIDENCE_READY → PROMOTING → PROMOTED lifecycle states (§3). The 4-criterion promotion gate (≥30d OR ≥50 trades, ≥5% Sharpe margin, positive absolute return, no worst-case divergence beyond 20% of live max-dd) — §3. Crypto / non-equity asset annualization (v1 assumes equities; equities-only per Q3 lean). Drift detection lifting its live-Sharpe deferral via the new equity-curve service (P6+ — drift can adopt the primitive when warranted by first-quarter data). Per-strategy capital_base override (uses backtest's initial_equity or $100k default; per-user override is P6+). Backfill of equity curves for historical variants (computes on-demand per request; cache is P6+ optimization). Stratified variant-vs-live comparison (per-symbol, per-time-bucket) — strategy-level only for v1. |

---

## ⚠ Review corrections (2026-06-03) — verified against the shipped §2a / §1a-drift code

This v0.1 was drafted before grepping the shipped modules; the code sketches below carry real drift that would crash or silently break on paste. The following corrections are verified against `p6b-session2a-variant-complete` and **supersede the sketches** wherever they conflict. (Some are applied inline below; the rest are authoritative here.)

1. **NO `compute_metrics` / `BacktestMetrics` in `app/strategies/metrics.py`.** §1a-drift shipped "extract functions, keep the dataclass" — `metrics.py` exposes ONLY `win_rate(pnls)`, `avg_return_per_trade(returns)`, `sharpe_ratio(equity_curve)`, `max_drawdown(equity_curve)`. `BacktestMetrics` lives in `app/strategies/backtest_models.py` (the full backtester field set — it has **no `avg_return_per_trade`**). → §2b.2 must NOT import/call `compute_metrics`/`BacktestMetrics` from metrics; build a §2b-local `VariantSideMetrics` dataclass computed by calling the four functions directly. (Corrected inline in §2b.2.)
2. **`app/services/market_data.py` does NOT exist** — no `get_close_price_for_symbol_on_date`. Historical bars come from **`BarCache.get_bars(ticker: str, timeframe: str, start, end)`** (`app/market_data/bar_cache.py`), injected like the morning-brief job. `BarCache` is in `app.state.bar_cache` (alpaca-block only; None in tests/data-only boots). The equity-curve service takes `bar_cache` as a dependency and reads per-day closes via `get_bars(ticker, "1Day", day, day)` → last bar's close. **`symbol` is a TICKER string** (`Order.symbol_id → Symbol.ticker`), not `symbol_id`. (Corrected in §2b.1.)
3. **NORTON BLOCKER on the close fetches.** `BarCache.get_bars` hits `data.alpaca.markets`, which Norton SSL-inspects and blocks locally — so the real-close path is **not exercisable in the dev env** (like every prior live-data step). Tests **mock** the bar fetch; the live equity-curve run is a deferred (non-Norton) gate. Bake into posture + deferred gates.
4. **`BacktestResult` has NO `config_json`** — only `params_json` / `metrics_json` / `equity_curve_json` / `trades_json` / `range_start`/`range_end` / `created_at` / `label`. `initial_equity` ("100000") is on `BacktestJob.config_json`; the result's `metrics_json.starting_equity` (float) carries the same value. → `_read_capital_base` reads `baseline.metrics_json.get("starting_equity")`, not `config_json.initial_equity`.
5. **`DEFAULT_CAPITAL_BASE_FALLBACK` does not exist in `drift_detection`.** Drop that import; use the local `DEFAULT_CAPITAL_BASE = Decimal("100000")`.
6. **`PaperVariantService.terminate` is `terminate(*, variant_strategy_id, reason, user_id)`** (keyword-only; requires `user_id`). The doc's `terminate(variant_id=…, reason=…)` is wrong on the param name AND the missing `user_id`. Also §2a already ships **`terminate_for_parent(*, parent_strategy_id, reason, user_id)`** + a private `_in_flight_variant_for(parent_strategy_id)` — the D8 hooks should call `terminate_for_parent` (no need for a new `find_in_flight_variant`; reuse/​promote `_in_flight_variant_for`).
7. **`spawn` raises plain `ValueError("variant_already_in_flight")`**, not a custom `ConcurrentVariantSpawnError`. The D5 best-effort hook catches `ValueError`.
8. **Engine handle is `app.state.strategy_engine`** (not `app.state.strategy_engine`); `PaperVariantService(session, engine)` with engine positional (defaults None).
9. **There is NO `PATCH /strategies/{id}/status`.** Status leaves LIVE via `POST /strategies/{id}/stop` (`stop_strategy` → IDLE) and the P5 §7 activation **deactivate** path (`ActivationService.deactivate`, LIVE/HALTED → IDLE). The D8 hook-(i) goes in **those** paths; the smoke's `PATCH /status` step changes to `POST /strategies/{id}/stop`.
10. **Envelope flag name: `auto_validate_proposals`** (the name §2a established in its D5), not `auto_validate_proposals`. Reconciled throughout this doc.
11. **MCP tool**: module-level `async def workbench_paper_variant_metrics(strategy_id: int)` — **POSITIONAL** (the `test_tools.py` calls are positional, e.g. `workbench_proposal_eval_summary(42, ...)`), added to the **`_TOOLS` list literal** (not `_TOOLS.append`). Count assertion 18 → 19.
12. **`reconstruct_round_trips(session, strategy_id, cutoff)` ✓ and `find_baseline_for_strategy(session, strategy)` ✓ are used correctly; `RoundTrip.pnl`/`.ret` ✓.** (No change.)
13. **Re-split note**: the §2a Results said §2b = metrics + MCP + **UI**; this doc moves UI to a new "§2c-variant." Reasonable given size, but the §2a "§2b adds the UI" is thereby superseded — call it out (or fold the small variant card into §2b).

---

## How this differs from the §2a-variant Results

Three §2a-variant execution-time deviations carried forward + one architectural lift:

- **§2a deferred D5 + D8 to §2b** (per §2a deviation #1 — "the explicit apply/deactivation invalidation hook (D8) and the auto-spawn-on-ACCEPT envelope flag (D5) are deferred to §2b"). §2b owns both. D5 hooks into the proposal-transition path; D8 hooks into two paths (status mutation + apply).
- **One audit row per transaction** (§2a deviation #3, originally §1a-drift contract). D5's auto-spawn calls `PaperVariantService.spawn(...)` which itself writes `PAPER_VARIANT_SPAWNED + STRATEGY_PROPOSAL_TRANSITIONED` in separate commits. D8's invalidation calls `PaperVariantService.terminate(...)` which writes `PAPER_VARIANT_TERMINATED + STRATEGY_PROPOSAL_TRANSITIONED` in separate commits. §2b's hook code calls these services; the multi-commit semantics are already correct in §2a's implementation.
- **`ENGINE_RUNNABLE_STATUSES` widening** (§2a deviation #2 — the engine `unregister` reset now covers `PAPER_VARIANT` too). Not directly relevant to §2b, but documenting traceability.

Plus the **architectural lift**: §1a-drift deliberately deferred live Sharpe / max-drawdown because it required equity-curve reconstruction. §2b's equity-curve service IS that reconstruction. After §2b ships, drift detection could lift the deferral by feeding the reconstructed equity curve into `sharpe_ratio(...)` / `max_drawdown(...)` (the §1a-drift metrics functions; CORRECTION #1) — but that's P6+ polish, not §2b scope. §2b builds the primitive; downstream consumers (variant comparison now, drift later, §3 gate next) use it.

Plus all standing P6+P6b deviations: `func.json_extract(...)` Core for JSON queries; `AuditLogger.write` sync staticmethod, single-commit caller; `AuditLog.target_id` STRING (per §1b-drift correction); `AuditLog.payload_json` STRING needing `json.loads`; MCP server pattern `_TOOLS: list[Callable]` + module-level `async def _get(...)` (per §1b-drift correction); endpoints on `proposals.py::strategies_router` per §1b coverage-gate lesson; `Strategy.status` lowercase StrEnum per §1a-drift correction; `ACTIVE_STRATEGY_STATUSES` frozenset import from `app.db.enums`; FIFO round-trip reconstruction from `app.services.drift_detection.reconstruct_round_trips` (reusable).

---

## ⚠ Posture

**§2b-variant is the data + integration half of P6b §2.** Two principles:

1. **Equity-curve reconstruction is the methodologically heavy work.** It's the same class as §1a-drift's round-trip reconstruction — non-trivial, multiple edge cases, market-data dependency. The capital_base choice for Sharpe comparison is load-bearing: **both sides must use the same capital_base** or the comparison is meaningless (Sharpe shifts with capital_base because daily returns are `dE/E`, not `dE`). The variant comparison service enforces this; the equity-curve primitive accepts capital_base as a required parameter.

2. **Auto-spawn (D5) and invalidation (D8) are integration hooks, not new logic.** Both call existing §2a `PaperVariantService` methods (`spawn` / `terminate`). §2b's work is wiring these calls into the right service sites: the proposal-transition path for D5, the status-mutation path + apply path for D8. The methods themselves are unchanged; the §2a "one row per transaction" audit contract is preserved.

Paper smoke from P1-P5 byte-identical. ADR-0002 `_router_token` discipline unaffected. `check_agent_no_db_access.sh` unaffected (§2b adds nothing to `apps/agent/`).

---

## Verification checklist — grep before pasting any code below

Per Retrospective Rec #5.

- [x] **`PaperVariantService` signatures** at `app/services/paper_variant.py` (VERIFIED against shipped §2a): `PaperVariantService(session, engine=None)`; `spawn(*, proposal_id, user_id)`; `terminate(*, variant_strategy_id, reason, user_id)`; `terminate_for_parent(*, parent_strategy_id, reason, user_id)` (no-op if none). All keyword-only. `spawn` raises plain `ValueError` on guard violations (CORRECTIONS #6/#7).
- [ ] **`StrategyStatus.PAPER_VARIANT`** enum value at `app/db/enums.py` per §2a — confirm. And `ACTIVE_STRATEGY_STATUSES` / `ENGINE_RUNNABLE_STATUSES` frozensets — confirm membership.
- [ ] **`PROPOSAL_TRANSITIONED to=ACCEPTED` service site** — likely in `app/api/v1/proposals.py` per §1b shipped, or in a transitions service. Find the post-transition hook insertion point. D5's auto-spawn check fires after the audit row writes + commits.
- [ ] **`apply_proposal` service location** — per §2a Results, requires parent status=IDLE; mutates `parent.params_json`; commits. D8 hook fires BEFORE the apply commits (terminate variants first, then apply, recoverable if apply fails).
- [x] **Strategy status mutation path** (VERIFIED — CORRECTION #9): there is NO `PATCH /strategies/{id}/status`. LIVE → IDLE happens via `POST /strategies/{id}/stop` (`stop_strategy`) and `ActivationService.deactivate` (P5 §7). D8 hook goes in both, firing on transition out of `ACTIVE_STRATEGY_STATUSES`. (`PUT /strategies/{id}` only edits params when status=IDLE — not a deactivation path.)
- [x] **Market-data path** (VERIFIED — CORRECTION #2): closes come from `BarCache.get_bars(ticker, "1Day", start, end)` (`app/market_data/bar_cache.py`), available as `app.state.bar_cache`. There is NO `app/services/market_data.py`. CORRECTION #3: BarCache hits `data.alpaca.markets` → Norton-blocked locally; tests mock the fetch and the live run is a deferred (non-Norton) gate.
- [x] **Capital-base source** (VERIFIED — CORRECTION #4): `BacktestResult` has NO `config_json` (that's on `BacktestJob`). Read the capital base from `BacktestResult.metrics_json["starting_equity"]` (float; falls back to `DEFAULT_CAPITAL_BASE = $100k`).
- [ ] **`Fill` model** at `app/db/models/fill.py` per §1a-drift correction: `qty`, `price`, `commission`, `filled_at`, `order_id`. Confirm exact field names.
- [ ] **`Order.source_type == OrderSourceType.STRATEGY`, `Order.source_id == str(strategy_id)`** — per §1a-drift correction; the variant's orders are scoped via its own strategy_id (the variant IS a Strategy row per §2a Model (a) choice).
- [ ] **`Symbol` model** — fetched via join from Order (`Order.symbol_id` FK). The equity-curve service needs symbol identifiers for market-data lookups.
- [ ] **NYSE calendar source** — `pandas_market_calendars`, `exchange_calendars`, or a hardcoded NYSE holiday list. v1 lean: install `pandas_market_calendars` (lightweight; widely used); fallback to a curated holiday list if Norton blocks the install.
- [ ] **MCP server `_TOOLS: list[Callable]` + module-level `async def _get(path, params=None)`** (per §1b-drift correction). New tool follows this pattern. Build-server test currently asserts 18 (per §1b-drift shipped); update to 19.

---

## Candid acknowledgment — what this session plan cannot predict

- **Capital_base choice and Sharpe sensitivity.** Sharpe uses daily returns `r(t) = (E(t) - E(t-1)) / E(t-1)`. With `E(t) = C + cum_pnl(t)`, the choice of C shifts the daily return denominator and thus Sharpe. For comparison purposes (variant vs live), both sides MUST use the same C — Sharpe is consistent. The variant comparison service reads C from the baseline backtest's `metrics_json.starting_equity` (CORRECTION #4 — `BacktestResult` has no `config_json`; or `DEFAULT_CAPITAL_BASE = $100k` if no baseline). This is the established convention; document.
- **Open positions at window start.** A variant spawned today inherits no open positions (it starts fresh). The parent may have open positions at `[variant.created_at, now]`'s start. Should those be marked at start, or ignored? **v1 lean: equity curve starts at capital_base for both sides on window-start day.** Positions that opened *before* `start` and close *after* `start` count their EXIT-side pnl at exit time (closed round-trip semantics from §1a-drift). Open positions throughout the window contribute unrealized pnl at each business-day mark. Document explicitly.
- **Strategy isolation in fill query.** §1a-drift's `reconstruct_round_trips` joins Fill → Order → Symbol filtered by `Order.source_type == STRATEGY` and `Order.source_id == str(strategy_id)`. §2b's equity-curve service uses the same query shape. The variant's strategy_id is distinct from the parent's (variant is its own Strategy row per §2a), so each query naturally isolates.
- **Market data missing for some days.** Alpaca's bars endpoint may have gaps (halted symbols, early/late market hours, splits/dividends adjustments). v1 lean: skip days where ANY open position's close is unavailable (drop that day from the equity curve). Document; if gaps become common, escalate to forward-fill.
- **Close-price caching within a single computation.** For a 30-day equity curve with 5 open positions, that's 30×5=150 close-price lookups. Each is one Alpaca API call. v1 lean: in-memory cache `{(symbol_id, date): close_price}` within `reconstruct_equity_curve` (LRU dict; max ~1000 entries). No persistent cache; refresh per-invocation. Profile and optimize if slow.
- **`pandas_market_calendars` vs hardcoded.** The package needs a network-accessible install (PyPI). If Norton blocks `uv add`, fall back to a hardcoded NYSE holiday list (~10 dates/year × known years). v1 lean: try `pandas_market_calendars`; if Norton blocks, ship hardcoded; document.
- **Variant termination ordering relative to apply (D8).** Terminate variant BEFORE apply commits. If apply fails after terminate succeeds: variant gone, parent unchanged — recoverable (user re-triggers apply, optionally re-spawns variant). If apply succeeds then terminate fails: variant runs on stale assumptions silently — worse. So terminate-then-apply is the safe order; document in Notes.
- **D5 envelope flag site.** The hook insertion point is the post-PROPOSAL_TRANSITIONED-to-ACCEPTED handler. If the transition happens via PATCH /api/v1/proposals/{id} (per §1b shipped), the hook lives in that endpoint. If transitions go through a service module, hook lives there. Verify at code-paste time.
- **D5 thread-safety.** If two ACCEPTs land concurrently for the same strategy, both could pass the "no in-flight variant" check before either spawns. PaperVariantService.spawn's concurrency guard (per §2a) handles this — the second spawn raises. Hook code should catch the exception and log (don't bubble up; auto-spawn is best-effort).
- **D8 in transit.** Between D8 terminate (commit 1) and apply (commit 2): brief window (~ms) where variant is gone but parent still has old params. Acceptable — this only affects subsequent variant-comparison reads in that window, which would return `no_active_variant` correctly.
- **The metrics primitives already exist** (CORRECTION #1 — per §1a-drift shipped, `app/strategies/metrics.py` exposes the FUNCTIONS `win_rate`, `avg_return_per_trade`, `sharpe_ratio(equity_curve)`, `max_drawdown(equity_curve)` — there is NO `compute_metrics` and NO `BacktestMetrics`). §2b builds the equity curve and calls `sharpe_ratio`/`max_drawdown` on it directly (see the `_side` helper in §2b.2). No changes to the metrics module.
- **Comparison for window < 2 business days** returns degenerate Sharpe (0.0 per `_sharpe`'s documented behavior). VariantComparison includes window dates; consumer (§3 gate) should check window length before trusting Sharpe deltas. Document.

---

## Goal

After §2b-variant ships:

- A user with an in-flight paper variant can call `GET /api/v1/strategies/{parent_id}/variant-comparison` and receive a `VariantComparison` with both sides' `VariantSideMetrics` (trade_count, win_rate, avg_return_per_trade, sharpe_ratio, max_drawdown) + deltas for the match-windowed period.
- The proposal agent, when proposing changes to a strategy with an in-flight variant, can fetch the same comparison via the `workbench_paper_variant_metrics(parent_id)` MCP tool (positional arg) — evidence for proposal grounding.
- A user with `agent_envelope_json.auto_validate_proposals=true` automatically spawns a paper variant when accepting a proposal on a LIVE parent (no manual `POST /validate` needed).
- A user deactivating a parent strategy (LIVE → IDLE) automatically terminates any in-flight variant (`reason="parent_deactivated"`). Same on `apply_proposal` (`reason="parent_proposal_applied"`).
- §3 gate has the metrics primitive it needs: live Sharpe + max-drawdown via the new equity-curve reconstruction service.
- All §2a mechanics unchanged — no service-module breaks; no migration; no new audit action; no new lifecycle states.
- Build-server tool count 18 → 19.
- All 13 CI invariants + 3 coverage gates green.
- Paper smoke from P1-P5 byte-identical.

---

## §2b-variant.1 — Equity-curve reconstruction service

Create `apps/backend/app/services/equity_curve.py`.

```python
"""Equity-curve reconstruction from fill history.

Per P6b §2b-variant settled decisions:
- Daily marks on NYSE business days (Q2 lean).
- E(t) = capital_base + realized_pnl_to_t + unrealized_pnl_at_close_t.
- capital_base passed by caller for apples-to-apples Sharpe comparison.
- Skip days where any open position's close is unavailable.

Used by: variant comparison (P6b §2b), drift detection live-Sharpe (P6+ when
adopted), §3 promotion gate.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderSide, OrderSourceType
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol

# CORRECTION #2: there is NO app/services/market_data.py. Daily closes come from
# the injected BarCache (app/market_data/bar_cache.py):
#     bars = await bar_cache.get_bars(ticker, "1Day", day, day)  # ticker, not symbol_id
#     close = float(bars["c"].iloc[-1])  # last bar's close (see morning_brief usage)
# CORRECTION #3: BarCache hits data.alpaca.markets, which Norton SSL-blocks
# locally → this path is NOT exercisable in dev; tests MOCK the close fetch and
# the live equity-curve run is a deferred (non-Norton) gate.


async def _close_on_day(bar_cache: Any, ticker: str, day: date) -> Decimal | None:
    """EOD close for a ticker on a date via BarCache. None if unavailable
    (missing data / Norton). bar_cache is None in tests/data-only boots."""
    if bar_cache is None:
        return None
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
    bars = await bar_cache.get_bars(ticker, "1Day", start, end)
    if bars is None or getattr(bars, "empty", True):
        return None
    return Decimal(str(bars["c"].iloc[-1]))


logger = structlog.get_logger(__name__)


DEFAULT_CAPITAL_BASE = Decimal("100000")
ZERO = Decimal("0")


def _get_nyse_business_days(start: date, end: date) -> list[date]:
    """Return list of NYSE business days in [start, end] inclusive.

    Uses pandas_market_calendars if available; falls back to weekday +
    hardcoded NYSE holiday list (per Candid Acknowledgment Norton fallback).
    """
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=start, end_date=end)
        return [d.date() for d in schedule.index.to_pydatetime()]
    except ImportError:
        # Norton fallback: weekday filter + hardcoded major holidays.
        return _fallback_nyse_business_days(start, end)


def _fallback_nyse_business_days(start: date, end: date) -> list[date]:
    """Hardcoded fallback: weekdays minus major US holidays (curated)."""
    NYSE_HOLIDAYS_2025_2027 = {
        date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17),
        date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19),
        date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27),
        date(2025, 12, 25),
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
        date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
        date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
        date(2026, 12, 25),
        # ... extend annually
    }
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in NYSE_HOLIDAYS_2025_2027:
            days.append(d)
        d += timedelta(days=1)
    return days


async def reconstruct_equity_curve(
    session: AsyncSession,
    strategy_id: int,
    start: datetime,
    end: datetime,
    capital_base: Decimal = DEFAULT_CAPITAL_BASE,
    *,
    bar_cache: Any = None,   # CORRECTION #2: app.state.bar_cache; None → closes unavailable
) -> list[tuple[datetime, Decimal]]:
    """Return list of (eod_timestamp, equity) for each NYSE business day in
    [start.date(), end.date()].

    Equity = capital_base + cumulative realized P&L + unrealized P&L from
    open positions marked at end-of-day close.

    Per Q2/Q3 leans: NYSE business days only; equities-only v1.
    Per Candid Ack: skip days where any open position's close is unavailable.
    """
    business_days = _get_nyse_business_days(start.date(), end.date())
    if not business_days:
        return []

    # One-shot fetch: all fills for this strategy in window, ordered by fill time.
    fills = list((await session.execute(
        select(Fill, Order, Symbol)
        .join(Order, Fill.order_id == Order.id)
        .join(Symbol, Order.symbol_id == Symbol.id)
        .where(Order.source_type == OrderSourceType.STRATEGY)
        .where(Order.source_id == str(strategy_id))
        .where(Fill.filled_at <= end)
        .order_by(Fill.filled_at.asc())
    )).all())

    # Per-symbol position state, walked cumulatively.
    # symbol_id → {"qty": Decimal (signed), "avg_cost": Decimal}
    positions: dict[int, dict[str, Decimal]] = {}
    # symbol_id → ticker (BarCache is keyed by ticker, not symbol_id — CORRECTION #2).
    tickers: dict[int, str] = {}
    realized_pnl = ZERO

    # Close-price cache for this computation (per Candid Ack).
    close_cache: dict[tuple[int, date], Decimal | None] = {}

    equity_curve: list[tuple[datetime, Decimal]] = []
    fill_idx = 0
    n_fills = len(fills)

    for day in business_days:
        eod = datetime.combine(day, datetime.max.time(), tzinfo=UTC)

        # Walk fills up to eod.
        while fill_idx < n_fills:
            fill, order, symbol = fills[fill_idx]
            if fill.filled_at > eod:
                break
            qty_signed = fill.qty if order.side == OrderSide.BUY else -fill.qty

            pos = positions.setdefault(symbol.id, {"qty": ZERO, "avg_cost": ZERO})
            tickers[symbol.id] = symbol.ticker
            existing_qty = pos["qty"]

            scaling_in = (
                (existing_qty >= 0 and qty_signed > 0)
                or (existing_qty <= 0 and qty_signed < 0)
                or existing_qty == 0
            )

            if scaling_in:
                # New avg cost = weighted average of existing + new at fill price.
                total_cost = existing_qty * pos["avg_cost"] + qty_signed * fill.price
                new_qty = existing_qty + qty_signed
                pos["qty"] = new_qty
                pos["avg_cost"] = total_cost / new_qty if new_qty != ZERO else ZERO
            else:
                # Reducing position; realize pnl for the closing portion.
                close_qty = min(abs(qty_signed), abs(existing_qty))
                direction_sign = Decimal("1") if existing_qty > 0 else Decimal("-1")
                pnl_per_share = (fill.price - pos["avg_cost"]) * direction_sign
                realized_pnl += pnl_per_share * close_qty - fill.commission
                pos["qty"] = existing_qty + qty_signed
                # Avg cost unchanged when reducing; reset to 0 if flat.
                if pos["qty"] == ZERO:
                    pos["avg_cost"] = ZERO

            fill_idx += 1

        # Mark open positions at eod close.
        unrealized_pnl = ZERO
        missing_close = False
        for symbol_id, pos in positions.items():
            if pos["qty"] == ZERO:
                continue
            cache_key = (symbol_id, day)
            if cache_key not in close_cache:
                close_cache[cache_key] = await _close_on_day(
                    bar_cache, tickers[symbol_id], day,
                )
            close_price = close_cache[cache_key]
            if close_price is None:
                missing_close = True
                break
            unrealized_pnl += pos["qty"] * (close_price - pos["avg_cost"])

        if missing_close:
            logger.debug(
                "equity_curve_skipping_day_missing_close",
                strategy_id=strategy_id, day=day.isoformat(),
            )
            continue

        equity = capital_base + realized_pnl + unrealized_pnl
        equity_curve.append((eod, equity))

    return equity_curve
```

**Verify before pasting:**
- `Fill` / `Order` / `Symbol` joined-load shape — confirm SQLAlchemy syntax for the three-way join.
- `Symbol.ticker` — confirm the attribute name carrying the BarCache lookup key (CORRECTION #2).
- `BarCache.get_bars(ticker, "1Day", start, end)` return shape — confirm it's a DataFrame with a `"c"` close column (mirror `morning_brief`'s usage); adjust `_close_on_day` if the shape differs. Norton blocks the live call → tests mock it (CORRECTION #3).
- `OrderSourceType.STRATEGY` enum value (lowercase string per §1a-drift correction).
- The FIFO semantics for reducing positions when scaling-down isn't exactly the same as round-trip FIFO; this uses avg-cost basis. Verify this matches the backtester's convention (most do avg-cost; some do FIFO/LIFO). If backtester uses FIFO, mirror that.

---

## §2b-variant.2 — Variant comparison service

Add to `app/services/paper_variant.py` (alongside the existing §2a `PaperVariantService`), or extract into `app/services/paper_variant_comparison.py` if file becomes large.

```python
"""Variant-vs-live comparison.

Per Q4 settled: VariantComparison dataclass with both sides' VariantSideMetrics
(CORRECTION #1 — local dataclass, NOT the nonexistent BacktestMetrics)
+ deltas + window dates + trade counts.
Per Q8 settled: match-windowed [variant.created_at, now].
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
# CORRECTION #5: no DEFAULT_CAPITAL_BASE_FALLBACK in drift_detection.
from app.services.drift_detection import (
    find_baseline_for_strategy,
    reconstruct_round_trips,
)
from app.services.equity_curve import (
    DEFAULT_CAPITAL_BASE, reconstruct_equity_curve,
)
# CORRECTION #1: metrics.py has FUNCTIONS, not compute_metrics/BacktestMetrics.
from app.strategies.metrics import (
    avg_return_per_trade,
    max_drawdown,
    sharpe_ratio,
    win_rate,
)


@dataclass(frozen=True)
class VariantSideMetrics:
    """One side's metrics — built from the shared metrics functions (CORRECTION
    #1: there is no `compute_metrics`/`BacktestMetrics` to return)."""
    trade_count: int
    win_rate: float
    avg_return_per_trade: float
    sharpe_ratio: float       # from the reconstructed equity curve
    max_drawdown: float       # from the reconstructed equity curve


@dataclass(frozen=True)
class VariantComparison:
    """Variant-vs-live comparison metrics. Per Q4 settled shape."""
    parent_strategy_id: int
    variant_strategy_id: int
    window_start: datetime
    window_end: datetime
    live_metrics: VariantSideMetrics
    variant_metrics: VariantSideMetrics
    deltas: dict[str, float | None]
    live_trade_count: int
    variant_trade_count: int


def _pct_delta(variant: float | None, live: float | None) -> float | None:
    """Relative percentage delta. None if either input is None or denominator zero."""
    if variant is None or live is None:
        return None
    if live == 0:
        return None
    return ((variant - live) / abs(live)) * 100


async def find_in_flight_variant(
    session: AsyncSession,
    parent_strategy_id: int,
) -> Strategy | None:
    """Return the in-flight PAPER_VARIANT for the parent strategy, or None.

    Per §2a concurrency guard: at most one in-flight variant per parent.
    """
    return (await session.execute(
        select(Strategy)
        .where(Strategy.parent_strategy_id == parent_strategy_id)
        .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
    )).scalar_one_or_none()


def _read_capital_base(baseline_metrics_json: dict[str, Any] | None) -> Decimal:
    """Capital base for Sharpe normalization. CORRECTION #4: BacktestResult has
    NO config_json — read `metrics_json.starting_equity` (== the backtest's
    initial_equity, stored as a float by the backtester); $100k default."""
    if not baseline_metrics_json:
        return DEFAULT_CAPITAL_BASE
    raw = baseline_metrics_json.get("starting_equity")
    if raw is None:
        return DEFAULT_CAPITAL_BASE
    return Decimal(str(raw))


async def compare_variant_to_parent(
    session: AsyncSession,
    variant_strategy_id: int,
    bar_cache: Any = None,   # CORRECTION #2: BarCache for the equity-curve closes
) -> VariantComparison | None:
    """Compute apples-to-apples variant-vs-parent metrics.

    Both sides use SAME capital_base (load-bearing for Sharpe comparability).
    Both windows are [variant.created_at, now] (Q8 settled). `bar_cache` is
    `app.state.bar_cache` (None in tests → equity curves degenerate / mocked).
    """
    variant = await session.get(Strategy, variant_strategy_id)
    if variant is None or variant.parent_strategy_id is None:
        return None

    parent_id = variant.parent_strategy_id
    parent = await session.get(Strategy, parent_id)
    if parent is None:
        return None

    start = variant.created_at
    end = datetime.now(UTC)

    # Capital base from parent's baseline backtest (metrics_json.starting_equity).
    baseline = await find_baseline_for_strategy(session, parent)
    capital_base = _read_capital_base(baseline.metrics_json if baseline else None)

    # Reconstruct equity curves with SHARED capital_base (CORRECTION #2: the
    # equity-curve service needs a BarCache — pass app.state.bar_cache through;
    # see §2b.1). Norton blocks real closes locally → tests mock the fetch.
    parent_curve = await reconstruct_equity_curve(
        session, parent_id, start, end, capital_base, bar_cache=bar_cache,
    )
    variant_curve = await reconstruct_equity_curve(
        session, variant_strategy_id, start, end, capital_base, bar_cache=bar_cache,
    )

    # Reconstruct round-trips for trade-based metrics (reuses §1a-drift:
    # reconstruct_round_trips(session, strategy_id, cutoff) → list[RoundTrip]).
    parent_trips = await reconstruct_round_trips(session, parent_id, start)
    variant_trips = await reconstruct_round_trips(session, variant_strategy_id, start)

    # CORRECTION #1: compute each side from the shared metrics FUNCTIONS.
    def _side(trips, curve) -> VariantSideMetrics:
        ec = [(t, float(e)) for t, e in curve]
        return VariantSideMetrics(
            trade_count=len(trips),
            win_rate=win_rate([t.pnl for t in trips]),
            avg_return_per_trade=avg_return_per_trade([t.ret for t in trips]),
            sharpe_ratio=sharpe_ratio(ec),
            max_drawdown=max_drawdown(ec),
        )

    parent_metrics = _side(parent_trips, parent_curve)
    variant_metrics = _side(variant_trips, variant_curve)

    deltas = {
        "sharpe_delta_pct": _pct_delta(
            variant_metrics.sharpe_ratio, parent_metrics.sharpe_ratio,
        ),
        "max_drawdown_delta_pct": _pct_delta(
            variant_metrics.max_drawdown, parent_metrics.max_drawdown,
        ),
        "win_rate_delta_pp": (
            (variant_metrics.win_rate - parent_metrics.win_rate) * 100
            if (variant_metrics.win_rate is not None and parent_metrics.win_rate is not None)
            else None
        ),
        "avg_return_delta_pct": _pct_delta(
            variant_metrics.avg_return_per_trade,
            parent_metrics.avg_return_per_trade,
        ),
    }

    return VariantComparison(
        parent_strategy_id=parent_id,
        variant_strategy_id=variant_strategy_id,
        window_start=start,
        window_end=end,
        live_metrics=parent_metrics,
        variant_metrics=variant_metrics,
        deltas=deltas,
        live_trade_count=len(parent_trips),
        variant_trade_count=len(variant_trips),
    )
```

**Verify before pasting:**
- Metrics functions (VERIFIED — CORRECTION #1): `win_rate(pnls)`, `avg_return_per_trade(returns)`, `sharpe_ratio(equity_curve)`, `max_drawdown(equity_curve)` in `app/strategies/metrics.py`. `RoundTrip` exposes `.pnl` and `.ret` (§1a-drift). The `_side` helper assembles a `VariantSideMetrics` from these — there is no `compute_metrics`.
- `find_baseline_for_strategy` exact signature (VERIFIED — `(session, strategy) → BacktestResult | None`).
- `reconstruct_round_trips` exact signature — per §1a-drift: `(session, strategy_id, cutoff) → list[RoundTrip]`. The `cutoff` here is the variant spawn time.

---

## §2b-variant.3 — API endpoint

Add to `apps/backend/app/api/v1/proposals.py::strategies_router` (per §1b coverage-gate lesson).

```python
"""GET /api/v1/strategies/{strategy_id}/variant-comparison

Returns variant comparison for the in-flight variant of `strategy_id` (parent).
Read-only; no detection run; no audit write.
"""
from app.services.paper_variant import (
    compare_variant_to_parent, find_in_flight_variant,
)


def _comparison_to_response(comp) -> dict:
    """Serialize VariantComparison to JSON-safe dict."""
    return {
        "parent_strategy_id": comp.parent_strategy_id,
        "variant_strategy_id": comp.variant_strategy_id,
        "window_start": comp.window_start.isoformat(),
        "window_end": comp.window_end.isoformat(),
        "live_metrics": _metrics_to_dict(comp.live_metrics),
        "variant_metrics": _metrics_to_dict(comp.variant_metrics),
        "deltas": comp.deltas,
        "live_trade_count": comp.live_trade_count,
        "variant_trade_count": comp.variant_trade_count,
    }


def _metrics_to_dict(m) -> dict:
    return {
        "trade_count": m.trade_count,
        "win_rate": m.win_rate,
        "avg_return_per_trade": m.avg_return_per_trade,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
    }


@strategies_router.get(
    "/{strategy_id}/variant-comparison",
    response_model=dict,
)
async def get_variant_comparison(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Variant-vs-live comparison for the in-flight variant of `strategy_id`."""
    parent = await session.get(Strategy, strategy_id)
    if parent is None or parent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    variant = await find_in_flight_variant(session, strategy_id)
    if variant is None:
        return {
            "status": "no_active_variant",
            "strategy_id": strategy_id,
        }

    # CORRECTION #2: bar_cache lives in app.state only when the alpaca block is
    # configured — getattr-guard it (None → equity curves degenerate gracefully).
    bar_cache = getattr(request.app.state, "bar_cache", None)
    comparison = await compare_variant_to_parent(session, variant.id, bar_cache=bar_cache)
    if comparison is None:
        # Edge: variant exists but compare returned None (race condition?).
        return {
            "status": "no_active_variant",
            "strategy_id": strategy_id,
        }

    return {
        "status": "variant_active",
        "strategy_id": strategy_id,
        "variant_strategy_id": variant.id,
        "comparison": _comparison_to_response(comparison),
    }
```

**Verify before pasting:**
- Add `Request` to the FastAPI import in `proposals.py` (`from fastapi import ..., Request`) — the handler now takes `request: Request` to reach `app.state.bar_cache` (CORRECTION #2).
- `strategies_router` is the router §1b added to `proposals.py`; confirm the prefix yields `/api/v1/strategies/{id}/variant-comparison`.

---

## §2b-variant.4 — MCP tool `workbench_paper_variant_metrics`

Add to `apps/mcp-workbench/src/mcp_workbench/server.py` (per §1b-drift correction: `_TOOLS: list[Callable]` + module-level `async def _get(path, params=None)`).

```python
"""mcp-workbench tool — read-only passthrough for variant comparison.

Keys by parent strategy_id (Q5 settled). Single in-flight variant per parent
per §2a concurrency guard.
"""

async def workbench_paper_variant_metrics(strategy_id: int) -> dict[str, Any]:
    # CORRECTION #11: POSITIONAL signature (test_tools.py calls tools positionally),
    # added to the `_TOOLS` list literal.
    """Return variant-vs-live comparison for the in-flight variant of
    `strategy_id` (the parent).

    Args:
        strategy_id: Parent strategy ID. The in-flight variant (if any) is
                     identified via parent_strategy_id FK.

    Returns:
        {
          'status': 'variant_active' | 'no_active_variant',
          'strategy_id': int,
          'variant_strategy_id': int,            # only if variant_active
          'comparison': {                         # only if variant_active
            'parent_strategy_id': int,
            'variant_strategy_id': int,
            'window_start': ISO timestamp,
            'window_end': ISO timestamp,
            'live_metrics': {trade_count, win_rate, avg_return_per_trade, sharpe_ratio, max_drawdown},
            'variant_metrics': {...same shape...},
            'deltas': {sharpe_delta_pct, max_drawdown_delta_pct, win_rate_delta_pp, avg_return_delta_pct},
            'live_trade_count': int,
            'variant_trade_count': int,
          },
        }
    """
    return await _get(f"/api/v1/strategies/{strategy_id}/variant-comparison")


# CORRECTION #11: `_TOOLS` is a LIST LITERAL in server.py — add the function to
# it directly (there is no `_TOOLS.append`):
#     _TOOLS = [ ... existing 18 ..., workbench_paper_variant_metrics ]
```

**Verify before pasting:**
- Build-server test (`apps/mcp-workbench/tests/test_tools.py`) asserts tool count 18 (per §1b-drift shipped) — update to 19. Tool-call tests pass args POSITIONALLY (e.g. `workbench_paper_variant_metrics(42)`), so the signature is `async def workbench_paper_variant_metrics(strategy_id: int)`.
- `apps/mcp-workbench/CLAUDE.md` — add decision-tree row for the new tool per §1b-drift pattern.

---

## §2b-variant.5 — D5 auto-spawn envelope flag hook

The hook fires after `PROPOSAL_TRANSITIONED to=ACCEPTED` writes commit. Per the verification checklist, the exact site depends on where the transition happens — likely in `apps/backend/app/api/v1/proposals.py`'s PATCH endpoint or a transitions service.

```python
"""Hook into PROPOSAL_TRANSITIONED to=ACCEPTED path.

Per Q6 lean: agent_envelope_json.auto_validate_proposals: bool (default false).
When enabled + parent is LIVE + no in-flight variant → spawn.

Per Candid Acknowledgment: best-effort; catches and logs concurrency-guard
exceptions (don't fail the proposal-transition because auto-spawn raced).
"""
# In apps/backend/app/api/v1/proposals.py PATCH endpoint, after the
# transition + audit + commit completes:

async def _maybe_auto_validate_proposals(
    session: AsyncSession,
    proposal: StrategyProposal,
    current_user: CurrentUser,
    engine,   # WorkbenchEngine | None per §2a pattern
) -> None:
    """D5: auto-spawn paper variant on ACCEPT if envelope flag enabled."""
    profile = await TradingProfileService(session).get(current_user.id)
    envelope = profile.agent_envelope or {}
    if not envelope.get("auto_validate_proposals", False):
        return

    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None or parent.status != StrategyStatus.LIVE:
        return

    # CORRECTION #7: spawn() itself enforces the guards (parent_not_live,
    # variant_already_in_flight, proposal_not_accepted) and raises plain
    # ValueError — so no pre-check lookup is needed here (the §2b.2
    # `find_in_flight_variant` helper exists but is for the comparison read).
    # Best-effort: just attempt the spawn and swallow ValueError on the race.
    try:
        await PaperVariantService(session, engine).spawn(
            proposal_id=proposal.id,
            user_id=current_user.id,
        )
    except ValueError as exc:   # variant_already_in_flight / parent_not_live / ...
        logger.info(
            "auto_validate_proposals_skipped",
            strategy_id=parent.id, proposal_id=proposal.id, reason=str(exc),
        )
    except Exception as exc:
        logger.warning(
            "auto_validate_proposals_failed",
            strategy_id=parent.id, proposal_id=proposal.id, error=str(exc),
        )


# In the PATCH /api/v1/proposals/{id} endpoint, after the existing
# transition logic when target_state == ACCEPTED:
if to_state == ProposalState.ACCEPTED:
    await _maybe_auto_validate_proposals(
        session, proposal, current_user, engine=request.app.state.strategy_engine,
    )
```

**Verify before pasting:**
- `app.state.strategy_engine` is the standard access pattern for the engine from FastAPI requests (per §2a). If `engine` lives somewhere else, adjust.
- `spawn` raises plain `ValueError` (`variant_already_in_flight` / `parent_not_live` / `proposal_not_accepted` / `proposal_not_found` / `parent_not_found`) — there is no custom guard exception (CORRECTION #7).

---

## §2b-variant.6 — D8 invalidation hooks (two trigger points)

### Hook 1: parent status leaving ACTIVE_STRATEGY_STATUSES

CORRECTION #9: there is **no** `PATCH /strategies/{id}/status`. A LIVE parent
leaves ACTIVE via `POST /strategies/{id}/stop` (`stop_strategy` → IDLE) or the
P5 §7 `ActivationService.deactivate` (LIVE/HALTED → IDLE). The hook goes in
**both** those paths (whichever transition out of `ACTIVE_STRATEGY_STATUSES` the
user actually takes).

```python
"""D8 (a): on parent leaving ACTIVE_STRATEGY_STATUSES, terminate any in-flight
variant with reason="parent_deactivated"."""

# CORRECTION #6: terminate's signature is keyword-only
# (*, variant_strategy_id, reason, user_id). Prefer the shipped
# `terminate_for_parent(*, parent_strategy_id, reason, user_id)` — it finds the
# in-flight variant for the parent and is a no-op if none exists (so no separate
# find_in_flight_variant lookup is needed). It commits internally (§2a).

# In stop_strategy (POST /strategies/{id}/stop) and ActivationService.deactivate,
# after confirming the parent is leaving ACTIVE but BEFORE the status-change commit:

await PaperVariantService(session, engine).terminate_for_parent(
    parent_strategy_id=strategy.id,
    reason="parent_deactivated",
    user_id=current_user.id,
)

# Then commit the status change in its own transaction (per §2a one-row-per-txn).
await session.commit()
```

### Hook 2: apply_proposal for parent

In the `apply_proposal` service site:

```python
"""D8 (b): on apply_proposal, terminate any in-flight variant with
reason="parent_proposal_applied"."""

# Per Candid Acknowledgment: terminate-then-apply ordering.
# Per §2a Results: apply_proposal already requires status=IDLE, so this
# mostly hits manually-spawned variants on IDLE parents (rare but possible).

async def apply_proposal(
    session: AsyncSession,
    proposal: StrategyProposal,
    engine,
    user_id: int,
) -> Strategy:
    """Existing apply logic — extended with D8 invalidation hook."""
    parent = await session.get(Strategy, proposal.strategy_id)
    # ... existing IDLE-check, etc ...

    # D8: terminate any in-flight variant BEFORE applying (terminate_for_parent
    # is a no-op if none; commits internally — ordering: terminate then apply).
    await PaperVariantService(session, engine).terminate_for_parent(
        parent_strategy_id=parent.id,
        reason="parent_proposal_applied",
        user_id=user_id,
    )

    # ... existing apply logic (mutate params_json, write
    #     STRATEGY_PROPOSAL_TRANSITIONED to=APPLIED, commit) ...
```

**Verify before pasting:**
- The exact apply_proposal location (service module vs endpoint inline).
- Whether the status-mutation path has a clean pre-commit hook point or needs restructuring.

---

## §2b-variant.7 — Tests

### Equity-curve service (`apps/backend/tests/services/test_equity_curve.py`)

**Non-negotiable (load-bearing):**
- `test_equity_curve_capital_base_invariance_for_comparison` — two strategies with same trades but different scaled fills produce same equity-curve shape when capital_base is matched (verifies the comparison-comparability contract).

**Algorithm:**
- `test_equity_curve_empty_fills_returns_capital_base_each_day`
- `test_equity_curve_realized_pnl_only_no_open_positions`
- `test_equity_curve_unrealized_pnl_with_open_position`
- `test_equity_curve_mixed_realized_unrealized`
- `test_equity_curve_long_then_short_position_flip`
- `test_equity_curve_avg_cost_basis_correct_after_scale_in`
- `test_equity_curve_short_position_unrealized_pnl`
- `test_equity_curve_skips_day_when_close_missing`
- `test_equity_curve_business_days_only_excludes_weekends`
- `test_equity_curve_fallback_when_pandas_market_calendars_unavailable`
- `test_equity_curve_close_price_cached_per_invocation`

### Variant comparison (`apps/backend/tests/services/test_variant_comparison.py`)

**Non-negotiable:**
- `test_comparison_uses_same_capital_base_both_sides` — capital_base from baseline backtest applied uniformly.
- `test_comparison_match_windowed_to_variant_created_at` — both sides' windows are `[variant.created_at, now]`.

**Algorithm:**
- `test_compare_returns_none_if_not_a_variant` (no parent_strategy_id)
- `test_compare_returns_none_if_parent_not_found`
- `test_compare_uses_baseline_initial_equity_for_capital_base`
- `test_compare_falls_back_to_100k_when_no_baseline`
- `test_compare_deltas_computed_correctly`
- `test_compare_deltas_handle_zero_baseline_safely`
- `test_compare_includes_trade_counts_from_round_trips`

### Find in-flight variant (`apps/backend/tests/services/test_find_in_flight_variant.py`)

- `test_find_returns_paper_variant_for_parent`
- `test_find_returns_none_when_no_variant`
- `test_find_ignores_terminated_variants` (status != PAPER_VARIANT)

### API endpoint (`apps/backend/tests/api/test_variant_comparison_endpoint.py`)

- `test_endpoint_returns_no_active_variant_when_no_variant`
- `test_endpoint_returns_comparison_when_in_flight`
- `test_endpoint_other_user_404`
- `test_endpoint_serializes_metrics_correctly`

### MCP tool (`apps/mcp-workbench/tests/test_paper_variant_metrics_tool.py`)

- `test_workbench_paper_variant_metrics_passthrough`
- `test_build_server_tool_count_increased_to_19`

### D5 auto-spawn hook (`apps/backend/tests/api/test_auto_validate_proposals.py`)

- `test_auto_spawn_fires_when_envelope_flag_enabled_and_parent_live`
- `test_auto_spawn_skipped_when_flag_disabled`
- `test_auto_spawn_skipped_when_parent_idle`
- `test_auto_spawn_skipped_when_in_flight_variant_exists`
- `test_auto_spawn_logs_and_continues_on_concurrent_spawn_error`

### D8 invalidation hooks (`apps/backend/tests/services/test_variant_invalidation.py`)

- `test_invalidation_on_status_leaving_active_set` (LIVE → IDLE)
- `test_no_invalidation_on_status_staying_active` (LIVE → PAPER)
- `test_invalidation_on_apply_proposal`
- `test_invalidation_terminate_commits_before_apply_commits` (ordering)
- `test_invalidation_no_op_when_no_in_flight_variant`

**Verify test paths.** Established conventions per §1a-drift / §2a-variant.

---

## §2b-variant.8 — Manual smoke

```bash
# 0. Prerequisites
git describe --tags --abbrev=0   # expect: p6b-session2a-variant-complete

# 1. Bring up stack
docker compose up -d
sleep 30
./scripts/login_helper.sh

# 2. Need a LIVE strategy + an in-flight variant. From §2a smoke, spawn one:
STRAT_ID=$(curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies" \
  | jq -r '.items[] | select(.status=="live") | .id' | head -1)
# Find an ACCEPTED proposal for that strategy:
PROP_ID=$(curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/proposals?strategy_id=${STRAT_ID}&state=ACCEPTED" \
  | jq -r '.items[0].id')
# Spawn manually (§2a validate endpoint):
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/validate" | jq

# 3. Get variant comparison (variant just spawned, so trade counts likely 0)
curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" | jq

# 4. Test no-variant case (a strategy without a variant)
OTHER_ID=$(curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies" \
  | jq -r '.items[] | select(.status=="idle") | .id' | head -1)
curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/strategies/${OTHER_ID}/variant-comparison" | jq
# Expect: {"status": "no_active_variant", "strategy_id": ...}

# 5. MCP tool
docker compose exec mcp-workbench uv run python -c "
import asyncio
from mcp_workbench.server import workbench_paper_variant_metrics
print(asyncio.run(workbench_paper_variant_metrics(strategy_id=${STRAT_ID})))
"

# 6. Build-server tool count
docker compose exec mcp-workbench uv run python -c "
from mcp_workbench.server import _TOOLS
print(f'Tool count: {len(_TOOLS)}')
"
# Expect: Tool count: 19

# 7. D5 auto-spawn: enable envelope flag for current user
curl -s -b /tmp/cookies.txt -X PUT \
  http://127.0.0.1:8000/api/v1/users/me/trading-profile \
  -H "Content-Type: application/json" \
  -d '{"agent_envelope": {"auto_validate_proposals": true}}'

# Generate + accept a new proposal on a LIVE strategy (no existing variant):
# (use propose endpoint per §1b shipped)
NEW_PROP=$(curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/propose" -d '{}' \
  -H "Content-Type: application/json" | jq -r '.id')
# Accept it:
curl -s -b /tmp/cookies.txt -X PATCH \
  "http://127.0.0.1:8000/api/v1/proposals/${NEW_PROP}" \
  -H "Content-Type: application/json" \
  -d '{"target_state": "ACCEPTED"}'

# Verify auto-spawn fired:
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT action, target_id, ts FROM audit_log
WHERE action='PAPER_VARIANT_SPAWNED'
ORDER BY id DESC LIMIT 1;"
# Expect: a new spawn audit row with recent ts

# 8. D8 invalidation: deactivate the parent (LIVE → IDLE).
# CORRECTION #9: no PATCH /status — stop the strategy via POST /{id}/stop.
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/stop"

# Verify variant was terminated:
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT action, target_id, json_extract(payload_json, '\$.reason') AS reason
FROM audit_log
WHERE action='PAPER_VARIANT_TERMINATED'
ORDER BY id DESC LIMIT 1;"
# Expect: reason='parent_deactivated'

# 9. LOAD-BEARING: paper smoke byte-identical
PAPER_ACC=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts \
  | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":${PAPER_ACC},\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"qty\":\"1\",\"tif\":\"day\",\"source\":\"manual\"}" \
  | jq '{status}'
# Expect: status=accepted
```

**Norton-deferred posture.** Steps 3-6 work without LLM. Step 7 requires LLM for proposal generation (skippable; can manually insert a DRAFT proposal via SQL).

---

## §2b-variant.9 — Notes & gotchas

1. **Capital_base equality across both sides is load-bearing.** Sharpe shifts with capital_base; if variant and parent use different bases, the comparison is meaningless. The variant comparison service reads one capital_base from the baseline backtest and passes the same value to both `reconstruct_equity_curve` calls. The non-negotiable test (`test_comparison_uses_same_capital_base_both_sides`) is the guard.

2. **NYSE business days only — pandas_market_calendars preferred, hardcoded fallback ships.** The dual-implementation pattern lets §2b ship even if Norton blocks `uv add pandas_market_calendars`. Fallback covers 2025-2027; document the annual extension.

3. **Equity-curve skips days with missing closes.** v1 doesn't forward-fill. If gaps become common in production, escalate to forward-fill or interpolation; for now, missing close → day dropped silently.

4. **Avg-cost basis (not FIFO) for position cost tracking in equity-curve.** §1a-drift's round-trip reconstruction uses FIFO matching; §2b's equity curve uses avg-cost for the unrealized-pnl computation. Different pieces of information — round-trips for win_rate/avg_return; positions for equity-curve. Both are correct in their context; verify the backtester uses avg-cost (most do) for consistency.

5. **Match-windowed `[variant.created_at, now]` for both sides.** Apples-to-apples. The parent's metrics in this window are the parent's own forward performance since variant spawn — NOT historical performance. This is the right comparison: "in the same period the variant has been running, how did each perform?"

6. **D5 auto-spawn is best-effort.** Concurrency-guard race losses are logged and swallowed. Don't fail the proposal-transition because auto-spawn didn't get the lock — user can manually spawn via `POST /validate` if needed.

7. **D8 ordering: terminate-then-apply.** If apply fails after terminate succeeds, variant is gone but parent unchanged — recoverable. The other order (apply-then-terminate) risks silent inconsistency if terminate fails.

8. **D8 hook (i) status-mutation:** terminate fires in the status-mutation endpoint's pre-commit phase; the terminate commit and the status-change commit are separate (one-row-per-txn). Verify hook ordering.

9. **D8 hook (ii) apply_proposal:** terminate fires inside the apply service before the params_json mutation. Same separate-commit pattern.

10. **No new audit action.** Comparison reads are silent. Spawn/terminate audits come from §2a's existing `PAPER_VARIANT_SPAWNED` / `PAPER_VARIANT_TERMINATED`. Total P6+P6b audit actions stays at 8.

11. **No new lifecycle states.** §2b doesn't touch the proposal lifecycle (`DRAFT → REVIEWING → ACCEPTED/REJECTED → APPLIED`). EVALUATING / EVIDENCE_READY / PROMOTING / PROMOTED are all §3.

12. **Build-server tool count 18 → 19.** Update the asserted-count test.

13. **MCP tool default has no lookback parameter.** Unlike `workbench_drift_findings` (lookback_days=30), variant comparison's window is determined by the variant's `created_at` — no user-tunable. The match-windowed semantics make a lookback param meaningless here.

14. **`_router_token` discipline preserved.** §2b adds nothing to order-routing code.

15. **`check_agent_no_db_access.sh` unaffected.** §2b adds nothing to `apps/agent/`.

16. **`check_workbench_mcp_readonly.sh` green.** New MCP tool is read-only GET passthrough.

17. **The §1b flaky test** has not resurfaced through 8 prior sessions (latest §1b-drift Results noted the related test_engine collection-order one — watch but not a §2b regression).

18. **Walk-away ≥1h before merge.** Per Retrospective Rec #6. The equity-curve algorithm is the riskiest part; fresh re-read catches edge cases.

19. **Standing cleanup-PR carry-forwards:** `check_p3_coverage.py --cov-report=xml` locally; explicit `git add` over `Docs/`.

---

## §2b-variant.10 — Commit and PR

Branch: `feat/p6b-session2b-variant`. Single PR; walk-away ≥1 hour before merge.

Tag: `git tag -a p6b-session2b-variant-complete -m "P6b §2b-variant comparison metrics + MCP + auto-spawn/invalidation hooks"`.

After §2b-variant ships: draft `TradingWorkbench_P6b_Session2c_variant_v0_1.md` against this Results doc. **Do not** draft §2c-variant speculatively before §2b-variant ships (Retrospective Rec #10).

---

## §2b-variant.11 — Verification Checklist (full session)

- [ ] §2b-v.1 `app/services/equity_curve.py` created; `reconstruct_equity_curve` returns business-day equity curve; capital_base parameter; close-price caching; NYSE business-days (pandas_market_calendars preferred, fallback ships); skip days with missing closes.
- [ ] §2b-v.2 `compare_variant_to_parent` (+ `VariantSideMetrics` dataclass, CORRECTION #1) in `paper_variant.py`; in-flight lookup reuses the service's `_in_flight_variant_for`; `VariantComparison` dataclass per Q4; match-windowed per Q8; capital_base shared per non-negotiable.
- [ ] §2b-v.3 GET `/strategies/{id}/variant-comparison` endpoint on `strategies_router`; ownership-validated; returns serialized comparison or `no_active_variant`.
- [ ] §2b-v.4 `workbench_paper_variant_metrics` MCP tool; build-server count 18 → 19; mcp-readonly invariant green; CLAUDE.md decision-tree row added.
- [ ] §2b-v.5 D5 auto-spawn hook fires on PROPOSAL_TRANSITIONED to=ACCEPTED when envelope `auto_validate_proposals=true` + parent LIVE + no in-flight variant; concurrency-guard exceptions logged not raised.
- [ ] §2b-v.6 D8 invalidation hook (i) on parent leaving ACTIVE_STRATEGY_STATUSES (in `stop_strategy` + `ActivationService.deactivate` — NOT a PATCH /status, CORRECTION #9) + hook (ii) on apply_proposal; both call `PaperVariantService.terminate_for_parent(parent_strategy_id=..., reason=..., user_id=...)` (CORRECTION #6); terminate-then-apply ordering.
- [ ] §2b-v.7 ~22 backend tests pass; full suite green; mypy/ruff clean; non-negotiable invariant tests (capital_base equality, match-windowed) green.
- [ ] §2b-v.8 Manual smoke: equity curve + variant comparison + MCP tool + D5 auto-spawn + D8 invalidation all exercised; paper smoke byte-identical.
- [ ] §2b-v.9 Notes & gotchas reviewed.
- [ ] `_router_token` discipline preserved; ADR-0002 invariant green.
- [ ] `audit_immutability` invariant green (no new enum / no payload schema changes).
- [ ] `check_agent_no_db_access.sh` unaffected.
- [ ] `check_workbench_mcp_readonly.sh` green.
- [ ] All 13 CI invariants + 3 coverage gates green; P3 gate verified locally with `--cov-report=xml`.
- [ ] §2b-v.10 PR merged; `p6b-session2b-variant-complete` tag pushed.

---

# Results template stub — fill at execution time

```markdown
# P6b Session 2b-variant — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | [YYYY-MM-DD] |
| Phase | P6b §2b-variant — Comparison Metrics + MCP + Auto-Spawn/Invalidation Hooks (companion to `TradingWorkbench_P6b_Session2b_variant_v0_1.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#[NN]** — branch `feat/p6b-session2b-variant`; tag **`p6b-session2b-variant-complete`** |
| Built against | `main` at `p6b-session2a-variant-complete` (`[SHA]`) |
| Verdict | **GO / NO-GO.** [Summary; P6b §2b-variant shipped; §2c-variant UI to follow.] |
| Method | Executed: backend pytest suite + new modules; mypy; ruff; all CI invariants. |

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 2b-v.1 | Equity-curve service: business-day marks + avg-cost basis + close-price cache + NYSE calendar | [✅ / details] |
| 2b-v.2 | Variant comparison service: match-windowed + shared capital_base + delta computation | [✅ / details] |
| 2b-v.3 | GET `/variant-comparison` endpoint: ownership + serialization | [✅ / details] |
| 2b-v.4 | `workbench_paper_variant_metrics` MCP tool; count 18 → 19 | [✅ / details] |
| 2b-v.5 | D5 auto-spawn hook on PROPOSAL_TRANSITIONED to=ACCEPTED | [✅ / details] |
| 2b-v.6 | D8 invalidation hooks (status + apply) | [✅ / details] |
| 2b-v.7 | ~22 backend tests pass; both non-negotiable invariant tests green | [✅ / details] |
| 2b-v.8 | Manual smoke; paper smoke byte-identical | [✅ / details] |
| — | `_router_token` discipline preserved | [✅] |
| — | `audit_immutability` invariant green (no schema changes) | [✅] |
| — | All 13 CI invariants + 3 coverage gates green | [✅] |

## Deliberate deviations (as-built vs the v0.1 plan)

Pre-named candidates (from v0.1's Candid Acknowledgment):

- **[Capital_base choice]** — [confirmed baseline initial_equity / required different source.]
- **[Open positions at window start]** — [v1 lean held / required entry-side accounting.]
- **[Market data missing handling]** — [skip-day worked / required forward-fill.]
- **[Close-price caching scope]** — [per-invocation acceptable / required persistent cache.]
- **[pandas_market_calendars install]** — [installed / Norton blocked, fallback shipped.]
- **[Variant termination ordering]** — [terminate-then-apply held / required different order.]
- **[D5 envelope flag site]** — [confirmed location / required different hook point.]
- **[Avg-cost vs FIFO for equity-curve positions]** — [avg-cost matched backtester / required FIFO.]

Other deviations:

- **[Deviation N].** [What changed and why.]

## Findings / punch list

- [ ] [Anything specific.]
- [ ] [Flaky test status.]

## Deferred gates — require a live stack

- [ ] **Variant accumulating real fills + comparison surfacing live metrics** end-to-end.
- [ ] **D5 auto-spawn firing on a real ACCEPT** with envelope flag enabled.
- [ ] **D8 invalidation observed on real status mutation / apply.**
- [ ] **Post-merge CI run green** — pending PR.

## To close §2b-variant cleanly

1. Walk away ≥1 hour before opening PR.
2. Confirm post-merge CI green; tag `p6b-session2b-variant-complete`.
3. **Next: §2c-variant** — variant UI (strategy-detail card + variants overview) — draft against this Results doc.

---

*P6b Session 2b-variant results v0.1 — recorded [DATE].*
```

---

*End of P6b Session 2b-variant v0.1. Drafted against §2a-variant Results' 4 execution-time deviations + the 10-question architecture-decision turn's settled answers (Q1 new module, Q4 VariantComparison dataclass, Q5 parent strategy_id MCP key, Q7 both invalidation triggers, Q8 match-windowed) + Jay's data-source call (Alpaca) + 5 carrying leans (NYSE business days, equities-only v1, auto_validate_proposals envelope flag, no-gating in comparison, no new audit action). Ships the equity-curve reconstruction primitive (~150 lines algorithm), variant comparison service, GET endpoint on `strategies_router`, `workbench_paper_variant_metrics` MCP tool (count 18 → 19), D5 auto-spawn hook on proposal-accept path, D8 invalidation hooks on status-mutation + apply paths. No new audit action, no new migration, no new lifecycle states. §2c-variant adds the UI surfaces on top of this foundation; §3 (promotion gate) consumes the comparison primitive for the 4-criterion gate.*
