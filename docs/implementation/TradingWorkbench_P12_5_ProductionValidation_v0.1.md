# Trading Workbench — P12.5: Production Validation (v0.1)

| Field | Value |
|---|---|
| Document | **P12.5 — Production Validation** — the bridge between P12 (Evidence Platform) and P13 (Product Readiness): turn the *live* paper book into continuous, verifiable evidence. |
| Version | v0.2 (2026-06-21) — live-evidence report + equity-snapshot persistence **shipped and activated**; weekly refresh **automated** (Windows Task Scheduler). |
| Predecessor | P12 §1–§3 (backtest evidence) + v1.1 enabled live (paper) |
| Successor | P13 — Product Readiness |
| Status | Live — tooling shipped + activated; the equity curve accrues daily; the weekly evidence PR is automated. |

---

## Why this milestone exists

The reviewer's point (and the platform's thesis): the biggest competitive advantage isn't another
backtested factor — it's being able to show **backtest → walk-forward → live paper → operational logs
→ evidence reports → monthly reviews**, *which most platforms cannot.* P12 produced the **backtest**
evidence; P12.5 produces the **live** evidence — the real-world track record that turns "it works in a
backtest" into "here is what it actually did, and here is the proof it's real."

It is deliberately a *bridge*, not a research phase: enable v1.1, let it run, and generate
weekly/monthly evidence — while P13 (productization) proceeds in parallel.

## What shipped (this deliverable)

- **Live paper-trading evidence report** (`apps/backend/scripts/live_evidence.py`) — read-only;
  turns the live workbench DB into a production-validation report: the strategy config (confirms
  **v1.1, vol-scaling on**), the current book (equity, exposure, per-position unrealized P&L), the
  realized trade log, and — the differentiating content — the **operational + safety + verifiability**
  trail. `script → JSON → Markdown`, runnable weekly/monthly. mypy/ruff clean.
- **First generated report** (`docs/implementation/evidence/p12_5_live/live_evidence.{json,md}`):
  v1.1 PAPER; equity $10,208, gross 78%; **risk engine demonstrably working** (8 orders passed, 2
  rejected by risk); the daily-loss **breaker tripped and recovered**; **replay + reconciliation
  clean (0/0)** — the live decisions are provable, not just reported.

## Equity-snapshot persistence (✅ shipped — the curve now accrues)

The gap this surfaced — `accounts_state` is point-in-time, so there was no equity-curve history — is
now closed:

- **`equity_snapshots` table** (Alembic `a1c3e5f7b9d2`) — append-only equity time series per account.
- **`equity_snapshot` daily job** (`app/services/equity_snapshot.py`, lifespan, **16:10 ET**) —
  appends one point per account from the current `accounts_state` near market close. Best-effort,
  single-flight; **no order path**. Registered in the ops feature registry.
- **The report now computes the live curve** — total return, ann. vol, **max drawdown**, Sharpe from
  the persisted series (shows *"accruing"* until ≥2 daily points). Tests + ruff/mypy clean.

So as v1.1 runs, the live book builds a real equity curve + realized-risk metrics — the time-series
performance the production-validation track record needs. (Turnover/slippage attribution is a later
increment.)

> ✅ **Activated (2026-06-21):** the backend was rebuilt + restarted → migration `a1c3e5f7b9d2`
> applied (table created), the `run_daily_equity_snapshot` job registered (16:10 ET), and strategy
> id=2 auto-resumed on v1.1. The first equity point was seeded (account 1, $10,208.14 @ 2026-06-21);
> the curve accrues 1 point/day from here (shows *"accruing"* in the report until ≥2 daily points).

## How to run (weekly / monthly cadence)

Manual:

```
apps/backend/.venv/Scripts/python.exe apps/backend/scripts/live_evidence.py \
    --db data/workbench.sqlite --strategy-id 2 --report-dir docs/implementation/evidence/p12_5_live
```

Each run overwrites the snapshot; archive a dated copy under `archive/<date>/` to build the live
track record. Read-only — it never touches the order path.

### Automated (✅ shipped 2026-06-21)

The weekly cadence is now unattended via a **Windows Task Scheduler** job —
**"TradingWorkbench LiveEvidence Weekly"**, Saturdays 08:00 (America/Chicago):

- **`scripts/weekly_live_evidence_refresh.ps1`** — regenerates the report, archives a dated copy under
  `archive/<date>/`, commits, pushes `docs/p12-5-live-evidence-<date>`, and opens a **docs-only PR**.
  Idempotent (same-day re-run = no-op; no DB change = no PR). Logs to `logs/live-evidence-refresh.log`.
- **`scripts/register_weekly_live_evidence_task.ps1`** — registers/refreshes the scheduled task
  (interactive user context for `gh`/git creds; `StartWhenAvailable` catches a missed 08:00).

> A **local** task, not a cloud `/schedule` routine: `data/workbench.sqlite` is gitignored and only
> exists on the host (the live Docker-mounted paper book), so only the local machine can read it.
> Shipped in PR #196; first automated run 2026-06-27.

## What this is NOT

- **Not** a performance claim — it's a *validation* report; absolute paper P&L over a short window is
  noise (ADR 0014). Its value is the **operational + verifiability** trail + the accumulating record.
- **Not** the equity-curve performance report yet (gated on the persistence job above).
- **Not** a new strategy or research — it observes the live book read-only.
