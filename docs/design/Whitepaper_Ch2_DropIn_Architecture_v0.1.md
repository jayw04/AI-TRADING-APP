# Whitepaper Chapter 2 — drop-in text & figure (v0.1)

> **Purpose.** Ready-to-paste prose + an ASCII figure for the Chapter 2 architecture section. The whitepaper
> master is a binary `.docx` that this repo can't edit directly, so this file supplies the content; the owner
> pastes it (and redraws the figure in the Word/diagram tool of choice). Mirrors **Methodology v1.1**
> (`docs/methodology/EvidenceEngineering_Methodology_v1.0.md`) and the **Research Program Registry v0.10**.

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
        │  Candidate Sets    │  Factor books        │  Evidence Packages   │
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

## §2.x — The four-layer product model (drop-in prose)

TradingWorkbench is best understood as four layers. **Evidence Engineering** is the *methodology* — the
discipline of producing, governing, and preserving the proof behind every decision. **TradingWorkbench** is
the *platform* — the operating system (risk engine, order router, immutable audit, scheduler) that makes the
methodology executable. **Research Infrastructure** is the set of reusable, platform-wide *assets* —
Discovery Lab, Factor Lab, the Evidence Engine, and the registries — that strategies are *produced by*;
this is the layer a customer actually buys. **Research Programs** are the individual strategies and
capabilities run through that infrastructure — each a validated, rejected, or deferred instance. A strategy
is a *result* of the method, never the product: Momentum is the reference implementation that proves the
first three layers work, the way Linux is a reference operating system rather than the operating system.

Discovery Lab and Factor Lab are **peers**: Discovery *finds market opportunities* (SCAN-001 is its first
profile; future Gap, News, Volume, Macro, ETF, and Options engines are *configurations*, not new codebases),
while Factor Lab *evaluates investment philosophies* (Momentum, Low-Volatility, Sector Rotation, Trend,
Multi-Factor). Between them they cover nearly the entire quantitative-research workflow.

## §2.y — Capability Maturity and the Operating Envelope (drop-in prose)

Two disciplines distinguish TradingWorkbench from a conventional quant platform. First, every capability
carries an explicit **Capability Maturity** level — L0 Concept, L1 Prototype, L2 Validated, **L3 Operating
Envelope Defined**, L4 Production-Ready, L5 Continuously Verified — so a reader always knows how far a result
has been proven and de-risked, not merely that it "works."

Second, no validated capability is deployed blindly. As an aircraft is certified for a range of altitude,
temperature, and payload rather than simply "it flies," every capability is certified for an **Operating
Envelope** — the market and volatility conditions under which it works well, works marginally, or must not be
used. The envelope is produced by a pre-registered regime-decomposition study that maps the *already-validated*
edge across regimes; it yields a **Capability Strength Map** (a star rating per regime) and a **Confidence
score** per regime that downstream strategies fold directly into position sizing. SCAN-001 was the first
capability mapped this way: its edge proved **regime-robust** — positive and statistically separated in every
market and volatility regime tested — strongest in rising, calm markets and weakest (but never absent) in
bear markets. Documenting *where a capability should not be used* is, counter-intuitively, one of the platform's
strongest trust signals: it is the opposite of marketing, and exactly what an enterprise or regulator expects.
