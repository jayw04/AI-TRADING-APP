# P13 Direction Document v0.1 — Product Readiness + the Post-P12 Program Roadmap

| Field | Value |
|---|---|
| Document version | **v0.1 (2026-06-21)** — first draft, from the owner's *"Tasks to work on"* notes (`Docs/implementation/Tasks to work on.md`). Frames P13 (Product Readiness) as the next phase while capturing the owner's **three parallel tracks** + **phased A→D roadmap**. Phase numbers (P13/P14/P15) are owner-confirmable per CLAUDE.md. |
| Date | 2026-06-21 |
| Phase | **P13 (proposed)** — Product Readiness / Commercialization (follows P12 Validation & Results) |
| Status | **Draft charter — owner confirmation pending** (the §8 open questions). Next: owner confirms the track sequence + the SF1 timing → then draft the first P13 per-session doc. |
| Predecessor | **P12** — Validation & Results — functionally complete (§1–§3 merged + tagged; both flagship deliverables on `main`). **P12.5** — Production Validation — live; the evidence track now accrues automatically. |
| Successor | **P14 — Factor Lab** (gated on SF1 acquisition) → **P15 — Research Marketplace / Continuous Research**. Roadmap arc: **P10 Portfolio Architecture → P11 Operational Trust → P12 Research & Validation → P12.5 Production Validation → P13 Productization → P14 Factor Lab (SF1) → P15 Research Marketplace.** |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | No new architectural invariant expected for the productization work itself. Research work (Track B) stays under **0014** (backtests = ground-truth) + **0019** (Research Engine read-only). Any new external dependency (e.g. SF1 data vendor) requires an **ADR** per CLAUDE.md (local-first invariant). |
| Inputs | The owner's *"Tasks to work on"* notes; the P12 Direction doc (`..._P12_Direction_ResultsValidation_v0.1.md`, v0.3); the [[factor-research-program]] (momentum = the OOS edge; multi-factor inconclusive→deferred-to-SF1); the live P12.5 paper book + weekly evidence automation. |

---

## 0. North star — the Evidence Engineering Platform thesis

> **The competitive advantage is no longer the momentum strategy. It is the *Evidence Engineering
> Platform*: a system that discovers strategies through disciplined research, validates them with
> statistical evidence, governs them through reproducible decision processes, executes them safely
> with institutional risk controls, and continuously accumulates verifiable operational evidence.**

Owner's honest assessment of where the project stands:

| Lens | Completion | Implication |
|---|---|---|
| **Research platform** | ~75–80% | The pipeline (research → evidence → governance → trading → operations) is proven end-to-end. |
| **Commercial software product** | ~25–30% | The backend is strong; the *product* (UI, APIs, installer, multi-user, packaging, docs) is largely unbuilt. |

P13's job is to close the **commercial-product** gap while the evidence track keeps compounding and
the research track advances in parallel. That is a stronger, more defensible vision than "another
algorithmic trading app."

## 1. Why this direction exists

P11 proved the platform is **trustworthy**; P12 proved its strategy carries a **real, honestly-measured
edge**; P12.5 turned the live paper book into **continuously-accruing, verifiable evidence**. The
remaining work is no longer *can we trust it* or *is it good* — it is **can someone other than the
author use it, and can the research program keep producing new validated edges.**

That splits into three tracks that advance in parallel, not in sequence.

## 2. The three parallel tracks

| Track | Theme | Priority | Headline outcome |
|---|---|---|---|
| **A — Production Evidence** | Let the proof grow | ★★★★★ | Weekly + **monthly** institutional reports, a **Production Confidence Score**, an **operational KPI dashboard**, long-term paper track record. *Mostly already automated (P12.5); extends it.* |
| **B — Product (P13)** | Make it usable + sellable | ★★★★★ | Product UI / unified dashboard, REST **product APIs**, installer + config wizard, authentication + multi-user, packaging, product docs. *The commercialization gap.* |
| **C — Research** | Settle the open factor question | ★★★★☆ | Acquire **SF1**, build a **generic factor engine** (Factor Lab), re-test Value + Quality, expand factor families. *Unlocks the next research generation.* |
| **(D — AI assistants)** | Force-multiply the above | ★★★★☆ | Research / documentation / strategy-review / governance assistants (all advisory, ADR 0006-constrained). |
| **(E — Whitepaper)** | Tell the story | ★★★★☆ | Chapters 9–12 + professional editing, graphics, website. |

**The competitive-advantage realization (owner):** every track reinforces the *Evidence Engineering
Platform* — A makes the evidence undeniable, B makes it usable, C makes it extensible, D/E make it
legible. None of them is "the strategy."

## 3. Phased roadmap (owner's recommendation)

- **Phase A (now → 3–6 months) — keep the evidence compounding.** Continue P12.5: live evidence,
  weekly reports (automated), **monthly reports**, operational KPIs, **confidence score**. *Background
  track; low marginal effort, high marginal product value.*
- **Phase B — P13 Productization.** Dashboard, product UI, APIs, installer, authentication, packaging,
  documentation. *The main build.*
- **Phase C — P14 Factor Lab (after SF1).** Purchase SF1, then build the generic factor engine: Value,
  Quality, Growth, Profitability, composite factors. *Settles the deferred multi-factor verdict.*
- **Phase D — P15 Research Marketplace.** Research → Evidence → Registry → Strategy Library; users
  browse validated strategies. *The long-term platform vision.*

## 4. Immediate development tasks (next 2–3 months)

Captured verbatim from the owner's notes, grouped by track (priority stars as given):

- **A. Production Evidence (★★★★★):** monthly evidence reports · production confidence score ·
  operational KPI dashboard · long-term paper-trading history · strategy health dashboard.
- **B. Product (★★★★★):** product UI · REST APIs · installer · configuration wizard · user
  management · product documentation.
- **C. Research (★★★★☆):** acquire SF1 · generic factor engine · factor-comparison framework ·
  multi-factor optimizer · factor correlation matrix.
- **D. AI (★★★★☆):** research assistant · documentation assistant · strategy-review assistant ·
  governance assistant.
- **E. Whitepaper (★★★★☆):** Chapters 9–12 → professional editing · graphics · cover · website.

### The three concrete Track-A increments (nearest-term, build on P12.5)

1. **Monthly Evidence Report** — beyond the weekly snapshot: performance · risk · operations ·
   incidents · recovery · replay · reconciliation · changes · **lessons learned**. *This is what
   turns the evidence trail into institutional reporting.* Natural extension of `live_evidence.py`.
2. **Production Confidence Score** — a single 0–100 score (e.g. 87 → 92 → 95) that **increases with
   time + clean operation**, composed from the operational/safety/verifiability signals already
   captured (uptime, clean replay/reconcile, incident-free days, risk-gate efficacy).
3. **Operational KPI Dashboard** — uptime · execution latency · broker latency · reconciliation
   success · risk rejects · breaker triggers · recovery time · replay success. *These become
   customer-facing metrics.* Builds on the P11 §2 Prometheus/Grafana substrate.

## 5. The SF1 decision (owner's CTO-hat recommendation)

> **Buy SF1 within the next month — but do not stop product development while waiting for it.**

**Why SF1 (and why *not* "because the platform needs it"):** the *platform* is already proven. SF1 is
needed because the **research roadmap** needs it — the current FMP data (197 mega-cap names, ~5yr,
non-survivorship-free) **cannot decisively answer** whether Momentum + Value + Quality + Profitability
+ Low-Vol actually outperform. That question requires better fundamentals: **20+ years, ~3000 stocks,
survivorship-free, point-in-time** — institutional-grade.

**What stays unblocked without SF1:** productization, paper trading, operations, whitepaper, APIs,
dashboard, SaaS, documentation, AI assistant. **What is blocked:** a decisive multi-factor verdict
(the [[factor-research-program]] / P12 §3 "inconclusive→deferred" question).

**Recommended parallelism:**

| Track A — Product | Track B — Research |
|---|---|
| P13 Product Readiness · UI · APIs · operations · live-evidence accumulation | Acquire SF1 · build the generic Factor Lab · re-test Value + Quality · expand factor families |

This keeps commercialization and the research program advancing together.

> ⚠ **ADR required:** SF1 is a **new external data dependency.** Per the CLAUDE.md local-first
> invariant, adding it requires an ADR (vendor, licensing, ingest path, where it sits relative to the
> existing `factor_data_full.duckdb` store). Draft that ADR as the first Track-C step.

## 6. How P13 fits the existing conventions

- **Productization does not relax any architectural invariant.** The single OrderRouter, the
  non-bypassable risk gates, the hash-chained audit log, no-LLM-in-the-order-path, activation
  cooldowns — all hold. A product UI / API surface is a *new front door to the same house*, not a new
  house. Any API that can submit an order routes through `OrderRouter.submit()` like everything else.
- **Multi-user + authentication** is the largest genuinely-new subsystem and will need its own
  session docs + likely an ADR (the platform was single-user/local-first; multi-user changes the
  threat model, the credential scoping, and the audit `actor` semantics).
- **Conservative defaults, configurable extremes** still governs every new product setting.

## 7. What this direction does NOT commit to yet

- A frozen P13 session sequence (this is the charter; per-session docs come after owner confirmation).
- The multi-user architecture (local-first → SaaS is a real architectural shift; ADR-gated).
- Enabling any new live strategy behavior (research stays advisory/evidence-only until gated).
- A specific SF1 vendor/SKU or price (Track-C ADR decides).
- Phase numbers P14/P15 as final (owner-confirmable).
- `p11-complete` / `p12-complete` tags — those are elapsed-time/owner calls, tracked separately.

## 8. Open questions for owner confirmation

1. **Track sequence:** confirm parallel **A (background) + B (main build) + C (SF1, start within a
   month)**, with D/E opportunistic — or reprioritize?
2. **P13 first session:** start B with the **unified product dashboard**, the **REST product APIs**, or
   **authentication/multi-user** (the dependency root)? Recommendation: APIs + dashboard first (they
   surface existing capability with no threat-model change); auth/multi-user as a deliberate ADR-gated
   session after.
3. **SF1 now or after a Track-A increment?** Recommendation: kick off the **SF1 ADR + acquisition** in
   parallel immediately (long lead time), build the Monthly Report meanwhile.
4. **Monthly report + confidence score:** are these P13 deliverables, or a P12.5 continuation (Track A)
   shipped before P13 formally opens? Recommendation: ship them as **P12.5 increments now** — they are
   small, build directly on `live_evidence.py`, and raise product value immediately.

## 9. Notes & gotchas

1. This doc is a **charter**, not a session plan — do not write code against it. The first executable
   artifact is a per-session doc once §8 is resolved.
2. Source: `Docs/implementation/Tasks to work on.md` (owner's raw notes, 2026-06-21).
3. The nearest-term, lowest-risk, highest-leverage work is the **three Track-A increments** (§4) —
   they extend the already-automated P12.5 evidence pipeline and need no new subsystem. Good
   candidates for "do now while the SF1 ADR and P13 scoping settle."
4. Keep the **Evidence Engineering Platform** framing front-and-center in the whitepaper + Platform
   Capability Report — it is the defensible product thesis, per the owner's overall assessment.
