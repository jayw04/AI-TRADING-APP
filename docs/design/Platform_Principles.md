# TradingWorkbench — Platform Principles (appendix)

> **What this is.** A synthesis and index of the recurring principles that the platform's ADRs and
> methodology already establish — collected in one place so they can be *cited* rather than re-argued.
> **This is not a decision record.** It introduces no new decision; each principle links to the ADR (or
> methodology doc) that actually decided it. Per the owner's 2026-07-03 ADR review (*"you now have enough
> recurring ideas… instead of repeating them, I'd collect them"* — and *"resist adding many more
> foundational operational ADRs"*), future operational improvements should **extend** these, not spawn new
> foundational ADRs.

---

## 1 — The platform in four layers

The architecture separates cleanly into four layers; every ADR belongs to one of them.

```
Evidence Engineering        ← the methodology (how a claim becomes trustworthy)
        │
        ▼
Data Integrity              ← trustworthy inputs (ADR 0018, 0033)
        │
        ▼
Portfolio / Strategy Research   ← Discovery Lab + Portfolio Engineering (ADR 0026, 0029, 0030)
        │
        ▼
Operational Governance      ← deterministic, contained, self-healing operation (ADR 0032, 0034, 0035)
```

And the operational lifecycle these produce:

```
Research → Deployment → Operation → Recovery → Continuous Evidence
```

---

## 2 — Platform principles (each links to where it was decided)

| Principle | Statement | Established by |
|---|---|---|
| **Historical Data Integrity First** | Trustworthy data is a prerequisite for trustworthy evidence; a data-integrity failure voids the evidence built on it. | ADR 0033 |
| **Evidence before Optimization** | Decisions follow evidence; the platform observes and measures before it tunes. The Continuous Evidence Engine *observes; it never optimizes.* | CEE charter (Principle #9); Evidence Engineering methodology |
| **Research ≠ Production** | Research and live operation are separate regimes; the eval/backtest harness never routes live orders, and *deployment begins* continuous evidence, it does not end research. | CEE charter; eval-harness-paper-only invariant (ADR 0006 v2) |
| **Portfolio Construction ≠ Factor Discovery** | Combining validated factors is risk-management (drawdown reduction), evaluated separately from discovering an edge. | Evidence Principle #7 (FI-001) |
| **Infrastructure Independence** | Infrastructure may change; research results and trading decisions must not. Same DB + config + data ⇒ same decisions, on any host. | ADR 0032 (Invariant 2), generalized |
| **One Active Scheduler** | Exactly one host is ARMED and may dispatch orders at any moment; every other host is STANDBY and inert. | ADR 0032 (Invariant 1) |
| **Risk Containment is Local** | A risk failure is contained to the smallest appropriate scope (the breaching account), never propagated across independent programs. | ADR 0034 |
| **Automation ≠ Governance** | Automation exists to improve reliability, not to override governance; it may only take actions whose correctness can be proven, and never alters risk-control state. | ADR 0035 |
| **Deployment Begins Continuous Evidence** | *"Deployment is not the end of research. Deployment begins Continuous Evidence."* Live behavior is continuously verified against the research envelope. | CEE charter |
| **Single OrderRouter** | Every order — manual, strategy, agent — flows through exactly one dispatch point; risk gates are non-bypassable. | ADR 0002 |

*Also load-bearing and worth citing: conservative defaults / configurable extremes; append-only hash-chained audit; credentials Fernet-encrypted at rest (ADR 0003).*

---

## 3 — Evidence Integrity hierarchy

The complete "why the evidence is trustworthy" foundation. ADRs 0014, 0018, and 0033 together define **Evidence Integrity**:

```
Evidence Integrity
├── Point-in-Time Integrity      — data available at decision time only        (ADR 0018)
├── Historical Data Integrity    — complete · correct · continuous · provenance (ADR 0033)
├── Reproducibility              — seeded, deterministic harness; same computation (ADR 0014)
└── Continuous Verification      — live behavior stays in the research envelope  (CEE)
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
└── Continuous Evidence — verify live behavior vs the envelope        (CEE)
```

---

## 5 — Platform Maturity model

A capability (or the platform as a whole) matures through six levels. This is a *roadmap*, distinct from a
capability's **evidence maturity** (how much live evidence has accrued — see the CEE charter §3).

| Level | Stage | Meaning |
|---|---|---|
| **L1** | Research | Hypothesis + methodology defined |
| **L2** | Backtesting | Reproducible historical evidence on integrity-checked data |
| **L3** | Paper | Live paper deployment on an isolated account |
| **L4** | Operational Governance | Deterministic, contained, self-healing operation (ADR 0032/0034/0035) |
| **L5** | Continuous Evidence | Live behavior continuously verified against the research envelope |
| **L6** | Production | Live capital, having cleared all of the above |

---

## 6 — A note on "Operational Confidence" (forward-looking)

The review observes that **Research Confidence**, **Operational Confidence**, and **Evidence Confidence** are
three distinct concepts (e.g. *Momentum: Research High · Operational 100% · Evidence Low — only 30 days
live*). The CEE's Evidence Clock already produces the Evidence-confidence axis; the Operational axis maps to
the ADR-0035 health states (🟢/🟡/🟠/🔴). Surfacing all three together on a dashboard is a natural future
step — recorded here, not yet built.

---

*Maintained as a living index. When an ADR adds or revises a principle, update the relevant row here rather
than restating the principle across documents.*
