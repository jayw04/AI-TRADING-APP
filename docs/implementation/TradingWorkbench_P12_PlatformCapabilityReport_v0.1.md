# Trading Workbench — Platform Capability Report (v0.1)

| Field | Value |
|---|---|
| Document | **Platform Capability Report** — the flagship P12 deliverable answering *"why should customers adopt TradingWorkbench?"* |
| Version | v0.1 (2026-06-20) |
| Audience | prospective customers / partners / investors evaluating the **platform** (not the momentum strategy) |
| Companion | the **Strategy Evidence Book** (*"should we trade this?"*) |

> **The positioning.** TradingWorkbench is **not a momentum trading system.** It is an
> **evidence-driven quantitative research & strategy-engineering platform** whose *first validated
> application* is a momentum strategy. Customers adopt the **loop** — research → validation →
> governance → evidence → deployment → monitoring — not a single factor. P12 is where that loop was
> proven end-to-end on a real strategy.

---

## 1. What the platform is

A local-first, discipline-first system that takes a quantitative idea from hypothesis to governed,
audited, monitored production — and is **honest enough to reject ideas**. Two cleanly separated
halves: a **Research Platform** (discovers, validates, retires strategies on point-in-time,
survivorship-free data) and an **Execution Platform** (deploys validated strategies under
non-bypassable risk gates, an immutable audit chain, and tightly-gated AI).

## 2. The capabilities P12 validated (customer-visible)

| Capability | What it means for a customer | Proven by |
|---|---|---|
| **Generic factor research** | Research *any* factor (momentum, value, quality, growth, low-vol, ESG, custom, AI) — not a hard-wired strategy | §3 composite engine + factor-agnostic backtest |
| **Multi-factor modelling** | Blend + rank factors into one governed book, no per-strategy code | §3 `composite_scores` + `score_fn` |
| **Statistically-defensible evidence** | Bootstrap CIs + p-values + walk-forward, not point estimates | §1 evidence harness |
| **Reproducible research** | Same seed + data → same result; every report carries its provenance | §1–§3 experiment ids + repro metadata |
| **Honest governance** | A pipeline that records *Validated / Rejected / Inconclusive / Deferred*, with a Decision Register | §2 (Rejected sector caps) + §3 (Inconclusive value/quality) |
| **Operational trust** | Decisions are replayable, reconciled, recoverable; orders can't bypass risk | P11 (ADR 0021, 13 CI invariants) |

## 3. Why this is rare (the moat)

1. **Honest no's.** The platform *rejected* sector caps (§2) and ruled value/quality *Inconclusive*
   (§3) rather than shipping a flattering blend. A research process that can say *no* is the asset —
   most tools can't.
2. **Verifiable evidence, not claims.** Every result is reproducible from a tagged run; every live
   decision is **replayable** (reconstructed from its audit fingerprint) and **reconciled** against
   the broker. *"The audit log is executable evidence."* Most "AI/quant trading" tools offer a
   number; this offers a *proof*.
3. **Discipline as a product property, enforced in code.** 13 CI invariants (single OrderRouter,
   non-bypassable risk gates, immutable hash-chained audit, no-LLM-in-order-path, …) — a reviewer
   can verify the guarantees in the source, not take them on faith.
4. **Governed AI.** AI advises; it cannot reach the broker by default; the one sanctioned exception
   is wrapped in stacked friction and fully audited.

## 4. The platform lifecycle (what a customer runs)

```
Idea → Infrastructure → Exploration → Validation → Evidence → Decision → Production → Monitoring
                                    (GO/NO-GO gate, allowed to say NO)        (P11 operational trust)
```

Every strategy a customer brings inherits the same point-in-time honest backtest, the same statistical
gate, the same governance registers, and the same audited, recoverable execution — momentum was
merely the first to traverse it.

## 5. Scalability (no architectural change required)

The §3 composite engine + factor-agnostic backtest mean **new factors and strategies plug in without
touching the architecture**:

```
            TradingWorkbench (the platform)
                       │
      ┌────────────────┴─────────────────┐
   Research Platform              Investment Strategies
   • Composite engine             • Momentum  (validated, live-paper)
   • Evidence harness             • Vol-scaling overlay (validated → v1.1)
   • Governance / registries      • Value / Quality (inconclusive → SF1)
   • Reproducible reports         • Future / AI-generated factors
```

A customer scales along the **Research Track** (more factors/strategies) on a fixed **Platform
Track** (registries, evidence engine, backtest engine, governance, reports).

## 6. Every research outcome creates value

| A study's outcome | Strategy value | **Platform value (always positive)** |
|---|---|---|
| Factor validated | new strategy candidate | engine validated on a winner |
| Factor rejected | momentum stands alone | platform validated — it can *reject* honestly |
| Data inconclusive | no change | infrastructure complete; gates the data decision |

This is by design: the platform's value does **not** depend on any single factor working — it
compounds with every study, which is the hallmark of a durable research product.

## 7. What P12 demonstrated, concretely

- **It can validate** a strategy with defensible statistics (momentum: Sharpe 0.48, p=0.003).
- **It can improve** a strategy with a measured, gated overlay (vol-scaling: −38% drawdown → v1.1).
- **It can reject / defer** honestly (sector caps Rejected; value/quality Inconclusive → SF1).
- **It can operate** that strategy with audited, replayable, reconciled, recoverable execution (P11).

## 8. Honest current boundaries (what a diligent buyer should know)

- **Single-operator, local-first today** — not yet a hosted multi-tenant SaaS (that is the proposed
  **P13 — Product Readiness** phase: user workflows, APIs, strategy catalog, dashboards, deployment,
  licensing).
- **Live is paper-validated, gated** — engineered and operationally proven, not yet a real-capital
  track record.
- **Fundamentals depth is data-gated** — value/quality need SF1 (deep, broad, survivorship-free) for
  a decisive multi-factor verdict.

These are disclosed, scoped boundaries — not hidden gaps — and each has a named path forward.

## 9. The one-line case

> **An institutional-grade quantitative research, governance, and execution platform whose first
> validated application is a profitable, drawdown-controlled momentum strategy — where every result
> is reproducible and every live decision is provable.** That combination (defensible evidence + a
> reusable, governable, auditable platform) is uncommon, and it is what a serious customer, partner,
> or investor is actually buying.
