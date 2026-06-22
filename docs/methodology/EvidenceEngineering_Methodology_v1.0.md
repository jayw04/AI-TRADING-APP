# Evidence Engineering — Methodology Specification (v1.0 · DRAFT for owner ratification)

> **What this is.** The frozen, versioned definition of *how TradingWorkbench does research* — the
> standard lifecycle, evidence gates, verdict taxonomy, evidence-package structure, registries, governance
> workflow, the **platform-vs-investment capability** taxonomy, and the **platform-capability Labs**
> (Discovery Lab, Factor Lab) that **every** research program inherits. It is the methodology layer of the
> three-layer product model, written down once so the whitepaper, patent, customer docs, and product UI
> can all cite a single stable source instead of re-deriving it per strategy.
>
> **Why v1.0 now.** Six programs (`MOM / RNG / MF / SEC / LOW / TREND-001`) have exercised the method
> end-to-end — a validated book, a formal rejection, an inconclusive, two diversifiers, and a planned
> program. The method has stopped changing; the strategies are now *instances* of it. Per the owner's
> final review (2026-06-22, 9.9/10): *"freeze the methodology — the methodology itself is the product."*

| Field | Value |
|---|---|
| Version | **v1.0 (DRAFT — pending owner ratification)** |
| Status | Proposed freeze. On ratification, this becomes the baseline; all later changes are versioned (v1.1 minor / v2.0 major) with a changelog (§11). |
| Sources codified | P12 Direction §4 (research methodology) · the Research Program Registry · the per-program plan/pre-registration docs (MOM/RNG/MF/SEC/LOW) · **ADR 0014** (backtests = primary eval ground-truth) · **ADR 0019** (Research Engine — read-only) · **ADR 0021** (operational contract — the trust substrate that makes results *verifiable*). |
| Relationship to code | The taxonomies here are mirrored by `apps/backend/app/research/programs.py` + the Evidence Dashboard (`/evidence`); the code is the runtime source of truth, this doc is the normative spec. A status-enum alignment follow-up is tracked in `tasks/todo.md`. |

---

## 1. The three-layer product model

Evidence Engineering is **Layer 1**. It is not a strategy and not the platform — it is the discipline the
platform implements and the programs obey.

| Layer | What it is | Examples |
|---|---|---|
| **Layer 1 — Methodology** | **Evidence Engineering** — the discipline of producing, governing, and preserving the proof behind every decision (this document) | the lifecycle, evidence gates, verdict taxonomy, evidence package, registries, governance |
| **Layer 2 — Platform** | **TradingWorkbench** — the operating system that makes the methodology usable | research engine, registries, risk engine, OrderRouter, audit, dashboards |
| **Layer 3 — Research Programs** | The individual philosophies run *through* the platform — each a validated, rejected, or deferred instance | `MOM-001 … TREND-001` |

> A strategy is a *result* of the method, never the product. Momentum is the reference implementation that
> proves Layers 1–2 work — the way Linux is a reference OS, not the OS.

### 1a. Two kinds of capability — Platform vs Investment

Every research program leaves behind a **capability**, and capabilities come in two kinds. Keeping them
distinct is the product architecture (and the commercial story — *customers buy the platform capabilities,
not the strategy logic*):

| | **Platform capability** | **Investment capability** |
|---|---|---|
| What it is | reusable **engine · method · workflow · registry** | the **investment logic / signal / profile** a strategy contributes |
| Layer | Layer 2 (the platform itself) | Layer 3 (content that runs on the platform) |
| Examples | bootstrap engine, Evidence Package, sector-neutral construction, the Research Registry, the Discovery Lab, the Factor Lab | cross-sectional momentum, vol-targeting, low-volatility, sector rotation, trend |
| Commercial role | **the product you sell** | the content the product produces |
| Lifecycle | accrues and compounds across programs | tied to a single program's verdict |

A rejected program (RNG) ships *zero* investment capability but still hardens *platform* capability (the
honest-rejection workflow). That is why "every exit is a success": each program advances at least one of
the two capability kinds.

### 1b. Platform-capability Labs — research becomes configuration

A **Lab** is a platform capability where authoring a *new* research program is **configuration over shared
infrastructure**, not a new bespoke script. This is the platform's maturity signal: after a handful of
bootstrapping programs prove the shared pipeline, the platform stops writing one-offs.

- **Factor Lab** — the factor-research engine. After `MOM / MF / SEC / LOW` demonstrated ~90% code reuse,
  a new factor study becomes a *configuration* over the shared evidence pipeline (universe + factor
  definition + gate), not a new document.
- **Discovery Lab** — the universal *"what's worth looking at?"* engine: pre-open / periodic candidate
  **discovery** that runs *in front of* the lifecycle and hands a curated **Candidate Set** to the matching
  research programs. `SCAN-001` is its first profile (daily intraday); swing / momentum / sector / ETF /
  macro / earnings are future profiles — each a *configuration*, never a new `DISCOVERY-00N` codebase.

**The canonical discovery pipeline** (discovery feeds the lifecycle; it never bypasses it):

```
Discovery Lab → Candidate Set → Research Program → Evidence Package → Governance → Paper → Production → Continuous Evidence
```

Both Labs embody the same rule: *new research is configuration, the engine is the durable asset.* New Labs
(beyond Factor and Discovery) are themselves platform capabilities and join the registry as such.

## 2. Research invariants (non-negotiable)

The research analogue of the platform's operational invariants. Violating one invalidates the evidence.

1. **Never optimize on test data** — parameters are fit on train, never on the out-of-sample window.
2. **Always preserve out-of-sample** — a held-out / walk-forward OOS segment is sacrosanct.
3. **Never cherry-pick periods** — report all regimes, not the flattering ones.
4. **Never suppress a negative study** — a rejected hypothesis is recorded, not deleted (§9 Negative findings).
5. **Every reported number is reproducible** — it traces to a versioned, seeded run (§7 Evidence versioning).

## 3. The standard research lifecycle

Every program travels the same phases. This is the canonical terminology — use it everywhere (whitepaper,
patent, UI, customer docs):

```
Hypothesis ─▶ Research ─▶ Evidence ─▶ Governance ─▶ Candidate ─▶ Paper ─▶ Production ─▶ Continuous Evidence
```

**Skipping the gate is forbidden.** The operational gate sequence inside the lifecycle is:

```
Research ─▶ Validated (OOS clears the §5 gate) ─▶ Production Candidate (owner decision) ─▶ Paper ─▶ Production
```

`Research → Production` directly, or `Research → live` directly, is **prohibited** (ADR 0014/0019; activation
cooldowns per ADR 0005/0006). `Continuous Evidence` (live monitoring) closes the loop and can *re-open*
Research when a factor decays — the method is a flywheel, not a pipeline with an end.

A program may **exit at any phase with a verdict**, and *every exit is a success* — Evidence Engineering
measures the quality of decisions, not the count of strategies shipped.

## 4. Status, verdict & research-line taxonomies (three orthogonal axes)

These never collapse into one column. A program has all three.

**Program status** — *where is it in its life?*

| Status | Meaning |
|---|---|
| **Planning** | Plan + pre-registration frozen. No research has run yet. |
| **Running** | The evidence harness is executing (or mid construction-sequence, e.g. a V2). |
| **Completed** | Research finished; verdict assigned; evidence package exists. |
| **Archived** | Research finished **and** the construction line is closed (rejection or stopping-rule fire). |
| **Production** | Promoted past governance into paper and/or live. |

**Verdict** — *what did the evidence conclude?*

| Verdict | Meaning |
|---|---|
| **Approved** | Validated standalone edge — clears the H1 gate. |
| **Diversifier (B)** | No standalone edge, but real overlay/diversification value (H2/H3). |
| **Inconclusive** | The gate held the line — promising but the CI spans zero; deferred, not shipped. |
| **Rejected** | No edge on honest, full-cycle data — a citable "honest no." |
| **Pending** | Research not yet run (Planning programs). |

**Research line** — *is there anything left to study?* (orthogonal to Status)

| Research line | Meaning |
|---|---|
| **Open** | Active or continuously accruing (a live book; a planned program). |
| **Follow-on available** | Research `Completed`, but pre-registered next variants exist. |
| **Closed** | Construction line finished; reopening needs a *fundamentally new hypothesis*. |

## 5. The standard evidence gate (pre-registered, frozen before results)

Every program pre-registers its hypotheses and acceptance criteria **before** running. The standard gate:

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of the headline metric (ΔSharpe vs the benchmark) **excludes 0** and is positive |
| **Statistical significance** | paired circular-block bootstrap (≥2000 resamples, fixed seed) + p-value where appropriate — not a point estimate (§6) |
| **Consistency** | positive in **≥ ⌈W/2⌉+1** walk-forward windows (no single-regime artifact) |
| **Cost-robust** | the edge survives a 5 / 10 / 20 / 50 bps turnover-cost sweep |
| **Honest defaults** | equal-weight, a single frozen signal definition, no in-sample tuning |
| **No-overfit clause (patent language)** | **No parameter is introduced solely to improve historical performance** — every frozen parameter is an inherited convention or a conservative default set before results |

The verdict is a **pre-registered decision tree** (which hypotheses clear → which verdict), optionally with
**pre-registered outcome probabilities** and a per-outcome **learning objective** (what we learn regardless
of result). A central principle, applied program-by-program: *when a philosophy appears promising but falls
short of significance, change only one dimension at a time to isolate the limiting factor* (e.g. SEC-001 V2
held signal/window/universe fixed and changed only construction).

> **Stopping rule.** Each construction sequence is bounded: if the isolating change shows no benefit, the
> program is **archived**, not refined forever. Further work requires a fundamentally new hypothesis, not
> another parameter sweep. This is what institutional investors trust — the platform that knows when to stop.

## 6. Statistical-confidence standard

Headline edge claims carry a significance read, not just a point estimate: **confidence intervals +
bootstrap of the return/Sharpe distribution + a p-value where appropriate + the distribution of outcomes**
(not only the mean). *A Sharpe with no CI is a number, not evidence.*

## 7. The Evidence Package (every study has the same shape)

A study is reproducible forever or it is not evidence (invariant 5).

**Standard structure:**

```
Objective ─▶ Dataset ─▶ Methodology ─▶ Results ─▶ Limitations ─▶ Decision ─▶ Recommendation
```

An evidence doc that skips *Limitations* or *Decision* is incomplete.

**Pipeline:** `script → JSON → Markdown`, seeded and deterministic (same inputs → byte-identical output).

**Experiment ID + reproducibility metadata.** Every execution mints an **`EXP-YYYYMMDD-NNNNNN`** id linking
its code, data, report, and decision, and auto-records: Python/DuckDB versions · git SHA · dataset SHA ·
seed · execution time · host · generated-at.

**Dataset-health gate (fail-closed).** Before every experiment a health report runs — date coverage/gaps ·
row count · missing-price % · delisted % · split/dividend sanity · point-in-time validation · survivorship
validation. A red flag blocks the run, so no report silently sits on bad data.

**Evidence versioning — the five coordinates** pinned in every report header: **dataset version · code
version · factor version · walk-forward version · report version** (the research analogue of the §4-replay
`algorithm_version`/`registry_version` triple).

## 8. The four research assets (experimentation vs governance, kept separate)

| Asset | Purpose |
|---|---|
| **Dataset** | input (the survivorship-free store + its health report) |
| **Research code** | analysis (harness, factors, walk-forward) |
| **Evidence** | results (JSON + the study report) |
| **Decision** | governance (Research Registry + Decision Register rows) |

Experimentation produces Dataset/Code/Evidence; governance consumes them into Decisions. Code and data may
churn; **decisions are durable and auditable.**

## 9. Governance & institutional memory

The flywheel that turns one-off studies into a compounding knowledge asset — *Research → Evidence →
Decision → Knowledge*, not *Research → Report → Forgotten*.

- **Research Program Registry** — the single catalog of every program from hypothesis through verdict,
  carrying Status · Progress · Research line · Verdict · Evidence package · Lesson learned · **Platform
  value** (why each program exists, beyond its result). The open-ended, forever-growing institutional record.
- **Capability Registry** — the catalogue of **reusable platform capabilities** each program leaves behind
  (engine code, methodology, workflow), indexed by origin program — because *customers buy capabilities, not
  strategies*. A rejected or archived program still hardens the platform. Seeded today as the Registry's
  **Platform Capability Matrix**; a first-class Capability Registry is Phase-B platform work.
- **Decision Register** — one auditable row per study: *Decision · Reason · Study # · Evidence* — the durable
  "why is this on/off."
- **Negative findings** — rejected and marginal studies are **kept with their reason**. Knowing what does
  *not* work is as valuable as what does, and prevents re-running dead ends (invariant 4).
- **Research-debt register** — a standing list of unresolved methodological limitations (e.g. full-history
  SPY, capacity/market-impact, dividend validation, liquidity model). An outstanding item must be disclosed
  in any report it affects.

## 10. Research-process calibration metrics

Evidence Engineering evaluates not only strategies but **its own research process**. Each program records,
*before* running where applicable:

| Metric | What it captures |
|---|---|
| **Research Confidence** | Expected confidence (Low/Med/High) + reasoning — later compared to the actual verdict. |
| **Research Complexity** | Low / Medium / High — engineering difficulty of the study. |
| **Research Duration** | Planned → Started → Completed — the lifecycle clock for ROI / enterprise reporting. |
| **Research Cost** | Developer time · CPU hours · storage · dataset · complexity · reuse %. |
| **Research Quality score** | ★1–5 self-rating on Data · Methodology · Reproducibility · Statistical power · Documentation, plus a Decision confidence (High/Med/Low). |
| **Research ROI** *(derived)* | Research Value / Research Cost. |
| **Research Accuracy** *(future)* | Expected → Observed → Calibration Score — how good the platform's own forecasts are, once the sample is large enough. |

## 11. Versioning this methodology

From v1.0 forward, the methodology is treated as software:

- **Minor (v1.x)** — additive clarifications, a new metric, a new registry field. Backward-compatible.
- **Major (v2.0)** — a change to an invariant, a gate criterion, the lifecycle, or a taxonomy. Requires an
  ADR and a migration note for existing evidence packages.
- Every change lands with a **changelog entry** (date · version · what changed · why). Existing evidence
  packages remain valid under the methodology version they cite (the five coordinates in §7 make that pin
  explicit).

### Changelog

| Version | Date | Change |
|---|---|---|
| v1.0 (draft) | 2026-06-22 | Initial freeze proposal — codifies the lifecycle, invariants, gate, taxonomies, evidence package, registries (incl. the Capability Registry), governance, and calibration metrics exercised across MOM/RNG/MF/SEC/LOW/TREND-001. |
| v1.0 (draft, rev.) | 2026-06-22 | **Architecture-freeze expansion (owner):** added §1a **Platform vs Investment capabilities** and §1b the **platform-capability Labs** — **Factor Lab** + **Discovery Lab** (research-as-configuration) with the canonical *Discovery → … → Continuous Evidence* pipeline. These join the frozen v1.0 concept set; owner direction is now *"freeze the architecture — implement, validate, commercialize,"* not invent further core abstractions. |

---

> **Ratification timing (owner, 2026-06-22).** The owner endorsed declaring Evidence Engineering **v1.0**
> formally **after TREND-001 completes** — i.e. once the initial six-program research catalog is closed.
> This document is therefore a DRAFT that *stages* the freeze: the content is stable now, and ratification
> flips it to official v1.0 at that milestone. On sign-off it is cited by the whitepaper (the three-layer
> model → Chapter 1; this spec + the Registry → an appendix), the patent (the full *Research Program →
> Evidence → Decision Registry → Research Registry → Promotion Gate → Continuous Evidence → Research
> Calibration* workflow as the invention), and the product. Nothing here is new behavior — it is the existing
> discipline, written down and version-pinned.
