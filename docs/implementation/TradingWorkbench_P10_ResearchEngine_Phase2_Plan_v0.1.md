# Research Engine — Phase 2 plan (P10)

| Field | Value |
|---|---|
| Document version | **v1.0** (frozen for execution) |
| Date | 2026-06-17 |
| Phase | P10 — Phase 2 (Research Engine as a top-level subsystem) |
| Predecessor | Phase 1 complete: momentum 12m (#143), risk overlays (#150), crash study (#151), evidence hardening (#154); capstone v1.1 (#149) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Promote the research *scripts* into a first-class, reproducible, versioned **Research Engine subsystem** — five registries + dependency graph, orchestrator, lifecycle-aware promotion gate with a confidence score, continuous revalidation, comparison tools, and (last) a dashboard. |
| Estimated wall time | ~5 sessions, 5–7h each |
| Out of scope | New strategies; live trading; **portfolio research (→ Phase 3A)**; factor expansion (→ Phase 3B); broaden-universe (→ Phase 4); options/futures (Phase 5). Also deferred (reviewer: stop expanding Phase 2): experiment tags, baseline-comparison fields, resource metrics, lineage visualization, research-KPI dashboard pages, meta-research. |

> **v1.0 — FROZEN. Three review rounds folded in; design is mature → build it.** The
> reviewer scored the design 10/10 and said the highest value now is to build it and
> validate with 5–10 real experiments, letting practice drive Phase 3 — not to keep
> expanding the design. This v1.0 adds only the reviewer's **five starred** items
> (Artifact Registry, dependency graph, research-vs-deployment state split,
> confidence score, transition-reason audit trail) and freezes scope there.

## 0. Architecture — Research Engine as a top-level subsystem

Five independent subsystems (reviewer's ordering):

```
Data Engine → Research Engine → Portfolio Engine → Risk Engine → Trading Engine
```

The Research Engine creates & validates ideas; the trading side executes what it
validates. It stays strictly read-only and off the order path (ADR 0018). Package
layout (own sub-packages, not one module):

```
app/research/
├── registry/     # the 5 registries + dependency graph + transition log
├── engine/       # the orchestrator (chains existing stages)
├── promotion/    # lifecycle-aware gate + confidence score
├── artifacts/    # artifact capture/versioning
├── comparison/   # compare_experiments
├── monitor/      # continuous revalidation + alerts
├── dashboard/    # built LAST
└── runbooks/
```
*(A short ADR records this subsystem boundary — §5.)*

## 1. The research lifecycle — two orthogonal axes

Per the reviewer, **research state and deployment state are different concepts** and
are tracked separately:

```
Research state:    RESEARCH → VALIDATED → REJECTED → ARCHIVED
Deployment state:  NONE → PAPER → CANARY → LIVE → RETIRED
```
A strategy can be `VALIDATED` (research) while still `PAPER` (deployment) — the split
makes that representable. Every transition on either axis records a **reason**.

## Why this phase exists

The *process* is the asset, but it lives in hand-run scripts with ad-hoc outputs, no
record of which code+data+config produced a result, and no way to query/compare
across experiments or trace what depends on what. Phase 2 makes research
reproducible, queryable, traceable, and lifecycle-aware.

## What already exists (the ~80%)

| Stage | Component |
|---|---|
| Universe | `factor_data/universe.py` (PIT top-N, survivorship-free) |
| Factor engine | `factors/{engine,momentum,fundamental,cross_section}.py` |
| Backtester | `factor_data/backtest.py` (+vol/drawdown overlays); single-name `Backtester` |
| IS/OOS validator | `scripts/factor_research.py` (IC, long-short, decay, rolling IC, IS/OOS, dataset/universe version #154) |
| Robustness | `scripts/range_5c_gate.py`, overlay/window sweeps |
| Promotion gate | §5c gate (range-trader-specific; already GO/GO-WARNING/NO-GO/INCONCLUSIVE) |
| Evidence | `research/*.md` + findings docs |

## Sessions (reviewer's build order: registries → orchestrator → gate → revalidation → dashboard)

### §1 — Five registries + dependency graph + transition log · ~7–9h
A dedicated `research.duckdb`. The **FK chain IS the dependency graph**: strategy →
features → dataset → experiment → artifact.

```sql
CREATE TABLE strategies_registry (
  strategy_id VARCHAR PRIMARY KEY, name VARCHAR, category VARCHAR,
  research_state VARCHAR, deployment_state VARCHAR,    -- the two axes (§1)
  paper_since TIMESTAMP, live_since TIMESTAMP, retired_at TIMESTAMP,
  current_version VARCHAR, current_commit VARCHAR, owner VARCHAR, notes VARCHAR);

CREATE TABLE features (
  feature_id VARCHAR PRIMARY KEY, description VARCHAR, formula VARCHAR,
  parameters JSON, introduced_in VARCHAR, deprecated_in VARCHAR);

CREATE TABLE datasets (
  dataset_id VARCHAR PRIMARY KEY, provider VARCHAR, version VARCHAR, created_at TIMESTAMP,
  coverage VARCHAR, row_count BIGINT, checksum VARCHAR, source_hash VARCHAR);

CREATE TABLE experiments (
  experiment_id VARCHAR PRIMARY KEY, parent_experiment_id VARCHAR,   -- DAG/genealogy
  created_at TIMESTAMP, duration_ms BIGINT, kind VARCHAR,
  strategy_id VARCHAR, dataset_id VARCHAR, feature_ids JSON,         -- dependency edges
  git_commit VARCHAR, host VARCHAR, python_version VARCHAR, package_versions JSON, seed BIGINT,
  params_json JSON, is_window VARCHAR, oos_window VARCHAR,
  cost_model VARCHAR, pit_mode VARCHAR, survivorship_mode VARCHAR,
  metrics_summary JSON, metrics_detail JSON, confidence_score INT,   -- 0–100 (§3)
  research_state VARCHAR, owner VARCHAR, notes VARCHAR);

-- ⭐ Artifact Registry: every report/json/chart/evidence file, versioned
CREATE TABLE artifacts (
  artifact_id VARCHAR PRIMARY KEY, experiment_id VARCHAR,
  type VARCHAR, path VARCHAR, checksum VARCHAR, created_at TIMESTAMP, description VARCHAR);

-- ⭐ Transition log: the "why" audit trail for every state change
CREATE TABLE transitions (
  transition_id VARCHAR PRIMARY KEY, entity_type VARCHAR, entity_id VARCHAR,
  axis VARCHAR,                                  -- 'research' | 'deployment'
  from_state VARCHAR, to_state VARCHAR, reason VARCHAR, at TIMESTAMP, actor VARCHAR);
```
Deliverables: schema + typed `record_*`/`get_*` APIs + a `dependencies(entity)`
query (walks the FK graph); `factor_research`/backtest drivers write experiment +
artifact rows referencing strategy/dataset/feature ids; #154 `_dataset_version`
feeds `datasets`. Tests: round-trip, FK/graph integrity, idempotency, a
transition writes a reason.

### §2 — ResearchEngine orchestrator + evidence + artifact capture · ~6–8h
One entrypoint: config → Universe → Features → Factor → Backtest → IS/OOS →
Robustness → Gate → evidence package + **registry & artifact rows** (reuse, don't
rebuild). Caches by `experiment_id`. **No dashboard yet** (built last). Deliverables:
`app/research/engine/` + CLI; evidence writer that registers each output as an artifact.

### §3 — Lifecycle gate + confidence score · ~6–8h
Generalize §5c into `promotion_gate(metrics, profile)` that:
- transitions **research_state** (RESEARCH→VALIDATED/REJECTED) and proposes
  **deployment_state** moves, writing a `transitions` row **with a reason** each time;
- computes a **⭐ confidence score 0–100** from OOS stability + trade count +
  robustness + rolling IC (surfaced in dashboards/decisions);
- uses per-`kind` threshold profiles (reuse §5c's frozen criteria as `book_backtest`).
Deliverables: gate + score + `docs/runbook/promotion-workflow.md` (Research → GO →
Paper → Paper Validation → Promotion Review → Live Candidate → Live → Monitoring).
Tests: existing §5c cases pass unchanged; score is deterministic; transitions logged.

### §4 — Continuous revalidation + comparison · ~6–8h
- **Continuous revalidation** (the loop-closer): a scheduled monthly job re-runs
  IC + rolling Sharpe/turnover/drawdown for PAPER/LIVE strategies; a threshold
  breach writes a **Research Alert** + a `transitions` proposal toward RETIRED
  (owner-reviewed, never auto-retire). Reuses the existing scheduler; read-only.
- **`compare_experiments`** — A/B/C table (Sharpe/CAGR/MaxDD/turnover/IC, winner per
  metric) from the registry.

### §5 — Dashboard (last) + ADR + subsystem move · ~5–7h
Now that the data model is stable, generate `research/dashboard.md` (latest
experiments by state, active vs retired strategies, confidence scores, the
experiment DAG). Write the subsystem-boundary ADR; move/alias research code under
`app/research/`; update `tasks/todo.md` + runbooks.

## Follow-on phases (reviewer's ordering)

- **Phase 3A — Portfolio research:** weighting / count / cadence / reconstitution delay / buffering / hysteresis **+ transaction_cost + rebalance_delay** sweeps ("construction often adds more value than another factor").
- **Phase 3B — Factor expansion:** Growth / Profitability / Capital allocation / Risk / Liquidity → 20–40 candidates (plug into the feature registry). *Also Phase 3:* the deferred niceties (experiment tags, baseline-comparison fields, resource metrics, lineage visualization, research-KPI pages) and **meta-research** ("research about research": which factor families/universes/parameter ranges survive OOS).
- **Phase 4 — Broaden universe** (top-200 → top-1000, small/mid/international); re-run everything (gated on the as-reported + delisted-coverage upgrades, per the FMP PIT doc).
- **Phase 5 — Options/futures/ETFs/international** (only after the equity platform is mature).

## Scope boundaries (non-negotiable)

- **Read-only, off the order path** (ADR 0018) — validate, don't execute.
- **No new external dependencies**; local-first DuckDB; OS-trust-store TLS.
- **Reuse, don't rebuild** — the value is integration.
- **Freeze the design here.** Build §1–§5, validate with 5–10 real experiments, then let practical experience drive Phase 3 — do not expand the Phase-2 design further.

## Decisions (locked for v1.0)

1. **Registry storage:** a dedicated `research.duckdb` (the Research Engine is its own subsystem), not an extension of `factor_data.duckdb`.
2. **Gate threshold profiles:** §5c's frozen criteria are the `book_backtest` profile; `factor_ic` thresholds are set in §3 against the existing momentum/value/quality results (momentum = the positive reference, value/quality = the negative reference).
3. **Generalization discipline:** build the minimum that serves the next 2–3 real experiments; no speculative framework.

## Notes & gotchas

1. `Date.now()`/randomness are fine in scripts; **store the seed** (reviewer: very useful) + git_commit + package_versions at run time.
2. The book backtest is slow (~7 min/segment); cache by `experiment_id`.
3. Artifacts: register the file + checksum; keep committed `.md`/`.json` in `research/`, gitignored data out.
4. Continuous revalidation reuses the breaker-monitor scheduler pattern; it must stay read-only — an **alert**, never an auto-trade or auto-retire without owner review.
5. The dependency graph is just the FK chain (strategy→features→dataset→experiment→artifact) + a walk query; don't build a graph DB.
