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
| **Healthy** *(basic, §1)* | The enabling actor is actually being dispatched (its scheduler job is registered). `n_a` when not enabled, `degraded` if enabled but no job. **Full KPI/freshness health is §2.** |
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

## What §1 does NOT cover (later P11 sessions)

- Full operational **KPIs** (scheduler success %, fail-open rate, duplicate-exec count,
  last-run freshness) + a dashboard → **§2**.
- Broker/local **reconciliation** → **§3**; **replay** → **§4**; restart/partial-fill
  **recovery** runbooks → **§5**.
