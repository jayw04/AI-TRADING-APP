# Research Portfolio Lineup — the live paper accounts as an Evidence-Engineering demonstration

| Field | Value |
|---|---|
| Date | 2026-06-23 |
| Status | Draft — **direction approved** (review 9.7/10); Phase 2 build-out not yet started |
| Owner | Jay Wang |
| Source | `Docs/review/comments.md` (reviewer 8.8/10 → owner second-pass → reviewer 9.7/10 approval) |

## Purpose

Define what the four live paper accounts should demonstrate. The claim this platform
exists to prove is **not** "we have a profitable strategy" — it is that **Evidence
Engineering consistently discovers, validates, rejects, deploys, and operates systematic
strategies, with transparent governance and honest distinctions.** The live accounts are
the demonstration of that claim, so each must be an **evidence-backed research program at
a known lifecycle stage**, not a brokerage account running an algorithm.

## What this proves

> This lineup proves that TradingWorkbench is **not a strategy factory**. It is an
> **Evidence Engineering platform that can promote, constrain, reject, and continuously
> monitor investment capabilities according to their evidence verdict.**

Concretely, the live accounts show the platform can distinguish, side by side and
operating: **Approved alpha → Diversifier sleeve → Archived/Rejected strategy → Capability
under validation.** That distinction *is* the product.

## The core principle: the verdict is the headline

Every live book's **most visible attribute is its research verdict**, not its name or its
returns. This is the moat. The registry's verdicts are:

| Program | Verdict | Evidence (summary) |
|---|---|---|
| **MOM-001** Momentum | ✅ **Approved — standalone alpha** | Sharpe 0.48, 95% CI [0.13, 0.85], p=0.003, 1997–2026, survivorship-free, cost-robust. Ships **with** the vol-target overlay (−76% raw drawdown is the risk story). |
| **LOW-001** Low Volatility | 🟡 **Diversifier (B)** — no decisive standalone edge | Best risk-adjusted book (Sharpe ~0.59) but no standalone edge; defensive complement. |
| **SEC-001** Sector Rotation | 🟡 **Diversifier (B)** — construction line **archived** | Non-momentum return source; archived per the stopping rule (no standalone edge). |
| **RNG-001** Range / Mean-Reversion | 🔴 **Rejected** — no edge | PF 1.27 (< 1.3 bar); bootstrap mean-P&L CI spans zero; walk-forward PF decays to 0.89. |
| **MF-001** Multi-Factor (value+quality) | 🟡 **Inconclusive** — gate held | ΔSharpe +0.04, CI [−0.35, +0.48] spans zero → keep Momentum v1.1. |
| **SCAN-001** Discovery Engine | ⚙ **Capability** — Validated, Maturity L3 | Not a strategy; shared infrastructure (Market Opportunity Discovery Engine). |

**Why this matters:** if four books sit side by side as peer "strategies" or
"hypotheses," a visitor reads four standalone alphas — which the evidence above
contradicts. The honest framing is **one validated standalone strategy + diversifier
*sleeves* shown for portfolio-construction value + a rejected benchmark + a capability
mid-validation.** Less immediately flashy; a much bigger story — it shows the platform can
tell **alpha from overlay from failure**.

## The target lineup (Phase 2)

| Account | Program (label by registry ID) | Verdict (headline) | Role in the demonstration |
|---|---|---|---|
| Research Portfolio A | **MOM-001 — Momentum** | ✅ Approved, standalone | The production strategy. Pick **one** vol target (e.g. Balanced 15%). |
| Research Portfolio B | **LOW-001 — Low Volatility** | 🟡 Diversifier — **sleeve** | Defensive sleeve, shown **for construction value**, not as standalone alpha. |
| Research Portfolio C | **SEC-001 — Sector Rotation** | 🟡 Diversifier — **overlay** | Run **as an overlay/sleeve only** — standalone would contradict its archived verdict. |
| Evidence Sandbox | **RNG-001 — Range / Mean-Reversion** | 🔴 Rejected — benchmark | The permanent honest-rejection account (most platforms only show winners). |
| (pipeline, not a live book yet) | **SCAN-001 — Discovery** | ⚙ Capability, L3 | A program visibly **in** the lifecycle, mid-validation. |

Name the live accounts by their **registry IDs** (MOM-001 / LOW-001 / SEC-001 / RNG-001),
not "Production 1/2/3" — so every account reads as an evidence-backed research program.

**One account per program/sleeve.** Each live program/sleeve gets its **own** account so
attribution stays clean (no shared cash or risk limits muddying which program produced
which result). That's four live accounts total: MOM-001, LOW-001, SEC-001, RNG-001.

**SCAN-001 is NOT a live account.** It is a *capability*, not a strategy — it lives in the
**lifecycle / Evidence Dashboard** (a program visibly mid-validation), never as a paper
"strategy account." Do not provision a book for it.

### Dashboard: a "Verdict / Role" field on every live account

Surface the verdict + role as a first-class label so the honest distinctions are visible,
not buried:

| Account | Verdict / Role |
|---|---|
| MOM-001 | **Approved / Production Strategy** |
| LOW-001 | **Diversifier / Defensive Sleeve** |
| SEC-001 | **Diversifier / Overlay Sleeve** |
| RNG-001 | **Rejected / Benchmark** |

## Two honesty guardrails (hard constraints, not preferences)

1. **Diversifiers run as sleeves, labeled as such — never marketed as standalone alpha.**
   LOW-001 and SEC-001 are Diversifier (B). Their value is **portfolio construction**, not
   edge. Running SEC-001 standalone would contradict its own evidence package (and risks
   being "momentum at another aggregation level" via its relative-strength internals — ask
   *is this different alpha, or momentum expressed differently?*). **The verdict gates the
   role.**
2. **No deployment ahead of a verdict.** No Quality/Value/Multi-factor production book yet
   — **MF-001 is Inconclusive**; deploying it would dress an inconclusive result as a
   deployable strategy. **Expansion is gated by the lifecycle reaching an Approved or
   Diversifier verdict, not by a desire for a fuller dashboard.**

## Two reframes adopted

- **The live account is one *stage* in the lifecycle, not the product.** The demonstration
  is the full chain running live — *hypothesis → evidence package → governance → production
  → continuous evidence → re-validation* — with books deliberately at **different verdicts
  and stages**. A visitor seeing one Approved book in production, two diversifier sleeves,
  one rejected benchmark, and one capability mid-validation is seeing the **process
  itself, operating, with its honest distinctions intact** — which no competitor can show.
- **Operational reliability is a co-equal pillar, not a Phase-1 warm-up.** One book that
  reconciles cleanly, recovers from failure (ADR-0021 recovery contract), and accrues
  continuous evidence is more persuasive than four that occasionally drift. The CI-enforced
  invariants and the recovery contract are **demonstration assets in their own right.** Do
  not let the rush to breadth outrun the operational trust that makes any of it believable.

## Roadmap

- **Phase 1 — now (✅ in place).** The three momentum books (Conservative 10 / Balanced 15
  / Growth 20) are live on PAPER with entry vol-scaling + the pending-aware risk gates +
  rebalance idempotency. **Keep them running** and accrue operational evidence (stability,
  execution, reconciliation, recovery, risk controls). This proves reliable operation —
  the co-equal pillar. *(Note: 3 vol-variants prove the **risk dial**, not research breadth
  — that's fine for Phase 1; the verdict-distinct lineup is Phase 2.)*
- **Phase 2 — verdict-distinct lineup.** Consolidate to **one** Momentum book (MOM-001,
  Approved); add **LOW-001** as a labeled defensive **sleeve** (needs a strategy template
  built from the LOW-001 research); deploy **SEC-001** as an **overlay** (merge its template
  — PR #242 — and run it as a sleeve, not standalone); keep **RNG-001** as the rejected
  benchmark on the sandbox. Every book's verdict is the most visible thing about it.
- **Phase 3 — gated factor expansion.** Quality / Value / Multi-factor / regime-aware /
  market-neutral — **only** as each research program reaches a real Approved/Diversifier
  verdict through the lifecycle. Aligns with the institutional point-in-time,
  survivorship-free factor direction.

## What's needed before Phase 2

- **SEC-001 template**: built + tested (PR #242, currently OPEN) — merge + deploy, and wire
  it to run **as a sleeve/overlay**, not standalone.
- **LOW-001 strategy**: only a research study exists; a runnable, evidence-cited strategy
  template must be built from the LOW-001 evidence package (defensive sleeve).
- **Account assignment (one per program)**: today's accounts are Balanced→acct1,
  Conservative→acct3 (now the old-Growth account), Growth→acct4, Range→acct2(sandbox).
  Phase 2 reassigns acct1/3/4 to **MOM-001 / LOW-001 / SEC-001** — one account per
  program/sleeve so attribution is clean (no shared cash/limits). Owner-gated; goes through
  activation/cooldown.
- **UI framing — the "Verdict / Role" field**: surface verdict + role as a first-class
  label on every live account (Evidence Dashboard + Strategies page), per the table above
  (e.g. `MOM-001 — Approved / Production Strategy`, `LOW-001 — Diversifier / Defensive
  Sleeve`). The honest distinctions must be visible, not buried.

## References

- Research Program Registry — `Docs/implementation/TradingWorkbench_Research_Program_Registry_v0.1.md`
- Evidence Engineering Methodology v1.0 — `Docs/methodology/EvidenceEngineering_Methodology_v1.0.md`
- ADR 0014 (backtests = primary eval ground truth), ADR 0021 (operational/recovery contract)
- SEC-001 template — PR #242; SEC-001 promotion plan — `Docs/implementation/TradingWorkbench_SEC001_PaperPromotion_Plan_v0.1.md`
- Review thread — `Docs/review/comments.md`
