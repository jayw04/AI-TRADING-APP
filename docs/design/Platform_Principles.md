# TradingWorkbench — Platform Principles

**Version 1.0 · Ratified 2026-07**

> **What this is.** The stable, named principles that govern TradingWorkbench — collected in one place so
> ADRs can *cite* them rather than re-argue them. **This is not a decision record**; it introduces no new
> decision. Each principle links to the ADR (or methodology doc) that actually decided it.
>
> **Why it's versioned.** Principles should change *rarely*. ADRs evolve, implementation changes, research
> changes — but the principles beneath them are meant to be durable. Versioning makes that stability
> visible and auditable: today is **v1.0**; a new or revised principle produces **v1.1**, and ADRs can name
> the version they were written against. Per the owner's 2026-07-03 review (*"resist adding more
> foundational ADRs; consolidate what you have and let future ADRs inherit these"*), future operational
> work should **extend these principles**, not spawn new foundational ADRs.

---

## 1 — The governance hierarchy

Principles sit *above* decisions, which sit above implementation. This is the shift from
"decisions → implementation" to a coherent, principle-led architecture:

```
                 Platform Principles          ← this document (stable; changes rarely)
                        │
                        ▼
               Architecture Decisions (ADRs)  ← apply the principles to a concrete problem
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  Evidence Layer  Operational Layer  Risk Layer
        │               │               │
        └───────────────┼───────────────┘
                        ▼
                Continuous Evidence          ← verifies live behavior against the research envelope
```

And the four architectural layers every ADR belongs to:

```
Evidence Engineering  →  Data Integrity  →  Portfolio / Strategy Research  →  Operational Governance
```

---

## 2 — The principles, by category

### 2.1 Scientific principles

| Principle | Statement | Established by |
|---|---|---|
| **Historical Data Integrity** | Trustworthy data is a prerequisite for trustworthy evidence; a data-integrity failure voids the evidence built on it. | ADR 0033 |
| **Research must be reproducible** | A result is only evidence if a seeded, deterministic harness reproduces it byte-for-byte. | ADR 0014 |
| **Evidence before Optimization** | The platform observes and measures before it tunes; the CEE *observes, it never optimizes.* | CEE charter (Principle #9) |
| **Research ≠ Production** | Research and live operation are separate regimes; the eval harness never routes live orders. | CEE charter; eval-harness-paper-only (ADR 0006 v2) |
| **Portfolio Construction ≠ Factor Discovery** | Combining validated factors is risk-management, evaluated separately from discovering an edge. | Evidence Principle #7 (FI-001) |
| **Continuous Evidence** | *Deployment is not the end of research; deployment begins Continuous Evidence.* | CEE charter |

### 2.2 Engineering principles

| Principle | Statement | Established by |
|---|---|---|
| **Infrastructure Independence** | Infrastructure may change; research results and trading decisions must not. | ADR 0032 (Invariant 2), generalized |
| **Deterministic Execution** | Same database + configuration + market data ⇒ the same decisions, on any host. | ADR 0032 · ADR 0014 |
| **One Active Scheduler** | Exactly one host is ARMED and may dispatch orders at any moment; every other is STANDBY and inert. | ADR 0032 (Invariant 1) |
| **Single OrderRouter** | Every order — manual, strategy, agent — flows through exactly one dispatch point. | ADR 0002 |

### 2.3 Governance principles

| Principle | Statement | Established by |
|---|---|---|
| **Automation ≠ Governance** | Automation exists to improve reliability, not to override governance; it acts only where correctness is provable. | ADR 0035 |
| **Risk Containment is Local** | A risk failure is contained to the smallest appropriate scope (the breaching account), never propagated. | ADR 0034 |
| **Human Approval for Risk Controls** | Risk-governance state (halts, breakers, caps) is never altered by automation; it always requires a human. | ADR 0035 (Level 4) · non-bypassable risk (ADR 0002) |

### 2.4 Operational principles

| Principle | Statement | Established by |
|---|---|---|
| **Quiet failures should become visible** | Silent degradation is the enemy; conditions that warrant a look are surfaced (alerts, the daily-report watchdog). | ADR 0035 (Level 3) · daily report |
| **Self-heal only operational state** | Automation may auto-correct operational faults (Levels 1–2) but never trading decisions or risk gates. | ADR 0035 |
| **Audit every automatic recovery** | Every automatic action leaves an append-only record of what was detected, what was done, and the before/after. | ADR 0035 · hash-chained audit log |

*Separation of concerns, in one line:* **Evidence** determines *what should happen*; **automation** ensures *the machinery works*; **governance** determines *what is permitted*.

---

## 3 — Evidence Integrity hierarchy

ADRs 0014, 0018, and 0033 together define **Evidence Integrity** — the "why the evidence is trustworthy" foundation:

```
Evidence Integrity
├── Point-in-Time Integrity      — data available at decision time only         (ADR 0018)
├── Historical Data Integrity    — complete · correct · continuous · provenance (ADR 0033)
├── Reproducibility              — seeded, deterministic harness                (ADR 0014)
└── Continuous Verification      — live behavior stays in the research envelope (CEE)
```

Data integrity and reproducibility are complementary: reproducibility guarantees the *same computation*; integrity guarantees it runs on the *complete and correct dataset*.

---

## 4 — Operational Governance hierarchy

```
Operational Governance
├── Deployment          — deterministic, infra-independent hosting   (ADR 0032)
├── Scheduler           — exactly one ARMED host                     (ADR 0032, Invariant 1)
├── Risk Containment    — failures contained to the smallest scope   (ADR 0034)
├── Self-Healing        — auto-fix only what's provably safe (L1–L4) (ADR 0035)
└── Continuous Evidence — verify live behavior vs the envelope       (CEE)
```

---

## 5 — Platform Maturity model

A capability (or the platform) matures through six levels. This is a *roadmap*, distinct from a capability's
**evidence maturity** (how much live evidence has accrued — CEE charter §3).

| Level | Stage | Meaning |
|---|---|---|
| **L1** | Research | Hypothesis + methodology defined |
| **L2** | Backtesting | Reproducible historical evidence on integrity-checked data |
| **L3** | Paper | Live paper deployment on an isolated account |
| **L4** | Operational Readiness | Deterministic, contained, self-healing operation is in place (ADR 0032/0034/0035 — the *Operational Governance* capability) |
| **L5** | Continuous Evidence | Live behavior continuously verified against the research envelope |
| **L6** | Production | Live capital, having cleared all of the above |

---

## 6 — "Operational Confidence" (forward-looking)

**Research Confidence**, **Operational Confidence**, and **Evidence Confidence** are three distinct axes
(e.g. *Momentum: Research High · Operational 100% · Evidence Low — only 30 days live*). The CEE Evidence
Clock already produces the Evidence axis; the Operational axis maps to the ADR-0035 health states
(🟢/🟡/🟠/🔴). Surfacing all three on one dashboard is a natural future step — recorded here, not yet built.

---

## Roadmap for this document

- **v1.1 (candidate, not yet added):** a **Principle Stability** principle — *principles should change very
  rarely; ADRs may evolve, implementation and research change, but the principles remain stable.* Deferred
  deliberately (owner: "not now — later") so v1.0 stays consolidated.

*Maintained as a living index. When an ADR adds or revises a principle, bump the version and update the
relevant row here rather than restating the principle across documents.*
