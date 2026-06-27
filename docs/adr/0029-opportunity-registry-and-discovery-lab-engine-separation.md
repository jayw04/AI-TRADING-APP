# ADR 0029 — Discovery Lab: the Opportunity Registry and the Qualification / Ranking / Assignment separation

| Field | Value |
|---|---|
| Date | 2026-06-27 |
| Status | **Proposed** — *conceptually approved, acceptance gated on Monday's trial.* Origin: owner review of the Range implementation (`Docs/review/comments.md`, 9.8/10 — "separate qualification, ranking, and opportunity assignment more explicitly"; "the Opportunity Registry becomes the official output of Discovery Lab; Range Trader simply consumes it"). This ADR itself reviewed (`Docs/adr/ADR-Review.md`, 9.8/10, "approve as proposed"): **promote to Accepted only after the first auto-select run (Mon 2026-06-29, ~09:00 ET) assigns an Opportunity Set cleanly** — do not accept before the live paper workflow proves it. See §Acceptance gate. |
| Phase | Range-trading research (P8 §5a/§7 follow-on) → cross-program platform architecture |
| Supersedes | — |
| Refines | **0028** (Scheduled Pre-Open Opportunity Assignment) — 0028 stays Accepted; this ADR names the three responsibilities its job already performs and lifts them to a reusable, multi-program contract |
| Related | 0019 (Research Engine subsystem), 0026 (research programs as configuration — this extends "selection is configuration" to "selection is a *shared, persisted artifact*"), 0014 (backtests are the primary eval ground truth — the evidence the Ranking Engine weights), 0002 (single OrderRouter — none of these three engines touch the order path), 0005 (activation cooldown — the Assignment Engine carries 0028's narrow exemption) |

## Context

The shipped Range stack (ADR 0028, PRs #281/#288/#290/#291) introduced a "Candidate Engine"
that, each morning, turns a candidate universe into the day's Top-N symbols for one Range Trader.
In the owner review of the implementation
(`Docs/review/comments.md`, `Docs/review/RangeStrategy_Implementation_Review_v1.0.md`) the owner
observed that what we have been calling a single "Candidate Engine" is in fact doing **three
distinct jobs**, and that conflating them under one name will limit reuse:

1. **Qualification** — *"Is this stock eligible?"* — the two-step hard-filter screen (price, ADV,
   ATR%; RVOL/spread deferred) that produces the **Qualified Universe** (#291).
2. **Ranking** — *"Among eligible stocks, which are best?"* — the evidence-weighted Range Score
   (realized win rate → Sharpe → structural `atr20_pct × oscillation`) that orders the qualified
   names (#281).
3. **Opportunity assignment** — *"Freeze today's set and hand it to the strategy before the open"* —
   the pre-open job that picks Top-N, freezes it for the session, and re-points the strategy
   (#288, governed by ADR 0028).

These three responsibilities already exist in shipped code; today they are **fused inside the Range
program's own modules** (`app/services/range_insight.py` does qualification + ranking,
`app/services/range_auto_select.py` does assignment) and their output — the day's chosen symbols —
exists only as an ephemeral `symbols_json` write plus an audit payload. Nothing persists "today's
opportunity set" as a first-class object, and no other program can consume it.

That fusion is fine while Range is the only consumer. It stops being fine the moment a second
program wants the same service. The owner's long-term architecture is explicit that Momentum, Sector
Rotation, Trend, and Breakout should all consume **the same opportunity output** rather than each
re-implementing "filter → rank → pick today's names." Without a shared contract we will copy the
Range selection logic into every program (drift, divergent audit shapes, N× the calibration
surface). With one, Discovery Lab has a single, auditable output that every strategy reads.

We must decide whether to (a) name these three responsibilities as distinct platform capabilities,
and (b) introduce a persisted **Opportunity Registry** as the official, shared output of Discovery
Lab that strategies consume — rather than each strategy deriving its own selection inline.

## Decision

1. **Name the three responsibilities as distinct capabilities** (vocabulary + module boundaries; no
   behavior change today). What the Range stack already does is recognized as three engines:
   - **Qualification Engine** — applies **hard filters** (structural eligibility constraints) to the
     candidate universe and emits the **Qualified Universe**. Hard filters are *structural* and are
     expected to change **infrequently**; they answer eligibility, not quality.
   - **Ranking Engine** — scores and orders the Qualified Universe using **evidence-weighted**
     metrics (realized-backtest evidence blended with a structural score). Ranking models are
     *research artifacts* and are **expected to evolve** as evidence accrues. (Renames the prior
     "evidence-**first**" wording, which implied a binary precedence; the algorithm is a *weighting*
     of historical evidence and structural score — see §Rationale.)
   - **Opportunity Assignment Engine** — **freezes** the day's Top-N **Opportunity Set** pre-open and
     **assigns** it to one or more strategies before the market opens (the ADR 0028 job, with its
     pre-flight guards, frozen-for-the-session rule, PAPER-only scope, and cooldown exemption intact).

2. **Introduce the Opportunity Registry** as the **official, persisted output of Discovery Lab.** An
   *Opportunity Set* is a frozen, dated, audited record of "the names Discovery Lab selected for a
   given program on a given session, and why." The Registry is the durable store of these sets. The
   Assignment Engine **writes** to the Registry; strategies **read** from it. Selection becomes a
   first-class artifact, not an ephemeral `symbols_json` diff. **An Opportunity Set is immutable for the
   trading session** — once frozen pre-open it is never replaced intraday, even if a better candidate
   appears later (this restates ADR 0028 §3 here because, under this ADR, the frozen set becomes the
   *official Registry artifact* that the audit log, signals, orders, and calibration all reference; its
   immutability is what makes those references reproducible).

3. **Strategies consume the Registry; they do not re-derive selection.** The Range Trader (today) and
   Momentum / Sector Rotation / Trend / Breakout (later) consume an Opportunity Set produced by the
   shared engines, parameterized per program (each program supplies its own qualification thresholds,
   ranking model, and N). One pipeline, many consumers — no per-program copy of the filter→rank→pick
   logic.

4. **Canonical terminology.** The day's frozen selection is the **Opportunity Set** throughout the
   platform (UI, docs, audit, whitepaper). "Top-N", "Today's universe", and "Today's range universe"
   are deprecated synonyms; the implementing surface (`range_auto_select`, the Strategies banner)
   migrates to "Opportunity Set" as it is touched. The ranking algorithm is described as
   **evidence-weighted**.

5. **No order-path impact.** All three engines run in the research/orchestration layer
   (`app/services/`), import nothing from `OrderRouter` / risk / broker / `anthropic`, and assign only
   PAPER strategies (ADR 0028 §4–6). The Registry is a read-model for strategies and an audit
   artifact; it never submits orders.

6. **Mitigate ranking staleness with a composite weighting (direction, not a frozen number).** The
   Ranking Engine must not let a single historical backtest dominate selection indefinitely (today
   NVDA ranks #1 only because it is the lone backtested+qualified name). The target is a **composite**
   score —
   `rank = w·HistoricalEvidence + (1−w)·CurrentOpportunityScore` — where `w` **shifts toward live
   evidence early and back toward historical evidence as a name's own forward sample grows**.
   *Illustrative only, **not a frozen rule**: e.g. start ~0.4 historical / 0.6 current, move toward
   ~0.6 / 0.4 after ≈60 trading days — these numbers are placeholders to convey the direction.* The
   exact weights and shift schedule are a **research result to be derived from the calibration data**,
   not fixed by this ADR; what the ADR fixes is the *requirement* that ranking blend historical and
   current evidence and not anchor on stale backtests.

7. **Every Opportunity Set carries a stable identifier** of the form `OPP-<PROGRAM>-<YYYYMMDD>-<NNN>`
   (e.g. `OPP-RANGE-20260629-001`; `<NNN>` is a per-program, per-day sequence — normally `001`, since
   the pre-open RTH gate prevents same-session re-freezes). The **same ID** appears in the **audit
   event**, the **Opportunity Registry** row, and every downstream **signal**, **order**, and the
   **weekly calibration report** — so "the day's frozen input" is one unambiguous object that joins
   cleanly across every surface. Pre-Registry (before Phase 1) the ID is carried in the audit
   `selection` payload; the Registry row is keyed by it.

8. **Registry↔audit reconciliation is an invariant.** Because the Registry is *derived* from the
   immutable audit log (the audit log stays the source of truth), **every Opportunity Registry row must
   reconcile to exactly one immutable audit event** (matched by `opportunity_set_id`). The Registry is
   a single-writer read-model written only by the Assignment Engine at assignment time; a reconciliation
   check (Registry row ⇒ one and only one `STRATEGY_UPDATED` SYSTEM audit event with the same ID, and no
   orphan rows) guards the derivation and is the first thing to verify if the two ever diverge.

## Acceptance gate & recommended implementation order

Per the ADR review (`Docs/adr/ADR-Review.md`), this ADR is **conceptually approved now** but its
status changes to **Accepted only after Monday's run validates the workflow** — the live paper trial is
the final gate, not a code refactor. The order is deliberately *operational-evidence-first*:

1. **Monday 2026-06-29 trial** on the **current audit-based selection evidence** (no Registry code yet).
   Success = the Assignment Engine fires ~09:00 ET and assigns a frozen Opportunity Set cleanly
   (a `STRATEGY_UPDATED` SYSTEM audit event with the `selection` payload + an `opportunity_set_id`; the
   sleeve trades the assigned names).
2. **If successful → mark ADR 0029 `Accepted`** (record the date + the Opportunity Set ID of the first
   run in the Status line).
3. **Phase 1** — implement the Opportunity Registry read-model + the §8 reconciliation check (derive
   from the existing audit payload; no behavior change).
4. **Weekly calibration report** — Selection Precision, the Opportunity Conversion funnel, and
   score-band → trades/P&L, built on the Phase-1 read-model.
5. **Only then Phase 2** — split the code into Qualification / Ranking / Assignment modules.

Phase 3 (a second consumer) follows once a second program is ready. **Nothing in steps 3–5 happens
before Monday**; the first trial runs entirely on the already-shipped, audit-based path.

## Rationale

**Why name the three engines now, before generalizing the code.** The owner's point is that
"qualification" and "ranking" are *different questions* — eligibility vs. quality — and the platform
will need to evolve them on different cadences (filters rarely, ranking models often). Naming them
distinctly is free, makes the existing code legible, and is the precondition for letting a second
program reuse them. We name first and refactor the modules as the second consumer lands, rather than
speculatively splitting modules with one consumer.

**Why "evidence-weighted", not "evidence-first".** "Evidence-first" reads as a hard precedence
("backtested names always beat non-backtested names"), which is both an overstatement of what the
ranker should do long-term and the root of the NVDA-anchoring concern. The honest description is a
**weighting**: realized evidence and structural score both contribute. Renaming aligns the vocabulary
with decision §6's composite direction.

**Why a persisted Opportunity Registry, not just an audit payload.** The audit log already records
*that* a selection happened (ADR 0028 §7), and that is the right place for the immutable governance
trail. But the audit log is an append-only governance artifact, not a query surface a strategy or a
dashboard reads. A first-class Registry gives (a) a stable read-model strategies consume, (b) the
substrate for the calibration metrics this review asks for — **Selection Precision** (selected →
actually traded) and the **Opportunity Conversion funnel** (Qualified → Selected → Triggered → Filled
→ Exited) — which require *joining* the frozen selection to subsequent signals/orders/fills, and (c) a
single shape every program shares. The audit log remains the source of truth for *what was decided*;
the Registry is the *operational read-model* derived from it.

**Why strategies consume rather than re-derive.** Re-deriving selection inside each program is the
"drift between strategy code and selection logic" failure mode (cf. the CLAUDE.md "proven costly"
list, strategy-code↔schema drift). One shared producer means one place to fix a filter, one audit
shape, one calibration surface — and clean cross-program attribution ("did the *opportunity* convert,
independent of which strategy traded it?").

**Why keep ADR 0028 Accepted and merely refine it.** 0028's *decisions* — opt-in marker, stop→start
mechanism, frozen daily input, pre-flight guards, PAPER-only, the narrow cooldown exemption — are
unchanged and correct. This ADR does not relitigate them; it renames the capability they implement
(Assignment Engine) and adds the Registry as the artifact the job writes. 0028 is the *mechanism*;
0029 is the *vocabulary + shared contract* around it.

## Implementation notes

> This ADR is **Proposed**. The three responsibilities already exist in shipped code; the work below
> is the *naming + generalization*, sequenced so nothing breaks the Monday paper trial.

- **Phase 0 (docs only, now).** Adopt the vocabulary in the implementation review (v1.1), the
  whitepaper Ch2 drop-in (v0.2), and ADR 0028's forward-pointer. No code change; "evidence-weighted"
  and "Opportunity Set" become the words we use.
- **Phase 1 (Registry as a read-model — after Monday).** Add an `opportunity_set` persisted record
  (`opportunity_set_id` (decision §7) as the key, program id, session date, frozen symbols with
  rank/score/evidence, qualified-universe size, ranking_version), written by `range_auto_select` at
  assignment time alongside the existing audit entry. Derive it from the same `selection` payload that
  already exists (ADR 0028 §7) — no new selection logic, just persistence. Add the
  **reconciliation check** (decision §8): each row maps to exactly one audit event by `opportunity_set_id`;
  no orphans. This unblocks the calibration metrics (§ below). Phase 1 is **sufficient after Monday** —
  it is persistence + reconciliation only, no behavior change to the live sleeve.
- **Phase 2 (engine boundaries — NOT before Monday; after Phase 1 + the weekly calibration report).**
  Extract the qualification screen and the ranking scorer from `range_insight.py` into named,
  **program-parameterized** services (a program supplies its `HardFilters`, its ranking model, and N).
  `range_auto_select` becomes the Assignment Engine that composes them and writes the Registry. Range
  remains the only consumer until Phase 3. This phase touches working Range code, so it is deliberately
  the last structural step — only after the audit-based trial and the Phase-1 read-model have proven
  the workflow.
- **Phase 3 (second consumer).** Point a second program (candidate: Momentum or a Breakout sleeve) at
  the same engines/Registry to prove the contract is genuinely shared, not Range-shaped.
- **Composite ranking (decision §6)** lands with Phase 2/3 and the calibration data — the weights come
  from observed outcomes, not assumption (consistent with ADR 0028's "threshold is a research result"
  stance and ADR 0014).
- **Calibration metrics the Registry enables** (requested in the review; built on the Phase-1
  read-model):
  - **Selection Precision** = `selected names that produced an entry / names selected`. Lets us improve
    the Ranking Engine without touching the strategy.
  - **Opportunity Conversion funnel** = Qualified → Selected → Triggered → Filled → Exited counts per
    session — a dashboard of where opportunity is lost.
  - **Rolling weekly report** (not a one-shot at day 40): every Friday, roll up per-program selected
    symbols, trades, hit rate, avg P&L, and score distribution, so the 40–60-day empirical-threshold
    decision (ADR 0028 / §11.2 of the review) reads a report that already exists.
- **No new CI invariant, no order-path import.** The Registry is a research read-model; ADR 0002 /
  0006 are unaffected. The Assignment Engine retains 0028's guards and PAPER-only scope verbatim.

## Consequences

- **Positive**: one shared, auditable selection pipeline for every program (no per-strategy copy of
  filter→rank→pick); selection becomes a first-class, queryable artifact; the calibration metrics the
  review asks for become *cheap* (a join on the Registry, not bespoke per-program plumbing); clean
  cross-program opportunity attribution; staleness in ranking is explicitly addressed by the composite
  direction.
- **Negative**: a new persisted read-model to maintain and keep consistent with the audit log
  (the audit log stays the source of truth — the Registry is derived); the Phase-2 extraction touches
  working Range code (sequenced *after* Monday's trial to avoid destabilizing the live sleeve); "one
  more abstraction" that must earn its keep — if no second consumer ever materializes, Phase 1's
  read-model is still justified by the metrics, but Phases 2–3 are not.
- **Neutral**: introduces "Opportunity Set / Opportunity Registry / Qualification·Ranking·Assignment
  Engine" as platform vocabulary; deprecates "Top-N / Today's universe" as synonyms (migrated as
  surfaces are touched, not in a big-bang rename).

## Alternatives considered (not chosen)

- **Leave it as one "Candidate Engine" and document the two/three jobs only in prose.** Cheapest, and
  adequate while Range is the sole consumer — but it defers the exact drift the platform's "proven
  costly" list warns about, and leaves the calibration metrics without a substrate. Rejected as the
  *end state*; accepted as **Phase 0**.
- **Persist selection only in the audit log; strategies/dashboards query the audit log directly.**
  Rejected: the audit log is an append-only governance chain, not an operational read-model; querying
  it for "today's set" and joining it to fills is awkward and couples consumers to the immutable-trail
  shape. The Registry is the right read-model; the audit log stays the source of truth.
- **Generalize all the way to a Discovery Lab microservice now.** Rejected as premature: we have one
  consumer. Name now (Phase 0), persist the read-model (Phase 1), extract when the second consumer is
  real (Phases 2–3).

## Re-evaluation triggers

- **A second program is ready to consume opportunities** → execute Phases 2–3; if the Range-derived
  engine interface doesn't fit the second program, revise the contract here before generalizing.
- **The calibration data contradicts the composite-ranking direction** (e.g. live evidence proves
  *less* predictive than the structural score) → revisit decision §6's weighting scheme.
- **The Registry read-model drifts from the audit log** in practice → tighten the derivation (single
  writer, reconciliation check) or collapse back to audit-log-only if the read-model isn't earning its
  cost.
- **LIVE programs want to consume opportunities** → inherits ADR 0028's LIVE-rotation gap; needs the
  separate LIVE-rotation ADR first.
