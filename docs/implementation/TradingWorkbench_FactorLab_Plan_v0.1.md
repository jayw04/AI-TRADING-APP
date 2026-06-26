# Factor Lab — Design & Plan (v0.1)

| Field | Value |
|---|---|
| Thread | Platform consolidation — **"programs as configuration"** (owner roadmap, post-TREND-001) |
| Status | **FROZEN (owner sign-off 2026-06-24).** OQ1–OQ5 resolved (§9). Build per §7, starting with the foundation. |
| Version | v0.2 — froze OQ1 Python dataclasses · OQ2 deprecate bespoke scripts after equivalence · OQ3 extend `app/research/` · OQ4 ADR on acceptance · OQ5 no new factors in V1. |
| Owner | Jay |
| Governing | ADR 0019 (Research Engine — read-only, two-axis lifecycle, gate-validates/owner-deploys), ADR 0014 (backtests = ground truth), the Strategy Roadmap evidence gate. |
| Goal | Turn a new research program from a **bespoke ~400-line script** into a **declarative config + (optionally) one score function**, run through a single, reproducible harness that plugs into the existing Research Engine. |

---

## 0. Strategic context

The owner's repeated directive after the initial 6-program catalog closed: **"stop authoring bespoke research scripts → build the Factor Lab, where programs become configuration, not new scripts."** Paired with the *"slow down and consolidate"* directive — this is consolidation, not new research or new concepts. The Factor Lab does not produce a new verdict; it makes the *next* verdict cheap, uniform, and reproducible.

This plan deliberately scopes a **minimal, faithful V1** and defers nice-to-haves (a YAML DSL, a UI) so we consolidate without over-building.

---

## 1. The insight (evidence)

The four research harnesses — `factor_research.py`, `sector_rotation_v2_research.py`, `low_vol_research.py`, `trend_research.py` — are **one pipeline executed four times**. Each repeats the identical 7-stage shape:

1. **score** the universe (the one genuinely different part),
2. **backtest** via `run_momentum_backtest(store, …, score_fn=…)` (`backtest.py:450`),
3. test **H1 / H2 / H3** with a paired circular-block Sharpe-difference bootstrap (the *same* `_paired_sharpe_diff_ci` copy-pasted in three scripts),
4. **walk-forward** over N windows (identical `_windows` helper, copy-pasted),
5. **cost sweep** 5/10/20/50 bps (identical loop),
6. a **verdict tree** (A/B/C/D) — pure logic, already extracted in `trend_research.py::classify_outcome`,
7. an **evidence package** (`script → JSON → Markdown`, near-identical `_render`).

Stages 2–7 are duplicated across all four; stage 1 (and a few construction knobs) is what actually varies. **That duplication is the thing the Factor Lab removes.**

---

## 2. What already exists to reuse (do NOT rebuild)

| Layer | Asset | Note |
|---|---|---|
| Backtest substrate | `factor_data/backtest.py::run_momentum_backtest(…, score_fn=…)` | Factor-agnostic already. Supports `weighting` ∈ {equal_weight, inverse_vol, risk_parity_diagonal}, `top_quantile`, `vol_target_annual`, `max_sector_pct`, `turnover_cost_bps`. **Cannot** do cash participation (always fully invested) — see §4. |
| Factor library | `factor_data/factors/` — `engine.momentum_scores`, `low_vol.low_vol_scores`, `composite.composite_scores`, `sf1`, `fundamental` | Canonical score signature: `(store, as_of, …) -> DataFrame[score]`. PIT, deterministic, pure, raise `FactorUnavailable` when thin. |
| Stats / evidence | `factor_data/evidence.py` | cagr/sharpe/sortino/maxDD/calmar/drawdown-profile + **seeded circular-block bootstrap CIs + p-values**. Delegate ALL curve math here. |
| Experiment backbone | `app/research/` (ADR 0019) | `ResearchStore` (DuckDB) + `orchestrator.run_experiment(config, runner)` with **content-addressed fingerprint → cache** + provenance; metric-agnostic **promotion gate** (`GateProfile`/`Criterion` → verdict + confidence). The Factor Lab plugs in here. |
| Closest precedent | `factor_data/factors/composite.py` (P12 §3) | Already config-driven *at the scoring stage* (`factors=[…]`, `weights={…}`). The Factor Lab generalizes that idea to the **whole pipeline**. |

**Seam in the Research Engine:** experiments are programmatic `ExperimentConfig` objects with per-program *runners*; there is no templated "a program is a config row" layer and no built-in hypothesis/verdict tree. That seam is exactly what the Factor Lab fills.

---

## 3. Design

### 3.1 `ProgramSpec` — the declarative program (the "configuration")

A frozen dataclass (Python-declarative; see OQ1 re YAML) capturing everything that varies:

```
ProgramSpec:
  id, name, philosophy                      # MOM-001 … or a new program
  # factor (stage 1)
  factor: str                               # registry key: "momentum" | "low_vol" | "sector_momentum" | "trend" | "composite"
  factor_params: dict                        # e.g. {lookback_days:252, skip_days:0} / {vol_lookback_days:252} / {sma_days:200}
  # universe & window
  n: int; start: date; end: date
  # construction (stage 2)
  construction: str = "quantile"            # "quantile" | "sector_baskets" | "participation"  (see §4)
  top_quantile: float = 0.20
  weighting: str = "equal_weight"
  vol_target_annual: float | None = None
  max_sector_pct: float | None = None
  turnover_cost_bps: float = 10.0
  # benchmark / control (stage 3, H2/H3)
  baseline: str = "equal_weight"            # "equal_weight" | "regime_filter"
  # evaluation
  windows: int = 5; bootstrap: int = 2000; seed: int = 17
  # verdict (stage 6)
  verdict: VerdictSpec                       # the A/B/C/D decision table as DATA (§3.4)
  gate_profile: str | None = None           # optional: a research/promotion GateProfile name
```

### 3.2 Factor registry (stage 1)

A dict mapping `factor` → a score-function factory `(factor_params) -> score_fn(store, as_of) -> DataFrame[score]`. Wraps the existing library: `momentum`→`engine.momentum_scores`, `low_vol`→`low_vol.low_vol_scores`, `composite`→`composite.composite_scores`, `sector_momentum`→the SEC basket scorer, `trend`→the per-name SMA in-trend flag. Adding a brand-new factor = register one function; **no new harness**.

### 3.3 Unified runner (stages 2–5, 7)

`run_program(spec) -> EvidencePackage`:
1. resolve `score_fn` from the registry,
2. run the backtest per `construction` (default `run_momentum_backtest`; `participation` dispatches to the cash-aware simulator, §4),
3. build the baseline/control curve (equal-weight or regime-filter),
4. evaluate **H1/H2/H3** with shared `evidence.py` helpers (one canonical `paired_sharpe_diff_ci` — promoted out of the scripts into `evidence.py`),
5. walk-forward (shared `_windows`) + cost sweep (shared loop),
6. apply the **verdict tree** (§3.4),
7. emit the standardized JSON+MD evidence package **and** register the run via `orchestrator.run_experiment` (fingerprint/cache/provenance) + optional promotion gate.

### 3.4 Verdict tree as data (stage 6)

The A/B/C/D logic becomes a small ordered list of `(condition, outcome, action)` rules evaluated against a flat metric dict (`h1_real`, `h1_ci_high`, `consistent`, `blend_helps`, `dd_vs_mom`, `dd_vs_eqw`, `beats_regime`, …) — the exact inputs `trend_research.classify_outcome` already uses. New programs declare their gate as data; the evaluator is pure and unit-tested (the discipline that caught the TREND-001 verdict-code bug).

---

## 4. What is genuinely program-specific (and how config expresses it)

Not everything generalizes cleanly; the honest knobs:

| Program-specific behavior | Config expression |
|---|---|
| **Trend cash participation** (gross < 1.0 in downtrends — `run_momentum_backtest` can't do this) | `construction="participation"` → dispatch to the existing `simulate_cash` (kept as a construction mode, *not* shoehorned into the shared backtest). |
| **Sector baskets** (top-K sectors, hold every name) | `construction="sector_baskets"` + `factor_params.k`. |
| **Regime-filter baseline** (trend's competing-explanation control) | `baseline="regime_filter"`. |
| **Per-program H3 nuance** (low-vol downside vs trend beats-regime vs sector V2-vs-V1) | encoded in the `verdict` rules + which H3 metrics the spec requests. |

These stay first-class but **declared**, so the runner branches on config, not on a new script.

---

## 5. Acceptance test — equivalence (this is how we know it's right)

The Factor Lab is proven by **reproducing the four existing verdicts as configs**:

- Author `ProgramSpec`s for MOM-001, LOW-001, TREND-001, SEC-001(V2).
- Run each through `run_program` with the same seed/window/n.
- Assert the books (CAGR/Sharpe/maxDD), H1/H2/H3 CIs, walk-forward, cost sweep, and **verdict** match the committed bespoke evidence packages (byte-identical where the math is shared; within seed-stable tolerance otherwise).

Only when all four reproduce do we (a) treat the Factor Lab as the canonical harness and (b) deprecate the bespoke scripts (OQ2). This equivalence run is the deliverable that justifies the consolidation — same discipline as every prior program (pre-registered, reproducible).

---

## 6. Scope (V1) — deliberately minimal

**In:** the `ProgramSpec` dataclass + factor registry + unified `run_program` + config-driven verdict evaluator + the standardized evidence package + ResearchStore/orchestrator integration + the 4 equivalence configs + tests.

**Out (deferred, named so we don't creep):** a YAML/UI config DSL (OQ1); a customer-facing Factor Lab dashboard; *new* research programs (none until the Lab is proven); auto-tuning/optimization (forbidden — the no-overfit invariant: tuning happens before a spec is frozen, the harness never searches); Discovery-Lab integration.

---

## 7. Build sequence (sessions)

1. **§1 — extract the shared core**: promote `paired_sharpe_diff_ci`, `_windows`, `_curve_stats`, the cost-sweep + walk-forward loops into a shared `factor_data` (or `app/research`) module; unit-test against the existing scripts' outputs. *(No behavior change — pure refactor with equivalence tests.)*
2. **§2 — `ProgramSpec` + factor registry + verdict evaluator** (pure, tested).
3. **§3 — `run_program` runner** (backtest dispatch incl. participation/sector modes; baseline/control; evidence package).
4. **§4 — Research Engine integration** (fingerprint/cache via orchestrator; optional promotion gate).
5. **§5 — the 4 equivalence configs + the equivalence test** (the acceptance gate). On green → deprecate bespoke scripts (OQ2) and update the catalog/docs.

Each session: ≥95% on new pure modules, ruff/mypy clean, walk-away, PR.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Refactor silently changes a verdict | The equivalence test (§5) is the gate — Factor Lab must reproduce all 4 committed evidence packages before anything is retired. |
| Reproducibility/determinism regressions | Reuse `evidence.py`'s seeded bootstrap; fingerprint via the orchestrator; no clock/`Math.random`. |
| Over-generalization (a DSL that fits nothing well) | V1 is Python-declarative dataclasses + a registry, not a DSL; cash/sector stay explicit construction modes. |
| Cash-aware correctness | Keep the unit-tested `simulate_cash` as-is; the Lab dispatches to it, doesn't reimplement. |

---

## 9. Open questions for the owner (FREEZE before building)

- **OQ1 — Config format:** **Python-declarative `ProgramSpec` dataclasses** (type-checked, testable, lowest risk) [recommended] vs a YAML/JSON DSL (nicer for non-devs, more to build/validate). Recommend Python for V1; YAML as a later thin loader if wanted.
- **OQ2 — Bespoke scripts after equivalence:** **deprecate** them (Factor Lab becomes canonical) [recommended], or keep both indefinitely (more maintenance, two sources of truth)?
- **OQ3 — Where it lives:** extend **`app/research/`** (it owns the experiment lifecycle, ADR 0019) [recommended] vs a new `app/factor_lab/` package. Recommend `app/research/` to avoid a parallel subsystem.
- **OQ4 — ADR?** A config-driven research runner that becomes the canonical harness is arguably an architectural decision → **write an ADR on acceptance** (extends ADR 0019) [recommended], or treat as a plain feature.
- **OQ5 — V1 factor set:** ship the registry seeded with the **5 existing factors** (momentum, low_vol, sector_momentum, trend, composite) and prove equivalence on the 4 programs — agree V1 adds **no new factors**.

✅ **RESOLVED (owner, 2026-06-24):** OQ1 **Python dataclasses** · OQ2 **deprecate bespoke scripts** (post-equivalence) · OQ3 **extend `app/research/`** · OQ4 **ADR on acceptance** (extends 0019) · OQ5 **no new factors in V1** (seed the registry with the 5 existing). Plan FROZEN; §7 build begins with the foundation.
