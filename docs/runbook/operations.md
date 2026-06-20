# Runbook — Operations & Reliability (P11)

Operating the platform's automated features safely. P11 §1 ships the **operational-state
surface**: what is enabled/running today and whether it's healthy. (Reconciliation,
replay, and full KPI dashboards arrive in later P11 sessions.)

## What's running today?

**Live view (the running server):**

```
GET /api/v1/ops/state      # authenticated; reads the live strategy engine + scheduler
```

Returns, per feature: `implemented` / `enabled` / `healthy` / `verified` (+ `governing_adr`,
`flag`, `note`). It derives state live — there is no operational table (P11 §1, ADR 0021).

**Static catalog (no server, no auth):**

```
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/ops_state.py
```

Prints the feature registry (key · kind · flag · verified · ADR). Use it to see the
inventory and each feature's promotion verdict; use the API for live enabled/healthy.

## Reading the four states

| State | Meaning |
|---|---|
| **Implemented** | Code is on `main` (always true for a registered feature). |
| **Enabled** | A strategy *running on a book* has the feature's flag on (flag features), or the infra job is registered (e.g. `breaker_monitor`). |
| **Healthy** *(measured, §2)* | From the scheduler last-success/last-error gauges per the feature's backing job(s): `ok` (fresh success) / `degraded` (most recent run errored/missed) / `stale` (no success within ~2× cadence) / `unknown` (no data yet, or within the 60s startup grace) / `n_a` (not enabled). `unknown` ≠ `degraded` — a fresh process doesn't false-alarm. The `/ops/state` envelope carries `health_algorithm_version` + `health_calculated_at`. |
| **Verified** | The promotion-backtest verdict — `validated` / `pending` / `no_go` / `n_a`. A research decision, curated in the registry (synced with the P10 roadmap's Implemented-vs-Proven table). |

## Operator notes

- **`verified=no_go` (the §5 breadth/VIX overlays):** these stay **off**. The promotion
  backtest found a drawdown tool with a Sharpe cost; do not enable without new evidence
  (deeper `^VIX` history) — *not* threshold tuning (overfit).
- **`verified=pending` (daily overlay, smoothing):** built and default-off; needs a
  promotion backtest before enabling on a book.
- **Enabling a feature** is a deliberate, backtest-gated decision — it is a strategy param
  change, not a code change. After enabling on the live book, populate any data the feature
  needs (e.g. breadth/`^VIX` in the live store) at that point.
- **`enabled=false` for everything** when querying via the standalone CLI is expected — the
  CLI shows the static registry; only the API endpoint sees the live engine.

## KPIs, SLOs & alerts (§2)

Metrics are on the Prometheus backbone (`GET /metrics`); the committed dashboard is
`docs/observability/grafana-operations.json` (import into a Grafana scraping `/metrics`).
KPIs are split **Platform** (the platform itself works) vs **Actor** (a given automation
works), each with an owner, SLO, and alert severity:

**Platform KPIs**

| KPI | Owner | Metric | SLO | Alert |
|---|---|---|---|---|
| Scheduler success | Scheduler | `scheduler_job_events_total` (executed ÷ all) | > 99.9% | WARNING |
| Job freshness | per-job | `time() - *_last_success_timestamp` | < 2× cadence | WARNING |
| Metrics endpoint | Observability | `/metrics` scrape | reachable | WARNING |

**Actor KPIs**

| KPI | Owner | Metric | SLO | Alert |
|---|---|---|---|---|
| Breaker-monitor success | Risk | `automation_runs_total{actor="breaker_monitor"}` | 100% | CRITICAL |
| Overlay outcomes | Overlay | `overlay_actions_total` | — (default off) | INFO |
| Fail-open frequency | Overlay | `overlay_actions_total{outcome="fail_open"}` | < 0.1% | WARNING |
| Duplicate executions | (invariant; `skip_idempotent` evidence) | — | 0 | CRITICAL |
| Replay consistency | Replay | (§4) | 100% | CRITICAL — *§4* |

Operator response: a **CRITICAL** (duplicate execution, breaker-monitor failing, replay
inconsistency) is a stop-and-investigate; a **WARNING** (scheduler dip, staleness,
elevated fail-open) is a look-soon. The breaker monitor swallows internal errors, so its
*outcome* (`automation_runs_total`), not just its scheduler execution, is the health
signal.

## What §2 does NOT cover (later P11 sessions)

- Broker/local **reconciliation** → **§3**; **replay** → **§4**; restart/partial-fill
  **recovery** runbooks → **§5**. The replay-consistency KPI row above is reserved until §4.
- A **persisted operational data model** (`automation_runs`/`*_runs`/`system_health`
  tables) — KPI history lives in Prometheus; durable run records arrive in §3/§4.
