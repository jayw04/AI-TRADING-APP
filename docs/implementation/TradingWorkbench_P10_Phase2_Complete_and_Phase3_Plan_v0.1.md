# P10 — Phase 2 complete + Phase 3 plan

| Field | Value |
|---|---|
| Document version | v1.0 (final — folds in review; execution started) |
| Date | 2026-06-17 |
| Phase | P10 — closing Phase 2, opening Phase 3 |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | What the Research Engine (Phase 2) shipped, and what Phase 3 is. |
| Related | Phase-2 plan v1.0 (`..._ResearchEngine_Phase2_Plan_v0.1.md`); ADR 0019; capstone v1.1 (`..._Strategy_Research_Report_v1.0.md`) |

---

## Part 1 — Phase 2: the Research Engine (COMPLETE, merged to main)

Phase 2 promoted the research process from a collection of scripts into a
first-class, read-only **Research Engine subsystem** (`app/research/`, ADR 0019) —
peer to the Trading / Risk / Portfolio / Data engines, strictly off the order path.
All five sessions are built, tested (42 tests, ruff + mypy clean), and merged.

| § | Delivered | PR |
|---|---|---|
| §1 | **Five registries** (strategies, features, datasets, experiments, artifacts) + **transition log** + **dependency graph** (FK chain) + two-axis lifecycle (research × deployment) | #156 |
| §2 | **Orchestrator** — `run_experiment()`: content-addressed (cache by config+code+data), provenance (git/host/python/versions/seed/duration), records experiment + checksummed artifacts; thin runners over existing study code | #157 |
| §3 | **Lifecycle promotion gate** — generalized §5c; profiles (`book_backtest` faithful to §5c, `factor_ic`); **confidence score 0–100**; transitions research_state with a reason; deployment stays owner-driven | #158 |
| §4 | **Continuous revalidation** (edge-decay → Research Alert, read-only/alert-only) + **`compare_experiments`** (direction-aware A/B/C) | #159 |
| §5 | **Dashboard** (KPIs, experiments by state + confidence, strategies by lifecycle, open alerts, experiment DAG) + **ADR 0019** | #160 |

**Subsystem layout:** `app/research/{registry,engine,promotion,monitor,comparison,dashboard}/`
+ CLIs `scripts/research_{run,compare,dashboard}.py` + `docs/runbook/promotion-workflow.md`.

**What it enables:** every future idea runs through one reproducible, versioned,
lifecycle-aware pipeline (run → gate → record → compare → dashboard → revalidate),
with full provenance and an audit trail — the same discipline that rejected
RangeTrader and value/quality and confirmed momentum, now systematized.

### Phase-1 context (already merged earlier in P10)
Momentum 12m upgrade (#143), R3 risk overlays (#150) + momentum-crash study (#151),
FMP data layer + Value/Quality study (#146–#148), capstone v1.1 (#149), evidence
hardening (#154), FMP PIT-assumptions doc + data-confidence (#152).

---

## Part 2 — Phase 3 plan

**Gating principle (reviewer):** do NOT keep expanding the design. **First validate
the engine with 5–10 real experiments**, then let that practical experience drive
Phase 3 priorities. Phase 3 work below is ordered per the reviewer's guidance
("portfolio construction usually adds more value than another factor").

### Immediate next step (before Phase 3 proper)
- **Run 5–10 real experiments through the engine** (`research_run.py` → gate →
  dashboard): the existing momentum/value/quality/low-vol/reversal studies, the
  momentum-window and overlay variants. Confirm registries, caching, gate verdicts,
  confidence scores, dependency graph, and the dashboard behave on real data — and
  surface what the engine is missing in practice (which should drive 3A/3B scope).

### §3.0 — Foundational registries (build first; reviewer ⭐⭐⭐⭐⭐)
Phase 3 generates many portfolio configs, benchmarks, and cost assumptions — they
deserve first-class identities, not JSON embedded in experiments. Extend the
registry layer with three registries (mirroring the §1 pattern):
- **`portfolio_models`** — portfolio_id, strategy_id, construction_method, weighting,
  rebalance, buffer, risk_model, turnover_model, capacity_model, created_at, status.
- **`benchmarks`** — benchmark_id, definition, source, rebalance, description
  (SPY/QQQ/equal-weight/prior-version, versioned).
- **`cost_models`** — model_id, commission, slippage, spread, borrow_cost,
  market_impact (experiments reference `cost_model_id`).
Experiments then reference `portfolio_id` / `benchmark_id` / `cost_model_id`.
**(Execution started here — see §3.0 implementation note at the end.)**

### Phase 3A — Portfolio **Construction** Research (highest value)
*Science, not engineering* — the goal is "discover which construction methods are
**robust**," not "add more knobs." Each portfolio model (from the registry) is run
through the §5c-style gate, IS/OOS, recorded as an experiment:
- weighting (equal / inverse-vol / risk-parity), name count, rebalance cadence,
  reconstitution delay, position buffering, rank hysteresis,
- **+ transaction-cost (cost_model) and rebalance-delay sweeps**,
- **+ regime-specific robustness (reviewer ⭐⭐⭐⭐):** evaluate each model across
  **bull / bear / sideways / high-vol / low-vol / rate-rising / rate-falling**
  regimes — "does it survive across regimes?" is worth more than another factor.

### Phase 3B — Analytics (deepen the evidence)
- **Alpha attribution** — decompose the edge by **selection / sizing / timing /
  risk-overlay** (and by sector / market-cap / holding): did momentum or vol-target
  create the improvement? was it 3 mega-caps or diversified?
- **Turnover attribution** — added / dropped / resized positions per rebalance.
- **Drawdown attribution** — drawdown → sector → stock → factor contribution.
- **Capacity analysis** — participation rate / ADV% / fill% / turnover (not just
  account size); where does the edge saturate?
- **Meta-research** ("research about research") — **edge persistence, parameter
  stability, regime sensitivity, feature importance** across the experiment history.

### Phase 3.5 — Paper Validation (reviewer ⭐⭐⭐⭐; the bridge to live)
A clean gate between research and live: research-passed → **paper account → ~90
days → revalidation → promotion**. Formalizes the deployment-axis transition
(PAPER → LIVE_READY) with paper evidence, using the §4 revalidation + gate.

### Factor-library expansion (parallel track within Phase 3/4)
Grow ~7 → 20–40 versioned **features** (Growth / Profitability / Capital-allocation
/ Risk / Liquidity), each gated IS/OOS. Run against cohorts in Phase 4.

### Cross-cutting: Research Scorecard (reviewer ⭐⭐⭐⭐)
Every completed experiment gets a scorecard — statistical quality, OOS stability,
turnover, capacity, robustness, regime stability, confidence → an **overall 0–100**
research score (extends the §3 confidence score; surfaced on the dashboard). Easier
to read than many individual metrics.

### Deferred niceties (opportunistic, not a phase)
Experiment **tags**, **baseline-comparison** fields, **resource metrics**
(runtime/memory/rows), experiment **lineage viz** + research **KPI** dashboard
pages + a **research-timeline** page (RangeTrader rejected → Momentum validated →
…). Add when a real experiment shows the need.

### Phase 4 (later) — broaden the universe by **cohort**
Not just top-200 → top-1000: define **size cohorts** (mega / large / mid / small /
micro) and compare Momentum / Quality / Growth **across cohorts** (richer than a
single bigger universe). **Gated on** the FMP **as-reported** ingest +
**delisted-name fundamental coverage** verification (FMP PIT-assumptions doc) before
any *positive* result is trusted.

### Phase 5 (much later)
Options / futures / ETFs / international — only after the equity platform is mature
(a platform project, not a strategy project).

### Recommended phase order (reviewer's final)
Phase 2 (done) → **§3.0 registries** → **3A Portfolio Construction Research** →
**3B Analytics** → **3.5 Paper Validation** → **Phase 4 broaden (cohorts)** →
Phase 5 options. Factor expansion + the scorecard run as parallel tracks. Each
stage builds on validated evidence from the previous one.

---

## Pending operational items (independent of the phases)

1. **Merge + deploy the Phase-1 review PRs** (#144 breaker baseline draft, #150–#155).
   The two drafts change live risk behavior and need a **backend restart** to take
   effect: **#144** (daily-loss breaker start-of-day baseline, ADR 0004 v2) and
   **#153** (vol-targeting on by default).
2. **Sector-data ingest** (Sharadar TICKERS with sector, or backfill from FMP
   profile) → then enable `max_sector_pct` on the momentum book (currently a no-op
   because the store's `tickers.sector` is empty — the crash study showed 24–56%
   tech concentration at troughs).
3. Wire **continuous revalidation** to the scheduler (monthly) once strategy
   run-configs are persisted (the core `revalidate()` is built and tested). Add a
   **quarterly full research replay** (recompute all factors / IC / rankings /
   evidence on newest data) to detect silent drift.

---

## §3.0 implementation note (execution started — no further design review)

Per the review ("stop expanding, start executing"), Phase 3 execution begins with
the foundational registries (§3.0): `portfolio_models`, `benchmarks`, `cost_models`
added to `ResearchStore` (typed records + `record_*`/`get_*`/`list_*` + experiment
FK references), following the §1 pattern. These unblock 3A (portfolio construction
research references portfolio/benchmark/cost-model ids). Subsequent steps proceed in
the recommended order without additional upfront design rounds.
