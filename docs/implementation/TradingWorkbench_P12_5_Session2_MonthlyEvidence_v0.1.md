# Trading Workbench — P12.5 §2: Monthly Evidence Report (v0.1)

| Field | Value |
|---|---|
| Document version | v0.1 (2026-06-21) |
| Date | 2026-06-21 |
| Phase | **P12.5 — Production Validation** (Track A — Production Evidence) |
| Session | §2 of the P12.5 evidence increments (Phase 1 of the P13 roadmap) |
| Predecessor | P12.5 §1 — live-evidence report + equity-snapshot persistence + weekly automation (PRs #192–#196) |
| Successor | P12.5 §3 — Production Confidence Score (the next Track-A increment) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A read-only **monthly** institutional evidence report that aggregates one calendar month of the live paper book — performance, risk, operations, incidents, recovery, replay, reconciliation, changes, lessons learned. |
| Estimated wall time | 2–3 hours |
| Tag on completion | (none — P12.5 increment, no phase tag) |
| Out of scope | The Confidence Score (§3); the operational KPI dashboard (§4); any order-path or schema change; turnover/slippage attribution. |

---

## 1. Why this session exists

The weekly `live_evidence.py` snapshot (P12.5 §1) proves *the plumbing works this week*. The owner's
P13 direction (v0.2 §4) calls for the next rung: a **monthly institutional report** that turns the
accumulating evidence trail into the kind of document an allocator or buyer reads — performance over
the month, the operational/safety record, an incident log, and lessons learned. This is what makes the
evidence *institutional* rather than a weekly heartbeat.

It is deliberately a **reporting** increment: read-only, reuses the §1 equity curve + the existing
audit/ops tables, builds no new subsystem.

## 2. What this session ships

- **`apps/backend/scripts/monthly_evidence.py`** — read-only; `build(db, strategy_id, month) → dict`
  + `script → JSON → Markdown`. Sections: **Performance** (month equity curve → return / vol / maxDD /
  Sharpe / Sortino / Calmar + drawdown profile, reusing `app/factor_data/evidence.py`), **Risk** (gates
  passed vs rejected, breaker trips/resets), **Operations** (orders, scanner runs, reconciliation +
  replay run counts), **Incidents** (breaker trips, broker rejects, replay mismatches, reconciliation
  discrepancies — each with timestamp), **Recovery** (resets + recovery story), **Replay** /
  **Reconciliation** (run summaries from `replay_runs` / `reconciliation_runs`), **Changes** (strategy
  registered / updated / deactivated / proposal transitions), **Lessons learned** (auto-derived from
  the incident set; "clean month" when empty).
- **A test** (`apps/backend/tests/scripts/test_monthly_evidence.py`) that builds a temp SQLite with the
  relevant tables and asserts the month-window aggregation, the incident classification (a risk
  *rejection* is NOT an incident; a breaker trip IS), and the performance calc / "accruing" fallback.

## 3. Prerequisites

- P12.5 §1 merged (equity-snapshot persistence live; `live_evidence.py` + `evidence.py` on `main`). ✓
- The live DB at `data/workbench.sqlite` with `audit_log`, `equity_snapshots`, `reconciliation_runs`,
  `replay_runs`, `strategies` (all present). ✓

## 4. Detailed work

### 4.1 Month window
`--month YYYY-MM` (default: current month). `_month_bounds` → `(first_day, last_day)` ISO date strings;
all queries filter `date(ts) BETWEEN first AND last` (`audit_log.ts` is stored
`"YYYY-MM-DD HH:MM:SS.ffffff"`, so `date()` parses cleanly — no isoformat/`T` comparison trap).

### 4.2 Sections (all read-only SQL + `evidence.py` reuse)
- **Performance** — `equity_snapshots` rows in-month, last per day → `ev.daily_returns / total_return /
  ann_volatility / max_drawdown / sharpe / sortino / calmar / drawdown_profile`. `< 2` in-month points
  → `status: "accruing"`.
- **Risk** — audit counts: `ORDER_RISK_PASSED`, `ORDER_REJECTED_BY_RISK`, `ORDER_REJECTED_BY_BROKER`,
  `CIRCUIT_BREAKER_TRIPPED` / `_RESET`.
- **Incidents** — breaker trips + broker rejects + `replay_runs.n_mismatched>0` +
  `reconciliation_runs` result `fail`/`warning` (or `n_discrepancies>0`). **A risk-engine rejection is
  NOT an incident** — it is the gate working; it lands under Risk.
- **Changes** — `STRATEGY_REGISTERED/UPDATED/DEACTIVATED/UNREGISTERED`, `STRATEGY_PROPOSAL_TRANSITIONED`.
- **Lessons learned** — derived: clean month → "the discipline held"; otherwise summarize incidents.

### 4.3 Output
Writes `monthly_evidence.{json,md}` to `--report-dir`; the weekly automation pattern (archive a dated
copy) applies at the monthly cadence too (a follow-on can extend the scheduled task to also run this on
the 1st of the month).

## 5. Manual smoke

```
apps/backend/.venv/Scripts/python.exe apps/backend/scripts/monthly_evidence.py \
    --db data/workbench.sqlite --strategy-id 2 --month 2026-06 \
    --report-dir docs/implementation/evidence/p12_5_live/monthly
```
Confirm: prints the month summary line; writes JSON + MD; the MD renders all nine sections; a clean
month shows an empty incident log + the "discipline held" lesson.

## 6. Walk-away discipline

≥1 hour (routine, read-only reporting; no audit/risk/order-path code).

## 7. What this session does NOT do

- No Production Confidence Score (that is §3, which *consumes* this report's signals).
- No KPI dashboard, no Grafana panels (§4).
- No schedule registration for the monthly run (a small follow-on to the §1 Task Scheduler job).
- No new tables, migrations, audit actions, or order-path code.
- No turnover / slippage / per-trade attribution (a later increment).

## 8. Notes & gotchas

1. `audit_log.ts` is `"YYYY-MM-DD HH:MM:SS.ffffff"` — filter with `date(ts)`, never a lexicographic
   compare against an isoformat string with `T`/offset (the P6 §1a 24h-spend bug).
2. Classify a **risk rejection as a success signal, not an incident** — conflating them would make the
   report read as if the platform misbehaved when the gate did exactly its job.
3. Default month = current month → an early-in-the-month run is mostly "accruing"; for a finished-month
   report pass `--month` for the prior month.
