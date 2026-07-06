# Evidence Engineering — Methodology Specification (v1.2 · base v1.1 RATIFIED 2026-06-24)

> **What this is.** The frozen, versioned definition of *how TradingWorkbench does research* — the
> standard lifecycle, evidence gates, verdict taxonomy, evidence-package structure, registries, governance
> workflow, the **platform-vs-investment capability** taxonomy, the **platform-capability Labs**
> (Discovery Lab, Factor Lab), and — new in v1.1 — the **Capability Maturity** ladder and the **Operating
> Envelope** that **every** capability carries. It is the methodology layer of the four-layer product model,
> written down once so the whitepaper, patent, customer docs, and product UI can all cite a single stable
> source instead of re-deriving it per strategy.
>
> **Why v1.0 now.** Six programs (`MOM / RNG / MF / SEC / LOW / TREND-001`) have exercised the method
> end-to-end — a validated book, a formal rejection, an inconclusive, two diversifiers, and a planned
> program. The method has stopped changing; the strategies are now *instances* of it. Per the owner's
> final review (2026-06-22, 9.9/10): *"freeze the methodology — the methodology itself is the product."*

| Field | Value |
|---|---|
| Version | **v1.2 (minor, additive — folds the `docs/review/comments.md` review, 2026-06-25)** — adds §7a **the four kinds of evidence** (Research / Proposal / Operational / Continuous) and the two validation pipelines, on the **v1.1 (RATIFIED 2026-06-24, owner ARD review — 10/10)** baseline that added the four-layer model, Capability Maturity (L0–L5), the Operating Envelope (§4a/§4b), Principle 0 (§2), and mandatory Operating Envelope in the evidence package (§7). |
| Status | **Ratified — this is the baseline.** All later changes are versioned (minor v1.x / major v2.0) with a changelog (§11). The methodology is now independent of any strategy. |
| Sources codified | P12 Direction §4 (research methodology) · the Research Program Registry · the per-program plan/pre-registration docs (MOM/RNG/MF/SEC/LOW) · **ADR 0014** (backtests = primary eval ground-truth) · **ADR 0019** (Research Engine — read-only) · **ADR 0021** (operational contract — the trust substrate that makes results *verifiable*). |
| Relationship to code | The taxonomies here are mirrored by `apps/backend/app/research/programs.py` + the Evidence Dashboard (`/evidence`); the code is the runtime source of truth, this doc is the normative spec. A status-enum alignment follow-up is tracked in `tasks/todo.md`. |

---

## 1. The four-layer product model

Evidence Engineering is **Layer 1**. It is not a strategy and not the platform — it is the discipline the
platform implements and the programs obey. v1.1 makes **Research Infrastructure** its own layer (owner): the
reusable, platform-wide research *assets* (the Labs, engines, registries) are neither the OS that hosts them
nor the programs that run on them — they are *what the customer buys*.

| Layer | What it is | Examples |
|---|---|---|
| **Layer 1 — Methodology** | **Evidence Engineering** — the discipline of producing, governing, and preserving the proof behind every decision (this document) | the lifecycle, evidence gates, verdict taxonomy, evidence package, registries, governance |
| **Layer 2 — Platform** | **TradingWorkbench** — the operating system that makes the methodology usable | risk engine, OrderRouter, audit/hash-chain, scheduler, execution |
| **Layer 3 — Research Infrastructure** | The reusable research *assets* strategies are produced *by* | **Discovery Lab · Factor Lab · Evidence Engine · Research Registry · Decision Registry · Evidence Dashboard** |
| **Layer 4 — Research Programs** | The individual philosophies/capabilities run *through* Layer 3 — each a validated, rejected, or deferred instance | `MOM-001 … TREND-001`, `SCAN-001` |

> A strategy is a *result* of the method, never the product. Momentum is the reference implementation that
> proves Layers 1–3 work — the way Linux is a reference OS, not the OS. The platform's stable subsystem map:
> **Evidence Engineering → Discovery Lab → Factor Lab → Execution Platform → Continuous Evidence.**

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

**Principle 0 — evidence precedes decisions (owner, ARD review).** *Absence of evidence is not
evidence of success.* A decision — a verdict, a promotion, an "it works" — is valid only when
backed by sufficient evidence to distinguish the hypothesis from the null. An evaluation that
produces no observations (e.g. a zero-trade backtest) is **INSUFFICIENT_EVIDENCE**, never a pass.
This is the principle the other invariants serve, and the single sentence that best captures the
platform's philosophy: it explains ADR 0014's eval rule, the RNG-001 rejection, SCAN-001's
iterations, and why SEC/LOW are diversifiers rather than approved alpha.

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

### 4a. Capability Maturity (L0–L5) — a fourth axis (v1.1, owner)

A platform-wide maturity ladder, applicable to **every** capability (strategy *or* infrastructure), so
maturity reads consistently across the Factor Lab, Risk Engine, Execution Engine, and every future
capability. Where Status says *where in its life* and Verdict says *what the evidence concluded*, Maturity
says *how far it has been proven and de-risked*.

| Level | Meaning |
|---|---|
| **L0** | Concept |
| **L1** | Prototype (built; not yet validated) |
| **L2** | Validated (a real, evidence-backed result on the full sample) |
| **L3** | **Operating Envelope Defined** (we know *where* it works and where it must not be used) |
| **L4** | Production-Ready (promoted past governance; live/paper) |
| **L5** | Continuously Verified (long-run live evidence keeps confirming it) |

*Reference path (SCAN-001):* v0.1 → L1, v0.2 → L2, v0.3 → L3. MOM-001 ≈ L4–L5 (live + continuous evidence).

### 4b. The Operating Envelope (v1.1, owner) — every capability has one

In engineering, no capability is certified "it works" — it is certified for an **operating envelope** (an
aircraft for a range of altitude, temperature, payload). Evidence Engineering adopts the same discipline:
**a validated capability is not deployed blindly; its envelope — the market/volatility conditions under which
it works (★★★★★), works marginally (★★), or must not be used (★) — is defined as a distinct maturity step (L3).**

- The envelope is produced by a pre-registered **regime-decomposition** study (market × volatility regimes,
  PIT-classified) that buckets the *already-validated* edge — it maps boundaries, it does not re-validate.
- Its two artifacts are a **Capability Strength Map** (★ per regime) and a **Discovery/Capability Confidence**
  score (∈ [0,1] per regime) — the latter composable into downstream sizing (`signal × confidence(regime)`).
- It applies to *all* capabilities, giving the platform one shared language: Momentum's envelope is trending
  markets; Low-Vol's is risk-off; SCAN-001's (the first formally mapped) is **regime-robust, strongest in
  bull + low-vol**. "Honest about where it fails" is itself a trust asset — the inverse of marketing.

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
Objective ─▶ Dataset ─▶ Methodology ─▶ Results ─▶ Operating Envelope ─▶ Limitations ─▶ Decision ─▶ Recommendation
```

An evidence doc that skips *Limitations* or *Decision* is incomplete.

**Operating Envelope is mandatory (owner, ARD review).** Every capability that reaches *Validated*
must carry an **Operating Envelope** in its evidence package before it can be promoted past L3 — a
**Capability Strength Map** (★ per market × volatility regime) and a **Confidence Map** (∈ [0, 1] per
regime, §4b). It is required, not optional: "works" is never certified without "*where* it works."
A pre-existing capability without one is at L2 until the envelope study runs.

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

## 7a. The four kinds of evidence (by lifecycle stage)

"Evidence" is not one thing. As the platform matured, the lifecycle (§3) began producing evidence
of four distinct kinds, each answering a different question and each with its own producer, verdict,
and home. Defining them once here lets every downstream document (proposal findings, paper-trial
runbooks, the whitepaper) refer to the right type instead of overloading the word.

| Evidence type | Question it answers | Produced by | Example artifact |
|---|---|---|---|
| **Research Evidence** | Does the hypothesis have an edge? | a research program's backtest harness (the §5 gate, §7 package) | the SEC / LOW / TREND-001 evidence packages |
| **Proposal Evidence** | Does this *change* beat the current baseline? | the Proposal Engine's baseline-vs-variant backtest eval (ADR 0014) | `strategy_proposals.evaluation_results_json` |
| **Operational Evidence** | Does the *execution platform* do what the code says, live? | a paper-trial / operational-validation run | the Range Trader paper-trial Operational Report |
| **Continuous Evidence** | Does the live edge *persist*? | live monitoring / continuous revalidation (ADR 0019 monitor) | the weekly live-evidence reports |

These correspond to the **two validation pipelines** the platform now runs in parallel:

- **Pipeline A — Research / Proposal:** `Research ─▶ Proposal ─▶ Backtest ─▶ Verdict` (produces Research + Proposal Evidence).
- **Pipeline B — Operational:** `Paper ─▶ Operations ─▶ Evidence ─▶ Operational Verdict` (produces Operational Evidence).

Two properties hold across all four kinds:

- **Sufficiency is universal (Principle 0, §2).** A verdict requires sufficient evidence — a producer
  that yields no observations returns **INSUFFICIENT_EVIDENCE**, never a pass. This is why a zero-trade
  proposal eval is insufficient, not "above baseline" (ADR 0014 v1.1).
- **Every kind lands in the institutional record (§9).** Each evidence artifact is stored in the
  **Evidence Registry** and referenced by the **Capability Registry** — so an *operational* exercise
  (a paper trial that validates a *platform* capability) contributes permanent platform evidence exactly
  as a *research* study (validating an *investment* capability) does. This is the §1a platform-vs-investment
  taxonomy seen from the evidence side: Operational and Continuous Evidence are how the platform validates
  *itself*, not only its strategies.

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
| **v1.2 (minor)** | **2026-06-25** | **Review fold (`docs/review/comments.md` — Proposal Findings 9.8 / Range Runbook 9.9).** Added §7a **the four kinds of evidence** — Research / Proposal / Operational / Continuous — distinguished from the §8 four research *assets*, with the two parallel validation pipelines (A Research/Proposal, B Operational), the universal sufficiency rule, and the Evidence-Registry → Capability-Registry destination. Additive only; no invariant, gate, lifecycle, or taxonomy changed. The owner's other two "biggest" review items were already present (Principle 0 / INSUFFICIENT_EVIDENCE in §2 + ADR 0014 v1.1; "validates platform capabilities" in §1a). |
| **v1.1 (RATIFIED)** | **2026-06-24** | **Ratified at the owner ARD review (10/10).** Added **Principle 0** (§2 — "evidence precedes decisions; absence of evidence is not evidence of success"); made the **Operating Envelope mandatory** in every evidence package (§7, Strength Map + Confidence Map, required before L4). Aligns with the ADR 0014 v1.1 amendment (INSUFFICIENT_EVIDENCE outcome). |
| v1.1 (draft) | 2026-06-23 | **Consolidation fold (owner, post-SCAN-001 v0.3 — minor/backward-compatible):** §1 three-layer → **four-layer** model (adds **Research Infrastructure** as an explicit layer); §4a new **Capability Maturity (L0–L5)** axis applied platform-wide; §4b new **Operating Envelope** concept (every capability is certified for the conditions it works within — a distinct L3 maturity step, with a Strength Map + Confidence score). First exercised end-to-end by SCAN-001 (prototype → validated → operating-envelope/regime-robust). No invariant, gate, or lifecycle changed — additive only. |

---

> **Ratification timing (owner, 2026-06-22).** The owner endorsed declaring Evidence Engineering **v1.0**
> formally **after TREND-001 completes** — i.e. once the initial six-program research catalog is closed.
> This document is therefore a DRAFT that *stages* the freeze: the content is stable now, and ratification
> flips it to official v1.0 at that milestone. On sign-off it is cited by the whitepaper (the three-layer
> model → Chapter 1; this spec + the Registry → an appendix), the patent (the full *Research Program →
> Evidence → Decision Registry → Research Registry → Promotion Gate → Continuous Evidence → Research
> Calibration* workflow as the invention), and the product. Nothing here is new behavior — it is the existing
> discipline, written down and version-pinned.
