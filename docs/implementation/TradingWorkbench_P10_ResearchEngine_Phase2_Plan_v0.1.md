# Research Engine — Phase 2 plan (P10)

| Field | Value |
|---|---|
| Document version | **v0.2** (revised per reviewer feedback) |
| Date | 2026-06-17 |
| Phase | P10 — Phase 2 (Research Engine as a top-level subsystem) |
| Predecessor | Phase 1 complete: momentum 12m (#143), risk overlays (#150), crash study (#151), evidence hardening (#154); capstone v1.1 (#149) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Promote the research *scripts* into a first-class, reproducible, versioned **Research Engine subsystem** — registries, orchestrator, lifecycle-aware promotion gate, dashboard, comparison tools, continuous revalidation. |
| Estimated wall time | ~5 sessions, 5–7h each |
| Out of scope | New strategies; live trading; **portfolio-construction research (→ Phase 3A)**; factor-library expansion (→ Phase 3B); broaden-universe re-test (→ Phase 4); options/futures (Phase 5) |

> **v0.2 changes (reviewer feedback):** added the **research lifecycle** spine; expanded
> one registry into **four** (experiment + strategy + dataset + feature); added
> **Research Dashboard**, **compare_experiments**, **promotion workflow**, and
> **continuous revalidation**; promotion gate now emits **lifecycle states**;
> experiment table gains seed/host/versions/`parent_experiment_id` and split
> summary/detail metrics; **portfolio research moved to Phase 3A**; and the headline
> architectural decision — **elevate the Research Engine to a top-level subsystem**.

## 0. Architectural decision — Research Engine as a top-level subsystem

Per the reviewer: stop treating research as supporting code under `factor_data`;
give it equal status to the trading side.

```
TradingWorkbench
├── Trading Engine     (executes ideas — OrderRouter, strategies)
├── Risk Engine        (gates every order)
├── Portfolio Engine   (construction/sizing)
├── Research Engine    (creates & validates ideas)   ← Phase 2 builds this
└── Data Engine        (PIT stores, providers)
```

The Research Engine (likely `app/research/`) owns: the four **registries**, the
**promotion gate**, **evidence packages**, the **research dashboard**, **continuous
revalidation**, and **comparison tools**. It stays strictly read-only and off the
order path (ADR 0018); the trading engine executes what the research engine
validates. *(A short ADR will record this subsystem boundary before §1.)*

## 1. The research lifecycle (the organizing spine)

Phase 2 makes this full lifecycle explicit and tracked, not just Idea→Research→Gate→Evidence:

```
Idea → Hypothesis → Experiment → Result → Promotion → Paper → Live → Monitoring → Retirement → Archive
```

Every artifact (experiment, strategy) carries a **lifecycle state**, and the
promotion gate + continuous revalidation move artifacts between states.

## Why this phase exists

The *process* (reject weak ideas, confirm robust ones, OOS-gate everything) is the
asset — but it lives in hand-run scripts with ad-hoc `research/*.md` outputs, no
record of which code+data+config produced a result, and no way to query or compare
across experiments. Phase 2 makes research reproducible, queryable, and
lifecycle-aware so every future idea goes through the same rigorous pipeline.

## What already exists (the ~80%)

| Stage | Component |
|---|---|
| Universe | `factor_data/universe.py` (PIT top-N, survivorship-free) |
| Factor engine | `factors/{engine,momentum,fundamental,cross_section}.py` |
| Backtester | `factor_data/backtest.py` (+vol/drawdown overlays); single-name `Backtester` |
| IS/OOS validator | `scripts/factor_research.py` (IC, long-short, decay, rolling IC, IS/OOS) |
| Robustness | `scripts/range_5c_gate.py`, overlay/window sweeps |
| Promotion gate | §5c gate (range-trader-specific; already emits GO/GO-WARNING/NO-GO/INCONCLUSIVE) |
| Evidence | `research/*.md` + findings docs; dataset/universe version block (#154) |

## The 20% (integration) — Phase 2 sessions

### §1 — The four registries (the reproducibility backbone) · ~6–8h
A local DuckDB schema every study/strategy reads & writes.

```sql
-- EXPERIMENT: one row per run (reviewer additions folded in)
CREATE TABLE experiments (
  experiment_id   VARCHAR PRIMARY KEY,        -- ulid
  parent_experiment_id VARCHAR,               -- research genealogy / DAG
  created_at      TIMESTAMP, duration_ms BIGINT,
  kind            VARCHAR,                     -- factor_ic | book_backtest | overlay | ...
  strategy_id     VARCHAR,                     -- FK → strategies (not a free-form name)
  dataset_id      VARCHAR,                     -- FK → datasets
  feature_ids     JSON,                        -- FK list → features
  git_commit      VARCHAR, host VARCHAR, python_version VARCHAR,
  package_versions JSON, seed BIGINT,          -- full reproducibility
  params_json     JSON, is_window VARCHAR, oos_window VARCHAR,
  cost_model      VARCHAR, pit_mode VARCHAR, survivorship_mode VARCHAR,
  metrics_summary JSON,                        -- Sharpe/CAGR/MaxDD/turnover (queryable)
  metrics_detail  JSON,                        -- daily_returns/IC_series/rolling_IC/sector_weights
  state           VARCHAR, owner VARCHAR, notes VARCHAR
);

-- STRATEGY: the things that get promoted/retired
CREATE TABLE strategies_registry (
  strategy_id VARCHAR PRIMARY KEY, name VARCHAR, category VARCHAR,
  state VARCHAR,                               -- lifecycle state (see §3)
  paper_since TIMESTAMP, live_since TIMESTAMP, retired_at TIMESTAMP,
  current_version VARCHAR, current_commit VARCHAR, owner VARCHAR, notes VARCHAR
);

-- DATASET: so "SEP updated → results changed" is explainable
CREATE TABLE datasets (
  dataset_id VARCHAR PRIMARY KEY, provider VARCHAR, version VARCHAR,
  created_at TIMESTAMP, coverage VARCHAR, row_count BIGINT,
  checksum VARCHAR, source_hash VARCHAR
);

-- FEATURE: factors as versioned, described entities (not buried in scripts)
CREATE TABLE features (
  feature_id VARCHAR PRIMARY KEY, description VARCHAR, formula VARCHAR,
  parameters JSON, introduced_in VARCHAR, deprecated_in VARCHAR
);
```
Deliverables: schema + typed `record_*`/`get_*` APIs; `factor_research` + the
backtest drivers write experiment rows referencing strategy/dataset/feature ids.
Tests: round-trip, FK integrity, idempotency, the #154 `_dataset_version` feeding `datasets`.

### §2 — ResearchEngine orchestrator + evidence package + dashboard · ~6–8h
One entrypoint takes a config and runs Universe → Features → Factor → Backtest →
IS/OOS → Robustness → Gate → Evidence + registry rows (reuse, don't rebuild).
Auto-generates a **research dashboard** (`research/dashboard.md`): latest
experiments (GO/NO-GO/pending), active vs retired strategies — the research
homepage. Caches by `experiment_id` so an unchanged config reruns instantly.
Deliverables: `app/research/engine.py` + CLI; evidence-package + dashboard writers.

### §3 — Lifecycle-aware promotion gate + workflow · ~5–7h
Generalize §5c into `promotion_gate(metrics, profile)` emitting **lifecycle states**
instead of bare GO/NO-GO:
```
RESEARCH → GO → GO_WARNING → PAPER → LIVE_READY → LIVE → RETIRED
```
Per-kind threshold profiles (reuse §5c's frozen criteria as the `book_backtest`
profile). Document the **promotion workflow** — Research → GO → Paper → Paper
Validation → Promotion Review → Live Candidate → Live → Monitoring — with the
gate/owner action at each stage. Deliverables: generalized gate + profiles +
`docs/runbook/promotion-workflow.md`. Tests: existing §5c cases pass through unchanged.

### §4 — Comparison tools + continuous revalidation · ~6–8h
- **`compare_experiments.py`** — A/B/C table (Sharpe/CAGR/MaxDD/turnover/IC, winner per metric) from the registry.
- **Continuous revalidation** (the reviewer's "largest missing capability"): a scheduled monthly job re-runs IC + rolling Sharpe/turnover/drawdown for LIVE/PAPER strategies; if a metric breaches its threshold it writes a **Research Alert** (and can transition the strategy toward RETIRED). Closes the loop on edge decay.
Deliverables: comparison CLI; revalidation job (reuse the existing scheduler) + alert surface. Tests: comparison math; a synthetic decayed-edge → alert.

### §5 — ADR + subsystem move + docs · ~4–6h
Write the ADR for the Research Engine subsystem boundary (§0); move/alias the
research code under `app/research/`; wire the dashboard + registries into the dev
docs. Deliverables: ADR, the subsystem package, updated `tasks/todo.md` + runbook.

## Follow-on phases (reviewer's reordering)

- **Phase 3A — Portfolio research** (moved out of Phase 2): weighting (equal / inverse-vol / risk-parity), name count, cadence, reconstitution delay, position buffering, rank hysteresis, **+ transaction_cost and rebalance_delay sweeps** — "construction usually adds more value than another factor."
- **Phase 3B — Factor expansion:** Growth, Profitability, Capital allocation, Risk, Liquidity → 20–40 candidates (plug into the feature registry).
- **Phase 4 — Broaden universe** (top-200 → top-1000, small/mid/international) and re-run everything through the same pipeline (gated on the as-reported + delisted-coverage upgrades, per the FMP PIT doc).
- **Phase 5 — Options/futures/ETFs/international** (only after the equity platform is mature).

## Scope boundaries (non-negotiable)

- **Read-only, off the order path** (ADR 0018) — the engine validates; the trading engine executes.
- **No new external dependencies**; local-first DuckDB; OS-trust-store TLS.
- **Reuse, don't rebuild** — the value is integration; don't re-implement the backtester/factor engine.

## Open questions (resolve before §1)

1. Registry storage: extend `factor_data.duckdb` vs a dedicated `research.duckdb`. Lean: dedicated store, since the Research Engine is now its own subsystem.
2. Promotion-gate threshold profiles per `kind` — §5c is the `book_backtest` profile; what are `factor_ic` thresholds?
3. Generalization discipline — build the minimum that serves the next 2–3 real experiments, not a speculative framework.

## Notes & gotchas

1. `Date.now()`/randomness are fine in scripts (unlike workflow scripts); stamp `created_at`/`seed`/`git_commit` at run time — and **store the seed** (reviewer: very useful for reproducibility).
2. The book backtest is slow (~7 min/segment); the orchestrator must cache by `experiment_id`.
3. Keep evidence + dashboard as committed `.md`/`.json` in `research/`; gitignored data stays out.
4. Continuous revalidation reuses the existing scheduler (the breaker-monitor job pattern); it must stay read-only — an alert, never an auto-trade or auto-retire without owner review.
