# TradingWorkbench — Research Program Registry (v0.18)

> The single catalog of every research program the platform has chartered — from hypothesis through
> evidence, governance, and (where warranted) production. This is the human-readable mirror of the code
> catalog (`apps/backend/app/research/programs.py`) and the live **Evidence Dashboard** (`/evidence`).
> The code is the source of truth; this doc is the narrative companion the whitepaper and patent cite.

| Field | Value |
|---|---|
| Version | **v0.18 (2026-07-08)** — folded the tri-doc review (`comments.md`): (1) **capability count 23 → 25** — catalogued **CAP-024** (PIT Security Master) + **CAP-025** (Intraday Replay & Entry-Funnel Diagnostics), both already cited in `programs.py`; (2) **code↔doc program sync** — added **SCAN-001** (validated) + **FI-003** (planned) to `programs.py` and **PORT-001** to the status dashboard, so the doc and code now mirror at **17 programs** (15 chartered + 2 not-yet-run); (3) **Executive Dashboard reconciled** — Programs chartered 14 → 15, Validated-capability 1 → 2 (SCAN-001 · PORT-001), buckets now sum to 17; (4) moved the long version history (v0.16 → v0.1) into **Appendix A** to keep the header executive-readable; (5) triage doc renamed v0.1 → **v0.2** (filename now matches title) + triage-outcome vocabulary (Go / No-Go / Reference-only / Reserved / Needs-new-harness) + License-vs-Commercial-path clarified. **v0.17 (2026-07-07)** — folded the three **EAD event-driven** verdicts (GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001, all 🔴 Rejected after matched controls + date-clustered bootstrap) into the status dashboard + executive counts (recount → **14 programs · Rejected 7 · Negative 10**). Framed the four rejections (with INSIDER-001) as **one finding** — *public corporate-disclosure events carry no residual alpha after sector/size/liquidity/momentum matching* — now a stopping rule: the **EAD Dataset Triage** gate (`TradingWorkbench_EAD_DatasetTriage_v0.2.md`; four hard vetoes: PIT clarity · distinct mechanism · license path · ≥100 sample) + the codified **`rejected_reference_only`** invariant (a rejected EAD pattern may be shown as context but must never enter ranking / sizing / order-path). EAD **reserved**: LOBBY-002 · OFX-001 (OFX = a *cross-sectional signal* program, not event-study — check FINRA-free before paying Quiver). Disposition: Quiver is a research/reference testbed + False-Positive-Reduction demonstration, **not** a tradable-alpha source; no subscription upgrade. _Full changelog (v0.16 → v0.1) preserved in **Appendix A** below._ |
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
| **Layer 3 — Research Infrastructure** | The reusable, platform-wide research *assets* — the subsystems strategies are produced *by*, not the strategies themselves | **Discovery Lab · Factor Lab · Portfolio Engineering · Evidence Engine · Research Registry · Decision Registry · Evidence Dashboard** |
| **Layer 4 — Research Programs** | The individual strategies/capabilities run *through* Layer 3 — each a validated, rejected, or deferred instance | the registry below (`MOM-001` … `TREND-001`, `SCAN-001`) |

Momentum is **Layer 4**, not the product — the *reference implementation* that proves Layers 1–3 work, much as Linux is a reference implementation of an operating system rather than the operating system itself. The platform's stable subsystem map (owner): **Evidence Engineering → Discovery Lab → Factor Lab → Portfolio Engineering → Execution Platform → Continuous Evidence → Institutional Knowledge** (the Registry + Decision Records are what that last block *is*).

**The research-to-operation lifecycle (three pillars).** `Discovery Lab → Portfolio Engineering → Continuous Evidence` — each consumes or verifies the prior. Discovery Lab *validates* individual capabilities (does this factor have an edge?); **Portfolio Engineering** is the discipline responsible for *combining* validated capabilities into resilient portfolios (FI-001 is its first evidence program); **Continuous Evidence** *verifies*, in live operation, that realized behavior stays within the research envelope that justified deployment. Portfolio Engineering is deliberately kept a *discipline*, not a heavyweight framework/registry: per Evidence Engineering's own logic, abstractions wait until a second program genuinely requires them (FI-001 alone does not).

> **Deployment is not the end of research. Deployment begins Continuous Evidence.**

**Evidence Engineering principles (the growing methodology).** The platform's established discipline,
made explicit — the first six are how every program has always operated; #7–#9 are the FI-001-era
additions:

1. **Pre-registration** — freeze the hypotheses and the promotion gate *before* running.
2. **A verdict requires evidence** — "Validated" means a confidence interval that *excludes zero*; nothing weaker earns the word.
3. **Every result is a success** — Approved / Rejected / Inconclusive / Diversifier all ship a citable evidence package; negative findings are preserved.
4. **The stopping rule** — don't loop on parameters; a pre-registered stopping rule closes a program (see SEC-001 V2, MOM-002).
5. **Reproducible & honest** — survivorship-free, no-look-ahead, seeded, tested; conservative labels, never overclaim.
6. **Capabilities outlive strategies** — every program leaves reusable platform capabilities (the CAP-NNN catalog).
7. **Portfolio construction is evaluated *separately* from factor discovery** — factor discovery seeks *alpha*; portfolio engineering seeks *robustness*. *(FI-001.)*
8. **Live observations accumulate evidence; they do not rewrite research** — a bad day is *added to the evidence set*, not a trigger to change the strategy; only sustained, statistically-meaningful drift reopens a program. *(FI-001 review → Continuous Evidence.)*
9. **Continuous Evidence observes; it does not optimize** — the engine surfaces evidence and escalates to humans; it never auto-adjusts a parameter or a weight. *(FI-001 review; consistent with ADR 0035.)*

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
| **Retired** | Production ended, but the evidence is preserved — a citable end-of-life, not a deletion. (Reserved; not yet used.) |

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

**Capability Maturity ≠ Evidence Maturity** (keep them distinct — L5 is *not* the same as "high
confidence"):

| Dimension | Meaning |
|---|---|
| **Capability Maturity** (L0–L5) | how mature the *implementation* is — built, validated, envelope-defined, production-ready |
| **Evidence Maturity** (the Continuous Evidence clock) | how much *live evidence* has accumulated — Insufficient → Preliminary → Emerging → Moderate → Mature |

A capability can be L4 (production-ready) yet have *Insufficient* evidence maturity (just deployed); the
two axes move on different clocks and the Continuous Evidence Engine tracks the second.

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

### Executive dashboard (portfolio at a glance)

The high-level indicators an executive, investor, or patent reviewer reads first. **Every number is a real
count from this registry** — where an aggregate can't be honestly computed (e.g. a single "research efficiency
%"), we say so rather than invent one. Reporting only what we can verify *is* the differentiator.

| Indicator | Value |
|---|---|
| Programs chartered | **15** (8 strategy + 1 external-import [TV-001] + 1 platform capability [SCAN-001] + 1 portfolio-engineering [FI-001] + 1 portfolio-construction [PORT-001, onboarded] + **3 EAD event-driven** [GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001]) + **2 not-yet-run** (FI-002 Correlation Stability *reserved* · FI-003 Tail-Hedge Overlay Validation *planned*) = **17 total in `programs.py`**; EAD reserved: LOBBY-002 · OFX-001. **Reserved EAD items are NOT counted in the 15 chartered programs** — they become chartered only once a pre-registration with a formal program ID exists. |
| Research verdicts | Approved **1** · Diversifier **3** · Inconclusive **1** · Rejected **7** (RNG-001 · MOM-002 · INSIDER-001 · TV-001 · **GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001**) · Planned/Pending/Reserved **3** (TREND-001 · FI-002 · FI-003) · Validated capability **2** (SCAN-001 · PORT-001 — construction-validated, not alpha) · *capability-level Rejected* **1** (CAP-020). *(The seven program buckets sum to 17 = the full `programs.py` catalog; CAP-020 is a capability, not a program.)* |
| In production (paper) | **1 canonical** — MOM-001 Momentum v1.1 (Balanced 15% default; Conservative/Growth are **selectable presets**, not separate books — the two redundant vol-variant accounts were archived after the risk-profile study concluded, ADR 0036) |
| Preserved negative / null findings | **10** — RNG-001 rejection · MOM-002 rejection (reshaping a validated book — breadth & sector cap both declined) · SCAN-001 v0.1 ATR-tautology self-catch · SCAN-001 v0.4 confidence-uninformative · INSIDER-001 rejection (beta-not-alpha) · CAP-020 rejection (regime overlay not a Calmar/return improver — survivorship-free confirmed) · TV-001-SUPERTREND rejection (community-strategy candidate fails generalization/parameter-stability/cost) · **GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001** (three EAD event-driven rejections — public-disclosure events carry no residual alpha after matched controls) |
| Evidence generated | **Positive 4** (MOM-001 · SCAN-001 · LOW-001 · SEC-001) · **Negative 10** (RNG-001 · MOM-002 · INSIDER-001 · CAP-020 · TV-001 · SCAN v0.1 · SCAN v0.4 · GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001) · **Neutral 1** (MF-001) — *negative evidence is productive: it is the majority of the record and the platform's differentiator* |
| Confidence models | **2 rejected → 1 accepted** (v0.4 ATR-blended ✗ · naive CM-chase ✗ · v0.5 ATR-decoupled ✓) |
| Platform capabilities catalogued | **25** (CAP-001 … CAP-025, below) |
| Evidence packages on disk (`evidence/`) | **10+**, every one seeded & reproducible |
| Decision records | one per executed study (Evidence → Decision → Lesson, below) |
| Capability reuse | **High** qualitatively (SEC/LOW ≈ 90% reuse; SCAN "Very High") — no single aggregate % asserted |

### Status dashboard

| ID | Philosophy | Status | Progress | Research line | Verdict | Platform value |
|---|---|---|---|---|---|---|
| **MOM-001** | Momentum (cross-sectional relative strength) | **Production** (paper) | `██████████` 100% | Open (continuous evidence) | ✅ **Approved** | **Reference strategy** — proves Layers 1–2 work. **Risk-profile study concluded 2026-07-04:** the 3 vol-variant books (Conservative/Balanced/Growth) were corr ≈ 1.00 / 100%-overlap (CAP-021) → *one* alpha, three risk settings. Consolidated to **one canonical book** (Balanced 15% default; presets configurable); the Conservative & Growth accounts (users 3/4) archived-after-research. Governed by **ADR 0036 (Canonical Strategy Representation)**; decision `evidence/mom_001/MOM001_RiskProfile_Consolidation_v1.0.md` |
| **MOM-002** | Reshaping a concentrated momentum book (breadth / sector cap) | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **Honest rejection #2** — the platform declines a plausible *enhancement*, not just a strategy; diversify via independent factors, not by weakening the signal |
| **RNG-001** | Range / mean-reversion | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **Honest rejection** — the platform can decline |
| **MF-001** | Multi-Factor (value + quality) | **Completed** | `██████████` 100% | Follow-on (→ SF1) | 🟡 **Inconclusive** | **Research discipline** — the gate held the line |
| **SEC-001** | Sector Rotation (sector relative strength) | **Archived** (construction) | `██████████` 100% | Closed | 🟡 **Diversifier (B)** | **Diversification** — a non-momentum return source |
| **LOW-001** | Low Volatility (defensive) | **Completed** | `██████████` 100% | Follow-on (sleeve / V2) | 🟡 **Diversifier (B)** | **Defensive strategy** — the calm-stocks complement |
| **TREND-001** | Trend Following (time-series trend) — **NOT related to TV-001 / Supertrend** | **Planning** | `█░░░░░░░░░` 10% | Open (not started) | — **Pending** | **Trend philosophy** — the time-series complement. ⚠ Distinct from the (rejected) TV-001-SUPERTREND import candidate: TREND-001 is a *planned, not-yet-run* research program; Supertrend was a community-import candidate already fully evaluated and rejected. Same word "trend", different concepts. |
| **INSIDER-001** 📅 | Insider-Conviction (SEC Form 4 exec/officer open-market buys) — **first event-driven / alt-data program** | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected (C)** | **Event-Driven Capability v1** — the reusable SEC-Filing → Event Store → Event-Study stack (the program's lasting asset, even though the signal was declined) |
| **GOVCONTRACT-001** 📅 | Government-contract awards (Quiver / USAspending) — **EAD alt-data (ADR-0037)** | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **EAD matched-control engine** — 289 benchmarked awards, no residual alpha after sector/size/liquidity/momentum; the reusable matched-control + date-clustered-bootstrap stack is the lasting asset |
| **CONGRESS-001** 📅 | Congressional-trading disclosures (Quiver) — **EAD alt-data** | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **EAD confirmation #2** — 314 benchmarked purchase clusters, no residual alpha; reuses the matched-control engine wholesale |
| **LOBBY-001** 📅 | Lobbying spend-spike (Quiver) — **EAD alt-data** | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **EAD confirmation #3** — 1,078 benchmarked spikes, no *positive* alpha (leans slightly negative). The 4-rejection **"one finding"** (public-disclosure events carry no residual alpha) → the **Dataset Triage gate** + `rejected_reference_only` invariant. LOBBY-002 reserved |
| **TV-001** 🌐 | External Strategy Import — top-3 TradingView community strategies — **first external-import program** | **Archived** | `██████████` 100% | Closed | 🔴 **Rejected** | **External-import precedent + Strategy×Symbol-Fit screener (CAP-023)** — proves community popularity ≠ edge; the Supertrend candidate was rejected on full pre-registered validation (beats buy-and-hold on 1/15, no parameter rescue). Lasting asset = the import→recon→validation pipeline |
| **SCAN-001** ⚙ | Market Opportunity Discovery Engine (Candidate Engine) — **platform capability, not a strategy** | **Completed** (L3) | `██████████` 100% | **Closed** (Discovery Lab v1.0 complete; premarket gate is separate infra) | ✅ **Validated · Regime-Robust · Discovery Confidence accepted (v0.5)** | **Discovery Engine** — the reusable morning scanner feeding the Intraday Research Framework |
| **PORT-001** 🧩 | Portfolio Construction Engine — **multi-sleeve ERC (crash-protected equity momentum + cross-asset TSMOM), onboarded from the sibling system** | **Completed** (Onboarding Gate passed) | `██████████` 100% | Follow-on (self-stack data-fidelity port) | ✅ **Validated (construction) — beta + diversification, NOT alpha** | **Portfolio Construction Engine (CAP-018) + Capability Onboarding (CAP-019)** — reproduce-first onboarding: the platform's PCE/ERC reproduces the sibling combined book from its own sleeve returns (daily-return corr 0.99994, Sharpe 0.9001 vs 0.9015). Honest verdict: crash-protected **beta**, stock-selection alpha refuted under PIT data. Governed by ADR 0030. Evidence: `evidence/port_001/EvidencePackage_PORT-001_v1.0.md` |
| **FI-001** 🧩 | Multi-Factor Interaction & Portfolio Engineering — **how validated factors interact & combine** | **Completed** (Phases 1–4 + sector arm) | `██████████` 100% | Follow-on (FI-002) | 🟡 **Diversifier (B) — portfolio-level** | **Portfolio Engineering** — the bridge from Discovery Lab to combining factors; verdict: combining validated books reduces drawdown more than it adds alpha. *(The market-regime gross overlay it proposed, CAP-020, was later **rejected** as a Calmar/return improver — survivorship-free confirmed — but spun out **CAP-022** as a crash-insurance hypothesis.)* |
| **FI-002** 🧩 | Correlation Stability — **is factor correlation stable enough to allocate on?** | **Reserved** (do not start yet) | `░░░░░░░░░░` 0% | Reserved | — **Pending** | **Portfolio Engineering** — FI-001's most interesting finding (Mom↔Low corr swings −0.16→0.95) earns its own identity; start only after enough live paper data accrues |
| **FI-003** 🧩 | Crash-Insurance / Tail-Hedge Overlay Validation — **is the CAP-020 regime overlay a worthwhile tail hedge?** | **Planned** | `░░░░░░░░░░` 0% | Open (planned) | — **Pending** | **Portfolio Engineering** — the constructive follow-on to the CAP-020 rejection; validates capability **CAP-022** under *tail-risk* criteria (crash-regime drawdown/CVaR vs calm-regime cost-of-carry), NOT Calmar. Charter: `evidence/cap_020/CAP022_CrashInsurance_Charter_v0.1.md` |

**Program type — SCAN-001 is the first Platform Capability program** (⚙), distinct from the strategy programs (MOM/RNG/MF/SEC/LOW/TREND). Strategies answer *"should we trade this?"*; a capability answers *"what shared infrastructure do strategies reuse?"*. Plan: v0.1 + v0.2 (`..._CandidateEngine_Plan_v0.1.md`, `..._Plan_v0.2.md`). **The full Evidence-Engineering cycle ran here:** v0.1 prototype → caught its own ATR tautology (findings v0.1, kept as the scientific record) → v0.2 pre-registered de-tautologized hypotheses → **Validated on both cuts** (results v0.2). **Verdict ✅ Validated (Capability):** candidates expand **beyond their own ATR** (1.18–1.49× vs baseline ≈0.94×, CI-separated, p≈0 on both the top-500/3y and top-200/5y cuts), the expansion is tradeable (capturable & net move ~2.5× baseline), and all three signals (ATR+Gap+RVOL) are additive. ⚠ **"Validated" is the *capability* verdict, not a live-trading green light** — promotion to any live use still requires the premarket-data gate (PR #221) + a live-data replication, and the v0.3 Discovery-Stability study (regime/seasonality). Magnitude is regime/universe-dependent (recorded honestly in results §3). **Capability Maturity: L3 — Operating Envelope Defined ✅** (v0.3 complete, results v0.3): the edge is **REGIME-ROBUST** — positive + CI-separated in *every* market & volatility regime (no no-go), **best Bull + Low-vol (★★★★★)**, weakest **Bear (★★★, still positive)**; a counter-prior finding that **low-vol > high-vol** (the engine is not a volatility-chaser). Next maturity step = L4 (premarket-data gate + live replication). **v0.4 Confidence Model — EXECUTED, CONFIDENCE-UNINFORMATIVE (pre-registered negative):** the per-candidate confidence does not predict ATR-normalized expansion `E` (mildly inverse, CI-separated) → the `Opportunity × Discovery` product is **not shipped** as a ranking key (confidence remains an explainability artifact). Honest companions: confidence *does* track absolute move `CM` (→ v0.5 CM-targeted confidence), and the per-day Discovery Confidence forward-calibrates weakly-but-correctly with ~0 throttle headroom (REGIME-ROBUST). **Maturity stays L3.** A clean capability-layer "the platform declines its own proposed feature." **v0.5 De-Tautologized Confidence — EXECUTED, DECOUPLED-CALIBRATED (positive):** v0.4's negative was an *ATR-poisoning* artifact — removing ATR from the confidence (Gap+RVOL only, customer name **Discovery Confidence**) **flipped** the high−low `E` from −0.45 to **+0.89** (CI-sep, monotone, both cuts), calibrated within **3/3 ATR bands** on `CM`, and **lifted the book** with the top-K ATR *equal* to flat (decoupled, not an artifact). **Lesson: ATR belongs in *selection*, not *confidence*.** → ship `confidence_gr` as the Candidate Report confidence (ranking gated). **The platform rejected two confidence models before accepting one.** This **completes Discovery Lab v1.0** (Selection v0.2 / Operating Envelope v0.3 / Discovery Confidence v0.5); Maturity stays L3, research line **closed** (promote-or-close discipline — no v0.6). **SCAN is becoming a *family*, not one program** (owner direction): SCAN-001 (the Candidate Engine) is the first of an eventual `SCAN-Regime / SCAN-News / SCAN-Options / SCAN-Earnings` line, all profiles under the **Discovery Lab** subsystem — built as *configuration* over the shared engine, the Factor-Lab pattern (leave room; do not build yet).

**Verdict confidence** (how much we trust each verdict — the review's "Confidence" dimension, kept in the one existing registry, no new registry). Confidence is *High* when the evidence is statistically decisive (a CI that excludes zero, either direction), *Medium* when the verdict is a confidently-held "no decisive edge" (a B / inconclusive whose CI just spans zero), and *n/a* for reserved/unstarted programs:

| Program | Verdict | Confidence | Basis |
|---|---|---|---|
| MOM-001 | ✅ Approved | **High** | Sharpe 0.48, CI [0.13, 0.85], p=0.003 |
| RNG-001 | 🔴 Rejected | **High** | bootstrap mean-P&L CI spans zero + walk-forward decay |
| MOM-002 | 🔴 Rejected | **High** | breadth OOS-confirmed; sector cap arm directionally clear (recent-window) |
| INSIDER-001 | 🔴 Rejected (C) | **High** | H1 Sharpe-diff −0.30, CI [−0.63, −0.004], p=0.039 (CI below 0) |
| SCAN-001 | ✅ Validated (capability) | **High** | edge CI-separated, p≈0, both cuts; regime-robust |
| LOW-001 | 🟡 Diversifier (B) | **Medium** | H1 +0.24, CI [−0.029, 0.53] just spans zero |
| SEC-001 | 🟡 Diversifier (B) | **Medium** | H1 +0.16, CI [−0.03, 0.366]; construction isolated (H3) |
| TREND-001 | — Pending | **n/a** | planned; not started (the H1 +0.11 / CI [−0.11, 0.33] figure is a preliminary factor-study note, **not** a program verdict) |
| MF-001 | 🟡 Inconclusive | **Medium** | ΔSharpe +0.04, CI [−0.35, 0.48] spans zero |
| FI-001 | 🟡 Diversifier (B, portfolio) | **Medium** | no interaction cleared the Sharpe gate across 4 phases + sector arm |
| FI-002 | — Pending | **n/a** | reserved; not started |
| FI-003 | — Pending | **n/a** | planned; not started (validates CAP-022 as crash insurance) |

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
| INSIDER-001 | Research Team (event-driven precedent) — signal declined for the Portfolio | **High** (the Event Store / Event-Study Engine reuse across earnings / buybacks / dividends / 13F) |
| SCAN-001 | the **Intraday/Discovery Engine** + every strategy that consumes its candidates | **Very High** (a capability every strategy reuses) |

### Portfolio KPI — retired

> The **Executive Dashboard** (above) is now the canonical count view. The older Portfolio KPI section has been **retired** (2026-07-04) to avoid duplicate/stale counts as the registry grew past MOM-002 / INSIDER-001 / FI-001 / CAP-020 / CAP-022. *Most software can validate; very few can decline — that story now lives in the Executive Dashboard's "Preserved negative / null findings" line and the Evidence & Decisions table.*

### Outcome taxonomy — every result is value (owner refinement)

"Negative" is not one thing. A result contributes on **two independent axes** — its **research verdict** (what
the evidence concluded) and its **platform contribution** (what the platform gained regardless) — so even a
rejected or null program scores measurable platform value:

| Research verdict | Platform contribution |
|---|---|
| Approved · Diversifier · Inconclusive · Rejected · Validated capability | Reusable Capability · Methodology Improvement · Negative Finding (preserved) · Risk Discovery · Operational Improvement |

- **RNG-001** = *Rejected* (research) **+** *Methodology Improvement* (the honest-rejection workflow, CAP-011).
- **SCAN-001 v0.4** = *Negative Finding* (research) **+** *Methodology Improvement* (a pre-registered decline +
  the named v0.5 direction) **+** *Reusable Capability* (the Confidence Model mechanics, CAP-012).
- **LOW-001** = *Diversifier* (research) **+** *Reusable Capability* (research-calibration metrics, CAP-009).
- **MF-001** = *Inconclusive* (research) **+** *Risk Discovery* (it justified the SF1 data investment).

This is why the portfolio's "4 not-deployed decisions" are assets, not gaps: each scored on the right axis.

### Program families & the Discovery Lab roadmap (owner direction)

The flat ID space (`MOM-001`, `SCAN-001`, …) is evolving into **families under the two Labs**, so future
expansion is "add a profile", not "charter a program from scratch":

- **Discovery Lab → SCAN family** — **SCAN-001** Gap/RVOL/ATR (validated, L3) · SCAN-002 Relative-Volume ·
  SCAN-003 News · SCAN-004 Options · SCAN-005 ETF · SCAN-006 Macro · SCAN-007 Sector. Each = *configuration* over
  the shared Candidate Engine (CAP-001).
- **Factor Lab → MOM / LOW / SEC / MF / TREND families** — e.g. **MOM-001** (live) → MOM-002 (variant);
  **LOW-001** → LOW-002 (defensive sleeve). Each = *configuration* over the shared composite/score engine
  (CAP-007).

Only **SCAN-001** and **MOM-001** are built; the rest are **named room** (the Factor-Lab pattern — leave room,
don't build). Investors read the roadmap and see scalability; the platform makes no claim beyond the two built.

### Capability IDs (CAP-NNN) — capabilities are distinct from programs (owner)

Programs answer *"should we trade this / does this work?"*; **capabilities** are the reusable engines a program
leaves behind. They carry their **own permanent IDs** so the whitepaper/patent can cite a capability
independently of the program that birthed it. The CAP space is open-ended like the program space.

| CAP ID | Capability | Origin | Status |
|---|---|---|---|
| **CAP-001** | Market Opportunity Discovery Engine (Candidate Engine) | SCAN-001 | validated (v0.2), L3 |
| **CAP-002** | Evidence Package (pre-reg → script → JSON → MD, seeded) | MOM-001 / methodology | shipped |
| **CAP-003** | Circular-block Bootstrap Engine (CIs + recentered-null p) | MOM-001 | shipped |
| **CAP-004** | Research Program Registry (this doc + `programs.py`) | methodology | shipped |
| **CAP-005** | Decision Registry + Negative-findings ledger | methodology | shipped |
| **CAP-006** | Evidence Dashboard (`/evidence`) | P13 | shipped |
| **CAP-007** | Multi-factor composite / factor-agnostic score engine | MF-001 | shipped |
| **CAP-008** | Sector-neutral construction + construction-isolation method | SEC-001 | shipped |
| **CAP-009** | Research-calibration metrics (Confidence/Complexity/Duration/Accuracy) | LOW-001 | shipped |
| **CAP-010** | Explainable Candidate Report (reason + bounded confidence) | SCAN-001 | validated (v0.2) |
| **CAP-011** | Honest-rejection workflow | RNG-001 | shipped |
| **CAP-012** | **Discovery Confidence** (ATR-decoupled Gap+RVOL candidate-ranking confidence) | SCAN-001 | **validated (v0.5)** — accepted; ship to the Candidate Report, ranking use gated by the premarket-data step |
| **CAP-013** | Confidence-Model research mechanics (Opportunity×Discovery composite, Expanding-Window PIT, the reject→diagnose→redesign method) | SCAN-001 | shipped (the v0.4→v0.5 method; cited in the whitepaper drop-in) |
| **CAP-014** | **Pending-Aware Exposure Projection** (projected-state risk accounting: settled + in-flight; the reusable principle extends to buying power / margin / cash reservation / options / multi-strategy allocation) | **operations incident** (momentum-conservative 2026-06-22) → ADR 0025 | shipped — *first operationally-derived capability (Incident → Root Cause → ADR → Capability)* |
| **CAP-015** | **SEC-Filing Ingestion** (native EDGAR client: fair-access UA + ≤10 req/s throttle, ticker→CIK map w/ explicit unresolved coverage, Form 4 ownership-doc XML parser → typed open-market-buy events; read-only, off the order path) | INSIDER-001 → ADR 0027 | shipped — *first event-driven / alt-data capability; extends to 8-K/10-Q/13F* |
| **CAP-016** | **PIT Corporate-Event Store** (DuckDB, event-type-agnostic, idempotent `event_id` upsert, `events_asof` no-look-ahead, naive-UTC filed-at boundary) | INSIDER-001 → ADR 0027 | shipped — *reusable for earnings / buybacks / dividends / analyst / 13F* |
| **CAP-017** | **De-overlapped Event-Study Engine** (entry-on-filing PIT, hold-window de-overlap, equal-weight-basket H1, circular-block bootstrap Sharpe-diff CI + declared verdict tree) | INSIDER-001 | shipped — *the event analogue of Factor Lab's `run_program`* |
| **CAP-018** | **Portfolio Construction Engine** (multi-sleeve **ERC** blend in Factor Lab — sqrt-damped risk-budgeting + correlation-regime de-risk overlay + look-through risk evidence; allocation-policy-agnostic, future Policy Registry) | PORT-001 → ADR 0030 | **built (core, unit-tested)** — `factor_lab/{erc,portfolio}.py`; reproduction run data-gated. *What makes a portfolio program differ from single-sleeve LOW/MOM/SEC* |
| **CAP-019** | **Capability Onboarding** (the reusable lifecycle: External Capability → Evidence Reproduction → objective **Onboarding Gate** → **Capability Certificate** + Manifest → Continuous Evidence → Retirement; reproduce-first) | PORT-001 → ADR 0030 | **built (Gate + Certificate, unit-tested)** — `factor_lab/onboarding_gate.py`; the platform standard for onboarding INSIDER / Discovery outputs / external-partner strategies |
| **CAP-020** | **Market Regime Overlay** (de-risk gross exposure below the market's 200d trend) | FI-001 Phase 4 | **🔴 Rejected (Evidenced) 2026-07-04 — as a Calmar/Sharpe/return improver for the combined book.** Survivorship-free validation (Option B, 10,492 tickers) confirmed negative ΔCalmar (uniformly negative across all 9 grid cells; A −0.22 / B −0.30), a failed Sharpe guardrail (−0.15 / −0.23), ~10pp CAGR give-up, and 0/9 robustness. The "deeper drawdowns rescue it" thesis failed — the eqw combined book's drawdown (−24.6%) is not deeper than the biased one. **Retained finding:** reproducible **crash-insurance** behavior in stress regimes (COVID ΔMaxDD +14.7pp/ΔCalmar +0.25; 2022 +12pp — near-identical in both runs) → spun out to **[[CAP-022]]** (validated by program **FI-003**). See `evidence/cap_020/CAP020_Validation_v1.2.md` + `CAP020_DataDeepening_Scope_v0.1.md`. *Historical note: FI-001 originally identified CAP-020 as "Promising · Sharpe-neutral" on return-level evidence; the full survivorship-free validation supersedes that label.* |
| **CAP-021** | **Portfolio Interaction Measurement — the measurement layer the Continuous Evidence Engine consumes** (pairwise + rolling correlation, stress correlation in a book's worst drawdown, holdings/sector overlap, diversification score). Produces the *observed* distributions the CEE compares against each book's Research Envelope. | FI-001 Phase 1 | **shipped** — `scripts/fi001_phase1_measurement.py` + `app/services/portfolio_analytics.py`; the observed-side feed for Continuous Evidence |
| **CAP-022** | **Crash-Insurance / Tail-Hedge Overlay** (the SAME 200d-trend gross de-risk mechanism as CAP-020, but evaluated as a tail hedge, not a return improver — reproducibly cut COVID/2022 drawdowns ~13-15pp) | FI-001 Phase 4 → CAP-020 spin-off; validated by program **FI-003** | **Planned · Promising.** Acceptance = *does it reduce crash/tail loss enough to justify its cost-of-carry in normal markets?* NOT "does it improve Calmar." Primary metrics: MaxDD reduction in stress regimes (2020/2022-like), CVaR/worst-month improvement, CAGR drag in calm/bull (cost-of-carry), regime-timing false-pos/neg, deployability (cuts live risk w/o excessive return sacrifice). Validated-as-insurance if: materially reduces stress-regime drawdown + improves worst-month/CVaR + bounded calm-regime carry + robust across sweeps + no curve-fit timing. Reuses the deepened survivorship-free store + `scripts/cap020_regime_validation.py` primitives. Charter: `evidence/cap_020/CAP022_CrashInsurance_Charter_v0.1.md`. |
| **CAP-023** | **Strategy × Symbol Fit screener** (match a symbol's character to a strategy's nature: rolling Kaufman segment-Efficiency Ratio + ADX + Choppiness Index + per-bar noise → composite TrendScore = segER ÷ TR%; high-choppiness = mean-reversion fit) | TV-001 | **prototype** — `docs/strategies/pine/trendiness_screener.pine`; documented direction = a Discovery Lab layer (`Opportunity Registry → Strategy × Symbol Fit → Candidate Strategy Test`), not yet built into the engine. *Re-IDed from the TV-001 branch's tentative "CAP-020" (that ID is the Market Regime Overlay on main — collision resolved).* |
| **CAP-024** | **Point-in-Time Security Master** (identity resolver: CIK / ticker / company-name → a stable security id *or* a typed-unresolved reason; the one non-negotiable property is **no silent bad mapping** — every uncertain case returns unresolved, never a confident-looking wrong id, because a bad mapping fabricates an event study) | EAD Phase 0B (GOVCONTRACT-001) → ADR-0037 Decision 9 | **shipped (v0, minimal-on-purpose)** — `app/altdata/security_master.py`; every EAD event resolves through it. Reused by GOVCONTRACT-001 + CONGRESS-001. Reserved v1 work: ticker reuse / mergers / delistings / subsidiary→parent. |
| **CAP-025** | **Intraday Replay & Entry-Funnel Diagnostics** (sequence-correct intraday bar replay from an activation boundary + explicit fill model + entry/target/stop funnel that classifies where each candidate-day leaks; encodes two discipline lessons — *daily OHLC lies about intraday tradability*, and *candidate-days are correlated within a day* → significance needs a **date-clustered** bootstrap over a **train/test** split) | RNG-001 entry-logic sub-study | **built (L1)** — strategy-agnostic (opening-range / VWAP / breakout / mean-reversion); charter `evidence/cap_025/CAP025_IntradayReplayFunnel_Charter_v0.1.md`. Caught a rally-artifact false positive that pooled per-trade PF had manufactured. |

*CAP-012 is the honest case: the mechanics are a real, documented, reusable capability (cited in
`Docs/design/Whitepaper_DropIn_ConfidenceModel_v0.1.md`) even though v0.4's evidence declined the ranking use.*

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
| **INSIDER-001** 📅 | **Rejected (C):** 487 conviction hits → 212 de-overlapped positions; book Sharpe 0.55 / +254% total / maxDD −70%, per-event mean +10.4% — **but** H1 vs the equal-weight 134-name basket = Sharpe-diff **−0.30, CI [−0.63, −0.004], p 0.039** (CI entirely below 0 → significantly *worse* than owning the basket). Independent reproduction on TradingWorkbench PIT data (134-name sibling survivor universe, 2016–2026, 2,148 Form 4 buy-events). | `evidence/insider_001_s4_reproduction/` (+ `evidence/insider_001_s2_validation/`) | The "edge" is small/mid-cap **beta, not alpha** — owning the basket beats it risk-adjusted. Pre-reg expected **B** (sibling's "factor tilt"); the full 134-name reproduction **hardened it to C** (same code, no re-tuning — divergence from the interim B is itself the evidence, OQ1). A faithful independent reproduction *is* the win — success is defined independent of the verdict. The lasting asset is the reusable event-driven stack (CAP-015/016/017). |
| **SCAN-001** ⚙ | **v0.2 (validated):** candidates expand **1.18–1.49× their own ATR** vs baseline ≈0.94× (CI-separated, p≈0 on both top-500/3y and top-200/5y); tradeable (capturable & net move ~2.5× baseline); ATR+Gap+RVOL all additive. **v0.3 (L3, REGIME-ROBUST):** edge positive + CI-separated in every market/vol regime; best Bull + Low-vol, weakest Bear (still +ve). **v0.4 — CONFIDENCE-UNINFORMATIVE:** ATR-blended confidence does not predict `E` (inverse, high−low −0.45). **v0.5 — DECOUPLED-CALIBRATED:** ATR-*decoupled* confidence (Gap+RVOL, "Discovery Confidence") flips it to **+0.89** (CI-sep, monotone, both cuts), calibrates 3/3 ATR bands on `CM`, lifts the book with top-K ATR = flat (decoupled) → **accepted**. *v0.1's +3.24% range edge was caught as partly definitional and superseded.* | `evidence/scan_001_candidate_engine_v0_5/` (v0.5), `..._v0_4/`, `..._v0_3/`, `..._v0_2/`, `scan_001_candidate_engine/` (v0.1) | **The full Evidence-Engineering cycle, three times:** v0.2 *caught its own ATR tautology → validated*; v0.4 *proposed a Confidence Model → tested → declined it*; v0.5 *diagnosed WHY (ATR poisoning) → redesigned (ATR out of confidence) → validated*. **The platform rejected two confidence models before accepting one** — correcting, declining, *and* repairing its own ideas. The lesson: ATR belongs in selection, not confidence. |
| **TV-001-SUPERTREND** 📈 | **Rejected (Evidenced):** the only surviving candidate of the top-3 TradingView community strategies fails full validation — beats buy-and-hold on **1/15** symbols (both fit-winners MSFT/PLTR fail; PLTR −13.8× vs holding), the **best of 9 ATR×mult settings reaches 13%** (no parameter rescues it), ~98 trades/yr cost-bleed, walk-forward not robust. Faint positive per-trade signal (CI [0.0008, 0.0025] excludes 0) but loses to holding → **research-yes / deployment-no.** | `evidence/tv_001_supertrend/TV001_Supertrend_Result_v1.0.md` (+ pre-reg v0.2) | *Popularity ≠ edge*, confirmed by validation: the interim MSFT/PLTR optimism was window/symbol-fit; a broad, parameter-robust, cost-realistic test overturned it. We did **not** promote on freed capacity — the verdict gates deployment (ADR 0036). TV-001 program **closed**; the reusable import→recon→validation pipeline is the lasting asset. |
| **CAP-020** ⚙ | **Rejected as a Calmar/Sharpe/return improver.** Survivorship-free Option B (10,492 tickers) confirmed negative ΔCalmar (A −0.22 / B −0.30, uniformly negative across all 9 grid cells) and a failed Sharpe guardrail (−0.15 / −0.23); 0/9 robustness; ~10pp CAGR give-up. The "deeper drawdowns rescue it" thesis failed (eqw maxDD −24.6% not deeper than the biased −24.9%). | `evidence/cap_020/CAP020_Validation_v1.2.md` (+ DataDeepening scope) | A regime gross overlay is **not** a portfolio improver for the combined book — but it revealed a reproducible **crash-insurance** property now split into **CAP-022** (validated by program **FI-003**). One of the platform's clearest "declined the primary hypothesis, preserved the finding" cases — and it drove the deepening of the factor store to a survivorship-free 2017+ universe (a durable research asset). |

## Research Impact — what changed because of this research (owner review)

A cross-cutting "so what?" dimension: the *magnitude of change* each program caused, independent of its
verdict (a rejection can be high-impact).

| Impact | Meaning | Examples |
|---|---|---|
| ★★★★★ | Changed platform architecture | **SCAN-001** (Discovery Lab) · **ADR-0036** (canonical representation) · **MOM-001** (reference book + vol-overlay) |
| ★★★★ | Created a reusable capability | **CAP-020 → CAP-022** (regime → tail-hedge) · **PORT-001** (PCE + Capability Onboarding) · **INSIDER-001** (Event Store / Event-Study) |
| ★★★ | Produced a deployable strategy / decisive verdict | **LOW-001 · SEC-001** (diversifier sleeves) · **TV-001** (import→validation pipeline) |
| ★★ | Produced a methodology improvement | **RNG-001** (the honest-rejection precedent) · the *no-100%-equity* promotion rule (TV-001) |
| ★ | Local finding | per-study notes |

## Research Lineage — origin → outcome → what it generated (owner review)

Explicit provenance chains (increasingly useful as the registry grows to dozens of programs):

- **TV-001:** TradingView import → Supertrend candidate → pre-registered validation → **Rejected** →
  *import→recon→validation pipeline + CAP-023 fit-screener retained.*
- **CAP-020:** FI-001 Phase 4 regime overlay → survivorship-free validation → **Rejected as improver** →
  *generated **CAP-022** (crash-insurance) → generated **FI-003** (validation program).*
- **MOM-001 risk profiles:** three vol-variant books → CAP-021 measured corr ≈ 1.00 / 100% overlap →
  **consolidated** to one canonical book → *generated **ADR-0036** (Canonical Strategy Representation).*
- **SCAN-001 confidence:** v0.4 ATR-blended **rejected** → diagnosed ATR-poisoning → v0.5 ATR-decoupled
  **accepted** → *knowledge: "ATR belongs in selection, not confidence."*

## Knowledge Assets — distinct from Capabilities (owner review)

Capabilities are *software* (engines / algorithms / APIs — the CAP-NNN catalog). **Knowledge Assets** are
the *scientific findings* the research produced — negative findings, operating envelopes, parameter
boundaries, research rules — equally citable and durable, and likely to number in the dozens over time:

- **"ATR belongs in *selection*, not *confidence*"** (SCAN-001 v0.4→v0.5).
- **"Widening the *same* factor ≠ independent evidence"** (MOM-002 / FI-001; cross-variant corr 0.90–1.00).
- **"Popularity ≠ edge"** (TV-001 — the most-boosted script was the worst performer).
- **"No 100%-equity sizing in promotion-grade tests"** (TV-001 rule).
- **"One alpha = one canonical live account; risk profiles are configuration"** (ADR-0036).
- **"No deployment ahead of a verdict; freed capacity ≠ evidence"** (research_portfolio_lineup / ADR-0036).
- **Operating envelopes:** SCAN-001 regime-robust (L3) · CAP-020 works-in-crashes-only (→ CAP-022).

*(Documented next addition — review #5: a single-page **Research Timeline** placing MOM / LOW / SEC / SCAN
/ FI / TV / INSIDER across 2026 so a reader sees what happened, when, and why at a glance.)*

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

## Dependency graph (one picture)

How the layers connect — methodology at the top, capabilities (CAP-NNN) in the middle, programs and their
evidence at the bottom:

```
 Evidence Engineering (methodology — how we do research)
        │
        ▼
 TradingWorkbench (platform — risk engine · OrderRouter · audit/hash-chain · scheduler · execution)
        │
        ├──► Evidence Engine (CAP-002/003) ──► Research Registry (CAP-004) ──► Decision Registry (CAP-005)
        │
        ├──► Discovery Lab ──► Candidate Engine (CAP-001) ──► SCAN family ──► Intraday Framework
        │
        └──► Factor Lab ──► composite / score engine (CAP-007) ──► MOM · LOW · SEC · MF · TREND
                                        │
                                        ▼
                       Research Programs ──► Evidence Packages ──► Governance ──► Production
```

## Research Knowledge Graph (documented direction — NOT built)

The reviewer's "biggest opportunity," captured so it isn't lost. Today the hierarchy is `Evidence Engineering →
TradingWorkbench → Research Infrastructure → Programs`. The next permanent layer inserts a **Knowledge Graph**
between platform and infrastructure — edges between **Programs ↔ Capabilities ↔ Evidence ↔ Decisions ↔ Lessons ↔
Dependencies ↔ Confidence models ↔ research lineage** — turning this registry from a *table* into a *queryable
research memory*. It would let an assistant answer:

- *"Show me every program that improved drawdown."*
- *"Which rejected programs strengthened the platform?"*
- *"Which capabilities are reused by the most research programs?"*
- *"What did we learn from every negative finding involving ATR normalization?"* (today: SCAN v0.1 + v0.4.)

**Enabling step (also a direction):** give every program a structured, searchable field set — *Inputs · Outputs ·
Consumers · Dependencies · Evidence · Owner · Version · Lifecycle · Related programs* — the "GitHub-for-research"
record. This is a **direction only**; no build is implied here. It is named so the registry's growth has a
destination, not so the next session starts coding a graph database.

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

> **Discovery Lab v1.0 — the three permanent capability levels (owner, post-v0.5).** SCAN-001's arc defined a
> three-level structure the Discovery Lab carries forward, each level a separable capability:
>
> | Level | Capability | Question | Status |
> |---|---|---|---|
> | **L1 — Selection Engine** | candidate discovery (CAP-001) | *which names are opportunities?* | ✅ Validated (v0.2) |
> | **L2 — Operating Envelope** | when to trust the engine | *in which regimes does it work?* | ✅ Defined (v0.3) |
> | **L3 — Discovery Confidence** | how to rank candidates (CAP-012) | *how much do we trust each candidate?* | ✅ Accepted (v0.5) |
>
> With all three landed, **Discovery Lab v1.0 is complete** — and the confidence-model research line is **closed**
> (promote-or-close: no v0.6 optimization). ⚠ **Naming reconciliation:** the **per-candidate ranking** number is
> **Discovery Confidence** (v0.5, CAP-012); the **per-regime/per-day** trust number (v0.3/v0.4 "Discovery
> Confidence") is **Regime Confidence** ("Operating Envelope" stays the *methodology* name). Merged v0.3/v0.4
> docs are not rewritten.
> *(These "levels" are a Discovery-Lab internal structure, distinct from the platform-wide Capability Maturity
> L0–L5 ladder — SCAN-001's maturity remains **L3 (Operating Envelope Defined)**; v0.5 did not advance it.)*
- **Factor Lab** — *researches investment philosophies* (Momentum, Low-Vol, Sector, Trend, …).
- **Evidence Engine** — *produces Evidence Packages, statistical validation, governance decisions*.
- **Execution & Operations** — *paper, production, monitoring, Continuous Evidence*.

Discovery and Factor as **peers** cover nearly the whole quant-research workflow (find opportunities ↔
evaluate philosophies). This is a documented *direction*, pending owner ratification — see the whitepaper
Ch2 figure and patent-family items in `tasks/todo.md`.

---

## Appendix A — Version history (v0.16 → v0.1)

Moved out of the header Version cell (v0.18 fold) to keep the registry executive-readable; the full institutional changelog is preserved verbatim.

**v0.16 (2026-07-04)** — folded the tri-doc review (Registry 10/10): added **Research Impact** (★ magnitude-of-change), **Research Lineage** (origin→outcome→generated), a **Knowledge Assets** section (scientific findings distinct from software Capabilities), an **Evidence-generated** dashboard metric (Positive 4 / Negative 7 / Neutral 1), and disambiguated **TREND-001** (planned, *not* the rejected TV-001-Supertrend); Research Timeline noted as the next addition. **v0.15 (2026-07-04)** — reconciled the **TV-001** program from the `research/tv-001` branch onto main: added TV-001 to the status dashboard + `programs.py` (status **rejected**, incl. the Supertrend full-validation rejection) and the **Strategy×Symbol-Fit screener as CAP-023** (re-IDed from the branch's tentative "CAP-020", which is the Market Regime Overlay on main — collision resolved); dashboard recount → 11 programs / 23 capabilities / Rejected 4. **v0.14 (2026-07-04)** — CAP-020 **Rejected** as a Calmar/Sharpe/return improver (survivorship-free Option B confirmed the negative); **CAP-022** crash-insurance capability + **FI-003** tail-hedge validation program opened; registry **consistency pass** (dashboard recount → 10 programs / 22 capabilities; TREND-001 verdict → Pending; FI-001 row reflects the CAP-020 rejection; Portfolio KPI retired in favor of the Executive Dashboard; CAP-020 row rewritten verdict-first; CAP-021/022 reordered; CAP-020 added to Evidence & Decisions). _Older version history retained inline below (v0.13 → v0.1)._ **v0.13 (2026-06-23) — **SCAN-001 v0.5 EXECUTED → DECOUPLED-CALIBRATED (a positive — the confidence model is ACCEPTED after two rejections).** Removing ATR from the confidence (testing **Gap+RVOL strength only**, customer name **Discovery Confidence**) **flipped** v0.4's inverse: high−low expansion `E` went **−0.45 (v0.4) → +0.89 (v0.5)**, CI-separated, monotone, BOTH cuts; calibrates within **3/3 ATR bands** on `CM` (de-tautologized); and **lifts the book** (top-K E +0.19/+0.17, CM +0.51/+0.67) with the top-K's mean ATR **equal to flat** (5.48 vs 5.48 → not an ATR-selection artifact). Lesson: **ATR belongs in *selection*, not in *confidence*.** Per the frozen §4 matrix → ship `confidence_gr` as the Candidate Report confidence (ranking gated by the premarket-data step). **Capability Maturity stays L3** (a ranking confidence is not a live/Operating-Envelope advance). This **completes Discovery Lab v1.0** (the three levels: Selection v0.2 · Operating Envelope v0.3 · Discovery Confidence v0.5). ⚠ **Naming reconciliation:** going forward the **per-candidate ranking** number is **Discovery Confidence** (v0.5); the **per-regime/per-day** trust number (v0.3/v0.4 "Discovery Confidence") is renamed **Regime Confidence** ("Operating Envelope" stays the *methodology* name) — merged docs not rewritten. Evidence `evidence/scan_001_candidate_engine_v0_5/`; results doc v0.5; plan v1.1 (frozen). **v0.12 (2026-06-23)** — **folds the v0.11 review (Registry 9.9/10, SCAN-001 v0.4 Results 10/10).** Adds: an **Executive Dashboard** (real counts only — no fabricated efficiency %), **Program Families** + the **Discovery Lab roadmap** (SCAN-001…007), **Capability IDs (CAP-NNN)** distinct from program IDs, a two-axis **Outcome Taxonomy** (Research verdict × Platform contribution — every result is value), a one-picture **Dependency Graph**, and the **Research Knowledge Graph** as a documented future direction (the reviewer's "biggest opportunity"). Discipline note: the reviewer's illustrative KPI numbers (e.g. "Research Efficiency 92%") are NOT adopted — we publish only counts we can verify, the same honesty the research applies to itself. **v0.11 (2026-06-23)** — **SCAN-001 v0.4 Confidence Model EXECUTED → CONFIDENCE-UNINFORMATIVE (a pre-registered negative).** The per-candidate confidence does **not** predict ATR-normalized expansion `E` (mildly *inverse*: high−low edge −0.45, CI-separated) — same numerator-vs-denominator coupling that caught the v0.1 ATR tautology. Per the frozen §4 matrix (`E` primary), the `Opportunity × Discovery` product is **not shipped** as a ranking key; the bounded confidence stays an *explainability* artifact. Two honest companions: confidence **does** track *absolute* move size `CM` (recency 4.71→6.20→6.94 → names the v0.5 direction: a CM-targeted confidence), and the per-day **Discovery Confidence forward-calibrates weakly but correctly** (covariance CI-separated +ve both cuts) yet has ~0 throttle headroom (REGIME-ROBUST, as v0.3 found). **Capability Maturity stays L3** — v0.4 declined a mechanism, it did not advance toward L4. The platform *declines its own proposed feature* (the RNG-001 pattern at the capability layer). Evidence `evidence/scan_001_candidate_engine_v0_4/`; results doc v0.4; plan v1.1 (frozen). **v0.10 (2026-06-23)** — **SCAN-001 v0.3 EXECUTED → Capability Maturity L3 (Operating Envelope Defined).** Result: **REGIME-ROBUST** — positive + CI-separated in every market/vol regime (no no-go), best Bull + Low-vol (★★★★★), weakest Bear (★★★, still positive); counter-prior **low-vol > high-vol**. Dashboard row → Completed (L3) / ✅ Validated · Regime-Robust; results doc v0.3 linked. **v0.9 (2026-06-23)** — folds the SCAN-001 v0.3 + Registry review (both 10/10): **three-layer → four-layer product model** (adds **Research Infrastructure** as an explicit layer — Discovery/Factor Labs, Evidence Engine, registries, dashboard); new **Capability Maturity (L0–L5)** axis applied platform-wide (SCAN at **L2**, → L3 on v0.3) + the **Operating Envelope** concept; SCAN noted as a **family** under Discovery Lab. **v0.8 (2026-06-23)** — **SCAN-001 Prototype → Completed / ✅ Validated (Capability)** after the v0.2 de-tautologized run (both cuts SUPPORTED): status + verdict + evidence row updated; **Market Opportunity Discovery Engine** adopted as the customer-facing name (Candidate Engine = internal); new **Research Infrastructure** capability lens (*"this is the product"*); **architecture direction** note — Discovery Lab as a first-class peer to Factor Lab (four capability domains), pending ratification. Folds the owner review (Prototype 9.9 / Results 10 / Registry 10). **v0.7** — **SCAN-001 registered as Prototype** (PR #229): status Planning → **Prototype** (40%, ⚪ caveated); first evidence row added (H1 edge +3.24% but flagged *partly definitional* — selection includes ATR; recorded as a prototype finding, not a validated edge); Candidate/Discovery Engine + Explainable Candidate Report listed as **prototype** platform capabilities; findings doc linked. **v0.6** — final SCAN-001 review: a **Reuse level** dimension per program (commercial-value signal — SCAN = Very High). **v0.5** folded the SCAN-001 review: **SCAN-001** added as the first **Platform Capability** program; the Capability Matrix **split into Platform vs Investment capabilities**; a **Primary consumer** dimension per program. **v0.4** folded the prior review (9.95/10): a **Platform Capability Matrix** (capabilities by origin program — *customers buy capabilities, not strategies*; the seed of a future Capability Registry). **v0.3** folded the prior review (9.9/10): a **Platform value** column (why each program exists, beyond its result) and a **Research line** status (Open / Follow-on / Closed) orthogonal to program Status (a program can be `Completed` with its research line still open). **v0.2** folded the prior review (10/10): an explicit **status taxonomy** (Planning → Running → Completed → Archived → Production) separating *plan-complete* from *research-complete*; a per-program **progress** indicator; a **portfolio KPI** (count by verdict); each program extended toward **Evidence Package → Decision → Lessons Learned** (institutional memory); and an **open-ended** registry note. v0.1 was the pre-review draft.
