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
| Position held **overnight** (panel/positions show a leftover next morning) | The pre-close force-exit was blocked | Was there a halt or a stuck `SUBMITTED` order yesterday afternoon? | Cancel the stuck order + flatten. **Root cause fixed** by per-account risk containment (ADR 0034 / #315; daily-loss halt) — one account's loss no longer halts the range book |
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

## 5. Buy/Sell-vs-High/Low history — the two membership rules

`GET /api/v1/range-execution` → `range_execution_records` is **read-through**: querying a window
materializes and *freezes* any completed day it does not already hold. Rows are never recomputed, so
a wrong row is permanent until someone deletes it. Two defects have been fixed here; both were
capable of writing permanent garbage from nothing more than an ordinary history query.

| | Defect | Fixed by |
|---|---|---|
| 1 | **Cross-window roster union** — one symbol list for the whole window meant a query spanning a Top-5 rotation minted frozen blank rows for every rotated name on days it was never held | #390 → **#638** |
| 2 | **Pre-history roster fallback** — with no signal evidence, membership fell back to the *current* roster, so a window opening before the first signal named whoever holds the rotating slot today | **#639** |

The governing rule now is: **no membership evidence → no historical row creation.** A day's book is
established only from that day's `range_levels` signals, or carried forward along a chain rooted in
them. `capture_window` skips any day it cannot establish, and a fail-closed invariant
(`range_capture_membership_overflow`) stops it adding to a date that already exceeds its
evidence-backed membership.

### ⚠ Do not remove the prune script's `evidence_based` guard

**This is a deletion-safety boundary, not a leftover.** In
`scripts/prune_range_execution_phantom_rows.py`:

```python
if not evidence_based(r.et_date):
    skipped_no_evidence.add(r.et_date)
    continue
```

Since #639, `_membership_by_day` returns the **empty set** for a day whose membership cannot be
established. Empty means **"no evidence"** — it does *not* mean "the book held zero symbols". Every
row on such a day therefore fails the `r.symbol in members` membership test and, without this guard,
would be classified as a phantom and deleted.

Concretely: the `range_levels` emit began **2026-07-06**. The 35 rows covering 2026-06-24..07-02 are
real, owner-approved reconstructions of days the strategy genuinely traded. Remove the guard and a
routine prune over a window that includes them **deletes all 35**.

The asymmetry is deliberate and worth stating plainly: **capture and deletion are both conservative,
but for different reasons.** Capture skips an unknown day because inventing membership fabricates
history. Deletion skips an unknown day because assuming membership destroys it. Neither may fall
back to the current roster.

⚠ There is **no test covering the prune script**, so CI will not catch the guard's removal — see
`tests/services/test_range_execution.py` for the capture-side coverage and treat the guard as
change-controlled until equivalent coverage exists.

### Verifying this path safely

`capture_window` **commits whenever it inserts** and has no dry-run mode. Any validation of it must
be **provably read-only or run against an isolated database copy** — never "a stub with benign
inputs". On 2026-08-18 a validation stub that fabricated bars for every calendar day defeated the
trading-day filter (which keys off bar presence) and wrote 50 weekend rows into the live database.

The safe equivalent asserts the same property without a write path, by asking what capture *would*
do: if no member-day in the window lacks a row, capture inserts zero regardless of the bar cache.

```python
# read-only: never calls capture_window, so it cannot commit
levels  = await _levels_by_day(s, strat_id, d_from, d_to)
members = await _membership_by_day(s, strat_id, levels, d_from, d_to)
# then compare members[day] against the (symbol, et_date) rows already on file
```

Expected healthy state: **0 blank rows, 0 weekend rows, exactly 5 symbols on every day**, and no
date whose symbols exceed `members[date]`. A newly-closed session showing up as 5 populated rows on
the next query is normal read-through capture, not corruption.

---

## Related
- Strategy: `apps/backend/strategies_user/templates/range_trader.py`
- Endpoint: `apps/backend/app/api/v1/range_levels.py` · Panel:
  `apps/frontend/src/components/strategies/RangeLevelsPanel.tsx`
- Halt fix: ADR 0034 (per-account risk containment; daily-loss halt) — why a range position no longer
  gets stranded overnight by another book's loss.
- Design: `docs/design/RangeTrading_Logic_and_Research_v0.1.md`,
  `docs/design/Range_BuySell_Formula_Study.md`.
- History capture: `apps/backend/app/services/range_execution.py` · prune
  `apps/backend/scripts/prune_range_execution_phantom_rows.py` · backfill
  `apps/backend/scripts/backfill_range_execution_levels.py` (§5 above — read it before touching
  either script).
