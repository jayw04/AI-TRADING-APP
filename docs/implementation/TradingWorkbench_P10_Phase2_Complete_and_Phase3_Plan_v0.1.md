# P10 — Phase 2 complete + Phase 3 plan

| Field | Value |
|---|---|
| Document version | v0.1 (for review) |
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

### Phase 3A — Portfolio-construction research (highest value)
Make construction a first-class, sweepable research axis (it "often adds more value
than another factor"):
- weighting (equal / inverse-vol / risk-parity), name count, rebalance cadence,
  reconstitution delay, position buffering, rank hysteresis,
- **+ transaction-cost and rebalance-delay sweeps** (reviewer: these matter as much
  as weighting),
- run through the §5c-style gate, IS/OOS, recorded as experiments.

### Phase 3B — Factor-library expansion
Grow from ~7 factors to 20–40 candidates, each a versioned **feature** in the
registry, each gated IS/OOS:
- **Growth** (revenue, EPS, FCF growth), **Profitability** (operating/gross margin,
  asset turnover, cash conversion), **Capital allocation** (buyback/dividend yield,
  net issuance, capex intensity), **Risk** (beta, vol, downside vol, skew),
  **Liquidity/market-structure** (gap frequency, ATR percentile, relative volume,
  VWAP deviation).

### Phase 3C — Analytics (deepen the evidence)
- **Alpha attribution** — decompose returns by sector / market-cap / factor /
  individual holdings (was it NVDA/MSFT/META = 70% of alpha, or diversified?).
- **Capacity analysis** — $100K → $100M (momentum saturates).
- **Meta-research** ("research about research") — which factor families / universes
  / parameter ranges historically survive OOS.

### Deferred niceties (fold in opportunistically, not a phase)
Experiment **tags**, **baseline-comparison** fields on experiments, **resource
metrics** (runtime/memory/rows), experiment **lineage visualization** + research
**KPI** dashboard pages. (All explicitly deferred in the Phase-2 review — add when a
real experiment shows the need.)

### Phase 4 (later) — broaden the universe
Top-200 → top-1000 (small/mid/international); re-run Value/Quality/Growth/multi-
factor through the same pipeline. **Gated on** the FMP **as-reported** ingest +
**delisted-name fundamental coverage** verification (per the FMP PIT-assumptions
doc) before any *positive* result is trusted.

### Phase 5 (much later)
Options / futures / ETFs / international — only after the equity platform is mature
(a platform project, not a strategy project).

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
   run-configs are persisted (the core `revalidate()` is built and tested).
