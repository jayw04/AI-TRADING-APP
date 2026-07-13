# Runbook — Daily & Weekly Pipeline Health Checklist

**Owner:** Jay Wang · **Runs on:** `ec2-paper` (the box; ADR 0032) · **Added:** 2026-07-13

---

## Why this exists

On Monday 2026-07-13 the `momentum-portfolio` book produced **zero orders** at its 10:00 ET
rebalance. Answering the obvious question — *did it run and correctly decide to trade nothing,
or did it never run at all?* — took an hour of manual archaeology, and the honest answer was
**the database could not tell us**. Those two cases are identical in the `orders` table: a
no-op leaves no orders to derive a run window from.

So we now record the **dispatch itself**, not just its output, and we run the freshness checks
on a timer instead of by hand when someone gets worried.

Three tables carry it (operational telemetry — **not** the audit log, not hash-chained;
they follow the `reconciliation_runs` precedent):

| Table | One row per | Answers |
|---|---|---|
| `strategy_dispatch_runs` | scheduled dispatch | *Did the 10:00 slot fire? When did it start/finish? How long? How many orders?* |
| `data_health_snapshots` | data source per check | *When was the factor store last refreshed? How stale is it? What's covered?* |
| `ops_check_runs` | checklist run | *What did the DAILY/WEEKLY check conclude, and what was the report?* |

> **The single most important property:** a dispatch that trades nothing still writes a row.
> A dispatch that never happened leaves a **hole**. The hole is the alarm. You cannot
> reconstruct that distinction after the fact from any other table.

---

## The schedule

| When (ET) | What | Unit |
|---|---|---|
| 06:00 weekdays | Factor store incremental refresh | `workbench-factor-refresh.timer` |
| 10:00 / 10:24 / 10:32 / 10:40 Mon | The four cron rebalances (momentum / sector / low-vol / combined) | strategy cron (in-app, ET) |
| every 10 min | Reconcile stuck-SUBMITTED orders (missed fills) | `workbench-reconcile-sweep.timer` |
| 16:35 weekdays | Daily per-account digest → SNS | `workbench-daily-report.timer` |
| 16:45 weekdays | Continuous Evidence Engine drift report → SNS | `workbench-cee-report.timer` |
| **16:50 weekdays** | **DAILY pipeline health → DB + SNS** | **`workbench-pipeline-health-daily.timer`** |
| **11:15 Monday** | **WEEKLY pipeline health → DB + SNS** (after all four rebalances) | **`workbench-pipeline-health-weekly.timer`** |

---

## The checks

### Data

| | Check | FAIL means |
|---|---|---|
| **D1** | Factor store `sep` freshness | `sep` is ≥3 **sessions** behind the last completed session. The factor books *rank* on this store — they are selecting on stale prices. |
| **D2** | Factor store `tickers`/`sep` lockstep | `tickers.lastpricedate` is **behind** `sep`. The PIT universe resolves **EMPTY** and every factor book **silently HOLDs without erroring** — this is the 2026-07-06 incident class, and it is the most dangerous failure here because nothing looks broken. |
| **D3** | Bar cache currency | The live universe is missing bars for the last session. The order path prices from bars, so this is an *execution* problem even when the factor store is perfect. |
| **D4** | Universe coverage | A live strategy's symbols are absent from the store. A coverage hole looks exactly like "the factor said no". |

Staleness is measured in **trading sessions**, not calendar days — "3 days old" over a holiday
weekend is current, and counting calendar days cries wolf every long weekend.

### Rebalance

| | Check | FAIL means |
|---|---|---|
| **R1** | Scheduled dispatch fired | A live strategy has **no dispatch row** in the window. It did not run. This is *not* the same as running and trading nothing. |
| **R2** | Dispatch outcomes healthy | A dispatch hit `ERROR` or was `SKIPPED_OUT_OF_SESSION`. |
| **R3** | Order outcomes | Orders are stuck open, or were rejected. |

---

## Reading the output

The report is emailed to the paper-alarms SNS topic, written to
`/opt/workbench/app/reports/pipeline-health/<date>-<kind>.md` on the box, **and** stored in
`ops_check_runs.report_md` so any past run can be read back verbatim.

Run it by hand at any time:

```bash
ssh workbench
sudo docker exec -i workbench-backend python - --kind DAILY \
  < /opt/workbench/app/apps/backend/scripts/reports/pipeline_health.py
```

`--no-persist` renders without writing DB rows. **`docker exec` needs `-i`** — without it the
script never reaches the container's stdin and the python block silently does not run (this has
bitten us before, PR #408).

Query the history directly:

```sql
-- Did every Monday rebalance fire? (a MISSING row is the finding)
SELECT s.name, d.started_at, d.finished_at, d.duration_ms, d.outcome, d.orders_submitted
FROM strategy_dispatch_runs d JOIN strategies s ON s.id = d.strategy_id
WHERE d.started_at >= date('now','-7 days') ORDER BY d.started_at;

-- When was the factor store last actually refreshed, and how stale was it?
SELECT captured_at, source, as_of_date, last_refresh_at, staleness_sessions, status
FROM data_health_snapshots ORDER BY captured_at DESC LIMIT 20;

-- Checklist history
SELECT kind, started_at, status, checks_fail, checks_warn FROM ops_check_runs
ORDER BY started_at DESC LIMIT 20;
```

---

## Responding to a finding

**D1 FAIL — factor store stale.** Check `workbench-factor-refresh.timer` (`systemctl status`,
`journalctl -u workbench-factor-refresh`). The previous day's store is safe to trade on for a
few days; several sessions is not. Rollback copy: `factor_data.prev.duckdb`.

**D2 FAIL — lockstep broken.** *Do not wait.* The next rebalance will HOLD every factor book
and produce zero orders while looking completely healthy. Re-run the refresh so
`tickers.lastpricedate` catches up to `sep`, and confirm before the next scheduled rebalance.

**R1 FAIL — a strategy never dispatched.** In order of likelihood: (a) the strategy is not
registered in the engine (`strategies.status` != PAPER, or it errored out and was dropped from
`_running`); (b) the backend restarted through its cron slot; (c) the schedule's day-of-week is
numeric — **use day names**, `0 14 * * 1` fires *Tuesday*, not Monday (APScheduler's
`from_crontab` numbers 0=Mon and does not remap). Do **not** "just fire it manually" without
first checking the clock: a manual trigger inside the scheduler's own window is how you get a
**double rebalance**, which is exactly the mechanism of the June 22–23 conservative-book −26%
leverage blowout (3× dispatch → 3.8× leverage).

**R3 WARN — orders still open.** The trade-updates websocket misses fills; the reconcile sweep
(every 10 min) is what heals them, so order state can be **up to 10 minutes stale** after a
large rebalance. Investigate only if they persist across two sweeps.

---

## Invariants this respects

- **Off the order path.** The report is read-only w.r.t. trading and imports no LLM (ADR 0006 v2).
- **Telemetry is an observer, never a gate.** The engine's dispatch recorder is fully wrapped:
  if it fails, it logs and swallows. A monitoring feature that can halt trading is worse than no
  monitoring feature. This is asserted by
  `tests/strategies/test_engine_dispatch_telemetry.py::test_telemetry_failure_cannot_break_the_dispatch`.
- **Not the audit log.** These tables are mutable telemetry. Consequential actions still go
  through the hash-chained `audit_log` via the typed `AuditLogger` API.
