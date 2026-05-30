# ADR 0006 — LLM in Order Path (Gated Behind Performance-Based Evaluation)

| Field | Value |
|---|---|
| Date | 2026-05-29 |
| Status | Accepted (supersedes 2026-05-28 draft) |
| Phase | Cross-phase architectural decision; governs P6 and P7 scope |
| Supersedes | ADR 0006 v1 (LLM not in order path — indefinite pause) |
| Related | ADR 0002 (single OrderRouter), ADR 0004 (circuit breaker), ADR 0005 (24-hour activation cooldown), ADR 0007 (auto-promotion of LLM-proposed updates) |

## Context

The original ADR 0006 (drafted 2026-05-28) paused "Architecture 3" — LLM in the per-order decision — indefinitely. The reasoning was sound for the moment of the decision: LLM non-determinism breaks audit reproducibility, LLM prompts are susceptible to social engineering, LLM latency is incompatible with bar-by-bar dispatch, LLM cost scales with market activity rather than user activity, and LLM-driven strategies cannot be meaningfully backtested.

Those concerns have not disappeared. But "paused indefinitely" leaves a question the team kept returning to: is this a decision about LLM-in-the-order-path *forever*, or about LLM-in-the-order-path *given what we know today*? The honest answer is the second, and the original framing didn't capture it. A trader evaluating the platform reads "paused indefinitely" as a permanent product limitation, when in fact the team's position is more nuanced: we don't trust this capability yet, we know how we'd evaluate it, and if it passed the evaluation we'd ship it behind a user opt-in.

This revision captures that more honest position. The capability remains off by default and unavailable in the current product. The pause is now coupled to a defined evaluation framework: when the LLM-driven decision path demonstrates measurable safety and effectiveness across an extended paper-trading evaluation, and the user explicitly opts in with full understanding of the trade-offs, the capability becomes available.

## Decision

Three things are true after this ADR:

**1.** The order routing path — `OrderRouter.submit()`, the risk engine, broker adapters, and any code path that produces a live order from a strategy — must not call the Anthropic API in the default product configuration. The CI invariant `check_no_llm_in_order_path.sh` enforces this for all default code paths.

**2.** An *evaluation harness* may exist alongside the default order path. The evaluation harness runs LLM-driven decision logic in paper trading, in parallel with deterministic strategies, on the same market data. It produces a defined set of comparison metrics over a defined sample size. The harness is permitted to call the Anthropic API because its output never reaches a live broker; the CI invariant has an explicit allowlist entry for the harness module.

**3.** A user who has reviewed the evaluation results may opt in to LLM-driven live trading for one or more of their strategies. Opt-in routes through an extended activation cooldown (7 days, not the 24 hours of standard activation) and requires a typed acknowledgment of the non-determinism, social-engineering, and reproducibility risks documented in this ADR. Once opted in, the user's chosen strategies bypass the default `check_no_llm_in_order_path` enforcement for that specific user and that specific strategy version. Every LLM-driven decision is audit-logged with the full prompt-response exchange.

## The evaluation framework

This section defines what "proven safe and effective" means concretely, so a future product decision to enable LLM-driven trading is grounded in evidence rather than confidence.

### The three-mode parallel run

For any strategy a user wants to evaluate for LLM-driven trading, the platform automatically maintains three parallel instances:

| Mode | Decision logic | Account |
|---|---|---|
| **A — Control** | Deterministic strategy code (the original Python file) | Paper |
| **B — LLM-managed** | Claude evaluates each signal from the deterministic code and decides whether to act | Paper |
| **C — Live** | Whichever mode the user has promoted (initially always Mode A) | Live |

Modes A and B receive identical signals from the same bar dispatch. They are compared structurally — same input, different decision logic on whether to fire. The comparison is fair because nothing varies except the decision layer.

### The metrics

The following are computed continuously and surfaced on a comparison dashboard:

| Metric | What it measures | Why it matters |
|---|---|---|
| **Win rate delta** | LLM win % minus deterministic win % | Is the LLM picking better trades on average? |
| **Sharpe ratio delta** | LLM Sharpe minus deterministic Sharpe | Is the LLM's risk-adjusted return better? |
| **Max drawdown delta** | LLM max drawdown minus deterministic max drawdown | Does the LLM avoid the worst losing streaks? |
| **Decision agreement rate** | Percentage of signals where both modes made the same call | How often does the LLM agree with the deterministic baseline? |
| **Disagreement asymmetry** | When they disagree, who is right more often? | Are the LLM's contrarian calls informed, or is it just noise? |
| **Worst single-decision divergence** | Largest single bad call the LLM made that the deterministic code would have avoided | Captures tail risk — one disastrous call matters more than average performance |

The dashboard updates in real time during the evaluation period; the user can watch the comparison build without committing to anything.

### The bar for opt-in

The platform does not auto-enable LLM-driven trading based on metric thresholds. The metrics inform the user; the user decides. However, the platform refuses to expose the opt-in flow at all unless minimum-sample criteria are met:

- At least **50 trades executed** in Mode B (LLM-managed), and
- At least **30 calendar days elapsed** since Mode B began, and
- The strategy has not been deactivated or substantively modified during the evaluation period (a parameter tweak resets the clock).

The "at least 50 trades and 30 days" double-floor exists because either alone is misleading. A high-frequency strategy may hit 50 trades in two days, which is statistically meaningful but doesn't capture market-regime variation. A low-frequency strategy may run 30 days with only a dozen trades, which is calendar-long but statistically thin. Both floors must be met before the opt-in dialog will even render.

When both floors are met, the user can review the metrics and choose whether to opt in. The platform offers no recommendation either way. It presents data; the user decides.

### What opt-in actually does

Opting in:

1. Requires a typed acknowledgment of the risks (specific text, similar in spirit to the typed-symbol confirmation for live orders).
2. Triggers a **7-day activation cooldown** for the LLM-driven variant before it can submit live orders. This is longer than the standard 24-hour cooldown of ADR 0005 because the trader is endorsing a strategy whose behavior they understand less directly.
3. Permits LLM-driven order generation for that one strategy on that one account, while leaving the default no-LLM-in-order-path discipline in place for all other strategies and all other users.
4. Audit-logs every LLM-driven decision with the full prompt sent, the full response received, the deterministic baseline's parallel decision for that same signal, and the resulting order outcome. The audit log can reconstruct exactly why each LLM-driven trade happened.

The user can opt out at any moment with no friction — the LLM-driven variant returns to paper-only and the deterministic variant resumes live duty. Opting out is the cheap direction. Opting back in requires a fresh evaluation window.

## What this revision changes from the original ADR 0006

| Property | Original (2026-05-28) | This revision |
|---|---|---|
| Default availability | Architecture 3 unavailable | Architecture 3 unavailable |
| Path to availability | None — "paused indefinitely" | Defined evaluation framework + user opt-in |
| Audit reproducibility property | Preserved by structural exclusion | Preserved by full prompt-response logging when LLM is in the path |
| User mental model | "AI will never trade for me on this platform" | "AI does not trade for me by default. If I want it to, here is the evaluation I can run and the opt-in I can make." |
| CI invariant | `check_no_llm_in_order_path.sh` enforces strict exclusion | Same script, with an explicit allowlist entry for the evaluation harness module and a per-user opt-in bypass that requires a database flag, not a code change |

## What this revision does NOT change

The original ADR 0006's five rationales remain accurate descriptions of why we don't trust LLM-in-the-order-path *by default*. They are reproduced here as documentation of why the default is what it is:

- **Non-determinism breaks audit reproducibility**: still true. Mitigated for opt-in users by full prompt-response logging, which provides forensic reconstruction even if the original decision is not deterministically reproducible.
- **Social engineering surface**: still true. Mitigated by the LLM having no read access to user-supplied free text in the order path. The LLM evaluates structured market data and pre-defined strategy logic; it does not read tweets, news headlines, or unsanitized inputs.
- **Latency**: still true. Mitigated by the LLM being invoked only at signal generation, not at bar dispatch. A signal that requires LLM evaluation accepts the LLM's latency budget; a signal that doesn't simply doesn't invoke the LLM.
- **Cost scales with market activity**: still true. Mitigated by the per-strategy and per-day budget caps inherited from P3 §4, plus a strict per-user budget cap (default $10/day for opted-in LLM-driven trading; user-configurable upward with an additional confirmation gate).
- **Backtest validity**: still true and not fully solvable. The paper-trade evaluation framework is the substitute for traditional backtesting. It is forward-looking, not historical, which is more honest about what we can know — the question is no longer "would this have worked on past data" but "is this working on current data."

These mitigations don't eliminate the underlying concerns. They make the concerns tractable enough that an informed user can decide for themselves whether the trade-off is worthwhile. That is the right shape of trust to ask the user for: not blind, but informed.

## Implementation notes

- The CI invariant script is updated to accept an allowlist entry for the evaluation harness directory and to recognize the `LLM_OPT_IN_ALLOWED` database flag as a permissible bypass for specific user-strategy pairs. The bypass cannot be granted by code change; it requires a database write that itself is audit-logged.
- The evaluation harness is a separate module from the default order router. It calls the same risk gates (the harness's orders, even in paper mode, route through `OrderRouter.submit` with appropriate paper-broker credentials).
- The 7-day cooldown for LLM-driven activation is enforced by the same scheduler that handles the 24-hour cooldown of ADR 0005, with a different timer constant.
- Opt-out is a one-click action with no cooldown. The audit log records the opt-out.

## Re-evaluation triggers

This ADR should be revisited if any of these happen:

- The evaluation framework, after a full year of platform operation, produces no users who have opted in. That would indicate the bar is too high, the value proposition is unclear, or the underlying concern about LLMs in trading is widely shared. We adjust based on the reason.
- Multiple users opt in and the LLM-driven strategies systematically underperform their deterministic counterparts across the metrics. That would indicate Architecture 3 is not the value-add the marketing materials claim it is, and we should reduce the prominence of the opt-in or remove it entirely.
- An LLM-driven strategy produces a catastrophic single-decision divergence (the "worst single decision" metric exceeds an acceptable bound). We pause new opt-ins, investigate, and consider tightening the evaluation criteria or revoking the opt-in entirely.
- The CI invariant is bypassed by code (a developer adds an Anthropic call to the order path without using the opt-in mechanism). This is treated as a process failure that triggers an audit of how it happened.

This is no longer "paused indefinitely." It is "available behind a defined evaluation framework and user opt-in, with documented conditions under which the policy changes."

*ADR 0006 v2. The architectural decision that defines what Trading Workbench is — and what it can become.*
