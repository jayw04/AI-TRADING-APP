# ADR 0026 — Factor Lab: research programs as configuration

| Field | Value |
|---|---|
| Date | 2026-06-25 |
| Status | **Accepted** (owner ratified 2026-06-25, after two ARD review rounds) |
| Phase | Platform consolidation (post-Phase-2 "Demonstrate Repeatability") |
| Supersedes | — |
| Related | 0019 (Research Engine subsystem — this extends it), 0014 (backtests = eval ground truth), 0018 (PIT factor data — the Lab reads it), 0002 (single OrderRouter — the Lab never submits orders) |

## Context

By the close of the initial six-program research catalog (MOM-001, RNG-001, the
multi-factor re-test, SEC-001, LOW-001, TREND-001), the same evidence pipeline had
been hand-written four times: `scripts/factor_research.py`,
`scripts/sector_rotation_v2_research.py`, `scripts/low_vol_research.py`, and
`scripts/trend_research.py`. Each is the *same* seven stages — score the universe →
backtest via `run_momentum_backtest(…, score_fn=…)` → test H1/H2/H3 with a paired
circular-block Sharpe-difference bootstrap → walk-forward over N windows → cost sweep
(5/10/20/50 bps) → an A/B/C/D verdict tree → a JSON+Markdown evidence package. Only
stage 1 (the score function) and a handful of construction knobs and verdict gates
actually vary between programs. Stages 2–7 were copy-pasted, including a
`_paired_sharpe_diff_ci` duplicated verbatim across three scripts and a verdict tree
expressed as ad-hoc code — the form in which the TREND-001 verdict bug (a `corr<0.7`
gate that was in the code but never in the pre-registered plan) hid until review.

The owner's directive after Phase 2 was explicit and repeated: *"stop authoring
bespoke research scripts; a new research program should become a configuration, not a
new script."* This is consolidation, not new research. The question this ADR records:
**should the research pipeline become a single, declarative, config-driven harness —
and on what terms, given ADR 0019 already makes the Research Engine a first-class
read-only subsystem?**

## Decision

**Adopt the Factor Lab: a research program is a declarative `ProgramSpec`
(+ optionally one registered score function) executed by a single unified runner,
`run_program`, living inside `app/research/` as an extension of ADR 0019 — not a new
subsystem and not a parallel package.**

> **Platform principle: research programs are *assets*, not scripts.** Once a program is a
> `ProgramSpec` it is versionable, reproducible, testable, promotable, comparable, and governed —
> a first-class, durable artifact of the platform rather than a one-off file. This single sentence
> is the motivation for the whole ADR; everything below serves it.

1. **Programs are data.** A `ProgramSpec` (frozen Python dataclass, `app/research/
   factor_lab/spec.py`) captures everything that varies: factor + params, universe +
   window, construction mode, weighting/cost knobs, baseline/control, evaluation seed/
   bootstrap/windows, and the verdict tree. Python dataclasses, not a YAML/JSON DSL
   (OQ1) — type-checked, testable, no `eval`.

2. **The verdict tree is data.** The A/B/C/D decision is a `VerdictSpec` — an ordered
   list of `(predicate, outcome, action)` rules evaluated against a flat metrics dict.
   The decision is *declared*, not coded, which is the discipline that would have
   caught the TREND-001 verdict bug at authoring time.

3. **One runner, three construction modes.** `run_program(spec, store)`
   (`app/research/factor_lab/runner.py`) dispatches on `spec.construction`:
   `quantile` (single-factor quantile books, e.g. LOW-001), `participation`
   (cash-aware trend books whose gross falls in downtrends, e.g. TREND-001, dispatched
   to `backtest.simulate_cash_book`), and `sector_baskets` (top-K sector-neutral
   equal-weight baskets vs an all-sector control, e.g. SEC-001). Program-specific
   behavior stays first-class but **declared** — the runner branches on config, never
   on a new script. The runner calls the *same* library backtest and the *same*
   `factor_data/evidence.py` statistics the bespoke scripts did, so it is equivalent
   **by construction**.

4. **Equivalence is the acceptance gate.** The Factor Lab is canonical for a program
   only once `run_program(spec)` reproduces that program's committed bespoke evidence
   package — books (CAGR/Sharpe/maxDD/Calmar), H1/H2/H3 CIs, walk-forward, cost sweep,
   and the **verdict** — on the full real-data window (2000-01-01 … 2026-06-12, seed 17,
   2000 resamples). **All three implemented programs passed** on 2026-06-25: LOW-001
   (reproduced in-session), **SEC-001 V2 — 62/62 fields matched** (verdict *B —
   Diversifier (confirmed)*), and **TREND-001 — 55/55 fields matched** (verdict *B —
   Diversifier / Defensive*). Every book stat, CI, K-band entry, walk-forward delta, and
   cost-sweep point reproduced exactly.

5. **Deprecate, do not delete.** On a green equivalence the three bespoke *verdict*
   harnesses (`low_vol_research.py`, `sector_rotation_v2_research.py`,
   `trend_research.py`) carry a deprecation notice directing future work to
   `run_program`; they are retained as the immutable scientific record (the Evidence
   Engineering moat depends on never rewriting committed evidence). `factor_research.py`
   is a deliberate exception: its IC / long-short factor-*measurement* study is a
   distinct capability **not** subsumed by `run_program`, and it remains an active
   Research-Engine dependency (`app/research/engine/runners.py` imports its
   `run_study`). It is annotated, not deprecated.

6. **No new factors, no auto-tuning in V1 (OQ5).** The factor registry is seeded with
   the five existing factors (momentum, low_vol, sector_momentum, trend, composite).
   The runner never searches a parameter space: tuning happens *before* a spec is
   frozen; the harness only ever runs a pre-registered config. This preserves the
   no-overfit invariant that underwrites every committed verdict.

7. **Programs are immutable and versioned, not edited.** **Existing `ProgramSpec`s are never
   edited after evidence has been generated; new research always produces a new `ProgramSpec`
   identifier or version** (`LOW-001` → `LOW-002`, not an edit of `LOW-001`) — mirroring Git
   history and scientific experiments: the committed evidence a program produced must stay
   attributable to the exact spec that produced it. Once a program is promoted, its spec is
   frozen. (A `version` field on `ProgramSpec` is a clean future addition; today the
   convention is carried by the id.)

8. **"Factor Lab" is Version 1 of a more general Research Program Framework.** The
   *implementation* is already broader than the name — it runs momentum, trend, sector,
   and low-vol, and the same `ProgramSpec` → runner → evidence shape will absorb discovery,
   quality, value, macro, and alternative-data programs. The framework spans the Labs:

   ```
   Evidence Engineering
   ├── Discovery Lab  → Candidate Programs       (SCAN-001 …)
   ├── Factor Lab     → Investment Programs       (LOW / SEC / TREND / MOM …)
   └── Future Labs    → same ProgramSpec lifecycle
   ```

   We deliberately **do not rename it today** (the name is load-bearing in code and docs), but
   record here that the abstraction is general; a future rename (e.g. *Research Program Engine*
   / *Capability Lab*) is a documentation decision, not a re-architecture.

## Platform impact

What the platform *gains* by making research programs declarative (the executive read):

- **New investment capabilities are authored as `ProgramSpec`s, not scripts** — a config (+ maybe
  one score fn) instead of a ~400-line harness.
- **Research results become directly comparable** — every program runs the same backtest, the
  same bootstrap, the same walk-forward, so cross-program comparison is apples-to-apples.
- **Capability promotion becomes uniform** — every program emits the same evidence-package shape
  the promotion gate consumes.
- **Every program shares identical statistical validation** — one bootstrap / CI / cost-sweep
  implementation, not four divergent copies.
- **Future Labs reuse the same lifecycle** — Discovery Lab and any later Lab plug into the same
  `ProgramSpec` → runner → evidence → registry → promotion path (decision 8).

This is the platform's three abstraction levels made concrete: **Methodology** (Evidence
Engineering) → **Research Framework** (`ProgramSpec` · runner · evidence · registry · promotion)
→ **Individual Programs** (Momentum, LOW, SEC, TREND, Discovery). The middle level is what this
ADR adds.

## Program lifecycle, fingerprint, and promotion

A program travels a fixed, auditable path from authoring to a paper capability — the
config-driven analogue of ADR 0019's experiment lifecycle:

```
Author ─▶ ProgramSpec (frozen) ─▶ run_program (the Program Runner) ─▶ Evidence Package
       ─▶ Research Registry (immutable) ─▶ Promotion Gate ─▶ Paper Capability ─▶ Continuous Evidence
```

(*"Program Runner"* / *"Research Runner"* is the conceptual name for `run_program`; the function
keeps its literal name in code.)

- **Evaluation is ADR 0014's ground truth.** Inside the runner, the evidence is produced by the
  same backtest-as-ground-truth rule the rest of the platform uses:

  ```
  run_program ─▶ Backtest ─▶ Evidence ─▶ ADR 0014 evaluation (verdict / sufficiency)
  ```

  So a program's verdict is an ADR-0014 evaluation, not a bespoke judgement — the `VerdictSpec`
  is just that evaluation declared as data.
- **Into the Registry.** An authored `ProgramSpec` is **frozen** before it runs; the run emits
  an Evidence Package that enters the Research Registry as an **immutable** row (ADR 0019's
  registry + provenance). Reproducibility, not editing, is the contract (decision point 7).
- **Research fingerprint (reproducibility).** Every Evidence Package is attributable to a
  **research fingerprint** = `ProgramSpec + factor-data version + seed + code (git) version` —
  the content-addressed identity ADR 0019 already mints, now anchored to the spec. "Produced by
  fingerprint XYZ" is what makes the equivalence gate (decision 4) and every committed verdict
  re-runnable forever. (Conceptual here; the orchestrator owns the implementation.)
- **A `ProgramSpec` is not a Capability.** A `ProgramSpec` defines a research *experiment*; a
  **Capability** exists only *after* its evidence has been evaluated and governance has approved
  promotion. The spec is the input to research; the capability is the governed output. Keeping
  them distinct is what lets a rejected program (RNG) still leave a *platform* capability behind
  while contributing *zero* investment capability.
- **To a capability (links to the Whitepaper).** The Evidence Package is not the end of the
  line. A validated program feeds the promotion chain that turns research into a deployable
  asset, and the artifacts have **distinct owning registries** — research artifacts and
  operational artifacts are kept separate:

  ```
  ProgramSpec ─▶ Research Registry ─▶ Capability Registry ─▶ Continuous Evidence Registry
              (the experiment)       (the governed asset)    (live, ongoing proof)
  ```

  The gate stays owner-driven (ADR 0019: the gate validates, the owner deploys); the Factor Lab
  produces the *evidence* a promotion decision consumes, it never promotes anything itself.

## Rationale

- **The pipeline is the durable asset (ADR 0019's thesis, applied one level down).**
  ADR 0019 made the Research Engine first-class because strategies are disposable and
  the validation framework compounds. The Factor Lab is the same argument for the
  *study harness*: four near-identical scripts are four chances to diverge silently.
  Collapsing them to one config-driven runner makes the next verdict cheap, uniform,
  and reproducible without inventing anything new.

- **Why extend `app/research/` rather than a new `app/factor_lab/` package (OQ3).**
  The Research Engine already owns the experiment lifecycle, the content-addressed
  fingerprint/cache, provenance, and the promotion gate. A parallel subsystem would
  duplicate that backbone and split "where does research live" into two answers. The
  Lab is the templated "a program is a config" layer ADR 0019 lacked, so it belongs
  inside it.

- **Why Python dataclasses over a YAML/JSON DSL (OQ1).** A DSL is nicer for
  non-developers but is more to build, validate, and keep faithful, and it invites the
  verdict logic to drift into stringly-typed predicates. For V1 the programs are
  authored by the owner-developer; type-checked dataclasses are the lowest-risk choice.
  A thin YAML loader remains a clean later addition if a non-developer authoring path
  is ever wanted — it would deserialize *into* `ProgramSpec`, not replace it.

- **Why equivalence-by-reproduction is the gate, not a unit test of the refactor.**
  The only credible proof that the config-driven runner did not silently change a
  verdict is that it reproduces the committed evidence packages the bespoke scripts
  produced — same seed, same window, same numbers, same A/B/C/D. This is the same
  pre-registered, reproducible discipline every prior program followed; it is what
  justifies retiring the scripts.

- **Why deprecate rather than delete.** The committed evidence packages and the scripts
  that produced them are the institutional record. Deleting them would erase the
  provenance chain the platform's whole credibility story rests on. A deprecation
  notice gets the "one canonical harness" benefit without erasing history.

- **Trade-off accepted.** The runner branches on three construction modes rather than
  being one perfectly general backtest. That is the honest shape of the problem — cash
  participation and sector baskets genuinely differ from a quantile book — and making
  the branch explicit in config beats a false generalization that fits none of them
  well. The cash-aware simulator (`simulate_cash_book`) is reused, not reimplemented.

- **Why it matters commercially.** Customers do not buy individual research *scripts*;
  they buy a *repeatable research capability*. Turning a research program into a
  declarative specification converts research from custom engineering into a reusable
  platform feature — the same shift the Whitepaper, the Evidence Engineering methodology,
  and the Capability Registry are built around. The abstraction is a **second, independent
  IP contribution** alongside Evidence Engineering itself: *Research Program → Declarative
  Specification → Standardized Validation → Promotion* is broader than the Factor Lab and
  is a research *method*, not a software refactor — a candidate for the platform's patent
  family worth raising with counsel.

## Implementation notes

- **Package:** `app/research/factor_lab/` — `spec.py` (`ProgramSpec`, `VerdictRule`,
  `VerdictSpec`), `verdict.py` (`classify(metrics, spec)` — pure, first-match,
  missing-key raises), `registry.py` (`build_score_fn` over the five factors),
  `runner.py` (`run_program` + the three `_run_quantile` / `_run_participation` /
  `_run_sector_baskets` branches), `configs.py` (`PROGRAMS = {LOW_001, TREND_001,
  SEC_001}`).
- **Promoted to the shared library** (so there is one copy): `evidence.paired_sharpe_
  diff_ci`/`SharpeDiffCI`; `backtest.simulate_cash_book` (the cash-aware sim, banks the
  uninvested fraction); the sector scorers in `factor_data/factors/sector.py`
  (`sector_ranking`, `basket_weights_from_ranking`, `v1_quantile_weights_from_ranking`,
  `sector_scores`) and trend scorers in `factor_data/factors/trend.py`.
- **Read-only / off the order path (ADR 0002, inherited from 0019):** the Lab imports
  no OrderRouter / risk / broker module, opens the factor store `read_only=True`, holds
  no DB session, and makes no LLM call. No new CI invariant — the property is structural,
  identical to ADR 0019's contract.
- **Determinism (ADR 0019 §5):** seed/bootstrap/windows are spec fields (defaults
  `seed=17`, `bootstrap=2000`, `windows=5`, matching the bespoke scripts); given
  identical data + code + seed the runner reproduces identical results — the basis of
  the equivalence gate.
- **Deprecation mechanics:** a docstring notice atop each of the three verdict scripts
  pointing to `run_program` and the corresponding `ProgramSpec`; the scripts remain
  importable and their tests remain green (the scientific record stays executable).
- **No new external dependency; no migration** (the Lab reads the existing DuckDB
  factor store and writes only JSON/Markdown evidence packages).

## Consequences

- **Positive:** a new research program is a config (+ maybe one score fn), not a
  ~400-line script; the verdict tree is data and unit-testable; one bootstrap / one
  walk-forward / one cost-sweep implementation instead of four copies; reproducibility
  and provenance come from ADR 0019's backbone for free.
- **Negative:** the runner carries three construction branches (some irreducible
  program-specificity now lives in `runner.py` rather than in separate scripts); two
  ways to *read* a result during the transition (the canonical `run_program` and the
  still-present deprecated scripts) until the latter are eventually removed; `run_program`
  is heavier per run than a single bespoke script because it computes more reference
  books (the full equivalence run is multi-hour single-threaded — acceptable for an
  offline acceptance gate, not for interactive use).
- **Neutral:** the trading/risk/execution path is entirely untouched; this is additive
  on the research side, exactly as ADR 0019 was.

## Alternatives considered (not chosen)

- **Keep the four bespoke scripts.** Rejected: four copies of the same pipeline are
  four chances to diverge, and the verdict-as-code form already hid one bug. The whole
  point of consolidation is a single source of truth.
- **A YAML/JSON config DSL now.** Rejected for V1: more to build and validate, and it
  pushes verdict predicates toward stringly-typed logic. Deferred as a possible thin
  loader over `ProgramSpec` if a non-developer authoring path is needed.
- **A new `app/factor_lab/` top-level subsystem.** Rejected: it would duplicate ADR
  0019's experiment backbone and fork "where research lives." The Lab is the missing
  config layer *inside* the Research Engine.
- **One fully-general backtest covering cash/sector inline.** Rejected: cash
  participation and sector baskets are genuinely different constructions; folding them
  into `run_momentum_backtest` would either complicate it or quietly approximate them.
  Explicit construction modes are the honest expression.
- **Delete the bespoke scripts on cutover.** Rejected: that erases the committed
  provenance the Evidence Engineering story depends on. Deprecate-and-retain instead.

## Re-evaluation triggers

- **A construction the runner cannot express cleanly.** If a future program needs a
  fourth construction mode that does not fit the dispatch shape, that is a design
  decision (extend the runner deliberately or spike a one-off study), not a quiet
  fourth `if` branch — revisit the "one runner" boundary.
- **Equivalence cannot be reproduced.** If `run_program` ever fails to reproduce a
  committed evidence package within seed-stable tolerance, the consolidation is not
  proven for that program — stop and diagnose before retiring anything.
- **A YAML/non-developer authoring path becomes a real requirement** (e.g. customer-
  facing Factor Lab): revisit OQ1 and add the thin loader.
- **New factors at scale.** If the factor registry grows well beyond the seeded five,
  revisit whether the registry/score-fn-factory shape still fits or wants its own
  lifecycle (OQ5 was explicitly "no new factors in V1").
- **`ProgramSpec` wants to split into factor / construction / evaluation.** Today one
  spec carries all three concerns (the factor, how the book is built, how it is judged).
  As programs diversify, those may deserve to be composed independently (a factor reused
  across constructions; a construction reused across factors). When a spec starts feeling
  overloaded, revisit the single-dataclass shape — recognized now as likely future growth,
  not implemented.
- **The name outgrows the scope.** Per decision 8, "Factor Lab" is V1 of a general
  Research Program Framework. When it routinely runs non-factor programs (discovery,
  macro, alt-data), revisit the name — a documentation change, not a re-architecture.
- **Multi-user / hosted deployment** (shared with ADR 0019/0018): the local-DuckDB,
  single-operator assumption would need revisiting.
