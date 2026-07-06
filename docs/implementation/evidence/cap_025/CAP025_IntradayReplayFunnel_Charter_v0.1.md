# CAP-025 — Intraday Replay & Entry-Funnel Diagnostics (Capability Charter v0.1)

| Field | Value |
|---|---|
| Date | 2026-07-06 |
| Capability | CAP-025 — Intraday Replay & Entry-Funnel Diagnostics |
| Type | Platform Capability (research infrastructure) — ADR-0030 Capability Onboarding |
| Maturity | L1 (built + used to reach a verdict; not yet a productized service) |
| Origin | RNG-001 entry-logic sub-study (`docs/implementation/evidence/range_entry_logic/`) |
| Related | ADR-0030 (Capability Onboarding), ADR-0033 (Historical Data Integrity), ADR-0014 (backtests = eval ground truth), `range_strategy_research_program` |

## Why this is a capability, not a one-off script

The RNG-001 entry-logic study needed to answer a question daily OHLC **cannot** answer: *given an
entry rule, was the target reachable in the correct sequence after a fill?* Answering it required a
**sequence-correct intraday replay** with an explicit fill model, an activation boundary, and a
funnel that classifies where each candidate-day leaks. That machinery is **strategy-agnostic** — any
intraday strategy (opening-range, VWAP, breakout, mean-reversion) has the same diagnostic needs — so
it is preserved as a reusable capability rather than left in a study's scratch scripts.

It also encodes two hard-won discipline lessons: (1) **daily OHLC lies** about intraday tradability
(price visiting both levels ≠ a takeable trade), and (2) **candidate-days are correlated within a
day**, so significance must be measured with a **date-clustered** bootstrap over a **train/test**
split — not pooled per-trade PF, which manufactured a false positive in the origin study.

## What it provides

1. **Intraday sequence replay** — walk 5-Min (or finer) bars in order from an activation boundary;
   never evaluate entries inside the level-forming window.
2. **Entry/target/stop funnel** — per candidate-day: buy-before/after-activation → fill →
   target/stop-after-entry → exit P&L, with a conservative stop-first-within-bar rule.
3. **Post-activation fill diagnostics** — fill rate vs candidate-days; touch-to-fill / reclaim-close
   fill models (documented as optimistic).
4. **Target-before-entry (path/sequence) detection** — distinguishes "missed the move" from "entered
   and lost", the distinction daily OHLC erases.
5. **Regime split** — up / down / chop by a market proxy (SPY open→close).
6. **Statistical honesty layer** — day-level portfolio collapse (idle capital = 0), **date-clustered
   bootstrap**, and **train/test time-split** — the tools that catch rally-artifact false positives.

## Reference implementation

`apps/backend/scripts/research/range/`:
- `backfill_intraday.py` — month-chunked intraday backfill (dodges the ADR-0033 10k-page truncation).
- `range_funnel.py` — the funnel diagnostic + bottleneck classification.
- `range_variant_study.py` — variant replay, selection filter, regime split, day-level bootstrap,
  train/test split.

These are the L1 reference forms. A future L2 promotion would generalize them behind a small API
(replay(bars, levels_fn, entry_rule, fill_model) → funnel + day-level stats) usable from the research
harness, and add the date-clustered bootstrap to the standard evidence-package emitter.

## Standard-of-use (what future intraday studies MUST do)

- Report **denominators explicitly** (candidate-days vs filled trades vs trading days).
- Judge significance with a **date-clustered bootstrap**, never pooled per-trade PF alone.
- Include a **train/test (or walk-forward) split** before any promotion claim.
- State the **fill model** and treat touch/close fills as optimistic.
- Verify **data completeness** (ADR-0033) before drawing conclusions.

## Re-evaluation triggers

- First reuse on a non-range intraday strategy (ORM-001 or other) → promote toward L2 with a shared API.
- If the reference scripts drift from the evidence-package emitter, reconcile or the capability rots.
