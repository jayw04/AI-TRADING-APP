# Trading Workbench — P11 §2: Observability + Operational KPIs

| Field | Value |
|---|---|
| Document version | v0.1 (draft — two decisions recommended below; confirm before v1.0) |
| Date | 2026-06-19 |
| Phase | **P11** — Operations & Reliability |
| Session | §2 of 5 (Observability) |
| Predecessor | P11 §1 — operational-state surface (merged **#178**, tag `p11-session1-complete`) |
| Successor | P11 §3 — Reconciliation |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Turn §1's coarse "basic" health into **measured** reliability: a scheduler-event-driven KPI set (scheduler success, fail-open frequency, idempotent-skip evidence, per-actor freshness) on the existing Prometheus backbone, a committed **Grafana dashboard** + **SLO/alert** thresholds, and an **enriched `/ops/state`** (real per-feature health + headline KPIs). **No new DB schema, no order-path change.** |
| Estimated wall time | 5–8 hours (scheduler listener + actor outcome metrics + health enrichment + dashboard JSON + SLO doc + tests) |
| Tag on completion | `p11-session2-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

P11 §1 answers *"what's enabled today?"* but its health is **coarse** — "the enabling actor
is dispatched," nothing about whether jobs actually fire on cadence or how often they
fail/fail-open. The Direction's objective is that operational reliability be **measured
with the same rigor as investment performance** (the four-goal filter: this is *Observable*,
made quantitative). §2 delivers the measurement: the operational **KPIs** + their targets
(SLOs) + a dashboard, and it upgrades §1's health from "basic" to "real."

It builds on infra that already exists — the Prometheus registry + `/metrics` endpoint
(`app/observability/metrics.py`), the `background_job_last_run_seconds` gauge + snapshot
job, and the overlay's `overlay_actions_total`/`overlay_gross`. §2 adds the missing
**scheduler-reliability** signal (centrally, via an APScheduler event listener) and the
**per-actor outcome** signal, then derives health + KPIs from them.

## What this session ships

1. **Scheduler-reliability metrics** — a single APScheduler **event listener**
   (`EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED`) registered in
   `WorkbenchScheduler.start()` → `scheduler_job_events_total{job_id, event}` +
   `scheduler_job_last_success_timestamp{job_id}`. Centralized: covers *every* recurring
   job (rebalance, overlay, breaker monitor) without per-actor wiring.
2. **Per-actor outcome metrics** — `automation_runs_total{actor, outcome}` (`actor` ∈
   `overlay`/`breaker_monitor`/`rebalance`; `outcome` ∈ `ok`/`skip_idempotent`/`skip_drift`/
   `fail_open`/`error`). The overlay's existing `overlay_actions_total` is folded into this
   convention; the breaker monitor + dispatch paths emit it too.
3. **Enriched health in `app/ops/state.py`** — health moves from §1-basic to **measured**:
   `ok` / `degraded` (recent errors/fail-opens) / `stale` (no success within 2× cadence) /
   `n_a`, derived by reading the metrics registry in-process. Still read-only.
4. **Enriched `GET /api/v1/ops/state`** — each feature gains headline KPI fields
   (`last_success_age_s`, `recent_failures`, `fail_open_count`) so a no-Grafana operator
   gets numbers, not just states.
5. **Grafana dashboard (committed config)** — `docs/observability/grafana-operations.json`:
   panels for scheduler success %, per-actor outcomes, fail-open rate, last-run freshness.
6. **SLO + alert thresholds** — documented in the runbook (`operations.md`): the exit-gate
   SLOs from the Direction DoD, each mapped to a metric + alert threshold.
7. **Tests** (listener increments the right counters; health = stale/degraded/ok under
   seeded metric values; endpoint exposes KPI fields) + **runbook** update.

## Prerequisites

- **P11 §1 merged** (`98cec54`): `app/ops/feature_registry.py`, `app/ops/state.py`,
  `GET /api/v1/ops/state`, engine `running_strategies()`/`scheduler_has_job()`.
- Existing metrics infra: `app/observability/metrics.py` (Prometheus registry +
  `background_job_last_run_seconds`), `/metrics` endpoint, `app/jobs/metrics_snapshot.py`.
- `WorkbenchScheduler` (`app/services/scheduler.py`) owns the `AsyncIOScheduler`
  (`start()` registers jobs); the §6 `breaker_monitor` + overlay/rebalance jobs run on it.

## Open questions — recommendations (confirm before v1.0)

1. **Dashboard surface (Direction OQ#2) → Prometheus backbone + committed Grafana JSON +
   enriched `/ops/state`.** Metrics already live in Prometheus; the dashboard is *config*
   (a committed Grafana JSON), and the `/ops/state` endpoint carries headline KPIs for the
   no-Grafana/in-app operator. *Recommend; no in-app charting UI in §2 (that's a frontend
   effort, out of scope).*
2. **KPI history / persisted ops data model → use Prometheus time-series in §2; NO new DB
   tables.** "Scheduler success over 30d", "fail-open frequency" are Prometheus
   rate()/over_time queries — no schema needed. The persisted **operational data model**
   (`automation_runs`/`reconciliation_runs`/`replay_runs`/`system_health`, Direction §4
   deferred) arrives in **§3/§4** when reconciliation/replay need durable *run records*.
   Keeps §2 schema-free, consistent with §1.

## Detailed work

### §A — Scheduler-reliability listener (`app/services/scheduler.py` + metrics)

```python
# metrics.py
scheduler_job_events_total = Counter(
    "workbench_scheduler_job_events_total",
    "APScheduler job lifecycle events, by job and event",
    labelnames=["job_id", "event"],          # event: executed | error | missed
)
scheduler_job_last_success_timestamp = Gauge(
    "workbench_scheduler_job_last_success_timestamp",
    "Unix ts of the last successful execution, by job",
    labelnames=["job_id"],
)
```

In `WorkbenchScheduler.start()`, before `self._scheduler.start()`:

```python
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
self._scheduler.add_listener(self._on_job_event,
                             EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
```

`_on_job_event(event)` maps the APScheduler event → `scheduler_job_events_total.labels(
event.job_id, <executed|error|missed>).inc()` and, on success, sets the last-success gauge.
**Scheduler success rate** = `executed / (executed + error + missed)` (PromQL / the
dashboard) — the SLO is > 99.9%.

### §B — Per-actor outcome metrics

`automation_runs_total{actor, outcome}` in metrics.py. Emit it:
- **overlay** — already emits `overlay_actions_total{strategy_id, outcome}` (§5); add an
  `automation_runs_total{actor="overlay", outcome=...}` increment alongside (or alias) so
  all actors share one KPI surface. Outcomes: `ok` (scaled) / `skip_idempotent` /
  `skip_drift` / `fail_open` / `error`.
- **breaker_monitor** (`app/jobs/breaker_monitor.py`) — increment `ok` per pass,
  `error` on exception (it already swallows; add the metric).
- **rebalance** (engine `_dispatch_bar_tick`) — `ok` / `error` (the on_bar exception path).

`duplicate executions = 0` is an **invariant** (idempotency guard), evidenced by the
`skip_idempotent` outcome firing — not a separate metric; the §1/§5 idempotency tests
assert it.

### §C — Measured health (`app/ops/state.py`)

Replace §1's basic health with a metrics-derived health per feature/actor:

```python
def _actor_health(actor: str, cadence_s: float) -> str:
    last = REGISTRY.get_sample_value("workbench_scheduler_job_last_success_timestamp",
                                     {"job_id": _job_for(actor)})
    if last is None: return "degraded"          # never succeeded
    if now - last > 2 * cadence_s: return "stale"
    if _recent_errors(actor) > 0: return "degraded"
    return "ok"
```

Reads the in-process Prometheus registry (no new dependency). Still read-only; degrades to
the §1 basic check if metrics are absent (tests).

### §D — Dashboard + SLOs

- **`docs/observability/grafana-operations.json`** — committed Grafana dashboard (panels:
  scheduler success %, per-actor outcome rates, fail-open rate, last-run age). Config, not
  code; importable into any Grafana pointed at `/metrics`.
- **SLO / alert table** in `operations.md`:

  | KPI | Metric | SLO / alert |
  |---|---|---|
  | Scheduler success | `scheduler_job_events_total` | > 99.9% (alert below) |
  | Fail-open frequency | `automation_runs_total{outcome="fail_open"}` | < 0.1% of runs |
  | Duplicate executions | (invariant; `skip_idempotent` evidence) | 0 |
  | Job freshness | `*_last_success_timestamp` | < 2× cadence |
  | Replay consistency | (§4) | 100% — *populated when §4 ships* |

### §E — Tests + runbook

- **`tests/observability/test_scheduler_listener.py`** — synthesize APScheduler
  executed/error/missed events → the right `scheduler_job_events_total` increments + the
  last-success gauge set on executed.
- **`tests/ops/test_operational_state.py`** (extend) — seed metric values → health
  resolves `stale` (old last-success) / `degraded` (recent error) / `ok`; endpoint exposes
  the KPI fields.
- **Runbook** — the SLO table + each alert's operator response.

## Manual smoke

1. `GET /metrics` on the running stack → `workbench_scheduler_job_events_total` present;
   after a tick, `..._executed` increments and `..._last_success_timestamp` advances.
2. `GET /api/v1/ops/state` → each feature now carries `last_success_age_s` /
   `recent_failures`; `breaker_monitor` health `ok` (fires every 60s).
3. Import `grafana-operations.json` into Grafana → panels populate from `/metrics`.
4. Stop the scheduler (or a job) → after 2× cadence, the relevant feature health flips to
   `stale` in `/ops/state`.

## Walk-away discipline

**≥ 2 hours.** §2 instruments the **live dispatch loop + scheduler** (the §A listener, §B
emits in `_dispatch_bar_tick`/`_dispatch_overlay_tick`/the breaker job). The additions are
side-effect-only metric calls, but they touch the safety-critical execution path — same
elevated bar as P10 §2.

## What this session does NOT do

- **No reconciliation (§3), replay (§4), or recovery hardening (§5).** §2's replay-
  consistency KPI slot stays empty until §4.
- **No persisted operational data model** (`automation_runs`/`*_runs`/`system_health`
  tables) — §2 uses Prometheus time-series for KPI history; durable run records come in
  §3/§4.
- **No in-app charting UI** — the dashboard is a committed Grafana JSON + the `/ops/state`
  KPI fields; a frontend ops page is out of scope.
- **No enabling of any overlay**, no order-path/risk/audit change, no new external
  dependency, no new auth.

## Notes & gotchas

1. **One central scheduler listener, not per-actor wiring** — `add_listener` covers every
   recurring job uniformly; resist instrumenting each job for *scheduler* success (only the
   *outcome* metric is per-actor).
2. **Prometheus counters are process-local** — a standalone CLI/script can't read the
   server's live counters (the §1/§5 lesson); KPIs are read via `/metrics`, the dashboard,
   or the in-process resolver — not a separate process.
3. **`docs/` vs `Docs/` git-add case quirk** (bit §1 and §5) — when adding the new
   `docs/observability/grafana-operations.json` + tests, `git add` with the index-matching
   case and verify `git diff --cached --name-only`.
4. **ASCII-only** any new CLI/printout output (Windows cp1252).
5. **Health reads the registry, fails soft** — if a metric is absent (fresh process,
   tests), fall back to the §1 basic check rather than raising; never let the ops surface
   crash because a counter hasn't been touched yet.
6. **Don't double-count the overlay outcome** — if folding `overlay_actions_total` into
   `automation_runs_total`, emit one or alias cleanly; two counters for the same event will
   skew the fail-open SLO.
