# Runbook — Range Trader daily operations & monitoring

How the Range Trader sets its buy/sell/stop prices each day, how the system now
surfaces and monitors those prices and the day's activity, and how to spot and
fix a trigger problem before it costs a day.

Applies to the `range_trader` template (`apps/backend/strategies_user/templates/range_trader.py`).
Live on paper as user 2 (`range@local.dev`), RNG-001 — the rejected-benchmark
sleeve. Runs every 5 minutes during RTH (`*/5 * * * *`, gated to the regular
session). Reflects the 2026-07-02 changes (per-symbol level publishing +
`GET /api/v1/range-levels` + the Range Levels UI panel).

---

## 1. How the daily prices are set

**Levels are recomputed from scratch every ET trading day, independently per
symbol.** The default `level_mode` is `opening_range`.

1. **Day roll.** On the first bar of a new ET day for a symbol, its state resets
   (`_SymState.roll_day`): opening range, session VWAP, trade counters, the
   in-flight (`pending`) flag, and the stop-out flag all clear. DAY orders from
   the prior session have already expired at the close.
2. **Opening range builds (09:30–10:00 ET).** For the first
   `opening_range_minutes` (default **30**) of regular-session bars, the strategy
   accumulates the symbol's `or_low` (running min low) and `or_high` (running max
   high). **No levels and no entries while the range is still forming.**
3. **Levels freeze (~10:00 ET).** Once the window completes and `or_high > or_low`,
   the day's levels lock in and do not change again that day:
   | Level | Formula | Meaning |
   |---|---|---|
   | **Buy** (entry) | `or_low` | support / bottom of the opening range |
   | **Sell** (exit) | `or_high` | resistance / top of the opening range |
   | **Stop** | `or_low × (1 − stop_buffer_pct)` | just below support (default buffer **0.5%**) |
4. **Universe also resets daily.** The five symbols the strategy trades are chosen
   each morning by the range auto-select (Top-5), so both the *symbols* and their
   *levels* are a fresh, daily-adaptive snapshot.

Two non-default variations exist: `level_mode = "fixed"` uses static
`entry_price`/`exit_price`/`stop_price` params instead of the opening range; and
`entry_zone_pct` widens the buy from an exact touch of `or_low` to anywhere in the
lowest N% of the day's range. The defaults above are what's live.

> Why a purchase can sit **above** today's range: the levels are *today's*. A
> position opened yesterday carries **yesterday's** entry price (shown as "Avg
> entry" on the Positions page) — it is unrelated to today's buy/sell levels.

---

## 2. The daily lifecycle (what the strategy does each day)

| Time (ET) | What happens |
|---|---|
| Pre-open | Backend armed; strategy registered; `*/5` cron gated to RTH. |
| **09:30** | Day rolls; opening range starts building. Status: **Forming…** |
| 09:30–10:00 | Range forming — **no entries**. |
| **~10:00** | Levels freeze **and are published** (see §3). Entries now possible. |
| Intraday | **Buy** when flat and price ≤ buy (support). **Sell** when holding and price ≥ sell (resistance). **Hard stop** when price ≤ stop → the range is treated as *broken*: no further entries that day (`stopped_today`). |
| Near close | **Force-exit** any open position `hard_exit_before_close_minutes` (default **5**) before the close. The Range Trader is **intraday** — by design it never holds overnight. |
| Close | DAY orders expire; tomorrow the opening range rebuilds. |

---

## 3. How the system publishes & monitors the daily prices (2026-07-02)

**Range Levels panel** — Strategies page (shown only for range strategies).
A live table, refreshing every 15s:

| Symbol | Buy | Sell | Stop | Current | Position | Status |
|---|---|---|---|---|---|---|

- **Buy/Sell/Stop** are the strategy's **actual** frozen levels (not a
  re-derivation), so if they were ever wrong you'd see it here.
- **Current** is highlighted **green** when price has crossed *below buy while
  flat* (a buy should be imminent) and **amber** when *above sell*.
- **Status** chips: `Forming…` · `Levels set` · `In range` · `At buy` · `At sell`
  · `Below stop!` · `Holding`.

Under the hood:
- The strategy emits a `range_levels` INFO **signal** once per ET day per symbol
  the moment its levels are valid (`{kind, buy, sell, stop, at_price}`).
  Observability only — it never gates trading, and it reuses the `signals` table.
- `GET /api/v1/range-levels` reads the latest published levels per symbol for the
  user's range strategy and enriches them with the current price (bar cache) and
  the held position (local `positions`), returning the per-symbol status.

Other monitoring surfaces:
- **Signals** (`signals` table): `ENTRY`/`EXIT` on trades (with the `reason`, and
  a `rejected` field if the risk engine refused), `INFO` for `range_levels` and
  for `entry_skipped_invalid_levels`.
- **Opportunity funnel** (`record_opportunity`): `universe → qualified → touched →
  entered → stopped → exited` — where each symbol got to in the day.
- **Range recap email** (SNS `workbench-paper-alarms`): `deploy/aws/range-report.sh`
  at **10:15** and **16:15 ET** — top-5, equity, positions, fills.
- **Daily report email** (SNS): `deploy/aws/daily-report.sh` at **16:35 ET** —
  flags stuck orders, `ERROR`/`halted` strategies, blocked accounts, stale data.
- **healthz** + breaker state — global halt cleared, per-account breakers clear.

---

## 4. Identify & fix issues in time

Read the Range Levels panel first; then confirm with the signals/orders below.

| Symptom (panel) | Likely cause | Confirm | Fix |
|---|---|---|---|
| **Forming…** past ~10:05 ET | Opening range not building — no bars, or dispatch not firing | Backend logs for `strategy_dispatch_get_bar_failed` / no `on_bar`; check Alpaca bar flow for the symbol | Restart/reload the strategy; confirm the range book is armed and the market-session gate says REGULAR |
| **At buy** + flat, persists (price ≤ buy, no position) | A buy that should have fired didn't | Latest `signals` for the symbol: a `rejected` reason? `strategy_cooldown_set` (order pacing)? `stopped_today`? global halt? | Clear the specific blocker — reset a spuriously-tripped breaker, clear the halt, or wait out the 60s order cooldown |
| **Below stop!** + still holding | Stop should have flattened the position | Same checklist as "At buy" — a rejected exit or a halt blocked it | Reconcile/flatten; investigate why the exit was refused |
| Position held **overnight** (panel/positions show a leftover next morning) | The pre-close force-exit was blocked | Was there a halt or a stuck `SUBMITTED` order yesterday afternoon? | Cancel the stuck order + flatten. **Root cause fixed** by the per-account daily-loss halt (ADR 0034 / #315) — one account's loss no longer halts the range book |
| Levels look inverted (buy ≥ sell) | Invalid level ordering | `INFO` signal `entry_skipped_invalid_levels` for that symbol | Strategy goes inert for **entries** only (existing position still protected). Investigate the OR data |
| Panel empty / all "Forming…" after a deploy | Strategy hasn't run yet since restart, or it's not a range strategy | It publishes levels only after it next dispatches post-open | Expected right after a deploy — populates during the next opening range |

Quick diagnostics (run in the backend container):

```python
# latest range_levels + recent signals for the range strategy (id=1)
SELECT s.received_at, sy.ticker, s.type, s.payload_json
FROM signals s JOIN symbols sy ON sy.id = s.symbol_id
WHERE s.strategy_id = 1 ORDER BY s.received_at DESC LIMIT 20;
```
- Global halt / breakers: `app.risk.halt.is_halted` + `accounts.circuit_breaker_tripped_at`.
- Stuck orders: look under Working/All (not just Today) for non-terminal orders; see
  `deploy/aws/reconcile-sweep.sh` (`scripts/reconcile_stuck_orders.py`).

---

## Related
- Strategy: `apps/backend/strategies_user/templates/range_trader.py`
- Endpoint: `apps/backend/app/api/v1/range_levels.py` · Panel:
  `apps/frontend/src/components/strategies/RangeLevelsPanel.tsx`
- Halt fix: ADR 0034 (per-account daily-loss halt) — why a range position no longer
  gets stranded overnight by another book's loss.
- Design: `docs/design/RangeTrading_Logic_and_Research_v0.1.md`,
  `docs/design/Range_BuySell_Formula_Study.md`.
