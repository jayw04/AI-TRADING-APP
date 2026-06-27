# Whitepaper Chapter 2 — drop-in text & figure (v0.3)

> **Purpose.** Ready-to-paste prose + ASCII figures for the Chapter 2 architecture section. The whitepaper
> master is a binary `.docx` that this repo can't edit directly, so this file supplies the content; the owner
> pastes it (and redraws the figures in the Word/diagram tool of choice). Mirrors **Methodology v1.1**
> (`docs/methodology/EvidenceEngineering_Methodology_v1.0.md`) and the **Research Program Registry v0.10**.
>
> **v0.2 changes** (fold of the Range implementation owner review, `docs/review/comments.md`, + **ADR 0029**):
> adds the **Opportunity Registry** as Discovery Lab's official output (Figure 2.2 + §2.z); decomposes
> Discovery into the **Qualification / Ranking / Assignment** engines; standardizes on **"Opportunity Set"**
> and **"evidence-weighted"** ranking.
>
> **v0.3 changes** (fold of the Ch2 v0.2 owner review, `docs/design/review-comments.md`, 9.9/10): adds
> **Principle Zero** (boxed, before Figure 2.1) and a **closing summary** (§2.summary); strengthens the
> Registry to the **single source of truth** for the day's Opportunity Set; clarifies **Platform *contains*
> Infrastructure *produces* Programs**; renames **L4 Production-Ready → L4 Production-Qualified**; adds the
> **Deployment Policy** chain (Operating Envelope → Confidence → Position Size); renames Figure 2.2's input
> from "Candidate Universe" to **"Research Universe"**; adds a determinism sentence to the Assignment Engine;
> notes Discovery's broader future scope; adds a **terminology-consistency** callout.

---

## Principle Zero (boxed statement — place immediately before Figure 2.1)

> ┌─────────────────────────────────────────────────────────────────────────────────────────┐
> │ **PRINCIPLE ZERO — Evidence precedes decisions.**                                         │
> │                                                                                           │
> │ Discovery identifies opportunities, Evidence validates them, Governance authorizes them,  │
> │ and only then are they executed. Every downstream capability **consumes evidence produced │
> │ upstream** rather than generating its own independent truth.                              │
> └─────────────────────────────────────────────────────────────────────────────────────────┘

This single principle explains the entire architecture that follows: the flow is always
**Evidence → Opportunity → Execution**, never a strategy inventing its own truth in isolation.

---

## Figure 2.1 — The TradingWorkbench capability architecture (canonical)

```
                          ┌──────────────────────────────┐
                          │     EVIDENCE ENGINEERING      │   ← the methodology (how we do research)
                          └──────────────┬───────────────┘
                                         │
        ┌────────────────────┬───────────┴───────────┬────────────────────┐
        ▼                    ▼                       ▼                    ▼
 ┌─────────────┐     ┌─────────────┐        ┌──────────────┐     ┌──────────────────┐
 │ DISCOVERY   │     │  FACTOR     │        │  EVIDENCE    │     │  EXECUTION &     │
 │   LAB       │     │   LAB       │        │  ENGINE      │     │  OPERATIONS      │
 │ (find       │     │ (evaluate   │        │ (validate +  │     │ (paper · live ·  │
 │  opportunity)│    │ philosophies)│       │  govern)     │     │  continuous evid)│
 └──────┬──────┘     └──────┬──────┘        └──────┬───────┘     └────────┬─────────┘
        │ Opportunity Sets   │  Factor books        │  Evidence Packages   │
        └──────────┬─────────┴──────────┬───────────┴──────────────────────┘
                   ▼                     ▼
            ┌─────────────────────────────────────┐
            │         RESEARCH PROGRAMS            │   ← instances (MOM/RNG/MF/SEC/LOW/TREND/SCAN…)
            └─────────────────────────────────────┘
```

**The end-to-end pipeline (the invention):**

```
Discovery → Research → Evidence → Governance → Promotion → Continuous Evidence
```

---

## Figure 2.2 — Discovery Lab's output: the Opportunity Registry (canonical)

Discovery Lab does not hand strategies a loose list of tickers; it produces a **frozen, dated, audited
Opportunity Set** through three named engines, and publishes it to the **Opportunity Registry** that every
strategy reads:

```
                         DISCOVERY  LAB
   ┌───────────────────────────────────────────────────────────────┐
   │  Research Universe         (the raw input pool, pre-screen)    │
   │        │                                                       │
   │        ▼  QUALIFICATION ENGINE   "Is this eligible?"           │
   │  Qualified Universe        (hard filters — structural,         │
   │        │                    change infrequently)               │
   │        ▼  RANKING ENGINE         "Which are best?"             │
   │  Ranked candidates         (evidence-weighted — research       │
   │        │                    model, expected to evolve)         │
   │        ▼  OPPORTUNITY ASSIGNMENT ENGINE   "Freeze & assign"    │
   │  Today's Opportunity Set   (Top-N, frozen pre-open for         │
   │        │                    the session)                       │
   └────────┼──────────────────────────────────────────────────────┘
            ▼
   ┌─────────────────────┐
   │ OPPORTUNITY REGISTRY│   ← single source of truth for the day's Opportunity Set
   └────────┬────────────┘
            │  (one contract, many consumers)
   ┌────────┴───────────┬───────────────┬───────────────┐
   ▼                    ▼               ▼               ▼
 Range              Momentum        Sector Rot.       Breakout / Trend …
```

**The long-term end-to-end architecture:**

```
Discovery Lab → Candidate Engine (Qualify → Rank → Assign) → Opportunity Registry
              → Strategy → Execution → Evidence → Continuous Verification
```

---

## §2.x — The four-layer product model (drop-in prose)

TradingWorkbench is best understood as four layers, in a precise **contains / produces** relationship:
**Methodology → Platform → (*contains*) Infrastructure → (*produces*) Programs.** **Evidence Engineering**
is the *methodology* — the discipline of producing, governing, and preserving the proof behind every
decision. **TradingWorkbench** is the *platform* — the operating system (risk engine, order router, immutable
audit, scheduler) that makes the methodology executable; **the platform *contains* the Research
Infrastructure**. **Research Infrastructure** is the set of reusable, platform-wide *assets* — Discovery Lab,
Factor Lab, the Evidence Engine, and the registries — that **strategies are *produced by***; this is the layer
a customer actually buys. **Research Programs** are the individual strategies and capabilities the
infrastructure *produces* — each a validated, rejected, or deferred instance. The distinction that readers
most often miss: the **Platform** is the runtime that *hosts* everything, while the **Infrastructure** is the
specific set of research *factories* it hosts — the platform runs; the infrastructure manufactures. A strategy
is a *result* of the method, never the product: Momentum is the reference implementation that proves the
first three layers work, the way Linux is a reference operating system rather than the operating system.

Discovery Lab and Factor Lab are **peers**: Discovery *finds market opportunities* (SCAN-001 is its first
profile; future Gap, News, Volume, Macro, ETF, and Options engines are *configurations*, not new codebases),
while Factor Lab *evaluates investment philosophies* (Momentum, Low-Volatility, Sector Rotation, Trend,
Multi-Factor). Between them they cover nearly the entire quantitative-research workflow. Discovery today finds
*tradable instruments*; the same machinery generalizes — tomorrow a Discovery profile could surface **data,
signals, events, anomalies, or themes**, making the architecture broader than equities selection (a direction
to keep in mind, not a commitment in this revision).

## §2.z — The Opportunity Registry and the three Discovery engines (drop-in prose)

Discovery Lab's job is to answer, every morning, *which* instruments a strategy should be looking at — and
to answer it as **evidence**, not as a hint. Internally it is **three distinct engines**, deliberately
separated because they answer different questions and evolve on different cadences:

1. The **Qualification Engine** answers *"is this instrument eligible?"* It applies **hard filters** —
   structural constraints such as minimum price, dollar-volume, and volatility — to the candidate universe and
   emits the **Qualified Universe**. Hard filters are structural and change **infrequently**; they are the
   eligibility gate, not the quality judgment.
2. The **Ranking Engine** answers *"among eligible instruments, which are best?"* It scores and orders the
   Qualified Universe using **evidence-weighted** metrics — realized-backtest evidence blended with a
   structural score — and the ranking model is a **research artifact expected to evolve** as forward evidence
   accrues. (The blend is a *weighting*, not a binary precedence: a single historical backtest is not allowed
   to dominate selection indefinitely; as a name accumulates its own forward sample, the weight shifts to keep
   the ranking honest.)
3. The **Opportunity Assignment Engine** answers *"what is today's set, and who gets it?"* It **freezes** the
   Top-N **Opportunity Set** before the market opens — immutable for the session, so each day's evidence is
   reproducible — and **assigns** it to one or more strategies. **Assignment is deterministic and reproducible
   precisely because the Opportunity Set is frozen before the market opens**: given the same inputs, the same
   set is produced, and nothing replaces it intraday — the bedrock of Evidence Engineering's reproducibility.

Keeping these three responsibilities distinct is what makes the architecture *reusable*. The frozen
Opportunity Set is published to the **Opportunity Registry** — the **single source of truth for the day's
Opportunity Set**, the official, persisted, audited output of Discovery Lab. A strategy never re-derives
selection; it **consumes** the Registry. Today the Range program is
the first consumer; the same contract — parameterized per program with its own filters, ranking model, and N —
is what Momentum, Sector Rotation, Trend, and Breakout consume next, instead of each re-implementing
"filter → rank → pick today's names." One producer, many consumers: a single place to fix a filter, a single
audit shape, and a single calibration surface across every program. (The immutable audit log remains the
source of truth for *what was decided*; the Registry is the operational, queryable read-model derived from
it.) This is the architectural decision recorded in **ADR 0029**.

## §2.y — Capability Maturity and the Operating Envelope (drop-in prose)

Two disciplines distinguish TradingWorkbench from a conventional quant platform. First, every capability
carries an explicit **Capability Maturity** level — L0 Concept, L1 Prototype, L2 Validated, **L3 Operating
Envelope Defined**, **L4 Production-Qualified**, L5 Continuously Verified — so a reader always knows how far a
result has been proven and de-risked, not merely that it "works." (We say *Production-**Qualified***, not
*Production-Ready*: "ready" is a subjective judgment, whereas "qualified" denotes that the capability has
**passed an evidentiary bar** — the term Evidence Engineering demands.)

Second, no validated capability is deployed blindly. As an aircraft is certified for a range of altitude,
temperature, and payload rather than simply "it flies," every capability is certified for an **Operating
Envelope** — the market and volatility conditions under which it works well, works marginally, or must not be
used. The envelope is produced by a pre-registered regime-decomposition study that maps the *already-validated*
edge across regimes; it yields a **Capability Strength Map** (a star rating per regime) and a **Confidence
score** per regime. That Confidence is not advisory — it is the input to a concrete **Deployment Policy** that
reaches all the way into live execution:

```
Operating Envelope → Capability Strength Map → Confidence (per regime) → Position Size
```

i.e. a capability operating in a regime where its Confidence is high is sized up; in a marginal regime it is
sized down; outside its envelope it is not deployed at all — the envelope governs *how much capital*, not just
*whether it works*. SCAN-001 was the first capability mapped this way: its edge proved **regime-robust** —
positive and statistically separated in every market and volatility regime tested — strongest in rising, calm
markets and weakest (but never absent) in bear markets. Documenting *where a capability should not be used* is,
counter-intuitively, one of the platform's strongest trust signals: it is the opposite of marketing, and
exactly what an enterprise or regulator expects.

## §2.summary — Chapter 2 closing (drop-in prose; place as the final paragraph)

> In conventional quantitative platforms, every strategy independently discovers, evaluates, and executes
> opportunities. TradingWorkbench separates those concerns into shared platform capabilities. Discovery
> identifies opportunities, the Evidence Engine validates them, Governance authorizes them, and reusable
> strategies consume the resulting **Opportunity Sets**. This architecture reduces duplication, improves
> reproducibility, and enables continuous calibration across every research program.

This ties Figures 2.1 and 2.2 together and states the differentiator plainly: TradingWorkbench is not trading
software with a methodology bolted on — it is an **Evidence Engineering platform** in which strategies are
interchangeable consumers of a shared, evidence-first opportunity pipeline. The compelling hierarchy the chapter
establishes:

```
Evidence Engineering → TradingWorkbench → Discovery Lab → Opportunity Registry
                     → Strategies → Execution → Continuous Evidence
```

---

## Terminology consistency (editorial note — applies whitepaper-wide, not just Chapter 2)

This chapter fixes the vocabulary the rest of the whitepaper should adopt. **Use consistently:**

| ✅ Canonical term | ❌ Never alternate with |
|---|---|
| **Opportunity Registry** | "candidate store", "selection table" |
| **Opportunity Set** | "Today's Universe", "Today's Range Universe", "Candidate List", "Top-N" |
| **Qualification Engine** | "screen", "filter step" (when naming the capability) |
| **Ranking Engine** | "scorer", "the ranker" (when naming the capability) |
| **Opportunity Assignment Engine** | "auto-select job" (when naming the capability) |
| **Research Universe** | "Candidate Universe" (for the *raw input pool*, pre-qualification) |

Consistency is not cosmetic: these terms are now load-bearing across ADR 0028/0029, the Range implementation
review, and this chapter — alternating synonyms makes the architecture read as several different systems
instead of one.
