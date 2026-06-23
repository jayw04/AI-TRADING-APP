# TradingWorkbench — Research Program Registry (v0.1)

> The single catalog of every research program the platform has chartered — from hypothesis through
> evidence, governance, and (where warranted) production. This is the human-readable mirror of the code
> catalog (`apps/backend/app/research/programs.py`) and the live **Evidence Dashboard** (`/evidence`).
> The code is the source of truth; this doc is the narrative companion the whitepaper and patent cite.

| Field | Value |
|---|---|
| Version | v0.9 (2026-06-23) — folds the SCAN-001 v0.3 + Registry review (both 10/10): **three-layer → four-layer product model** (adds **Research Infrastructure** as an explicit layer — Discovery/Factor Labs, Evidence Engine, registries, dashboard); new **Capability Maturity (L0–L5)** axis applied platform-wide (SCAN at **L2**, → L3 on v0.3) + the **Operating Envelope** concept; SCAN noted as a **family** under Discovery Lab. **v0.8 (2026-06-23)** — **SCAN-001 Prototype → Completed / ✅ Validated (Capability)** after the v0.2 de-tautologized run (both cuts SUPPORTED): status + verdict + evidence row updated; **Market Opportunity Discovery Engine** adopted as the customer-facing name (Candidate Engine = internal); new **Research Infrastructure** capability lens (*"this is the product"*); **architecture direction** note — Discovery Lab as a first-class peer to Factor Lab (four capability domains), pending ratification. Folds the owner review (Prototype 9.9 / Results 10 / Registry 10). **v0.7** — **SCAN-001 registered as Prototype** (PR #229): status Planning → **Prototype** (40%, ⚪ caveated); first evidence row added (H1 edge +3.24% but flagged *partly definitional* — selection includes ATR; recorded as a prototype finding, not a validated edge); Candidate/Discovery Engine + Explainable Candidate Report listed as **prototype** platform capabilities; findings doc linked. **v0.6** — final SCAN-001 review: a **Reuse level** dimension per program (commercial-value signal — SCAN = Very High). **v0.5** folded the SCAN-001 review: **SCAN-001** added as the first **Platform Capability** program; the Capability Matrix **split into Platform vs Investment capabilities**; a **Primary consumer** dimension per program. **v0.4** folded the prior review (9.95/10): a **Platform Capability Matrix** (capabilities by origin program — *customers buy capabilities, not strategies*; the seed of a future Capability Registry). **v0.3** folded the prior review (9.9/10): a **Platform value** column (why each program exists, beyond its result) and a **Research line** status (Open / Follow-on / Closed) orthogonal to program Status (a program can be `Completed` with its research line still open). **v0.2** folded the prior review (10/10): an explicit **status taxonomy** (Planning → Running → Completed → Archived → Production) separating *plan-complete* from *research-complete*; a per-program **progress** indicator; a **portfolio KPI** (count by verdict); each program extended toward **Evidence Package → Decision → Lessons Learned** (institutional memory); and an **open-ended** registry note. v0.1 was the pre-review draft. |
| Source of truth | `apps/backend/app/research/programs.py` + the Evidence Dashboard |
| Convention | Permanent IDs (`MOM / RNG / MF / SEC / LOW / TREND-NNN`) are platform IP — citable in the whitepaper, patent, and customer docs. The registry is **open-ended**: it grows one program at a time, forever (the GitHub-repositories model), and never "closes." |

---

## The four-layer product model

The platform is best understood as four layers — a framing customers grasp immediately. The **Research
Infrastructure** layer is owner-added: the platform-wide *assets* (engines, registries, labs) are distinct
from both the operating system that hosts them and the individual programs that run on them.

| Layer | What it is | Examples |
|---|---|---|
| **Layer 1 — Methodology** | **Evidence Engineering** — the discipline of producing, governing, and preserving the proof behind every decision | pre-registration, evidence packages, the promotion gate, the stopping rule |
| **Layer 2 — Platform** | **TradingWorkbench** — the operating system that makes the methodology usable | the risk engine, OrderRouter, audit/hash-chain, scheduler, execution |
| **Layer 3 — Research Infrastructure** | The reusable, platform-wide research *assets* — the subsystems strategies are produced *by*, not the strategies themselves | **Discovery Lab · Factor Lab · Evidence Engine · Research Registry · Decision Registry · Evidence Dashboard** |
| **Layer 4 — Research Programs** | The individual strategies/capabilities run *through* Layer 3 — each a validated, rejected, or deferred instance | the registry below (`MOM-001` … `TREND-001`, `SCAN-001`) |

Momentum is **Layer 4**, not the product — the *reference implementation* that proves Layers 1–3 work, much as Linux is a reference implementation of an operating system rather than the operating system itself. The platform's stable subsystem map (owner): **Evidence Engineering → Discovery Lab → Factor Lab → Execution Platform → Continuous Evidence**.

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

## Capability Maturity (L0–L5) — owner

A fourth axis, applicable **platform-wide** (every capability — strategy or infrastructure — gets a level), so
maturity reads consistently across the Factor Lab, Risk Engine, Execution Engine, and every future capability.
It refines `Status`: where Status says *where in its life*, Maturity says *how far it has been proven and
de-risked*.

| Level | Meaning |
|---|---|
| **L0** | Concept |
| **L1** | Prototype (built; not yet validated) |
| **L2** | Validated (a real, evidence-backed result on the full sample) |
| **L3** | Operating Envelope Defined (we know *where* it works and where it must not be used) |
| **L4** | Production-Ready (promoted past governance; live/paper) |
| **L5** | Continuously Verified (long-run live evidence keeps confirming it) |

First applied to **SCAN-001**: v0.1 → L1, **v0.2 → L2 (current)**, v0.3 → L3 (the Operating-Envelope study).
Retrospectively, MOM-001 ≈ L4–L5 (live + continuous evidence). The **Operating Envelope** (L3) is the concept
that every capability has conditions under which it operates safely — Momentum's is trending markets,
Low-Vol's is risk-off, Discovery's is set by SCAN v0.3.

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
| **SCAN-001** ⚙ | Market Opportunity Discovery Engine (Candidate Engine) — **platform capability, not a strategy** | **Completed** | `█████████░` 90% | Follow-on (v0.3 stability + premarket gate) | ✅ **Validated (Capability)** | **Discovery Engine** — the reusable morning scanner feeding the Intraday Research Framework |

**Program type — SCAN-001 is the first Platform Capability program** (⚙), distinct from the strategy programs (MOM/RNG/MF/SEC/LOW/TREND). Strategies answer *"should we trade this?"*; a capability answers *"what shared infrastructure do strategies reuse?"*. Plan: v0.1 + v0.2 (`..._CandidateEngine_Plan_v0.1.md`, `..._Plan_v0.2.md`). **The full Evidence-Engineering cycle ran here:** v0.1 prototype → caught its own ATR tautology (findings v0.1, kept as the scientific record) → v0.2 pre-registered de-tautologized hypotheses → **Validated on both cuts** (results v0.2). **Verdict ✅ Validated (Capability):** candidates expand **beyond their own ATR** (1.18–1.49× vs baseline ≈0.94×, CI-separated, p≈0 on both the top-500/3y and top-200/5y cuts), the expansion is tradeable (capturable & net move ~2.5× baseline), and all three signals (ATR+Gap+RVOL) are additive. ⚠ **"Validated" is the *capability* verdict, not a live-trading green light** — promotion to any live use still requires the premarket-data gate (PR #221) + a live-data replication, and the v0.3 Discovery-Stability study (regime/seasonality). Magnitude is regime/universe-dependent (recorded honestly in results §3). **Capability Maturity: L2 (Validated) now → L3 on v0.3** (the Operating-Envelope study, approved). **SCAN is becoming a *family*, not one program** (owner direction): SCAN-001 (the Candidate Engine) is the first of an eventual `SCAN-Regime / SCAN-News / SCAN-Options / SCAN-Earnings` line, all profiles under the **Discovery Lab** subsystem — built as *configuration* over the shared engine, the Factor-Lab pattern (leave room; do not build yet).

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
| **SCAN-001** ⚙ | **v0.2 (validated):** candidates expand **1.18–1.49× their own ATR** vs baseline ≈0.94× (CI-separated, p≈0 on both top-500/3y and top-200/5y); tradeable (capturable & net move ~2.5× baseline); ATR+Gap+RVOL all additive. *v0.1 prototype's +3.24% range edge was caught as partly definitional (selection includes ATR) and superseded.* | `evidence/scan_001_candidate_engine_v0_2/` (v0.2), `evidence/scan_001_candidate_engine/` (v0.1, archival) | **The full Evidence-Engineering cycle in one program:** build → detect a methodological flaw in our *own* result (the ATR tautology) → pre-register de-tautologized hypotheses → re-test rigorously → validate. The kept v0.1 doc shows the platform *correcting its own mistake* — the behavior to associate with TradingWorkbench. |

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
| **Market Opportunity Discovery Engine** (Candidate Engine — selection core + research harness) | **SCAN-001** | **validated** (v0.2) |
| **Explainable Candidate Report** (reason + bounded transparent confidence) | **SCAN-001** | **validated** (v0.2) |

**Investment capabilities** (the investment logic / signal / profile a strategy contributes):

| Capability | Origin | Status |
|---|---|---|
| Cross-sectional momentum | MOM-001 | shipped (live) |
| Volatility targeting (the risk dial) | MOM-001 | shipped (v1.1 live) |
| Multi-factor (value + quality) blend | MF-001 | shipped (inconclusive) |
| Sector rotation | SEC-001 | shipped (diversifier) |
| Defensive / low-volatility | LOW-001 | shipped (diversifier) |
| Trend following | TREND-001 | planned |

### Research Infrastructure — *this is the product* (owner)

A third lens on the platform capabilities above: the subset that is **reusable research infrastructure** —
the engines, registries, and surfaces that exist *independent of any single strategy* and constitute what a
customer, partner, or patent reviewer is actually buying. Strategies are content; this is the platform. (As
Discovery Lab and Factor Lab mature into peer components, this table is the seed of the four enduring
capability domains — *Discovery · Research · Evidence · Operations* — see the architecture note below.)

| Research-infrastructure capability | Origin | Status |
|---|---|---|
| **Evidence Package** (pre-registration → script → JSON → MD, seeded/reproducible) | MOM-001 / methodology | shipped |
| **Circular-block Bootstrap Engine** (CIs + recentered-null p-values) | MOM-001 | shipped |
| **Research Program Registry** (this document + `app/research/programs.py`) | methodology | shipped |
| **Decision Registry** + Negative-findings ledger | methodology | shipped |
| **Evidence Dashboard** (`/evidence`) | P13 | shipped |
| **Market Opportunity Discovery Engine** (Candidate Engine, SCAN-001) | SCAN-001 | validated (v0.2) |
| **Factor Lab** (factor-agnostic composite/score engine) | MF-001 | shipped (engine), program-config WIP |

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

### Architecture direction (owner, post-SCAN-001) — Discovery Lab becomes a first-class peer

SCAN-001's validation makes **Discovery** a first-class capability domain alongside the existing ones, not a
sub-feature of any strategy. The recommended enduring structure — to be ratified into the methodology + the
whitepaper Ch2 figure (captured in `tasks/todo.md`, not executed unilaterally here):

`TradingWorkbench → { Discovery Lab · Factor Lab · Evidence Engine · Execution & Operations }`

- **Discovery Lab** — *finds market opportunities* (SCAN-001 today = the first profile; future Gap / Volume /
  News / Macro / ETF / Options engines = configurations, the Factor-Lab pattern).
- **Factor Lab** — *researches investment philosophies* (Momentum, Low-Vol, Sector, Trend, …).
- **Evidence Engine** — *produces Evidence Packages, statistical validation, governance decisions*.
- **Execution & Operations** — *paper, production, monitoring, Continuous Evidence*.

Discovery and Factor as **peers** cover nearly the whole quant-research workflow (find opportunities ↔
evaluate philosophies). This is a documented *direction*, pending owner ratification — see the whitepaper
Ch2 figure and patent-family items in `tasks/todo.md`.
