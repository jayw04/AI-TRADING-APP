# ADR 0019 — Research Engine as a Top-Level Subsystem

| Field | Value |
|---|---|
| Date | 2026-06-17 |
| Status | Accepted |
| Phase | P10 Phase 2 |
| Supersedes | — |
| Related | 0018 (PIT factor data — the Research Engine reads it), 0014 (backtests as eval ground truth), 0002 (single OrderRouter — the engine never submits orders), 0004 (circuit breaker) |

## Context

P10 produced a working research *process* — survivorship-free PIT data, factor
study, backtester, the §5c GO/NO-GO gate, evidence packages — but it lived as a
loose collection of scripts under `app/factor_data/` and `scripts/`, with results
in ad-hoc `research/*.md` files. There was no record of *which code + data + config*
produced a result, no way to query or compare experiments, and no lifecycle for an
idea beyond a one-shot gate.

The reviewer's position (and the Phase-2 plan): the *process* is the durable asset,
not any single strategy — so it deserves first-class architectural status, not
"supporting code." The question: should research be a top-level subsystem on par
with the trading side, and on what terms?

## Decision

**Adopt the Research Engine as a top-level subsystem** (`app/research/`), peer to
the trading-side engines:

```
Data Engine → Research Engine → Portfolio Engine → Risk Engine → Trading Engine
```

1. The Research Engine **owns** the experiment / strategy / dataset / feature /
   artifact **registries** + a transition log (`registry/`), the **orchestrator**
   (`engine/`), the lifecycle-aware **promotion gate** + confidence score
   (`promotion/`), **continuous revalidation** + Research Alerts (`monitor/`),
   **comparison** tools (`comparison/`), and the **dashboard** (`dashboard/`).
2. It is **strictly read-only and off the order path** (ADR 0002): it creates and
   validates ideas; the trading engine executes what it validates. It never imports
   the OrderRouter / risk engine / brokers, and never submits, modifies, or halts an
   order. Revalidation **alerts**; it never auto-retires or auto-trades.
3. It persists to its **own** local DuckDB store (`data/research.duckdb`,
   `research_db_path`), separate from the factor-data store — gitignored,
   read-only-derived, never committed.
4. **Lifecycle is two orthogonal axes** — `research_state`
   (RESEARCH/VALIDATED/REJECTED/ARCHIVED) and `deployment_state`
   (NONE/PAPER/CANARY/LIVE/RETIRED); the gate drives research_state automatically,
   deployment_state is owner-driven, and every transition records a reason.
5. **The Research Engine is deterministic and reproducible.** Given identical data,
   code version, configuration, and random seed, it must reproduce identical experiment
   results — which is what the content-addressed experiment identity and provenance
   (git commit / host / seed) exist to guarantee.

*(Point 5 added 2026-06-19 as a clarification — making an already-implied property
explicit — before this ADR is treated as a frozen architectural baseline. No decision
change.)*

## Rationale

- **Strategies are disposable; the pipeline compounds.** RangeTrader was rejected,
  momentum confirmed, value/quality rejected — the *validation framework* is what
  produced those honest answers. Making it a first-class, versioned, queryable
  subsystem is the highest-leverage investment (it serves every future strategy).
- **Reproducibility needs a home.** Content-addressed experiments + dataset/feature
  versioning + provenance (git/seed/host) require a registry, which requires a
  subsystem to own it — not scattered script output.
- **Separation of concerns mirrors the trading side.** The trading engine already
  has clear boundaries (OrderRouter, risk, brokers). Giving research equal status
  keeps "create/validate" cleanly separate from "execute," which is easier to
  audit, test, and extend.
- **Read-only is the safety contract.** Keeping the whole subsystem off the order
  path means none of P5's hard-won invariants (single router, non-bypassable risk,
  no-LLM-in-order-path) are touched; research can iterate freely without risk to
  live execution.

## Implementation notes

- Package: `app/research/{registry,engine,promotion,monitor,comparison,dashboard}/`.
  (The code was authored here from the start, so no move was required — this ADR
  records the boundary, it does not relocate code.)
- Store: `app/research/registry/store.py` (`ResearchStore`), DuckDB at
  `research_db_path` (default `data/research.duckdb`); JSON-ish columns persisted as
  text. Reserved-word note: `at` is reserved in DuckDB → the transition column is
  `transitioned_at`.
- Entry points (CLIs): `scripts/research_run.py` (orchestrate an experiment),
  `scripts/research_compare.py`, `scripts/research_dashboard.py`.
- Runbook: `docs/runbook/promotion-workflow.md`.
- No new external dependency (DuckDB already in use for factor data); no CI
  invariant added — the read-only/off-order-path property is structural (the
  subsystem imports no order-path module).

## Consequences

- **Positive:** reproducible, queryable, lifecycle-aware research; one homepage
  (dashboard); a generalized promotion gate reusable by any strategy; edge-decay
  alerting closes the loop. Every future idea goes through the same evidence-driven
  pipeline.
- **Negative:** a second local store + a subsystem to maintain; some duplication of
  "version" concepts between the factor-data store and the research registry
  (dataset rows mirror the factor store's snapshot). More surface to keep tested.
- **Neutral:** the trading/risk/execution path is entirely unchanged — this is
  additive on the research side.

## Alternatives considered (not chosen)

- **Keep research as scripts under `factor_data`.** Rejected: no reproducibility
  record, no lifecycle, no queryability — the problems this ADR exists to solve.
- **One shared store with the factor data.** Rejected for v1: the Research Engine is
  its own subsystem with a distinct lifecycle; a separate store keeps the boundary
  clean and avoids coupling research churn to the data spine. Reconsider only if the
  two stores prove redundant in practice.
- **Let the gate auto-promote/retire.** Rejected: deployment changes move real
  (paper/live) capital and must stay owner-decisions; the gate validates, the
  monitor alerts, the owner acts (see promotion-workflow runbook).

## Re-evaluation triggers

- **The pipeline doesn't earn its keep:** if, after 5–10 real experiments, the
  registry/gate/dashboard aren't materially speeding research or improving decision
  quality, trim the subsystem rather than expand it.
- **Multi-user / hosted deployment:** the local-DuckDB, single-operator assumption
  (shared with ADR 0018) would need revisiting (shared store, access control).
- **Order-path coupling pressure:** if anything ever wants the Research Engine to
  act on orders directly, that is a new decision (new ADR), not a quiet expansion —
  the read-only contract is load-bearing.
