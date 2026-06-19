# P11 Direction Document v0.1 — Operations & Reliability

| Field | Value |
|---|---|
| Document version | v0.2 (2026-06-19: + objective sentence & 4-goal scope filter, the Implemented→Enabled→Healthy→Verified state model, an architecture-freeze guardrail, and the Operational Readiness Report as the phase's final deliverable — from the v0.1 review. Detailed operational artifacts deferred to per-session docs to keep this a direction, not a grab-bag.) |
| Date | 2026-06-19 |
| Phase | **P11** — Operations & Reliability (follows P10 Portfolio-Level Risk Engineering) |
| Status | Direction-set. Foundation = ADR 0021 (Draft → accept first). Per-session docs may be drafted once the §1 scope is confirmed. |
| Predecessor | **P10** — code-complete (every §1–§8/§3C on `main`; all overlays default-off; §5 regime overlay backtest = NO-GO). Roadmap `..._P10_PortfolioRisk_Roadmap_v0.1.md` (v0.6.1). |
| Successor | TBD |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | **0021** (Operational Recovery Contract — *Draft*; this phase implements + formalizes it), 0004 (circuit breaker — the canonical fail-safe), 0002 (single OrderRouter — recovery never adds an order path), 0019 (Research Engine — read-only, alerts-not-trades posture this phase mirrors), 0020 (overlay — first recurring automated re-sizer), 0003/0017 (creds/TLS unchanged) |
| Inputs | The P10 roadmap-v0.6 review's closing verdict (*"architecture is no longer the limiting factor… demonstrate the platform behaves predictably and safely over time"*); ADR 0021's six contract properties; the §2/§6 Prometheus metrics already shipped; the §5 partial-fill / NO-GO findings |

---

## 0. Objective (the north star + the scope filter)

> **The objective of P11 is to make every automated action in Trading Workbench
> observable, reproducible, recoverable, and auditable — so operational reliability can
> be measured with the same rigor as investment performance.**

Those four words are the **scope filter**: every proposed P11 task must advance at least
one of them — **Observable · Reproducible · Recoverable · Auditable**. If it doesn't, it
belongs in another phase. (This guards against the real risk of P11 drifting into a grab
bag of unrelated operational tweaks.)

**Architecture freeze (guardrail):** P11 adds **no architectural expansion — only
operational hardening** of what P10 already built. New subsystems/strategies/data
dependencies are out of scope by construction (each would be its own ADR + phase).

## 1. Why P11 exists

P10 completed the **architecture**: a single OrderRouter, non-bypassable risk gates, an
immutable audit chain, a research engine, and a family of default-off portfolio-risk
overlays. The honest assessment at the end of P10 (owner review): *the architecture is
no longer the limiting factor.* The next gain in confidence comes not from more design
but from **demonstrating the platform behaves predictably and safely over time** under
real operational conditions — which is exactly what institutional-grade trading systems
strive for.

The trigger is concrete: the platform now runs **multiple automated actors** — the §6
continuous circuit-breaker monitor (60s), scheduled strategy rebalances, and (when
enabled) the §2/§4/§5 overlays — against a live paper book. ADR 0021 already named the
**contract** these actors must satisfy (idempotent, fail-safe, restart-recoverable,
reconciled, replayable, self-healing) but flagged most of it as *phased*. P11 is that
phase: turn the contract from asserted to **enforced + measured**, so reliability is as
observable as strategy performance.

This phase is about **operating the existing system**, not adding capability. It is
deliberately *not* about enabling the default-off overlays (that is a separate,
backtest-gated decision) or finding new alpha.

## 2. Scope

**In scope** (the ADR-0021 properties, made real + measured):
- **Observability** — a coherent operational KPI set on top of the §2/§6 metrics
  (scheduler success rate, fail-open frequency, duplicate-execution count, replay
  consistency), with targets, a dashboard, and alert thresholds.
- **Operational state** — a queryable record of *what is actually enabled/running today*,
  and a feature registry (version · ADR · flag · state). Four **distinct** states per
  feature (extends P10's Implemented/Proven/Enabled):
  **Implemented** (code on `main`) → **Enabled** (running on a book) → **Healthy**
  (running *correctly*) → **Verified** (cleared its promotion backtest). They are
  independent — e.g. the overlays are Implemented=yes / Enabled=no / Healthy=N/A /
  Verified=no (§5 = NO-GO). **"Healthy"** is defined concretely: *no stale jobs, no failed
  reconciliations, no replay failures, no duplicate executions, no unresolved alerts.*
- **Reconciliation** — a periodic broker-vs-local position/order reconcile that **alerts
  on discrepancy and never silently auto-corrects** (ADR 0021 property 4); first concrete
  consumer = the overlay partial-fill gap.
- **Replay** — reconstruct any automated decision from its audit fingerprint (overlay
  `overlay_event_id` + inputs; breaker trip payload), proving forensic replayability.
- **Recovery hardening** — restart-recovery and partial-fill self-heal, with tests and a
  runbook that is *followed* to validate it.
- **Runbooks + an event-timeline** (market close → data refresh → breadth/VIX → overlay →
  desired gross → orders → audit) so operational sequencing is explicit.

**Out of scope / non-goals:**
- **Enabling the default-off overlays** (§1 vol-target / §2 / §4 / §5) — each is its own
  backtest-gated owner decision; §5 is already a NO-GO. P11 makes operation *safe*, not
  *broader*.
- New alpha / factors / strategies; new external dependencies; multi-user / hosted
  (each would be its own ADR).
- A standalone Execution Engine — extract only if a second consumer needs shared order
  diffing/batching/retry (ADR 0020/0021 trigger), not pre-emptively.
- *(Forward pointer, not now):* a future **P12 — Institutional Platform** (multi-account /
  portfolio hierarchy / permissions / HA / scaling) is the natural successor, but it is an
  architectural expansion and therefore explicitly outside P11's freeze.

## 3. Foundation — ADR 0021 first

ADR 0021 (Operational Recovery Contract) is currently **Draft**. P11 **§1 is to review
and accept it** (a focused pass like ADR 0020/0022 got), since it is the contract every
session below implements. The contract's six properties become this phase's backbone;
each session maps to making one or more of them enforced + measured.

## 4. Proposed sessions (sequence — to be confirmed, then drafted as per-session docs)

1. **§1 — Accept ADR 0021 + operational-state/feature registry.** Formalize the contract;
   add a queryable "what's enabled today" surface + a feature registry (version/ADR/flag).
   Smallest, unblocks the rest.
2. **§2 — Observability + KPIs.** Consolidate the §2/§6 Prometheus metrics into an
   operational KPI set with targets (scheduler success >99.9%, fail-open <0.1%, duplicate
   executions = 0, replay consistency = 100%); a dashboard + alert thresholds; a runbook.
3. **§3 — Reconciliation job.** Periodic broker-vs-local position/order reconcile,
   alert-only; covers the overlay partial-fill gap. Risk-engine-adjacent → ≥95% coverage bar.
4. **§4 — Replay.** A tool/verifier that reconstructs an automated decision from its audit
   fingerprint; tie into the existing audit hash-chain verifier.
5. **§5 — Recovery hardening.** Restart-recovery + partial-fill self-heal tests and a
   *tested* runbook; close the ADR-0021 phased items.

(Ordering favors the cheapest, highest-leverage first; §3/§5 are the heavier, risk-adjacent
builds.)

**Detailed operational artifacts are deferred to the per-session docs** (kept out of this
direction to avoid the grab-bag). The relevant session will specify, as needed: operational
**SLOs** (scheduler ≥99.9% · replay 100% · duplicate-exec 0 · reconcile latency <5min ·
fail-open detection 100%) → §2; an **operational data model** (`automation_runs` /
`reconciliation_runs` / `replay_runs` / `alerts` / `system_health` / `scheduler_history` —
also open-question #1) → §1/§3; an **ops-architecture + dashboard** layout → §1/§2; a
**recurring-actor lifecycle** (Scheduled→Started→Completed→Verified→Archived) → §2; **replay
depth** (Inputs→Decision→Orders→Broker result→Final state) → §4; **incident severities**
(P1 duplicate order · P2 broker mismatch · P3 replay failure · P4 delayed scheduler) and a
**production-readiness checklist** (code·tests·metrics·replay·runbook·alert·dashboard) →
§5; and **reliability-testing classes** (chaos / restart / recovery / replay / failover) →
§5. Each must trace to one of the four objective goals (§0) or it doesn't belong in P11.

## 5. Governing principles (inherited, non-negotiable)

- **Read-only / off the order path** for monitors and reconciliation (ADR 0002/0019);
  recovery never adds an order path — induced orders still go through `OrderRouter`.
- **Alert, don't auto-correct.** A local/broker discrepancy surfaces to the owner; it
  never silently emits corrective orders (mirrors the Research Engine's monitor posture).
- **Fail-safe asymmetry** (ADR 0004): degrade toward *less* action; a false halt is cheap,
  a false action can be ruinous.
- **Conservative defaults**, and every consequential automated action audit-logged with a
  replayable fingerprint.

## 6. Success criteria — reliability, not returns

P11 succeeds when operational behavior is **measurable and demonstrably safe over time**,
not when returns improve:
- the operational KPIs are emitted and within target over a sustained paper window;
- a broker/local discrepancy reliably alerts (and is never silently auto-traded);
- any automated decision is replayable from its fingerprint;
- restart and partial-fill scenarios self-heal, validated by a followed runbook.

Returns/enabling decisions remain separate and backtest-gated (P10's posture).

**Final deliverable — the Operational Readiness Report.** P11 closes with a one-page report
attesting each capability is operationally proven, not just coded:

| Category | Status |
|---|---|
| Replay | PASS / FAIL |
| Recovery (restart + partial-fill) | PASS / FAIL |
| Reconciliation | PASS / FAIL |
| Alerts | PASS / FAIL |
| Scheduler reliability | PASS / FAIL |
| Audit integrity | PASS / FAIL |

All-PASS over a sustained paper window is the bar for declaring the platform
operationally trustworthy (a much stronger basis for any future live deployment than more
strategies or alpha).

## 7. Open questions (resolve before drafting §1)

1. **Operational-state store** — a new small table, or derive from existing config +
   `audit_log`? (Lean: derive/queryable view first; avoid new schema if the data exists.)
2. **Dashboard surface** — Prometheus/Grafana (metrics already in `app/observability/`),
   an in-app ops page, or both? Which is the owner's day-to-day?
3. **Reconciliation cadence + source of truth** — how often, and is Alpaca the truth for
   positions (it is for fills)? Norton/market-data constraints on the reconcile call.
4. **Replay depth** — reconstruct *inputs + decision* (cheap, from the fingerprint) vs.
   *re-execute the decision logic* (heavier; needs pinned code/version). v1 = the former.
5. **Phase identifier** — "P11" for ordering consistency vs. a themed name ("Operations &
   Reliability"); this doc uses both (number for sequence, theme for clarity).

---

*This is a direction doc, not an implementation spec. Once §1 scope is confirmed, draft
per-session docs (`TradingWorkbench_P11_Session1_*_v0.1.md`) in the usual format. ADR 0021
acceptance is the first gate.*
