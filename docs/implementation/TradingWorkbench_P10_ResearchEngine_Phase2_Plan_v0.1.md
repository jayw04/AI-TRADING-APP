# Research Engine — Phase 2 plan (P10)

| Field | Value |
|---|---|
| Document version | v0.1 (plan for review) |
| Date | 2026-06-17 |
| Phase | P10 — Phase 2 (Research Engine as a product) |
| Predecessor | Phase 1 complete: momentum 12m (#143), risk overlays (#150), crash study (#151), evidence hardening (#154); capstone v1.1 (#149) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Promote the research *scripts* into a first-class, reproducible, versioned pipeline with an experiment registry and a generalized promotion gate — the reviewer's "biggest recommendation." |
| Estimated wall time | ~4 sessions, 5–7h each |
| Out of scope | New strategies; live trading; options/futures (Phase 5); broaden-universe re-test (Phase 4); alpha attribution + capacity (Phase 3) |

> **Short version:** we have ~80% of a research engine as separate scripts. Phase 2
> is the **20% integration**: a registry that makes every experiment reproducible,
> a thin orchestrator that chains the existing steps, and a generalized promotion
> gate — so every future factor/strategy goes through the same evidence-driven
> process that rejected RangeTrader and confirmed momentum.

## Why this phase exists

The reviewer's key observation: the *process* (reject weak ideas, confirm robust
ones, OOS-gate everything) is the real asset — but it currently lives in a
collection of hand-run scripts with results in ad-hoc `research/*.md` files. There
is no record of *which code + data + config* produced a result, and no single
pipeline to run a new idea end-to-end. That blocks scaling (every new factor is
bespoke) and reproducibility (a rerun months later may differ silently). Phase 2
makes research a product, not a folder of scripts.

## What already exists (the 80%)

| Pipeline stage | Existing component |
|---|---|
| Universe | `app/factor_data/universe.py` (PIT top-N dollar-volume, survivorship-free) |
| Feature/Factor engine | `factors/{engine,momentum,fundamental,cross_section}.py` (momentum, value, quality) |
| Backtester | `factor_data/backtest.py` (`run_momentum_backtest` + vol/drawdown overlays); single-name `Backtester` |
| IS/OOS validator | `scripts/factor_research.py` (IC, long-short, decay, rolling IC, IS/OOS split) |
| Robustness | `scripts/range_5c_gate.py` (`evaluate_gate`), overlay/window sweeps |
| Promotion gate | §5c pre-registration gate (range-trader-specific today) |
| Evidence package | `research/*.md` + findings docs; dataset/universe version block (#154) |

## The gap (the 20% — integration)

1. **No experiment registry / metadata** — results aren't stored with their config, so reruns aren't comparable and nothing is queryable.
2. **No orchestrator** — the stages are run by hand; no single "run this idea end-to-end."
3. **Promotion gate is bespoke** — §5c is range-trader-shaped; it should be the universal factor/strategy gate.
4. **Portfolio construction isn't a research knob** — weighting/cadence/buffering are hard-coded per strategy, not swept.

## Sessions

### §1 — Experiment registry (the reproducibility backbone) · ~4–6h
The highest-leverage 20%. A local table every study writes one row to.
```sql
-- in the factor-data DuckDB store (read-only-derived; ADR 0018)
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id   VARCHAR PRIMARY KEY,   -- ulid/hash
  created_at      TIMESTAMP,
  kind            VARCHAR,               -- 'factor_ic' | 'book_backtest' | 'overlay' | ...
  git_commit      VARCHAR,
  dataset_version VARCHAR,               -- SEP snapshot + fundamentals rows (see #154 _dataset_version)
  universe_id     VARCHAR,               -- rule + N + as-of
  params_json     JSON,                  -- the full config
  is_window       VARCHAR, oos_window VARCHAR,
  cost_model      VARCHAR, pit_mode VARCHAR, survivorship_mode VARCHAR,
  metrics_json    JSON,                  -- the result summary
  status          VARCHAR,               -- 'GO'|'NO-GO'|'INCONCLUSIVE'|'recorded'
  owner           VARCHAR
);
```
Deliverables: the table + a `record_experiment(...)` API + `factor_research`/the
backtest drivers writing a row. Tests: round-trip + idempotency.

### §2 — ResearchEngine orchestrator · ~5–7h
A thin pipeline that takes a factor/strategy config and runs Universe → Factor →
Backtest → IS/OOS → Robustness → Gate → Evidence + registry row, reusing the
existing components (no re-implementation). One entrypoint, one config object.
Deliverables: `app/factor_data/research_engine.py` + a CLI; an evidence-package
writer. Tests: a tiny end-to-end run on the fixture store.

### §3 — Generalized promotion gate · ~5–7h
Lift the §5c gate from range-trader-specific into a reusable
`promotion_gate(metrics, thresholds) -> GO/NO-GO/INCONCLUSIVE` that the
orchestrator calls for any factor/strategy, with per-kind threshold profiles.
Deliverables: generalized gate + threshold profiles + evidence JSON. Tests:
the existing §5c cases pass through the generalized gate unchanged.

### §4 — Portfolio-construction research · ~5–7h
Make weighting (equal / inverse-vol / risk-parity), name count, cadence,
reconstitution delay, position buffering, and rank hysteresis **sweepable** knobs
in the backtest, with an IS/OOS comparison — "these often improve performance more
than new alpha." Deliverables: a portfolio-construction sweep driver + findings.

> **Phase 3 (separate plan, after Phase 2):** factor-library expansion
> (Growth/Profitability/Capital-allocation/Risk/Liquidity → 20–40 factors), alpha
> attribution (which names/sectors drove returns), capacity analysis. **Phase 4:**
> broaden universe (top-200 → top-1000) + re-run Value/Quality/Growth/multi-factor
> (gated on the as-reported + delisted-coverage upgrades, per the FMP PIT doc).

## Scope boundaries (non-negotiable)

- **Read-only, off the order path** (ADR 0018) — the engine never touches
  `OrderRouter`/risk/brokers; it feeds strategy logic + evidence only.
- **No new external dependencies**; local-first DuckDB store; OS-trust-store TLS.
- **Reuse, don't rebuild** — the value is integration; resist re-implementing the
  backtester/factor engine.

## Open questions (resolve before §1)

1. Registry storage: extend `factor_data.duckdb` (simplest) vs a separate
   `research.duckdb` (cleaner separation). Lean: same store, new table.
2. Promotion-gate thresholds per experiment kind — reuse §5c's frozen criteria as
   the `book_backtest` profile; what are the `factor_ic` thresholds?
3. How much to generalize now vs keep momentum-shaped — bias to the minimum
   generalization that serves the next 2–3 real experiments, not a framework.

## Notes & gotchas

1. `Date.now()`/randomness are fine in scripts (unlike workflow scripts); stamp
   `created_at`/`git_commit` at run time.
2. The momentum book backtest is slow (~7 min/segment); the orchestrator should
   cache by `experiment_id` so reruns of an unchanged config are instant.
3. Keep evidence packages in `research/` (gitignored data stays out; committed
   `.md`/`.json` summaries stay in).
