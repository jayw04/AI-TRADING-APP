# TradingWorkbench — Research Program Registry (v0.1)

> The single catalog of every research program the platform has chartered — from hypothesis through
> evidence, governance, and (where warranted) production. This is the human-readable mirror of the code
> catalog (`apps/backend/app/research/programs.py`) and the live **Evidence Dashboard** (`/evidence`).
> The code is the source of truth; this doc is the narrative companion the whitepaper and patent cite.

| Field | Value |
|---|---|
| Version | v0.7 (2026-06-22) — **SCAN-001 registered as Prototype** (PR #229): status Planning → **Prototype** (40%, ⚪ caveated); first evidence row added (H1 edge +3.24% but flagged *partly definitional* — selection includes ATR; recorded as a prototype finding, not a validated edge); Candidate/Discovery Engine + Explainable Candidate Report listed as **prototype** platform capabilities; findings doc linked. **v0.6** — final SCAN-001 review: a **Reuse level** dimension per program (commercial-value signal — SCAN = Very High). **v0.5** folded the SCAN-001 review: **SCAN-001** added as the first **Platform Capability** program; the Capability Matrix **split into Platform vs Investment capabilities**; a **Primary consumer** dimension per program. **v0.4** folded the prior review (9.95/10): a **Platform Capability Matrix** (capabilities by origin program — *customers buy capabilities, not strategies*; the seed of a future Capability Registry). **v0.3** folded the prior review (9.9/10): a **Platform value** column (why each program exists, beyond its result) and a **Research line** status (Open / Follow-on / Closed) orthogonal to program Status (a program can be `Completed` with its research line still open). **v0.2** folded the prior review (10/10): an explicit **status taxonomy** (Planning → Running → Completed → Archived → Production) separating *plan-complete* from *research-complete*; a per-program **progress** indicator; a **portfolio KPI** (count by verdict); each program extended toward **Evidence Package → Decision → Lessons Learned** (institutional memory); and an **open-ended** registry note. v0.1 was the pre-review draft. |
| Source of truth | `apps/backend/app/research/programs.py` + the Evidence Dashboard |
| Convention | Permanent IDs (`MOM / RNG / MF / SEC / LOW / TREND-NNN`) are platform IP — citable in the whitepaper, patent, and customer docs. The registry is **open-ended**: it grows one program at a time, forever (the GitHub-repositories model), and never "closes." |

---

## The three-layer product model

The platform is best understood as three layers — a framing customers grasp immediately:

| Layer | What it is | Examples |
|---|---|---|
| **Layer 1 — Methodology** | **Evidence Engineering** — the discipline of producing, governing, and preserving the proof behind every decision | pre-registration, evidence packages, the promotion gate, the stopping rule |
| **Layer 2 — Platform** | **TradingWorkbench** — the operating system that makes the methodology usable | the research engine, registries, risk engine, OrderRouter, audit, dashboards |
| **Layer 3 — Research Programs** | The individual strategies run *through* the platform — each a validated, rejected, or deferred instance | the registry below (`MOM-001` … `TREND-001`) |

Momentum is **Layer 3**, not the product — the *reference implementation* that proves Layers 1–2 work, much as Linux is a reference implementation of an operating system rather than the operating system itself.

## The research lifecycle (standardized phase terminology)

Every program travels the same phases — the terminology used across the whitepaper, the patent, and the codebase:

`Hypothesis → Research → Evidence → Governance → Candidate → Paper → Production → Continuous Evidence`

A program can exit at any phase with a verdict (Approved / Rejected / Inconclusive / Diversifier) — and **every exit is a success**, because Evidence Engineering measures the quality of decisions, not the count of strategies shipped.

## Program status taxonomy (plan-complete ≠ research-complete)

`Status` answers *"where is this program in its life?"* and is deliberately distinct from `Verdict`
(*"what did the research conclude?"*). The separation exists so a reader is never misled into thinking
research has happened when only the **plan** is frozen:

| Status | Meaning |
|---|---|
| **Planning** | Chartered; plan + pre-registration written/frozen. **No research has run yet.** |
| **Running** | The evidence harness is executing (or mid-construction-sequence, e.g. a V2 follow-on). |
| **Completed** | Research finished; a verdict is assigned and an evidence package exists. The program may still have open follow-on variants. |
| **Archived** | Research finished **and** the construction line is closed — a rejection, or a stopping-rule fire. A citable end-state, not a failure. |
| **Production** | Promoted past governance into paper and/or live trading. |

`Status` is a property of the program; `Verdict` is a property of the evidence. A program can be
`Completed · Diversifier (B)` (research done, overlay value) or `Archived · Rejected` (research done,
shelved) — the two columns never collapse into one.

**Research line** (a third, orthogonal axis). A program's *research line* can stay open after a verdict is
reached — `Completed` is not the same as "nothing left to study":

| Research line | Meaning |
|---|---|
| **Open** | Active or continuously accruing evidence (e.g. a live book under continuous monitoring; a planned program not yet run). |
| **Follow-on available** | Research is `Completed`, but pre-registered next variants exist (e.g. LOW-001's defensive-sleeve / broader-universe V2; MF-001's SF1 re-test). |
| **Closed** | The construction line is finished — a rejection or a stopping-rule fire; reopening requires a *fundamentally new hypothesis*. |

---

## The registry

### Status dashboard

| ID | Philosophy | Status | Progress | Research line | Verdict | Platform value |
|---|---|---|---|---|---|---|
| **MOM-001** | Momentum (cross-sectional relative strength) | **Production** (paper) | `██████████` 100% | Open (continuous evidence) | ✅ **Approved** | **Reference strategy** — proves Layers 1–2 work |
| **RNG-001** | Range / mean-reversion | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **Honest rejection** — the platform can decline |
| **MF-001** | Multi-Factor (value + quality) | **Completed** | `██████████` 100% | Follow-on (→ SF1) | 🟡 **Inconclusive** | **Research discipline** — the gate held the line |
| **SEC-001** | Sector Rotation (sector relative strength) | **Archived** (construction) | `██████████` 100% | Closed | 🟡 **Diversifier (B)** | **Diversification** — a non-momentum return source |
| **LOW-001** | Low Volatility (defensive) | **Completed** | `██████████` 100% | Follow-on (sleeve / V2) | 🟡 **Diversifier (B)** | **Defensive strategy** — the calm-stocks complement |
| **TREND-001** | Trend Following (time-series trend) | **Planning** | `█░░░░░░░░░` 10% | Open (not started) | — **Pending** | **Trend philosophy** — the time-series complement |
| **SCAN-001** ⚙ | Daily Candidate Selection / Market Opportunity Discovery — **platform capability, not a strategy** | **Prototype** | `████░░░░░░` 40% | Open (v0.2 next) | ⚪ **Prototype — caveated** | **Candidate Engine** — the reusable morning scanner feeding the Intraday Research Framework |

**Program type — SCAN-001 is the first Platform Capability program** (⚙), distinct from the strategy programs (MOM/RNG/MF/SEC/LOW/TREND). Strategies answer *"should we trade this?"*; a capability answers *"what shared infrastructure do strategies reuse?"*. Plan: `docs/implementation/TradingWorkbench_SCAN001_CandidateEngine_Plan_v0.1.md`. Prototype findings: `docs/implementation/TradingWorkbench_SCAN001_CandidateEngine_PrototypeFindings_v0.1.md` (PR #229). **Prototype status:** the pure selection core + research harness are built and tested; the first H1 run is **caveated, not validated** — the headline edge is partly *definitional* (selection includes ATR, a range measure), so it is recorded as a prototype finding that sharpened the research questions, **not** an approved capability. The ⚪ verdict reflects "built and instructive, not yet validated."

**Verdict legend:** Approved (validated standalone) · Rejected (no edge) · Inconclusive (gate held the line) · Diversifier (B — overlay value, not standalone) · Pending (research not yet run). Colors match the Evidence Dashboard (green / red / amber / amber-blue). **Platform value** answers *why each program exists* — its contribution to the platform, not just its result; a rejection and a diversifier are both assets. **Research line** is orthogonal to Status (above).

**Primary consumer** + **Reuse level** (owner) — *who* each program's output is for, and *how broadly* its
capabilities get reused (the commercial-value signal: high-reuse capabilities are what customers pay for):

| Program | Primary consumer | Reuse level |
|---|---|---|
| MOM-001 | Portfolio Manager (the production book) | **Medium** |
| RNG-001 | Research Team (the honest-rejection precedent) | **Low** |
| MF-001 | Research Team (factor research) | **High** (composite engine) |
| SEC-001 | Portfolio Construction (the diversification sleeve) | **High** (sector-neutral construction) |
| LOW-001 | Risk Management (the defensive complement) | **High** (calibration metrics) |
| TREND-001 | Portfolio Manager (a return source) | **Medium** |
| SCAN-001 | the **Intraday/Discovery Engine** + every strategy that consumes its candidates | **Very High** (a capability every strategy reuses) |

### Portfolio KPI (the "Insights" view)

> **6 programs chartered** → **Approved 1** · **Rejected 1** · **Diversifier 2** · **Inconclusive 1** · **Planned 1**

- **1 deployed** (Momentum, live on paper as three vol-target Risk Profiles).
- **4 evidence-based "not deployed" decisions** — Range (rejected), Multi-Factor (inconclusive), Sector Rotation (diversifier, construction archived), Low Volatility (diversifier, best risk-adjusted book, no decisive standalone edge). *Most software can validate; very few can decline.*

## Evidence & decisions (institutional memory)

Each program is more than a verdict — it is a durable chain of **Evidence Package → Decision → Lesson
Learned**, the research analogue of GitHub's *Issue → PR → Merge → History*. This is what makes the
registry institutional memory rather than a scoreboard.

| ID | Headline result | Evidence package | Lesson learned |
|---|---|---|---|
| **MOM-001** | Sharpe 0.48, 95% CI [0.13, 0.85], p=0.003 (1997–2026, survivorship-free), cost-robust. Live as three vol-target Risk Profiles. | `evidence/p12_s1/`, `evidence/p12_s2_*` | Momentum is a real, cost-robust edge — but its −76% drawdown is the risk story, which is why it ships **with** the vol-target overlay (v1.1). |
| **RNG-001** | First formal rejection: PF 1.27 (< 1.3 bar); bootstrap mean-P&L 95% CI [−$19.74, +$57.53] spans zero; walk-forward PF decays to 0.89. | `evidence/range_rejection/` | The platform can say **no**. A plausible, popular pattern failed the pre-registered bar — and the decline is itself a citable asset. |
| **MF-001** | On survivorship-free SF1: genuine diversifier (corr −0.09 / −0.005), DD −51%→−40%, but ΔSharpe +0.04, CI [−0.35, +0.48] spans zero → keep Momentum v1.1. | `evidence/p12_s3_explore/`, `evidence/p14_s1_multifactor/` | A promising signal that the evidence gate held the line on. "Inconclusive" is not "negative" — it justified the SF1 data investment, not a strategy ship. |
| **SEC-001** | Strongest non-momentum book (Sharpe 0.51), but no standalone edge (V1 H1 +0.16, CI [−0.03, 0.366]). V2 pure baskets confirmed B; H3 showed construction is **not** the limiter → construction archived per the stopping rule. | `evidence/sec_001_sector_rotation/` (V1), `evidence/sec_001_v2_pure_baskets/` (V2) | The **stopping rule works**: V2 isolated construction, found it wasn't the constraint, and the program closed instead of looping on parameters. |
| **LOW-001** | Best risk-adjusted book on the platform: Sharpe 0.59 (vs momentum 0.39), maxDD −39% (≈ half of momentum's −76%), Calmar 0.20. H1 standalone +0.24, CI [−0.029, 0.53] just spans zero; H2 corr **−0.15** (true defensive diversifier); H3 shallower DD than benchmark in **5/5** windows. | `evidence/low_001_low_volatility/` | A prior negative (#142) **reversed** once tested on the right universe/cycle — narrow-universe results don't generalize. Low-vol is the defensive complement to momentum. Open follow-on: defensive sleeve / blend, or broader-universe V2. |
| **TREND-001** | — (planned; charter pending). | — | — |
| **SCAN-001** ⚙ | Prototype H1 (2018–2026, 2,123 days): candidate intraday range 6.33% vs baseline 3.09%, edge **+3.24%**, CI [3.08, 3.41], p≈0, **99.9% daily win** — **caveated as partly *definitional*** (selection includes ATR, a range measure; the ~100% win rate is the tell), so recorded as a prototype finding, not a validated edge. | `evidence/scan_001_candidate_engine/` | The honest catch fired on our *own* result: a clean, significant number that the methodology flags as near-tautological. Value = the engine + harness + three sharpened questions (range *expansion beyond* ATR, directionality, gap/RVOL attribution), not the +3.24%. v0.2 kills the tautology. |

## Platform Capability Matrix (capabilities outlive strategies)

Every program leaves behind **reusable platform capabilities** — engine code, methodology, and workflow
that stay part of TradingWorkbench long after the strategy's research line closes. This is the commercial
crux: *customers don't buy strategies, they buy capabilities.* A rejected program (RNG) still hardened the
platform; an archived construction line (SEC) still contributed sector-neutral construction. The matrix is
the seed of a future first-class **Capability Registry** (Phase B platform work).

Capabilities split into two kinds (owner) — the distinction customers grasp immediately: **Platform
capabilities** are the reusable engines/methods/workflows (the product you *buy*); **Investment
capabilities** are the investment logic each strategy contributes (the *content* that runs on the platform).

**Platform capabilities** (engines · methods · workflows · registries):

| Capability | Origin | Status |
|---|---|---|
| Circular-block bootstrap engine | MOM-001 | shipped |
| Evidence Package (script → JSON → MD, seeded) | MOM-001 | shipped |
| Honest-rejection workflow | RNG-001 | shipped |
| Multi-factor composite engine | MF-001 | shipped |
| Factor-correlation analysis | MF-001 | shipped |
| Sector-neutral construction + construction-isolation methodology | SEC-001 | shipped |
| Research-calibration metrics (Confidence/Complexity/Duration/Accuracy) | LOW-001 | shipped |
| Research Registry · Decision Register · Negative-findings ledger | the methodology (cross-program) | shipped |
| Evidence Dashboard (`/evidence`) | P13 | shipped |
| **Candidate / Discovery Engine** (pure selection core + research harness) | **SCAN-001** | **prototype** (PR #229) |
| **Explainable Candidate Report** (reason + bounded transparent confidence) | **SCAN-001** | **prototype** (PR #229) |

**Investment capabilities** (the investment logic / signal / profile a strategy contributes):

| Capability | Origin | Status |
|---|---|---|
| Cross-sectional momentum | MOM-001 | shipped (live) |
| Volatility targeting (the risk dial) | MOM-001 | shipped (v1.1 live) |
| Multi-factor (value + quality) blend | MF-001 | shipped (inconclusive) |
| Sector rotation | SEC-001 | shipped (diversifier) |
| Defensive / low-volatility | LOW-001 | shipped (diversifier) |
| Trend following | TREND-001 | planned |

## How this evolves

The registry is **open-ended** — it grows one program at a time and never closes, the way a GitHub
account accumulates repositories. The chartered horizon runs `MOM → RNG → MF → SEC → LOW → TREND`, and the
backlog beyond it (`OPTIONS-001`, `MACRO-001`, `ML-001`, `ALT-001`, …) is illustrative, not committed.

The pivot point is **TREND-001**. After it, the platform **stops authoring bespoke research scripts** and
generalizes into the **Factor Lab**, where a new program is a *configuration* over the shared evidence
pipeline rather than a new script + document — the natural endpoint of the high reuse % each successive
program has demonstrated (SEC-001 ~90%, LOW-001 ~90%). New programs are still added to `programs.py`
(which the Evidence Dashboard renders live) and mirrored here; the Factor Lab only changes *how cheaply* a
new row appears.
