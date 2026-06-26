# Trading Workbench — P10 Phase 3A: Portfolio Construction Research

| Field | Value |
|---|---|
| Document version | **v1.0 (2026-06-18 — FROZEN FOR EXECUTION).** Incorporates reviewer round-3 (final) comments.md: §0 resolved, two-PR split formalized, GO/NO-GO thresholds frozen (§4.7a), artifact retention rules (§4.9), result-interpretation template (§4.10), do-not-promote reminder at the gate. Reviewer verdict: "ready to execute." |
| Date | 2026-06-18 |
| Phase | P10 — Portfolio-Level Risk Engineering · **Phase 3A** (Portfolio Engine) |
| Session | §3A of Phase 3 (predecessor §3.0 registries; successor §3B Analytics) |
| Predecessor | §3.0 registries — PR #162 (`6a431ab`, OPEN at time of writing) on top of Phase 2 complete (`55340d0`, PR #160) |
| Successor | §3B — Analytics (alpha / turnover / drawdown *attribution*, full capacity model) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Establish a **reproducible framework for evaluating portfolio construction methods**: split portfolio *model* from *instance*, add a risk-model registry + the experiment FK wiring, enforce portfolio invariants, make every experiment emit a standard evidence bundle (incl. stability + basic capacity + regime slices), add a `portfolio_construction` runner + transparent gate scorecard, and run the first comparison study (equal-weight vs inverse-vol vs diagonal-risk-parity) against versioned benchmark classes. *Discover which construction methods are robust* — do not add knobs, do not add optimizers. |
| Estimated wall time | 8–11 hours (substantial: registry additions + backtester extension + orchestrator FK wiring + evidence bundle + new runner/scorecard + regime-sliced comparison study + invariants/health-check tests + runbook) |
| Tag on completion | `p10-phase3a-complete` |
| Out of scope | Covariance-aware optimizers / mean-variance / Black-Litterman / risk budgeting (reviewer's explicit final warning); daily exposure overlay (separate engine — roadmap §2); fractional shares (roadmap §7); live/paper deployment of any method; new alpha signals; regime-*conditioned* construction (regimes are a reporting *slice*, never a method that switches weighting); full capacity model + attribution decomposition (→ §3B) |

---

## §0 — Resolved decisions (frozen; was "open questions")

Resolved by the reviewer's final comments.md ("My preferred choices"). Frozen.

1. **`cost_model` field migration → ADDITIVE.** Keep the legacy free-text
   `cost_model` descriptor; add a new `cost_model_id` FK column. Preserves Phase-2
   `factor_ic` rows and their fingerprints. *(reviewer: "additive cost_model_id")*

2. **FK ids do NOT join the fingerprint → fingerprint on CONTENT.** Random ids
   (`pf_…`/`cost_…`/`rm_…`) would make identity non-reproducible. The runner folds
   the referenced records' **content** (portfolio spec / numeric cost params /
   risk-model spec / benchmark *definition+version*) into `config.params` (already
   hashed); the resolved random ids ride as **provenance** only. `fingerprint()`
   unchanged. *(reviewer: "fingerprint on content, not random IDs")*

3. **Risk Model Registry → INCLUDE NOW**, as the leading commit of **PR A**
   (mirrors §3.0). *(reviewer: "include risk model registry now")*

4. **Construction trio → equal_weight / inverse_vol / `risk_parity_diagonal`.**
   Renamed from `risk_parity_lite`. ⚠ **The reviewer's caveat is accepted and made
   explicit:** since `risk_parity_diagonal == inverse_vol` in v1, the first study is
   *materially* a **two-method** comparison (equal-weight vs inverse-vol); the
   diagonal variant is retained **only as a labeled future seam** and the study
   artifact must say so plainly (no pretending it's three independent methods). See
   §4.4 + Gotcha 5.

5. **Benchmark classes & SPY → DEFER SPY.** Ship the first study with Factor
   (`equal_weight_universe`), Version (`momentum_v0.3`), and Portfolio
   (`previous_best_experiment`) classes — no new data. The Market/SPY class is
   deferred to §3B. *(reviewer: "defer SPY benchmark")*

6. **Study store → FULL-HISTORY** `factor_data_full.duckdb` (~28.5 yr); record the
   dataset row's `survivorship_mode`/`coverage` honestly and read **relative**
   cross-method ΔmaxDD as the signal. *(reviewer: "run full-history store")*

7. **Two-PR split → ADOPTED** (reviewer's recommendation; scope is large):
   - **PR A — framework:** risk-model registry, FK wiring, portfolio invariants,
     scorecard component breakdown + `min_confidence` floor plumbing. *(this
     session, first)*
   - **PR B — study:** weighting extension, `portfolio_construction_runner`, the
     **evidence-bundle helper** (`build_evidence_bundle`), comparison study,
     results/result-interpretation artifact. *(stacked on PR A)*
   Each PR carries its own ≥1hr walk-away. Split point is the §2 framework/study
   seam. **Execution note:** the evidence-bundle helper moved from PR A → PR B
   because it is coupled to the runner's `MomentumBacktestReport` shape and is only
   testable end-to-end alongside the runner; landing it in PR A would add untested
   surface nothing calls. The PR-A scorecard plumbing it depends on ships here.

---

## §1 — Why this session exists

Phase 2 made the *research process* a first-class subsystem (ADR 0019): every
experiment is content-addressed, provenance-stamped, gated, queryable. Phase 3
turns that subsystem on the **Portfolio Engine** — the layer between alpha
(momentum selection, **frozen** per Review v2) and risk (the breaker).

The reviewer's mandate for Phase 3 was a *mindset*: **"portfolio science, not
portfolio engineering"** — don't bolt weighting knobs onto the strategy; *discover
which construction methods are robust* and let evidence decide. The round-2 review
of this doc's v0.1 sharpened that into a concrete instruction: **expand the
evidence framework and the registry vocabulary, keep the set of methods tiny.**
Every round-2 recommendation is about *what each experiment records* (invariants,
stability, capacity, regime slices, a standard evidence bundle, a transparent
scorecard) or *how portfolios/risk are identified* (model vs instance, a risk-model
registry, versioned benchmark classes) — none adds an optimizer. The closing
warning is explicit: *resist covariance optimizers / Black-Litterman / risk
budgeting; 3A's purpose is the reproducible evaluation framework.*

§3.0 shipped the portfolio/benchmark/cost-model registries but they are **inert** —
nothing references them. This session closes that loop and makes the framework real:
the FK wiring §3.0 deferred to "3A," the missing risk-model registry, the invariants
and evidence every experiment must satisfy/emit, and the **first comparison study**
so the registries hold real, regime-sliced, scored rows the dashboard can show.

The deliverable is **"the research engine can answer, with a reproducible evidence
package: across regimes, which construction method on the frozen momentum signal
gives the best risk-adjusted, stability- and capacity-aware book."** Enabling any
method on the live book stays a later, owner-gated deployment decision (ADR 0019).

---

## §2 — What this session ships

1. **Portfolio *model* vs *instance* split** (reviewer #1) — the reusable
   `portfolio_models` row is the *model* (Momentum12 + InverseVol); the
   *instantiated* portfolio (that model run against a dataset/window on a date)
   *is* the experiment. No new table — the experiment **is** the instance, joined
   to its model by FK. Documented as the identity contract that later enables
   paper/live/historical portfolio snapshots.
2. **`risk_models` registry + `risk_model_id` FK** (reviewer #2) — a 6th registry
   making vol-target / sector-cap / max-position first-class and separable from
   alpha. Leading commit, mirrors §3.0.
3. **Experiment ↔ registry FK wiring** — `portfolio_id`, `benchmark_id`,
   `cost_model_id`, `risk_model_id` columns on `experiments` (+ `ExperimentConfig` /
   `ExperimentRecord` fields + orchestrator persistence), content-addressed by the
   referenced records' *content* (§0 Q2).
4. **Portfolio invariants** (reviewer #3, ⭐⭐⭐⭐⭐) — a documented + code-enforced set
   of mathematical properties every weight vector must satisfy (sum, sign, NaN,
   determinism, explicit cash), asserted in the weigher and tested independently of
   method.
5. **Backtester weighting extension** — `run_momentum_backtest(weighting=...)`
   adding `inverse_vol` and `risk_parity_diagonal` alongside the default
   `equal_weight` (byte-for-byte unchanged, default-inert), no-look-ahead vol.
6. **Standard evidence bundle + stability + basic capacity + regime slices**
   (reviewer #5/#6/#7/#10) — every `portfolio_construction` experiment emits the
   *same* artifact set (equity, drawdown, rolling Sharpe/vol/turnover, sector
   weights over time, top holdings by period, rebalance log) and records weight-
   stability metrics, basic capacity metrics, and per-regime (bull/bear/high-vol/
   low-vol) sliced summaries — without changing the method.
7. **`portfolio_construction_runner` + transparent `portfolio_backtest` scorecard**
   (reviewer #4/#9) — runner produces book-vs-benchmark metrics incl. downside/tail
   (Sortino, Calmar, Ulcer, worst month, worst rolling 3m, recovery time); the gate
   exposes **component scores** (statistical / OOS stability / drawdown / turnover /
   capacity) summing to the 0–100 confidence ("Research Scorecard").
8. **Portfolio health checks** (reviewer #11) + **first regime-sliced comparison
   study** (CLI) over versioned benchmark classes, with the **comparison report as
   a first-class registry artifact** (reviewer #10 minor) — plus tests, the runbook
   update, and the **explicit Phase-3A success criteria** (§6, reviewer #12).

*(Deliverable count is higher than the ≤8 ideal because the round-2 review widened
the framework; each remains a concrete, pointable artifact. If this proves too
large for one PR, split at the natural seam: a "framework" PR — items 1–4 + 7's
scorecard plumbing — then a "study" PR — items 5–8. Decide at §0.)*

---

## §3 — Prerequisites

- **§3.0 registries merged** (PR #162) — the FK wiring imports the §3.0 records and
  alters `experiments`. Rebase this branch onto `main` after #162 lands; do not
  start §4.3 before then.
- **Phase 2 complete** (`55340d0`) — orchestrator/gate/compare/dashboard present
  (verified: `app/research/{engine,promotion,monitor,comparison,dashboard}/`).
- **A factor store with regime breadth** — full-history `factor_data_full.duckdb`
  for the §5 study (study-time input, not a code prerequisite; the study still runs
  on the live store with a noted breadth caveat).
- **No new external dependency** — everything reads the existing SEP store; ADR 0019
  read-only / off-order-path contract preserved (no order-path import).

---

## §4 — Detailed work

### §4.1 — Model vs instance, and the experiment FK wiring

**Identity contract (reviewer #1).** A `portfolio_models` row is a *reusable model*
(strategy + construction_method + weighting + rebalance + buffer + risk/turnover/
capacity descriptors). A *portfolio instance* = that model **applied to a dataset
over a window** — which is exactly what an `experiment` already is. So the instance
needs **no new table**: the experiment row, joined to `portfolio_id` (+ `dataset_id`,
`benchmark_id`, `cost_model_id`, `risk_model_id`, window), *is* the instance. This
keeps the model reusable across many experiments and sets up later paper/live/
historical portfolio snapshots (a snapshot will reference the same `portfolio_id`).

Add four nullable FK columns to `experiments` (additive; existing rows → NULL).
The schema is `CREATE TABLE IF NOT EXISTS` in `store.py::_SCHEMA`; for an existing
store, run idempotent guarded `ALTER`s (DuckDB: check `information_schema.columns`
before `ADD COLUMN`):

```sql
ALTER TABLE experiments ADD COLUMN portfolio_id   VARCHAR;
ALTER TABLE experiments ADD COLUMN benchmark_id   VARCHAR;
ALTER TABLE experiments ADD COLUMN cost_model_id  VARCHAR;
ALTER TABLE experiments ADD COLUMN risk_model_id  VARCHAR;   -- §4.2
```

`ExperimentConfig` and `ExperimentRecord` gain the four fields (**appended** after
`notes` — see Gotcha 1). The orchestrator persists them.

> **Decision (§0 Q1/Q2): additive + content-fingerprint.** Keep the legacy free-text
> `cost_model` descriptor; `cost_model_id` is the new FK. Do **not** hash the random
> ids into `fingerprint()` — the runner folds the referenced records' *content*
> (portfolio spec / numeric cost params / risk-model spec / benchmark
> *definition+version*) into `config.params` (already hashed) and passes the random
> ids as provenance. `fingerprint()` itself is unchanged.

### §4.2 — Risk Model Registry (reviewer #2, ⭐⭐⭐⭐⭐)

A 6th registry, added in a leading commit mirroring §3.0's pattern in `store.py`:

```sql
CREATE TABLE IF NOT EXISTS risk_models (
  risk_model_id VARCHAR PRIMARY KEY, kind VARCHAR,            -- none|vol_target|sector_cap|max_position|drawdown_overlay
  vol_target_annual DOUBLE, vol_ewma_span INTEGER,
  max_sector_pct DOUBLE, max_position_pct DOUBLE,
  drawdown_trigger DOUBLE, params VARCHAR, description VARCHAR, created_at TIMESTAMP
);
```

```python
@dataclass
class RiskModelRecord:
    risk_model_id: str = ""
    kind: str = "none"                  # none | vol_target | sector_cap | max_position | drawdown_overlay
    vol_target_annual: float | None = None
    vol_ewma_span: int | None = None
    max_sector_pct: float | None = None
    max_position_pct: float | None = None
    drawdown_trigger: float | None = None
    params: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    created_at: datetime | None = None
```

`record_risk_model` / `get_risk_model` / `list_risk_models` follow the §3.0 method
pattern exactly; `row_count` allowlist + `__init__` exports updated. This makes the
already-shipped vol-target overlay (roadmap §1) and sector-cap (roadmap §3) **named,
versioned risk models** an experiment references via `risk_model_id` — keeping alpha
research and risk research independent (reviewer's stated goal). The `vol_target_*`
fields back the existing overlay; `max_sector_pct` / `max_position_pct` are recorded
now and *consumed* by the weigher only where already supported (vol-target),
sector-cap consumption stays a §3B/strategy concern (recorded ≠ enforced here).

### §4.3 — Portfolio invariants (reviewer #3, ⭐⭐⭐⭐⭐)

A small `app/factor_data/portfolio.py` (or `app/research/portfolio_invariants.py`)
with a single `assert_valid_weights(w: dict[str, float], *, cash: float, long_only:
bool = True)` enforcing properties that hold **regardless of weighting method**:

- **Sum:** `sum(w.values()) + cash ≈ target_gross` (default 1.0) within tolerance.
- **Sign:** no negative weights when `long_only`.
- **Finiteness:** no NaN / inf weights.
- **Determinism:** identical scores → identical ordering → identical weights
  (tie-break by ticker, as the harness already sorts deterministically).
- **Stability for identical inputs:** same store + args → same weights (the existing
  prefix-invariance discipline).
- **Deterministic turnover:** turnover is computed the same way every run.
- **Explicit cash:** cash allocation is explicit (fully invested, or a defined
  `cash_buffer`) — never an implicit residual.

The weigher (`_weigh`, §4.4) calls `assert_valid_weights` before returning, so an
invariant violation fails the experiment loudly rather than producing a silently
wrong book. Tested independently of method (one parametric test over all three
weightings asserts every invariant).

### §4.4 — Backtester weighting extension

`run_momentum_backtest` (factor_data/backtest.py) gains `weighting` +
`vol_lookback_days`. Today `book_select` (backtest.py:292) hard-codes equal weight;
replace the weight assignment with a pluggable `_weigh`:

```python
def book_select(d: date) -> dict[str, float]:
    ranked = scores_by_date[d]
    k = max(1, math.ceil(len(ranked) * top_quantile))
    chosen = ranked[:k]
    return _weigh(store, chosen, d, method=weighting,
                  vol_lookback_days=vol_lookback_days)   # invariant-checked, sums to 1.0
```

- `equal_weight` → `1/len(chosen)` (identical to today; regression guard asserts
  byte-for-byte curve equality).
- `inverse_vol` → `w_i ∝ 1/σ_i`, normalized, σ_i = trailing realized daily-return
  vol over `vol_lookback_days` ending **strictly before** `d` (no-look-ahead, mirrors
  `_vol_target_overlay` at backtest.py:125). Insufficient history / σ≈0 → fall back
  to cross-sectional median σ (never divide-by-zero).
- `risk_parity_diagonal` → equal risk contribution under a **diagonal** covariance
  (no off-diagonal, no optimizer) — which *is* inverse-vol in v1. A named seam; the
  equality is documented in code + the study artifact (Gotcha 5), not a bug.

The vol-target overlay (`vol_target_annual`, now sourced from the experiment's
`risk_model`) is unchanged and composes *on top of* any weighting.

### §4.5 — `portfolio_construction_runner` + standard evidence bundle

New runner in `engine/runners.py` (pattern: `factor_ic_runner` — adapter over
existing study code, compute nothing here). It calls `run_momentum_backtest` with
the §4.4 `weighting`, then shapes the `MomentumBacktestReport` into:

- **`metrics_summary`** (flat dict the scorecard reads): `sharpe, sortino, calmar,
  ulcer_index, cagr, total_return, max_drawdown, worst_month, worst_rolling_3m,
  recovery_days, benchmark_sharpe, benchmark_max_drawdown, excess_sharpe,
  excess_max_dd, turnover_annual, n_rebalances` + **stability** (`avg_weight_change,
  max_weight_change, avg_names_added, avg_names_removed`) + **basic capacity**
  (`avg_position_size, avg_adv_participation, avg_daily_turnover,
  max_rebalance_notional`).
- **`metrics_detail`**: full book/baseline/vol-scaled summaries, skipped-rebalance
  count, per-rebalance turnover + stability series, **per-regime sliced summaries**
  (bull/bear/high-vol/low-vol — §4.6).
- **Standard evidence bundle (reviewer #10)** — *every* experiment emits the **same**
  artifact set so experiments are comparable: `equity_curve`, `drawdown_curve`,
  `rolling_sharpe`, `rolling_vol`, `rolling_turnover`, `sector_weights_over_time`,
  `top_holdings_by_period`, `rebalance_log`. Implemented as a single
  `build_evidence_bundle(report)` helper returning the list of `ResearchArtifact`,
  reused by any future portfolio runner.
- **Health checks (reviewer #11)** — before returning, assert: no missing prices on
  held names, no missing factor values, no duplicate holdings, no stale weights,
  sector-classification completeness ≥ threshold, benchmark availability. A failed
  check raises → the experiment is rejected at run time (data-quality caught early).

Capacity/ADV note: ADV participation uses SEP volume we already have (roadmap §6 #6).
This is *basic metric collection now to avoid re-running later* (reviewer #7) — the
full capacity *model* stays in §3B.

### §4.6 — Regime slices (reviewer #6)

The study **auto-reports** sub-window summaries without changing the method. Classify
each backtest day into bull / bear / high-vol / low-vol from the **baseline universe
curve** (e.g. above/below its 200-day MA for bull/bear; above/below median rolling
realized vol for high/low) — computed from data already in the curve, no new
dependency, no look-ahead beyond each day's trailing window. The runner emits a
per-regime metrics block in `metrics_detail`; the comparison artifact tabulates each
method × regime. This is a reporting slice only — **never** a method that switches
weighting by regime (out of scope, §7).

### §4.7 — `portfolio_backtest` transparent scorecard (reviewer #4/#9)

New `GateProfile` in `promotion/gate.py`, registered in `PROFILES`. To expose
**component scores** (reviewer #9), tag each `Criterion` with a `component` and
extend `evaluate`/`GateResult` to emit a per-component breakdown alongside the single
0–100 confidence:

```
Component            Weight   Criteria (examples)
statistical          30       sharpe, sortino, excess_sharpe
oos_stability        25       oos-vs-is sharpe ratio, rolling-sharpe positive %
drawdown             20       maxDD <= benchmark maxDD (×2), calmar, ulcer
turnover             15       turnover_annual <= ceiling, weight-stability
capacity             10       avg_adv_participation <= ceiling, max_rebalance_notional
                     ----
                     100  →  e.g. 24/30 + 22/25 + 18/20 + 10/15 + 7/10 = 81/100
```

`evidence_key = n_rebalances` (floor ~52 ≈ 1yr weekly; strong ~156 ≈ 3yr).
**Raw return is deliberately not a criterion** — risk-adjusted + downside only
(the review's framing). All thresholds are **§0-confirmable placeholders**. The
component breakdown is stored in `metrics_detail` and rendered by the dashboard, so
two portfolios' differing scores are explainable, not opaque.

> Implementation note: `GateProfile.criteria` is currently a flat `list[Criterion]`
> with `weight`. Add an optional `component: str` to `Criterion` and group in
> `evaluate`; when unset, all criteria fall in a single `"overall"` component, so the
> existing `book_backtest` / `factor_ic` profiles are unchanged.

> **⚠ A `portfolio_construction` GO means research-valid, NOT deployable.** A GO
> verdict transitions only the experiment's `research_state` → VALIDATED. It does
> **not** move any `deployment_state`, touch the live paper book (id=2), or authorize
> paper/live trading. Deployment stays an owner decision via the promotion-workflow
> runbook (ADR 0019: the gate validates, the monitor alerts, the owner acts). This
> reminder is intentionally duplicated here (it also appears in §1/§8) because it is
> easiest to forget exactly at the gate. *(reviewer: "add do-not-promote near the
> gate profile")*

#### §4.7a — Frozen GO/NO-GO thresholds (reviewer: "freeze before running")

These are **frozen before the study runs** so the gate is pre-registered, not
tuned to the result (the §5c discipline). A method must satisfy **all** to earn GO:

| Gate criterion | Threshold | Component | Weight |
|---|---|---|---|
| Minimum confidence score | **≥ 70 / 100** (overall) | — (meta) | — |
| Book Sharpe | ≥ 0.5 | statistical | 2.0 |
| Sortino | ≥ 0.7 | statistical | 1.0 |
| Excess Sharpe (vs benchmark) | ≥ 0.0 | statistical | 1.0 |
| OOS Sharpe ≥ 0.8 × IS Sharpe | ratio ≥ 0.8 | oos_stability | 2.0 |
| Rolling-Sharpe positive fraction | ≥ 0.55 | oos_stability | 1.0 |
| **Max drawdown ≤ benchmark maxDD** | `excess_max_dd ≥ 0` | drawdown | 2.0 |
| Calmar | ≥ 0.5 | drawdown | 1.0 |
| **Max annual turnover** | ≤ **400%** (`turnover_annual ≤ 4.0`) | turnover | 1.0 |
| Max single-name weight stability | `max_weight_change ≤ 0.25` | turnover | 1.0 |
| **Max ADV participation** | ≤ **2%** (`avg_adv_participation ≤ 0.02`) | capacity | 1.0 |
| **Minimum rebalances** (evidence floor) | ≥ **52** (strong ≥ 156) | evidence | — |

The five the reviewer named explicitly are bolded + meta: **min confidence 70**,
**max turnover 400%**, **max DD ≤ benchmark**, **min 52 rebalances**, **max ADV
participation 2%**. Confidence below 70 → NO-GO even if individual criteria pass
(a deployable-research bar above the bare weighted average). Evidence below 52
rebalances → INCONCLUSIVE (can't pass or fail — thin sample). Raw return is **not**
a criterion (risk-adjusted only).

### §4.8 — Comparison study driver (`scripts/research_portfolio_study.py`)

Local-only CLI (pattern: `scripts/research_run.py`):

1. Open the chosen store (§0 Q6) + a `ResearchStore`.
2. Record the frozen momentum strategy row; **versioned benchmark rows by class**
   (Factor=`equal_weight_universe`, Version=`momentum_v0.3`, Portfolio=
   `previous_best_experiment`; Market/SPY deferred — §0 Q5). Benchmarks carry a
   **version field** (reviewer minor) so methodology changes don't silently alter
   historical comparisons.
3. One `PortfolioModelRecord` + `CostModelRecord` + `RiskModelRecord` per
   method × {no overlay, vol-target 15%}; build an `ExperimentConfig` with the four
   FK ids + content spec; `run_experiment(..., portfolio_construction_runner)`.
4. `gate_experiment(store, exp_id, profile="portfolio_backtest")` → component
   scorecard + confidence.
5. `compare_experiments([...ids...], metric=...)` (§4 comparison) across Sharpe /
   Sortino / Calmar / maxDD / turnover **and per regime** → write a ranked
   comparison report and **register it as a first-class artifact** (reviewer minor)
   on a dedicated "comparison" experiment or against the study, not just a loose MD.
6. `render_dashboard(store)` so lineage + scorecards are visible.

After this runs, all six registries hold real rows and `experiments` carry the four
FKs + component scores — the §3.0 registries are no longer inert.

### §4.9 — Artifact retention rules (reviewer: define committed/gitignored/size/checksum)

The evidence bundle (§4.5) can be large and is *derived* (reproducible from the
content-addressed experiment), so retention is explicit:

| Artifact | Committed? | Notes |
|---|---|---|
| Comparison report (markdown, the decision doc) | **Committed** | Small, human-read, first-class registry artifact; the durable study output. |
| Result-interpretation block (§4.10) | **Committed** | Embedded in the comparison report. |
| `rebalance_log`, `top_holdings_by_period` (JSON) | **Committed** if < 256 KB each | Decision-relevant + small; else gitignored + checksummed. |
| Equity / drawdown / rolling-* curves, `sector_weights_over_time` | **Gitignored** | Bulky, fully reproducible from the experiment; regenerate on demand. |
| The DuckDB stores (`research.duckdb`, `factor_data*.duckdb`) | **Gitignored** | Already gitignored; never committed (ADR 0018/0019). |

Rules: **(a)** every artifact row stores a **sha256 checksum** (the orchestrator
already checksums at `orchestrator.py:167` — keep it for all bundle artifacts).
**(b)** Per-artifact **max committed size = 256 KB**; anything larger is written to
the gitignored `reports/` dir and only its registry row (path + checksum) is
committed. **(c)** Bundle artifacts go under a per-run `report_dir`
(`reports/<experiment_id>/`) so they're cleanly gitignorable as a unit. **(d)** A
committed artifact's checksum must match its registry row — `verify` re-checksums on
read (cheap integrity check; no hash chain needed — research is not the audit log).

### §4.10 — Result-interpretation template (reviewer: keep the study decision-oriented)

The comparison report ends with this fixed, decision-oriented block (one per study
run), so the artifact answers "what do we *do*," not just "what are the numbers":

```markdown
## Result interpretation — <study name>, <date>, <store + window>

- **Best method:**            <equal_weight | inverse_vol> (and by which metric)
- **Why:**                    <the evidence — which scorecard components decided it>
- **Risk tradeoff:**          <return given up vs drawdown/Sharpe gained>
- **Turnover impact:**        <annual turnover + weight-stability vs equal-weight>
- **Capacity impact:**        <ADV participation / max rebalance notional headroom>
- **Regime weakness:**        <which regime slice the winner is weakest in>
- **Recommended action:**     <e.g. "carry inverse_vol to §3B capacity study" —
                               NEVER "deploy"; deployment is owner-gated, ADR 0019>
- **Do NOT do:**              <explicit anti-actions, e.g. "do not enable on the
                               live book on this study alone; survivorship-biased pool">
```

The `Recommended action` line is constrained: it may recommend *further research*,
never deployment (see §4.7 do-not-promote reminder).

---

## §5 — Manual smoke

From `apps/backend` (host venv — roadmap gotcha #2; research-side, off the order
path, do **not** rebuild the container):

```bash
# 1. Unit suites green (the load-bearing invariants for this session)
uv run pytest tests/research/ tests/factor_data/test_backtest.py -q

# 2. equal_weight regression: the new weighting path reproduces the v0.3 curve
uv run pytest tests/factor_data/test_backtest.py -k "equal_weight_unchanged" -q

# 3. Portfolio invariants hold for every method
uv run pytest tests/factor_data/test_portfolio_invariants.py -q

# 4. End-to-end regime-sliced study against a real store
uv run python scripts/research_portfolio_study.py --store data/factor_data_full.duckdb \
    --start 2007-01-01 --end 2026-06-12 --n 200 --top-quantile 0.20

# 5. Registries populated + experiments carry all four FKs + component scores
uv run python -c "
from app.research.registry import ResearchStore
s = ResearchStore('data/research.duckdb', read_only=True)
for t in ('portfolio_models','benchmarks','cost_models','risk_models','experiments'):
    print(t, s.row_count(t))
for eid in s.list_experiments(kind='portfolio_construction'):
    e = s.get_experiment(eid)
    print(eid, e.portfolio_id, e.benchmark_id, e.cost_model_id, e.risk_model_id, e.confidence_score)
"
```

**Load-bearing assertion:** step 2 passes (equal-weight byte-for-byte unchanged —
the new code is inert for the existing book), step 3 passes (every method satisfies
the invariants), and step 5 shows `portfolio_construction` experiments with all four
non-NULL FKs and a gate confidence score with a component breakdown. No order is
submitted — read-only research (ADR 0019).

---

## §6 — Phase 3A success criteria (reviewer #12) — explicit "done"

Phase 3A is complete when **all** hold:

1. All three weighting methods run successfully end-to-end.
2. Experiments are reproducible (same config + code + data → cache hit, same id).
3. The standard evidence bundle is generated for every experiment.
4. The comparison artifact is generated **and registered** as a first-class artifact.
5. All six registries (strategy/feature/dataset/portfolio/benchmark/cost/risk —
   note: feature+dataset+strategy from Phase 2) are populated by the study.
6. Confidence scores **with component breakdowns** are computed and stored.
7. Benchmark comparisons (by class, versioned) are available.
8. Portfolio invariants pass for every method; health checks gate bad data.
9. **No regression in the equal-weight baseline** (the §5 step-2 guard).
10. The dashboard displays portfolio experiments + scorecards correctly.

---

## §7 — Walk-away discipline

**≥1 hour** (research-side; off the order path, no audit-subsystem or risk-engine
code). The PR touches `app/factor_data/backtest.py` and `app/research/` only —
neither in the order path nor the audit chain — so the 2-hour bar does not apply.
Honor the hour even though the change is additive and default-inert. *(If the
session is split into "framework" + "study" PRs per §2, each gets its own ≥1hr.)*

---

## §8 — What this session does NOT do

1. **No covariance-aware optimizers / mean-variance / Black-Litterman / risk
   budgeting** — the reviewer's explicit final warning. 3A is the *framework*;
   sophisticated optimization is a later phase built on it.
2. **No daily exposure overlay** — separate Overlay Engine (roadmap §2, Review v2 #2).
3. **No fractional shares** — roadmap §7; touches the order path, own session.
4. **No live/paper deployment** of any method — the gate *validates*; deployment is
   owner-driven (ADR 0019). Live paper book (id=2) untouched; it doesn't set
   `weighting`, so it stays equal-weight.
5. **No regime-*conditioned* construction** — regimes are a reporting *slice* (§4.6),
   never a method that switches weighting.
6. **No new alpha signal / factor** — momentum is frozen (Review v2 guardrail); this
   session changes *sizing*, never *selection*.
7. **No full capacity *model* or attribution decomposition** — basic capacity
   *metrics* are collected (§4.5) to avoid re-runs; the model + turnover/drawdown/
   alpha *attribution* are §3B.
8. **Sector-cap *enforcement* in the weigher** — the risk-model registry *records*
   `max_sector_pct`, but enforcing it in construction stays a §3B/strategy concern;
   3A records, it does not consume beyond the existing vol-target overlay.
9. **No SPY/Market benchmark class** in the offline backtester (deferred, §0 Q5)
   unless that question resolves to "add now."
10. **No frontend** — dashboard is the existing markdown renderer; no React work.

---

## §9 — Notes & gotchas

1. **Column-order fragility in `store.py`.** `record_experiment` uses a positional
   `INSERT OR REPLACE ... VALUES (?,…)` and `get_experiment` reads by index
   (`d[0]…d[24]`). **Append** the four FK columns to the `_SCHEMA` DDL, the INSERT
   list, and the get index map; bump the `?` count. A mismatch is silent until a
   round-trip test fails. Same discipline when adding `risk_models`.
2. **`equal_weight` must be the default and inert.** The backtester is the eval
   ground truth (ADR 0014); keep `weighting="equal_weight"` default so every existing
   test/backtest is unchanged. The §5 step-2 regression test is the guard.
3. **No-look-ahead in `_weigh` and in regime classification.** Both use only data
   strictly *before* the bar in question (mirrors `_vol_target_overlay`,
   backtest.py:125). The prefix-invariance test is the canary.
4. **Fingerprint reproducibility (§0 Q2).** Do **not** hash random
   `portfolio_id`/`cost_model_id`/`risk_model_id` into the experiment fingerprint —
   hash the referenced *content*. Get this wrong and every study run duplicates
   experiments. The benchmark *definition + version* (not its id) is the content.
5. **`risk_parity_diagonal == inverse_vol` in v1 is intentional** (diagonal
   covariance). Renamed from `risk_parity_lite` per the reviewer so the assumption is
   explicit. Document loudly in code + the study artifact so nobody "fixes" the
   apparent duplication — it is the seam for a future covariance-aware method.
6. **Run against the full-history store; read ΔmaxDD relatively.** Pool is
   survivorship-biased for deep windows (roadmap §6/§8). Cross-*method* comparison is
   the trustworthy signal; absolute returns are not. State it in the artifact.
7. **Host venv, not the container** (roadmap gotcha #2). `app/` edits need a
   `docker compose build backend` to reach the running container — but this session
   is validated via the host venv to avoid perturbing the live paper strategy. Do
   not rebuild the backend image as part of this session.
8. **Component scorecard back-compat.** Adding `component` to `Criterion` must leave
   `book_backtest` / `factor_ic` profiles unchanged (default component `"overall"`).
   Existing gate tests must stay green.
9. **Reviewer's framing is the acceptance test.** If the PR reads as "added weighting
   knobs to the strategy," it missed the point. The artifact must answer *"which
   construction method is most robust, with a reproducible evidence package and a
   transparent score"* — that is the Portfolio *Science* deliverable.
10. **Scope-vs-focus tension is real.** Round-2 widened the *framework* while warning
    to keep *methods* narrow. The resolution baked into this doc: expand registries /
    invariants / evidence / scorecard freely; the *method* set stays exactly three,
    all diagonal/linear, zero optimizers. If the PR grows unwieldy, split at the §2
    framework/study seam — do not drop framework items to fit one PR.
