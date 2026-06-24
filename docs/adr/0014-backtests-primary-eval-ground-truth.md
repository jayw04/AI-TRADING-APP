# ADR 0014 — Backtests as the Primary Eval Ground Truth

| Field | Value |
|---|---|
| Date | 2026-06-02 (v1.1 amended 2026-06-24) |
| Status | Accepted · **v1.1 amended (owner ARD review)** — adds the INSUFFICIENT_EVIDENCE outcome and the "primary *research* ground truth, not final truth" clarification. |
| Phase | Decided in `TradingWorkbench_P6_Architectural_Decisions_v0_1.md` (Decision 8) |
| Supersedes | — |
| Superseded by | — |

## Context

To know whether the agent's proposals are any good, we need an evaluation
signal. Options: pure human judgment, live/paper PnL, or backtests against a
holdout window. P3 already ships a backtest harness.

## Decision

**Backtests are the primary ground truth.** A proposal is "successful" if
applying it and backtesting on a holdout window beats the strategy's existing
baseline (composite metric — Sharpe primary, drawdown floor — finalized in
Session 2). Supporting commitments: a **minimum of 5 backtested proposals per
strategy** before any "the agent's proposals are working" claim, and a **10%
weekly human-review sample** (thumbs up/down + reason) captured for eval.
Results live in `strategy_proposals.evaluation_results_json`.

### v1.1 amendment — evidence sufficiency (owner ARD review)

A "success" verdict requires *evidence*. Per the Evidence Engineering Principle 0
(*absence of evidence is not evidence of success*):

> A proposal evaluation is only considered valid if sufficient evidence exists to
> distinguish baseline and variant behavior. Evaluations producing no trades, no
> observations, or otherwise insufficient data are classified as **INSUFFICIENT_EVIDENCE**
> rather than PASS or FAIL.

So the eval verdict is **above_baseline / below_baseline / insufficient_evidence** (and
needs_review when only one side trades) — a zero-trade baseline *and* variant must never read
as above_baseline. Implemented in `proposal_evaluation.compute_verdict` (review E4).

### v1.1 amendment — primary *research* ground truth, not final truth

Backtests are the **primary _research_ ground truth**, not the platform's ultimate truth.
They sit at the start of the evidence lifecycle, which continues forward:

```
Research ─▶ Backtest ─▶ Paper Evidence ─▶ Production ─▶ Continuous Evidence
```

Continuous Evidence (live, ongoing) is the highest level of truth; the backtest is the
gate that lets a candidate *enter* paper. This aligns ADR 0014 with the Evidence
Engineering lifecycle (research program → candidate → paper → production → continuous
evidence).

## Rationale

- Backtests are objective (a metric, not a judgment), cheap to run at scale, and
  directly tied to the user's outcome; the harness already exists.
- "Above baseline," not an absolute threshold — baselines vary widely across
  strategies, so relative comparison is the only fair one.
- A minimum sample size guards against overfitting on a single backtest.
- Human review at 10% catches the qualitative dimensions backtests miss without
  overburdening the user.

## Status note — ahead of the code

This ADR is written **ahead of its implementing code**. §1a/§1b do **not**
exercise the eval harness: `evaluation_results_json` stays empty through §1b.
The integration (backtest invocation after proposal creation, the human-review
sampling cron, the eval-summary MCP tool) is **P6 Session 2**. The ADR is
recorded now because the commitment is settled and the schema column already
exists; the forward reference is deliberate.

## Reversal cost

Low. The composite metric and sample/review rates are tunable. If backtests
prove inadequate (e.g., forward-looking sensitivity), a paper-trading-pass
overlay can be added without restructuring.
