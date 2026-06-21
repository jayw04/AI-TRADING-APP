# P13 Direction Document v0.1 — Product Readiness + the Post-P12 Program Roadmap

| Field | Value |
|---|---|
| Document version | **v0.3 (2026-06-21)** — **2nd owner review folded (`comments.md`, post-P14/P13.5).** v0.1 = first draft; v0.2 folded the strategy-expansion decision (3→2→4) + P13.5/Track-D/Factor-Lab-first. **v0.3 reframes the strategy direction (§9):** the *Evidence Engineering Platform* thesis is **confirmed + elevated to the moat** ("the platform validated AND declined a strategy"); future strategies become **diverse investment *philosophies*, not momentum variants**, via a **three-tier framework** + **two parallel tracks** (Platform / Research); **SF1 = done → supporting infra (don't buy more)**; 6–12-month priorities set. §8 (the P13.5 decision) is retained as executed history. |
| Date | 2026-06-21 |
| Phase | **P13 (proposed)** — Product Readiness / Commercialization (follows P12 Validation & Results) |
| Status | **Phase 1 SHIPPED + direction refined.** SF1 acquired (ADR 0023) → bulk ingest → Factor Lab → multi-factor re-test (INCONCLUSIVE → keep v1.1); Monthly Report + Confidence Score + KPI Scorecard shipped; 3 Risk Profiles LIVE on PAPER. **Next per §9:** build the live evidence record + the **Range Trader research program** (→ Strategy #2) + **Sector Rotation** + **Low Volatility**. |
| Predecessor | **P12** — Validation & Results — functionally complete (§1–§3 merged + tagged; both flagship deliverables on `main`). **P12.5** — Production Validation — live; the evidence track now accrues automatically. |
| Successor | **P13.5 — Platform Validation** (validate the platform itself: 3 live risk profiles + 90–180d evidence + benchmarks) → **P14 — Factor Lab** (gated on SF1) → **P15 — Research Marketplace**. Roadmap arc: **P10 Portfolio Architecture → P11 Operational Trust → P12 Research & Validation → P12.5 Production Validation → P13 Productization → P13.5 Platform Validation → P14 Factor Lab (SF1) → P15 Research Marketplace.** |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | No new architectural invariant for the productization work itself. Research work stays under **0014** (backtests = ground-truth) + **0019** (Research Engine read-only). **SF1 = a new external data dependency → `ADR 0023` (Sharadar SF1 Integration, Draft)**, per the CLAUDE.md local-first invariant; relates to **0018** (point-in-time factor data FMP/Sharadar). |
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

## 8. Confirmed direction (owner review folded — `comments.md`, 2026-06-21)

The owner approved expanding beyond one strategy — **but evidence-gated, in a structured sequence** —
holding to the thesis: *"every strategy answers a research question; don't add strategies just to have
more."* The v0.1 §8 open questions are resolved as follows.

### 8.1 Strategy expansion — all three approved, sequenced

| Priority | Option | Decision | Timing |
|---|---|---|---|
| ★★★★★ | **Option 3 — SF1 + Factor Lab** | **Start immediately** — highest strategic priority; resolves the biggest remaining evidence gap | Week 1 |
| ★★★★☆ | **Option 2 — Live vol-target variants** | Approved — demonstrates *configurable risk*, not new alpha | After SF1 acquisition underway |
| ★★★☆☆ | **Option 4 — Range Trader validation** | Approved as a **research track only — do NOT activate yet** | After Factor Lab infra complete |

- **Option 2 → "Risk Profiles," not raw numbers:** **Conservative 10% · Balanced 15% · Growth 20%**,
  all paper-traded, so customers see the *risk dial working live* (strong marketing; same strategy, no
  new alpha claim).
- **Option 4 → the platform demonstration:** run Range Trader through Backtest → Walk-Forward →
  Bootstrap → Evidence → Governance → Decision. **Both outcomes prove the platform** — "Momentum
  approved, Range rejected" is itself proof the evidence process is real. Activate later *only* if it
  clears its gate.

### 8.2 New milestone — P13.5 Platform Validation (between P13 and P14)

Validate the *platform itself* before expanding the research program with SF1:
- Three live momentum **Risk Profiles** (10 / 15 / 20%); **90–180 days** accumulated paper evidence.
- Monthly evidence reports · Production Confidence Score · Operational KPI dashboard.
- Product dashboard · product APIs · platform **performance & scalability benchmarks**.

### 8.3 New Track D — Platform Capability Validation

*Platform, not strategy.* Enterprise benchmarks: e.g. **1000 strategies / 100M rows / 10 years** —
performance, scalability, parallelism, cloud, database, API, stress, recovery, failure, replay,
monitoring. These become the **enterprise-benchmark** story (feeds P13.5 + the Platform Capability
Report).

### 8.4 Roadmap reorder — Factor Lab first

Build the **generic Factor Lab first**, then everything plugs into it:
**Factor Lab → Momentum → Value → Quality → Composite → Range → future factors (Sector Rotation,
ETF Rotation, …).** *"That architecture will last for years."* (Supersedes the §3
Momentum→Value→Quality ordering.)

### 8.5 Execution order (owner's 12-week plan)

| Phase | Weeks | Work |
|---|---|---|
| **1** | 1–4 | **SF1 ADR + acquisition** (Option 3 kickoff) · continue P12.5 evidence · build **Monthly Evidence Reports + Production Confidence Score** |
| **2** | 5–8 | Build the **Factor Lab** · enable **10/15/20% vol paper books** (Option 2) · unified **product dashboard + APIs** |
| **3** | 9–12 | **Re-test Value + Quality** on SF1 · first **multi-factor portfolio** · begin **Range Trader OOS validation** (Option 4) |
| **4** | — | Promote winners through the full lifecycle (Research → Evidence → Governance → Paper → Production Validation); reject/defer those that miss the threshold |

**Immediate next actions (Phase 1):** (1) **ADR 0023 — Sharadar SF1 Integration** (Draft); (2)
**Monthly Evidence Report** + (3) **Production Confidence Score** as P12.5 increments on
`live_evidence.py`.

## 9. Strategy & roadmap reframe (2nd owner review — `comments.md`, post-P14/P13.5)

After P14 (multi-factor re-test) + P13.5 (Risk Profiles live), the owner's strategic read crystallized.

### 9.1 The thesis is the moat
TradingWorkbench is an **Evidence Engineering Platform**; strategies merely *prove* it. The defensible
IP is that **the platform validated AND declined a strategy** (P14 kept v1.1 on an honest,
non-significant multi-factor result). *"Most software can validate; very few can reject."* Keep this
front-and-center in the whitepaper, Platform Capability Report, and patent.

### 9.2 Add strategies — as diverse *philosophies*, not variants
"More strategies? Yes, but not immediately" — and **NOT another momentum/value/quality variant** (those
barely move confidence). Build strategies that demonstrate **multiple investment philosophies**:
momentum chooses *what*, sector rotation chooses *where*, mean-reversion is a different alpha class.

| Tier | Meaning | Strategies | Action |
|---|---|---|---|
| **A** | Validated → first commercial offering | Momentum **Balanced / Conservative / Growth** | ✅ live on PAPER; accrue the evidence record |
| **B** | Research candidates (build, need evidence) | **Sector Rotation** (favorite — complements momentum) · **Low Volatility** (institutional; reuses vol infra) · **Trend Following** (institutional pedigree) · **Range / Mean Reversion** | OOS → walk-forward → bootstrap → evidence package → governance, THEN paper |
| **C** | Wait — P14 already answered | Value · Quality · Dividend · Growth · AI-generated factors · alt-data | deprioritize |

⚠ **Range Trader = Strategy #2** (demonstrates multiple alpha classes — momentum/trend ↔
range/mean-reversion; powerful marketing), but **DO NOT paper-trade it yet** — it must clear the full
research gate first (the same discipline P14 applied to multi-factor).

### 9.3 Two parallel tracks (supersedes the §3 phased A→D order)
- **Platform Track (never stops):** Evidence Engine · Governance · Operations · AI · Reporting ·
  Patent · Product · Commercialization.
- **Research Track:** Momentum ✅ → Risk Profiles ✅ → **Range (in progress)** → **Sector Rotation
  (next)** → **Low Vol (next)** → **Trend Following (next)** → Factor Lab (continuous).

New strategy roadmap: *Better Momentum → Risk Profiles → Range → Sector Rotation → Low Vol → Trend
Following → Factor Lab* — the platform demonstrates **multiple investment philosophies**, far stronger
commercially than multiple momentum variants. Full detail in the **Strategy Development Roadmap**
(`TradingWorkbench_StrategyRoadmap_v0.1.md`).

### 9.4 SF1 — purpose achieved; now supporting infrastructure
The owner's SF1 stance **changed**: a month ago "buy more"; **today "no."** The current investment has
already (1) resolved value/quality on survivorship-free data, (2) validated the factor-research infra,
(3) strengthened the evidence-based-"no" thesis. SF1 is now **supporting infrastructure, not the
primary driver** — don't buy more unless a *specific* new factor study needs deeper coverage. (This
deprioritizes ADR 0023's "deeper-history tier" as a near-term item; it stays a documented re-eval
trigger, not a plan.)

### 9.5 Recommended priorities (next 6–12 months)
1. **Continue live paper trading** the 3 momentum profiles → a **3–6 month evidence record** (highest).
2. **Complete the Range Trader research program** (OOS / walk-forward / bootstrap / evidence package /
   governance) → if it passes, promote to paper (Strategy #2).
3. **Develop Sector Rotation** — broadens beyond stock selection; a different investment philosophy.
4. **Develop Low Volatility** — institutionally recognized; leverages the existing vol infrastructure.
5. **Continue productization** — web/evidence dashboards, strategy-comparison + customer reporting,
   whitepaper, patent filing, public website.

> **Final framing (owner):** TradingWorkbench is *not* a quant trading application — it is an **Evidence
> Engineering platform with a validated operational foundation, a proven research methodology, and its
> first production-quality strategy family.** The next stage is proving the platform can reliably
> **discover, validate, reject, and operate diverse strategy classes** under a common governance
> framework — the shift from *proving one strategy* to *proving the platform* is the commercial + IP win.

## 10. Notes & gotchas

1. This doc is a **charter**, not a session plan — do not write code against it. The first executable
   artifact is a per-session doc once §8 is resolved.
2. Source: `Docs/implementation/Tasks to work on.md` (owner's raw notes, 2026-06-21).
3. The nearest-term, lowest-risk, highest-leverage work is the **three Track-A increments** (§4) —
   they extend the already-automated P12.5 evidence pipeline and need no new subsystem. Good
   candidates for "do now while the SF1 ADR and P13 scoping settle."
4. Keep the **Evidence Engineering Platform** framing front-and-center in the whitepaper + Platform
   Capability Report — it is the defensible product thesis, per the owner's overall assessment.
