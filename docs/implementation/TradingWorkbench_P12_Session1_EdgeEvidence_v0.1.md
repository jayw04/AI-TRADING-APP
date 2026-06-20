# Trading Workbench — P12 §1: Edge Evidence Package (the baseline)

| Field | Value |
|---|---|
| Document version | **v0.2 — draft + review fold** (2026-06-20). v0.1 was the first plan; v0.2 folds the doc review (`comments.md`) — the research-platform elevation, all additive to the harness (no new operational features): an **Experiment ID** per run, a **reproducibility-metadata** block, a **dataset-health gate** before the backtest, an **outlier report**, a **stability score**, **benchmark characteristics**, a **decision-confidence** level, a **failure-analysis** section, the **strategy-version** field, and seed entries for the **research-debt register**. Drafted against P12 Direction (v0.3 carries the matching framework: strategy versioning, research pipeline, Go/No-Go gate, research debt). |
| Date | 2026-06-20 |
| Phase | **P12** — Validation & Results |
| Session | §1 of 4 (Edge evidence package — the baseline; owner-selected first) |
| Predecessor | P11 §5 (tag `p11-session5-complete`); P12 Direction v0.2 (`498051e`) |
| Successor | P12 §2 — Harden the live strategy (measure the lift), reusing this session's harness |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Build a **reproducible out-of-sample evidence harness** (`script → JSON → Markdown`) for the **current** momentum-portfolio book on the survivorship-free history, and produce the **baseline edge-evidence report**: full metrics vs three benchmarks (SPY TR · equal-weight · cash), a **cost-sensitivity sweep** (5/10/20/50 bps), **walk-forward** across regimes, and **statistical-confidence** (bootstrap CIs + p-value). Read-only research; **no order path, no strategy change.** |
| Estimated wall time | 6–9 hours (harness script + bootstrap/CI metrics + benchmark wiring + cost sweep + walk-forward generalization + tests + the results study doc) |
| Tag on completion | `p12-session1-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

P12's objective is to prove the strategy has a **real, honestly-measured edge** (Direction §0).
This session builds the *baseline*: a rigorous, **reproducible** measurement of the strategy as it
trades today, on the 28.5-yr survivorship-free store, read with full honesty (OOS, survivorship,
cost, capacity). It is deliberately first because (a) it establishes the honest starting point
every later claim is measured against, and (b) **the harness it builds is reused by §2 (measure
the lift of vol-scaling/sector-caps) and §3 (the multi-factor book)** — so building it well once
pays off three times.

The deliverable is not "the number went up." It is *defensible evidence*: a one-command pipeline
that emits the metrics, a study doc that interprets them with caveats, and — because P11 made the
live book replayable/reconciled — a provenance line tying the studied logic to what actually
trades. **Verifiability is the differentiator** (Direction §0).

This session also instantiates the Direction's research governance (§4): it is the first entry in
the **Research Registry**, follows the **Evidence Package Template**, pins the **evidence
versions**, and ends with a **Decision Register** row.

## What this session ships

1. **Evidence harness** (`apps/backend/scripts/edge_evidence.py`) — one command runs the momentum
   backtest over a date range + universe, computes the full metric set + benchmarks + bootstrap
   CIs, and emits **JSON** (raw, machine-readable) **+ Markdown** (the interpreted report). CLI
   per the existing script convention (`argparse`, `FactorDataStore(read_only=True)`, `--report-dir`).
2. **Statistical-confidence module** (`apps/backend/app/factor_data/evidence.py`) — pure functions:
   bootstrap confidence intervals for CAGR/Sharpe, a p-value for "Sharpe > 0 / > benchmark", and
   the outcome distribution. Deterministic (seeded) so a re-run reproduces (Direction research
   invariant 5).
3. **Three benchmarks** — SPY total-return (via `benchmark.py::benchmark_metrics`), the
   equal-weight-universe baseline (already in `run_momentum_backtest`'s `baseline_curve`), and
   cash (0%). Reported side-by-side.
4. **Cost-sensitivity sweep** — the headline run repeated at **5 / 10 / 20 / 50 bps**
   (`turnover_cost_bps`), so capacity/robustness is explicit, not a single point.
5. **Walk-forward** — generalize the `walk_forward_vol_scaling.py` window pattern into a reusable
   `walk_forward()` over the regime windows: **n=80 / 5-window** for iteration, **n≈200 / 7-window**
   for the headline report.
6. **Two universes** — headline = live top-200 (what trades); appendix = full survivorship-free
   universe (robustness). Both from `dollar_volume_universe` / `universe_asof` (PIT).
7. **The baseline edge-evidence report** (`docs/implementation/TradingWorkbench_P12_Session1_EdgeEvidence_Results_v0.1.md`)
   — generated-then-interpreted, following the **Evidence Package Template** (Objective → Dataset →
   Methodology → Results → Limitations → Decision → Recommendation), with the evidence-version
   header and the Research Registry + Decision Register rows.
8. **Tests** (`tests/factor_data/test_evidence.py`) — the bootstrap/CI/p-value functions (known
   inputs → known bounds; determinism under seed), the JSON schema, and a smoke that the harness
   runs end-to-end on a small fixture window.
9. **Research-platform plumbing** (review fold, all additive): an **Experiment ID**
   (`EXP-YYYY-NNNN`) generated per run and stamped on the JSON + report; a **reproducibility
   metadata** block (Python/DuckDB versions · git SHA · dataset SHA · seed · duration · host ·
   generated-at); a **dataset-health gate** that runs *before* the backtest; an **outlier report**
   + **stability score**; **benchmark characteristics**; a **decision-confidence** level; a
   **failure-analysis** section; the **strategy-version** identifier; and the first **research-debt**
   entries.

## Prerequisites

- **The survivorship-free full-history store exists** — `apps/backend/data/factor_data_full.duckdb`
  (39M SEP rows, 1997→2026, incl. delisted names) per [[factor-research-program]]. The harness
  opens it read-only.
- **The backtest engine** (`run_momentum_backtest`) returns `equity_curve` + `baseline_curve` +
  `metrics`/`baseline_metrics` (+ optional `vol_scaled_*`); cost is the `turnover_cost_bps` param.
- **Existing metric helpers** — `app/strategies/metrics.py` (sharpe, max_drawdown),
  `app/research/engine/portfolio_eval.py` (sortino, calmar, ulcer), `app/research/engine/benchmark.py`
  (`benchmark_metrics`, `load_spy_curve`).
- **A full-history SPY series** — ⚠ **open prerequisite (see §C + Open questions):** SPY is an ETF,
  **not** in the Sharadar SEP store, and `load_spy_curve()` reads a *test fixture*
  (`tests/fixtures/spy_daily.parquet`) that may not span 1997–2026. A full-history SPY (or proxy)
  series must be sourced for the SPY benchmark over the headline window; until then the
  **equal-weight-universe baseline is the primary market benchmark** (it spans the full history)
  and SPY is reported over whatever window is available.

## Methodology (the Evidence Package Template — locked for every run)

```
Objective ─▶ Dataset ─▶ Methodology ─▶ Results ─▶ Limitations ─▶ Decision ─▶ Recommendation
```

- **Objective** — does the live momentum book carry a real, OOS, survivorship-free edge vs SPY /
  equal-weight / cash, robust to cost?
- **Dataset** — `factor_data_full.duckdb` (pinned date bounds + row count); live top-200 universe
  (headline) / full survivorship-free universe (appendix).
- **Methodology** — weekly long-only top-quintile momentum (the production config), equal-weight,
  cost-swept; walk-forward across 5–7 regime windows; bootstrap CIs + p-value.
- **Results / Limitations / Decision / Recommendation** — filled by the generated report.

**Evidence versioning** (header of every JSON + MD): `dataset_version` (store path + date-bounds +
row count), `code_version` (git short SHA), `factor_version` (momentum 6-1 / params), `walk_forward_version`,
`report_version`.

## Detailed work

### §A — Evidence harness script (`scripts/edge_evidence.py`)

```
python scripts/edge_evidence.py \
    --store data/factor_data_full.duckdb \
    --start 1997-12-31 --end 2026-06-12 \
    --universe live200          # or 'survivorship-free' (appendix)
    --costs 5,10,20,50 \
    --walk-forward 80x5         # or 200x7 for the headline
    --bootstrap 2000 --seed 17 \
    --report-dir docs/implementation/evidence/p12_s1
```

Boilerplate per the existing convention: `BACKEND_ROOT` on `sys.path`,
`FactorDataStore(db_path=..., read_only=True)` in try/finally, `argparse`, exit `0`. Output:
`edge_evidence.json` (raw) + `edge_evidence.md` (interpreted), plus a stdout summary table.

### §A2 — Dataset-health gate + reproducibility metadata (review fold)

**Before** any backtest runs, the harness emits a **dataset-health report** so every study answers
"can we trust the data?" automatically (reviewer's biggest gap):

```
Dataset health  →  date coverage (min/max, gaps) · row count · missing-price %
                →  delisted % · split/dividend-adjustment sanity · PIT validation
                →  survivorship validation (delisted names present)
```

A **fail-closed** gate: a health red-flag (e.g. a coverage gap in the window) is surfaced and the
run records it — the evidence report cannot silently sit on bad data.

Every run also stamps **reproducibility metadata** (the research analogue of Docker image
metadata) into the JSON header + report:

```json
"experiment_id": "EXP-2026-0001",
"repro": {"python": "3.12.x", "duckdb": "x.y", "git_sha": "…", "dataset_sha": "…",
          "seed": 17, "duration_s": 0.0, "host": "…", "generated_at": "<passed in, not Date.now>"}
```

`experiment_id` links the JSON, the Markdown report, the Decision Register row, and any notebook —
one id per execution. (`generated_at`/timestamps are passed in or read once at process start, not
sprinkled — same determinism discipline as §4 replay.)

### §B — Statistical-confidence module (`app/factor_data/evidence.py`)

```python
@dataclass(frozen=True)
class ConfidenceResult:
    point: float            # the metric (e.g. Sharpe)
    ci_low: float           # bootstrap percentile low (e.g. 2.5%)
    ci_high: float          # bootstrap percentile high (97.5%)
    p_value: float          # H0: metric <= 0 (or <= benchmark); one-sided
    n_resamples: int

def bootstrap_metric(daily_returns: Sequence[float], metric: Callable[[Sequence[float]], float],
                     *, n_resamples: int = 2000, seed: int = 17, alpha: float = 0.05) -> ConfidenceResult:
    """Stationary/block bootstrap of a curve metric. Pure + seeded (deterministic). No clock/IO."""

def sharpe_pvalue(daily_returns: Sequence[float], *, n_resamples: int = 2000, seed: int = 17) -> float:
    """One-sided bootstrap p-value for Sharpe > 0."""
```

Block bootstrap (returns are autocorrelated) — block length stated and tested. Seeded so a re-run
reproduces (research invariant 5). NB: `Math.random` is fine here (real Python `random`/`numpy`
with an explicit seed); the determinism requirement is *seeded*, not absent.

### §C — Benchmarks (SPY · equal-weight · cash)

- **Equal-weight** — already produced by `run_momentum_backtest` (`baseline_curve` /
  `baseline_metrics`); the primary market benchmark (full history). The book's excess return vs
  this is the headline alpha read.
- **SPY total-return** — `benchmark_metrics(book_curve, spy_curve)` → beta/alpha/IR/TE/correlation.
  ⚠ needs a full-history SPY series (Open question 1) — over whatever window is available, clearly
  labelled with its bounds.
- **Cash (0%)** — a flat 0% line; total return / Sharpe vs cash is the absolute read.

### §D — Cost-sensitivity sweep

Run the headline config at `turnover_cost_bps ∈ {5, 10, 20, 50}`; report CAGR/Sharpe/maxDD at each
+ the breakeven cost where excess-vs-benchmark → 0. Surfaces capacity honesty (a strategy that only
works at 5bps is a different claim than one robust to 50bps).

### §E — Walk-forward generalization

Lift the `WINDOWS` regime list + loop from `walk_forward_vol_scaling.py` into a reusable
`walk_forward(store, windows, *, n, **bt_kwargs)` returning per-window metrics. Dev runs use
n=80 / the existing 5 windows; the **headline** run uses n≈200 / 7 windows (add the 2 recent
windows). Report per-window + the across-window stability (mean/std/worst), the OOS honesty check.

### §F — The baseline edge-evidence report (study doc)

`..._P12_Session1_EdgeEvidence_Results_v0.1.md` — the generated numbers interpreted under the
Evidence Package Template, with the evidence-version header + `experiment_id`, the **Research
Registry** row (Momentum = Validated, with this study as evidence), the **Decision Register** row
(Decision = "baseline established; no enable/disable this session"; **Confidence = High/Medium/Low**),
and an explicit **Negative/Limitations** section. It also carries the review-fold sections:

- **Strategy version** — the report names the exact version it evaluates (e.g. **`1.0 — Momentum`**;
  §2 produces `1.1 — Momentum+VolScaling`, §3 `2.0 — Multi-factor`). Distinct from factor/report version.
- **Benchmark characteristics** — annual return · vol · maxDD · Sharpe · turnover for *each*
  benchmark (SPY/equal-weight/cash), so the comparison has context, not just the book's numbers.
- **Outlier report** — top-10 winners/losers, largest drawdown, highest-turnover rebalance, worst
  month, worst year (these usually explain surprises).
- **Stability score** — a one-word summary of the walk-forward (**Stable / Moderately stable /
  Unstable**) over the regime windows, alongside the full per-window table.
- **Failure analysis** — when/if the book underperforms a benchmark, *why*: sector concentration,
  turnover drag, crash exposure, factor decay. Institutional knowledge, not just "it lagged."
- **Research-debt seed** — the first entries of the Direction's research-debt register: *missing
  full-history SPY · capacity study · dividend-adjustment validation · liquidity model* — each
  marked Outstanding so methodological gaps stay visible.

### §G — Tests (`tests/factor_data/test_evidence.py`)

- `bootstrap_metric` / `sharpe_pvalue`: known synthetic series → CI brackets the point estimate;
  a zero-edge series → p-value ≈ not-significant; a strong-edge series → significant; **same seed →
  identical result** (determinism).
- JSON schema: the harness emits every required field incl. the evidence-version header.
- End-to-end smoke on a small fixture store window (a few years) → JSON + MD produced, exit 0.

## Manual smoke

1. `python scripts/edge_evidence.py --store data/factor_data_full.duckdb --start 2015-01-01
   --end 2020-01-01 --universe live200 --costs 10 --walk-forward 80x5 --bootstrap 500 --report-dir /tmp/ev`
   → `edge_evidence.json` + `.md` written; stdout shows CAGR/Sharpe/maxDD vs equal-weight + the CI.
2. The JSON header carries the 5 evidence versions; re-running with the same `--seed` reproduces the
   CIs byte-for-byte.
3. The MD report renders the Evidence Package Template sections + the benchmark + cost-sweep tables.

## Walk-away discipline

**≥ 1 hour.** §1 is **read-only research** — no order path, no risk engine, no strategy change, no
schema/migration. The lighter bar applies (it cannot affect live trading). Held to ≥1h, not the
audit/risk ≥2h bar.

## What this session does NOT do

- **No strategy change, no enabling anything** — it *measures* the current book; vol-scaling /
  sector-caps decisions are §2, multi-factor is §3.
- **No live-capital claim** — it produces the evidence a live decision would rest on; the decision
  is separate and owner-gated.
- **No order-path / risk-engine / scheduler touch** — pure research read.
- **No new strategy factor** — momentum only (the live book); new factors are §3.
- **No claim from paper P&L** — paper is plumbing-proof (§4 window), not edge (Direction §0 caveat).
- **No backtest-engine rewrite** — it *uses* `run_momentum_backtest`; only additive helpers
  (`evidence.py`) + the harness script.

## Open questions — to confirm before execution

1. **Full-history SPY series.** SPY isn't in the SEP store and `load_spy_curve()` reads a test
   fixture. Options: (a) source a full SPY daily series (Alpaca/another vendor) into a parquet; (b)
   use a broad ETF/index proxy already obtainable; (c) make the **equal-weight baseline the
   primary** benchmark and report SPY only over the fixture-available window. *Lean: (c) for this
   session (equal-weight spans the full history and is the ADR-0014 baseline) + flag (a) as a small
   data follow-on so a later report has full-history SPY.*
2. **Bootstrap style & block length.** Stationary bootstrap vs fixed-block; block length (e.g. 5,
   10, 21 trading days)? *Lean: fixed-block, length 21 (≈1 month) to respect monthly autocorrelation;
   report the choice + a sensitivity note.*
3. **Headline window granularity.** Add exactly which 2 windows extend the existing 5 to 7
   (2013–2016, 2016–2019, 2019–2022, 2022–2026 recut?). *Lean: keep the 5 existing + add 2019–2022
   and 2022–2026 for 7 contiguous regime windows.*
4. **Report-dir location.** `docs/implementation/evidence/` (committed artifacts) vs a gitignored
   `reports/`? *Lean: commit the JSON + MD under `docs/implementation/evidence/p12_s1/` so the
   evidence is versioned with the repo.*

## Notes & gotchas

1. **The harness is the asset** (Direction note 2). Build `edge_evidence.py` + `evidence.py` to be
   re-run by §2/§3 with different params — not a one-off script.
2. **Equal-weight is the honest market benchmark here**, not SPY, until full-history SPY is sourced
   — the live top-200 universe is survivorship-biased, so read book-vs-equal-weight (same-universe)
   as the cleaner alpha signal; SPY is the external reference where available.
3. **Determinism = seeded, not absent.** The bootstrap uses RNG; pin `--seed` and store it in the
   JSON header so the CIs reproduce (research invariant 5). A test asserts same-seed reproducibility.
4. **Survivorship cuts both ways** (Direction note 3): the live top-200 is today's names (biased ↑);
   the survivorship-free appendix is the robustness check. Label each result for what it is.
5. **`docs/` vs `Docs/` git-add case quirk** — tracked path is lowercase `docs/`; verify
   `git diff --cached --name-only` before committing the report + harness.
6. **Cost is multiplicative per rebalance** (`equity *= 1 - bps/1e4 * turnover`) — the 50bps run is
   not 5× the 10bps drag (turnover varies); report the realized drag, not the nominal bps.
