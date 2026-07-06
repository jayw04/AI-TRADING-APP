# Trading Workbench — Product & Architecture Overview

| Field | Value |
|---|---|
| Document version | v0.2 (living draft) |
| Date | 2026-06-19 |
| Owner | Jay Wang — GlobalComplyAI, LLC |
| Audience | (a) technical experts asked to critique and suggest improvements; (b) prospective investors / partners doing product review |
| Status of the product | Pre-revenue, single-operator, **local-first**. Paper-trading by default; live trading is built but gated and not run at scale. |

### How to read this document (honesty notes)

This overview is written to be *useful to a critic*, so it is deliberate about maturity. Throughout, capabilities are tagged:

- **✅ Built & operational** — shipped, tested, used.
- **🔶 Built but gated / paper-only / not yet live-validated** — the code exists and is exercised, but it is intentionally behind friction, or has not been validated with real capital.
- **🔭 Planned / in progress** — designed (often in detail) but not yet fully shipped.

Two caveats a reviewer should hold throughout: (1) the platform today is a **single-user, locally-run application**, not a hosted multi-tenant product; (2) it is **paper-first** — the live path is engineered and gated but is not a track record. Where those matter, they are called out. This is a *capability and architecture* document, not a performance claim.

---

## 1. Executive summary

### 1.1 Why this product exists

Individual traders today have access to institutional-quality data, cheap cloud compute, and capable generative AI — yet most retail trading platforms still optimize for execution speed, charting convenience, or one-click automation rather than *disciplined decision-making*. The mistakes that actually destroy individual accounts are rarely a missing feature; they are emotional overrides, untested ideas pushed live, look-ahead-biased backtests believed too readily, and AI handed more authority than it has earned. **Trading Workbench is built to close that gap** — to bring institutional governance, reproducible research, and tightly-bounded AI assistance into a local-first platform for a serious individual trader.

### 1.2 What it is

Trading Workbench is a **local-first, discipline-first systematic trading platform for an individual, experienced trader.** It runs entirely on the user's hardware; its only external dependencies are explicit and audited — Alpaca (brokerage execution + market data), Anthropic/Claude (AI assistance), and two read-only market-data vendors for research (Sharadar via Nasdaq Data Link, and FMP).

The product thesis is not "fastest" or "most features." It is **"most disciplined."** Every architectural choice — a single order entry point, non-bypassable risk gates, an immutable hash-chained audit log, multi-day activation cooldowns, and a hard rule that *AI does not touch the order path by default* — exists because the mistakes that destroy individual trading accounts happen under emotional pressure, and structured friction is the feature that prevents them.

Two coordinated subsystems have emerged:

- a **Research Platform** that discovers, validates, and *retires* trading strategies with point-in-time, survivorship-free data and an explicit GO/NO-GO gate; and
- an **Execution Platform** that deploys validated strategies under strong governance, full auditability, and tightly-gated use of AI.

Keeping those two cleanly separated — in both architecture and process — is the central design bet.

### 1.3 The platform in numbers

A few figures that make the architecture concrete and verifiable (all checkable against the repository, not marketing claims):

| Property | Value |
|---|---|
| Order entry points (manual, strategy, and agent orders alike) | **1** (`OrderRouter.submit()`) |
| Code paths that call a broker SDK directly | **0** (CI-enforced) |
| Orders that bypass the risk engine | **0** — every order, paper or live, is gated |
| Immutable, hash-chained audit chains | **1**, append-only, re-walked by a verifier |
| Architecture Decision Records | **19** (`Docs/adr/0001`–`0019`) |
| CI invariants enforcing the architecture | **13** shell/Python checks |
| Required branch coverage on the risk engine | **≥95%** |
| Activation cooldown, deterministic → live | **24 hours** |
| Activation cooldown, LLM-driven variant → live | **7 days** |

These are not aspirations; each is enforced by code, by CI, or by an explicit gate (see §2.3).

### 1.4 Institutional influence

Many of these choices are adapted from **enterprise financial systems and safety-critical software engineering** rather than from retail trading applications: Architecture Decision Records, immutable audit logging, promotion workflows and change control, circuit breakers, CI-enforced architectural invariants, and activation delays. That lineage is deliberate — it is unusual for single-operator retail software, and it is the source of the platform's credibility.

---

## 2. Core design principles

Six principles run through every section that follows; each later capability is best read as an *instance* of one of these.

1. **Local-first.** The platform runs on the user's hardware, on the user's keys, with the smallest possible external surface (see §6 for why).
2. **Research before execution.** Nothing goes live without surviving a point-in-time, survivorship-free backtest and an explicit GO/NO-GO gate — and the gate is allowed to say *no*.
3. **Safety before automation.** Risk gates, cooldowns, and the circuit breaker are non-bypassable; convenience never overrides them.
4. **Deterministic by default.** Strategies are deterministic Python. Non-determinism (i.e., AI) is the exception, fenced and opt-in.
5. **AI as advisor first.** AI informs the human; it does not reach the broker by default. The single sanctioned exception is wrapped in extraordinary friction.
6. **Every consequential decision is auditable.** Orders, state changes, risk-limit edits, breaker trips, and LLM calls are all appended to one immutable, verifiable chain.

---

## 3. Architecture

### 3.1 Topology

A small number of localhost-bound services (Docker Compose), each with a narrow responsibility:

| Service | Port | Role |
|---|---|---|
| Backend (FastAPI, Python 3.12) | 8000 | Orders, risk, strategies, audit, accounts, all business logic; SQLAlchemy 2.x async + Alembic over SQLite (WAL) |
| Frontend (React 19 + Vite + Tailwind) | 5173 | The trader's UI |
| Chart-data MCP | 8765 | Read-only tool server (Streamable HTTP) consumed by Anthropic's server-side connector |
| Workbench MCP | 8766 | Read-only tool server (SSE, per-user bearer auth) consumed by the agent and by Claude Code |
| Agent | 8767 | Stateless, single-shot proposal generator (reads via MCP, writes via the backend API) |

At a glance, the request and control flow:

```
                          +--------------------------+
                          |     React Frontend        |
                          |        (5173)             |
                          +-------------+-------------+
                                        |  REST + WebSocket
                          +-------------v-------------+
                          |   FastAPI Backend (8000)  |
                          |   all business logic       |
        +-----------------+------+---------+----------+------------------+
        |                 |      |         |          |                  |
  +-----v-----+   +-------v---+  |  +------v------+  +-v-----------+  +---v--------+
  | Risk      |   | Research  |  |  | Trading     |  | AI services |  | Audit &     |
  | Engine    |   | Engine    |  |  | Engine      |  | (advisory)  |  | Observ.     |
  | (gate)    |   | (PIT)     |  |  | strategies  |  | morning     |  | hash-chain  |
  +-----+-----+   +----+------+  |  +------+------+  | brief,agent |  +------+------+
        |              |         |         |         +------+------+         |
        |         +----v-----+   |  +------v------+         |          (append-only,
        |         | DuckDB   |   |  | OrderRouter |<--------+           verifiable)
        |         | PIT data |   |  |  .submit()  |  proposals only,
        |         +----------+   |  +------+------+  never orders
        |                        |         |
        +------------------------+---------+   every order, every origin
                                           |   passes Risk + audit, then:
                                  +--------v---------+
                                  | Broker Adapter   |  (only module allowed
                                  | (Alpaca today)   |   to import a broker SDK)
                                  +--------+---------+
                                           |
                                  +--------v---------+
                                  |   Alpaca API     |
                                  +------------------+
```

The picture encodes the two invariants that matter most: **everything funnels through one OrderRouter**, and **AI feeds the human/proposal side, never the broker side** (by default).

External dependencies (all explicit, each justified by an ADR): **Alpaca** (execution + live bars), **Anthropic** (LLM), and for research only **Sharadar/Nasdaq Data Link** + **FMP** (read-only factor data). Adding any new external dependency requires an ADR.

### 3.2 Subsystems

The codebase is organized as a set of engines with a sharp **read-only research side** and a **governed execution side**:

- **Data Engine** (`app/market_data/`, `app/factor_data/`) — live bars/quotes (Alpaca, cached) and the point-in-time factor store (DuckDB). Read-only; never calls the order path.
- **Research Engine** (`app/research/`) — registries (strategy / feature / dataset / experiment / portfolio / benchmark), a content-addressed experiment orchestrator, a promotion gate with a confidence score, continuous revalidation, experiment comparison, and a dashboard. Elevated to a first-class subsystem by **ADR 0019**.
- **Risk Engine** (`app/risk/`) — the non-bypassable pre-trade gate (position size, gross-exposure, daily-loss cap, order-rate, PDT/buying-power, market-session) plus the daily-loss **circuit breaker** (ADR 0004). Held to **≥95% branch coverage** by CI.
- **Trading Engine** (`app/strategies/`, `app/orders/`) — bar-by-bar strategy execution and the **single OrderRouter** (ADR 0002) through which *every* order flows.
- **Execution Governance** (`apps/agent/`, `app/services/eval_harness/`, `app/services/llm_live_gate/`, proposal/promotion services) — the agent, the paper-only LLM evaluation harness, the strategy-proposal lifecycle, and the heavily-gated LLM-in-order-path opt-in.
- **Audit & Observability** (`app/audit/`, `app/observability/`) — the typed `AuditLogger` writing to an append-only, hash-chained `audit_log`, plus metrics.
- **Broker Adapters** (`app/brokers/`) — the only modules permitted to import a broker trading SDK (Alpaca today; the interface is broker-agnostic).

The backend is **event-driven** where it counts: a scheduler fires cron/event strategy runs, market data and order/fill/position updates stream over WebSocket, background jobs drive research and evaluation, and every consequential action emits an audit event. Service boundaries are wired with **dependency injection**, which keeps each engine independently testable.

### 3.3 Architectural invariants (the spine)

These are enforced by code, by CI, or by convention; changing one requires an ADR.

1. **Single OrderRouter (ADR 0002).** Manual, strategy, and agent orders all flow through `OrderRouter.submit()`. No code path calls a broker adapter directly.
2. **Non-bypassable risk gates.** Every order — paper or live — passes the risk engine. Strategies cannot self-police; the centralized engine is the single source of truth.
3. **Hash-chained immutable audit log.** Every consequential action (orders, strategy state changes, risk-limit edits, credential rotations, breaker trips, LLM calls) is appended with `row_hash`/`prev_hash`; SQL triggers block UPDATE/DELETE; a verifier re-walks the chain.
4. **No LLM in the order path by default (ADR 0006 v2).** The order path must not import the Anthropic SDK except behind a tightly-gated, per-user, per-strategy opt-in (see §6.2).
5. **Real activation cooldowns (ADR 0005).** Idle→live is a 24-hour cooldown for deterministic strategies, 7 days for LLM-driven variants. Cancelling is frictionless; activating is the expensive direction.
6. **Local-first with explicit, encrypted external dependencies.** Credentials are Fernet-encrypted at rest (ADR 0003); outbound TLS verifies against the OS trust store so corporate/AV TLS-inspection doesn't force insecure fallbacks (ADR 0017).

**Thirteen CI invariants** make these load-bearing rather than aspirational: single-router, strategy isolation, risk coverage ≥95%, P2/P3 module coverage, MCP read-only, broker isolation, no-env-credentials, audit immutability, workbench-MCP read-only, no-LLM-in-order-path, eval-harness-paper-only, and llm-opt-in-bypass-gated. Each is a shell/Python check wired into CI; disabling one requires an ADR.

### 3.4 Performance & operational characteristics

Stated qualitatively — this is a single-operator, local-first system, and concrete latency/throughput numbers would be invented rather than measured at this stage.

- **Workload profile.** The platform is **decision-paced, not latency-arbitrage-paced.** Strategies are scheduled (e.g., daily/weekly rebalances and event triggers), and manual trading is human-speed. Order submission is bounded by broker round-trips, not by internal compute, so the design optimizes for *correctness and auditability per order*, not microsecond fill latency.
- **Footprint & scale.** Designed to run comfortably on a single developer-class machine. The execution store is SQLite (WAL); the research store is DuckDB. The realistic scaling axis is *number of concurrent strategies and research experiments*, not order rate — and that is bounded by the operator, not the architecture.
- **Restart & recovery.** State lives in durable local stores, not in process memory; services restart cleanly, and order/position state reconciles against the broker on reconnect. The immutable audit chain provides an after-the-fact, verifiable reconstruction of what happened.
- **Fault posture.** External-dependency failures (broker, LLM, data vendor) degrade toward *safety*: AI failures fall back to deterministic behavior, and the circuit breaker hard-halts on the daily-loss condition until a manual reset.
- **Testability by design.** The architecture was built for **unit + integration testing, deterministic strategy replay, and reproducible research** — the same property that makes CI invariants enforceable also makes behavior reproducible.

### 3.5 Decision record

Architecture decisions are captured as ADRs (`Docs/adr/0001`–`0019`), covering the stack, the single order entry point, the circuit breaker, activation cooldowns, the gated LLM-in-order-path and its auto-promotion flow, the stateless agent and its read-via-MCP/write-via-API split, the per-user agent cost cap, backtests-as-ground-truth, OS-trust-store TLS, point-in-time factor data, and the research engine as a top-level subsystem. The ADR set *is* the architecture's source of truth.

---

## 4. Functionalities

### 4.1 What has been built

**Execution & manual trading**
- ✅ Manual order entry (market/limit/stop/stop-limit, TIF, extended-hours, optional brackets) through the risk-gated OrderRouter; live order/fill/position updates over WebSocket.
- ✅ Risk engine: symbol allow/deny, position-size and notional caps, gross-exposure cap, order-rate cap, daily-loss **circuit breaker** (hard halt + manual reset), PDT and buying-power checks, and a market-session gate.
- 🔶 Live trading: fully built (paper/live account modes, reconciliation, extended live-confirmation UX). It is gated behind explicit acknowledgements and **has not been run at scale** — paper is the default.

**Systematic strategies**
- ✅ Deterministic Python strategy framework (`Strategy` base class, typed `params_schema`, the UI form derived from that schema), a backtest harness, and scheduled (cron/event) execution.
- ✅ Strategy lifecycle with enforced activation cooldowns and activation prerequisites (a backtest must exist, no pending risk-limit edit, cooldown elapsed, etc.).
- ✅ A worked example program in equities **factor research**: a momentum book (the out-of-sample edge), with value/quality factors tested and **honestly rejected** on the current universe — see §5.

**Research platform (P10)**
- ✅ The Research Engine: registries, a content-addressed orchestrator (provenance: git commit, host, seed), a profile-driven promotion gate emitting GO/NO-GO + a 0–100 confidence score, experiment comparison, a dashboard, and continuous revalidation.
- ✅ Portfolio-construction research (Phase 3A): weighting methods (equal-weight / inverse-vol / risk-parity), an evidence bundle, a scorecard against frozen GO/NO-GO thresholds, and per-regime reporting. The first study ran the full 2007–2026 history.
- ✅ Phase 3B analytics (just completed): a real **capacity model** (participation distribution + an AUM ceiling), **return / turnover / drawdown attribution** by name and sector, and a **SPY/market benchmark** (excess return, beta, CAPM alpha, information ratio) computed over the data overlap.

**AI assistance (advisory, by default off the order path)**
- ✅ Daily **morning brief** — a scheduled natural-language digest of the watchlist; advisory only; audit-logged with cost.
- ✅ **Agent** — stateless, single-shot; reads state via the read-only MCP and writes *proposals* (never orders) via the API; bounded by a per-user **daily cost cap** (hard pre-call check).
- 🔶 **Strategy-proposal lifecycle** — the agent proposes parameter changes; the platform clones the strategy to a paper variant, runs it in parallel, accumulates evidence against a promotion gate, and presents it for **human** promotion. Built; exercised on paper.
- 🔶 **LLM evaluation harness** — runs a deterministic vs. LLM-gated variant in parallel **on paper only**, producing comparison metrics. Built and CI-fenced to never touch a live account.
- 🔶 **NL → Python strategy authoring** — describe a strategy in English, get generated code that must pass the *same* backtest + cooldown + risk gates as hand-written code. Built out across sessions; treated as in-progress / late-stage rather than a finished headline feature.

**Platform hardening**
- ✅ Immutable hash-chained audit log with a verifier; Fernet-encrypted credentials; OS-trust-store TLS; Prometheus metrics; a tested on-call runbook.

### 4.2 What is planned next

- 🔭 **§3C portfolio risk**: enforce sector caps in construction (today they are recorded, not enforced); a daily gross-exposure **overlay** engine kept architecturally separate from weekly stock selection; exposure smoothing.
- 🔭 **Multi-factor book**: deferred — *not* because the data is missing (it isn't) but because value/quality showed no out-of-sample edge on the current mega-cap universe; a re-test on a broader universe is the gate.
- 🔭 **Regime/market-context data** (e.g., volatility-percentile and breadth series) to inform the exposure overlay — requires a new vendor and therefore a new ADR.
- 🔭 **Deeper AI governance** (for the opt-in path): explicit per-decision metadata (latency, tokens, prompt version), a decision-replay capability ("would today's model decide the same?"), and a decision registry — all designed to stay *single-provider* and ADR-bounded (see §6.4).
- 🔭 **Beyond single-operator / local-first** (hosted, multi-user) is explicitly *not* in scope today; it would trigger a re-evaluation of several invariants.

### 4.3 Problems we intentionally do NOT solve

Knowing the boundaries is as important as knowing the features. Trading Workbench is **not** designed for:

- **High-frequency / low-latency trading** — it is decision-paced, not microsecond-paced.
- **Options market-making or complex derivatives** — equities-first by design.
- **Crypto / cross-venue arbitrage.**
- **Multi-user SaaS / hosted multi-tenancy** — single-operator, local-first today; changing this re-opens several invariants.
- **Black-box / fully-autonomous AI trading** — AI is an advisor by default; full autonomy is explicitly out of scope.

These are deliberate scope decisions, not gaps. Each keeps the discipline contract tractable for a single serious operator.

---

## 5. The Research Engine — the compounding asset

Strategies are disposable; the *validation pipeline* is the durable asset. The Research Engine (ADR 0019) makes that pipeline versioned, queryable, and reproducible, so every future idea inherits the same honest gate. The lifecycle it enforces:

```
   Idea
     │
     ▼
   Backtest            point-in-time, survivorship-free (ADR 0018)
     │
     ▼
   Validation          content-addressed run; provenance: git commit, host, seed
     │
     ▼
   Promotion Gate      GO / NO-GO + 0–100 confidence score (and it is allowed to say NO)
     │
     ▼
   Paper Trading       parallel paper variant accumulates evidence
     │
     ▼
   Continuous          ongoing revalidation; drift detection
   Validation
     │
     ▼
   Production          live, under the same risk gates + audit chain
     │
     ▼
   Retirement          strategies are retired explicitly, not left to rot
```

Few retail platforms have the *retirement* and *honest-no* steps at all. A concrete proof point: value and quality factors were implemented, tested, and **rejected** for lack of out-of-sample edge on the current universe — the pipeline recorded the no and deferred the multi-factor book rather than shipping a flattering blend (see §6.1).

---

## 6. Data & Generative AI — our approach, edge, and uniqueness

### 6.1 Data: honest by construction

The research side runs on **point-in-time, survivorship-free** data (ADR 0018). Prices and the tradeable universe come from **Sharadar** (decades of history including delisted names); fundamentals come from **FMP** on its current API (≈40 years of quarterly+annual statements with SEC acceptance timestamps). Everything is ingested into a **local DuckDB store** and joined **as-of** — a factor on date *D* can only read data that was knowable on *D*. This is the difference between a backtest that flatters itself and one a reviewer can trust.

A concrete proof point of the discipline: value and quality factors were *implemented and tested*, and the honest finding was **no robust out-of-sample edge on the current mega-cap universe** — only momentum survived. The platform recorded that result and **deferred** the multi-factor book rather than shipping a flattering-but-fragile blend. The competitive asset here is not any single factor; it is a pipeline that produces **honest no's.**

### 6.2 Generative AI: advisor by default, executor only under extraordinary friction

The defining choice is architectural: **the LLM does not touch the order path by default** (ADR 0006 v2), enforced by CI. AI is used where judgment helps and mistakes are recoverable:

- **Morning brief** — natural-language synthesis of the watchlist (cost-sensitive Claude tier); advisory.
- **Agent proposals** — read-only context in, *proposals* out (never orders), bounded by a hard per-user daily cost cap; the human executes.
- **Strategy review / proposed parameter changes** — evaluated on **paper** first, promoted only by a human against an evidence gate.
- **NL → Python authoring** — generates code that must clear the same gates as hand-written strategies.

The **one** sanctioned path for AI-in-the-order-path is a per-user, per-strategy **opt-in** with stacked friction: a paper-only evaluation harness must first produce a defined sample of comparison metrics; then the user types an acknowledgement of the non-determinism / social-engineering / reproducibility risks; a **7-day** cooldown applies; the opt-in is **version-pinned** (any parameter change re-opens evaluation); a **hard daily spend cap** applies; and **every** LLM decision is logged with the full prompt, the response, and the parallel deterministic baseline.

### 6.3 Why that is the edge (and the uniqueness)

- **AI safety as a product property, not a disclaimer.** Three of the thirteen CI invariants exist specifically to keep AI in its lane: no-LLM-in-order-path, eval-harness-paper-only, and opt-in-bypass-gated. A reviewer can *verify* the boundary in code, not just read a promise.
- **Forensic reproducibility of non-deterministic decisions.** Because the full prompt/response and the deterministic baseline are audit-logged, an LLM-influenced action can be reconstructed after the fact even though it isn't bit-reproducible — a property most "AI trading" tools simply don't offer.
- **Research as a compounding asset.** Strategies are disposable; the *validation pipeline* compounds. The Research Engine (ADR 0019) makes that pipeline versioned, queryable, and reproducible, so every future idea inherits the same honest gate.
- **Latest-model-ready, single-provider by design.** The platform targets current Claude models and is deliberately **single-provider**: the recommendation from internal review was explicit — do *not* add multiple LLM vendors or consensus voting yet; one provider → one gate → one policy is the right complexity for now. (A provider *interface* with a single implementation is acceptable; multi-vendor is an ADR conversation, not a default.)

### 6.4 Where AI governance is heading (designed, not yet built)

For the opt-in path specifically: explicit per-decision metadata (latency, token counts, prompt version), a **decision-replay** capability to ask "would the current model make the same call?", and a **decision registry** mirroring the research registries. These are scoped as low-priority, ADR-safe additions — useful when the opt-in path is actually exercised, deliberately *not* built ahead of need.

### 6.5 Why local-first

A recurring reviewer question is "why not cloud?" The local-first choice is deliberate and buys several properties at once:

- **Data privacy & full user control** — the trader's keys, positions, and strategy IP never leave their machine.
- **Reduced attack surface** — no public ingress, no multi-tenant boundary to defend; the MCP servers are localhost-bound and read-only.
- **Lower operating + AI cost** — no hosting bill, and LLM usage is scoped to one operator under a hard cap.
- **No multi-tenant complexity** — single-operator state is simpler to reason about, audit, and reproduce.
- **Better reproducibility** — a local, content-addressed research store makes "re-run exactly what happened" tractable.

The trade-off (no remote access, single machine) is accepted intentionally; lifting it is an explicit future decision, not an oversight.

---

## 7. How this differs from other tools

A few representative comparables, and where Trading Workbench deliberately diverges. (Competitor capabilities evolve; these contrasts describe *this product's design choices*, not a claim that others can't do X.)

- **Retail algo/backtest platforms (e.g., QuantConnect, Backtrader, NautilusTrader).** These are excellent strategy *engines*. Trading Workbench is less a backtesting library and more a *governed operating environment*: a single audited order path, non-bypassable risk gates, an immutable audit chain, and activation cooldowns wrap the strategy engine. The differentiator is **the discipline layer around execution**, not the backtester itself.
- **No-code/portfolio automation (e.g., Composer).** Those optimize for *accessibility* — assemble a strategy from blocks and let it run, hosted. This product optimizes for *control and provenance* for an experienced operator: deterministic Python strategies, point-in-time honest backtests, and a research lifecycle that *rejects* ideas, all running locally on the user's own keys.
- **Signal/scanner products (e.g., Trade Ideas, TrendSpider, TradingView alerts).** Those surface ideas. Trading Workbench surfaces ideas *and* runs the full loop — risk-gated execution, audit, and a validation gate that decides what is allowed to go live.
- **Discretionary broker front-ends (e.g., thinkorswim, IBKR TWS).** Mature manual trading, little systematic-research governance and no first-class AI-assistance discipline. Trading Workbench adds the systematic + research + governed-AI layers while keeping manual trading through the same gates.
- **Quant-research / crowdsourced alpha (e.g., Numerai, Alphalens-style tooling).** Strong on research rigor, detached from a personal execution path. Trading Workbench couples a survivorship-free PIT research engine *directly* to a governed personal execution platform.

**The synthesized difference:** most tools are strong on *one* of {execution, research, AI assistance}. This product's bet is the **integration under a discipline contract** — research that can say "no," execution that can't be bypassed, AI that can't reach the broker by default, and an audit chain that can reconstruct every consequential decision.

---

## 8. What makes this hard

For a reviewer weighing where the real engineering investment goes: the difficult problems here are *not* "build another backtester." They are the problems that retail tools usually skip because they are unglamorous and unbounded:

- **Preventing look-ahead bias** — as-of joins, point-in-time fundamentals, survivorship-free universes, and corporate-action/restatement timing edge cases.
- **Ensuring audit integrity** — an append-only hash chain that genuinely cannot be edited, verified end-to-end, extending naturally to non-deterministic AI calls.
- **Governing AI safely** — letting AI help without letting it reach the broker, and making the one sanctioned exception both usable and impossible to trip into by accident.
- **Making research reproducible** — content-addressed runs with full provenance, so "re-run exactly what happened" is real.
- **Preventing operational mistakes** — cooldowns, circuit breakers, and non-bypassable gates that hold up precisely when the operator is under pressure.

Those are the engineering investments, and they are where the architecture spends its complexity budget.

---

## 9. What we'd most value expert input on

1. **Portfolio risk overlay architecture** — keeping a daily gross-exposure overlay cleanly separated from weekly stock selection without coupling the two engines.
2. **Capacity & attribution methodology** — the §3B capacity ceiling (AUM at which the marginal trade hits a participation limit) and the first-order return attribution residual: are these the right defaults for a single-operator book?
3. **The multi-factor re-test design** — what universe/regime would make a value/quality re-test decisive rather than another regime-specific "no"?
4. **The AI opt-in friction** — is the 7-day cooldown + version-pin + per-user cap + full audit the right envelope, or over/under-engineered?
5. **Survivorship/PIT edge cases** — places where the as-of discipline could still leak look-ahead (corporate actions, restatement timing).

---

## 10. Key takeaways

Trading Workbench is:

- ✓ **Research-first** — nothing goes live without surviving an honest, point-in-time gate.
- ✓ **Local-first** — the user's hardware, the user's keys, the smallest external surface.
- ✓ **Audit-first** — one immutable, verifiable chain over every consequential action.
- ✓ **Governance-first** — invariants enforced by code and CI, not by good intentions.
- ✓ **AI-assisted** — AI where judgment helps and mistakes are recoverable.
- ✓ **Human-controlled** — AI advises; the human (or an extraordinarily-gated opt-in) executes.
- ✓ **Evidence-driven** — strategies earn their way live and are retired when the evidence turns.

The architecture is already strong; the work ahead is to *exercise* the gated paths (live, AI opt-in) and to broaden the research book — not to relax the discipline that makes the platform trustworthy.

---

## Appendix A — Source-of-truth pointers (for the technical reviewer)

- Conventions & invariants: `CLAUDE.md`
- Decision records: `Docs/adr/0001`–`0019`
- CI invariants: `.github/workflows/ci.yml` + `apps/backend/scripts/check_*.{sh,py}`
- Order path: `app/orders/router.py`; risk: `app/risk/engine.py`, `app/risk/circuit_breaker.py`
- Audit: `app/audit/logger.py`, `app/observability/audit_hash.py`, `scripts/verify_audit_integrity.py`
- Research engine: `app/research/` (registry / engine / promotion / comparison / monitor / dashboard)
- Factor data: `app/factor_data/` (store, providers, factors); guide: `Docs/implementation/TradingWorkbench_FactorData_Acquisition_Guide_v0.1.md` (v1.0)
- AI services: `app/services/morning_brief.py`, `app/services/eval_harness/`, `app/services/llm_live_gate/`, `apps/agent/`

*This is a living document; sections will be revised as §3C ships and as the AI opt-in path is exercised. Figures and statuses reflect 2026-06-19.*
