# ADR 0006 — LLM Not in Order Path

| Field | Value |
|---|---|
| Date | 2026-05-28 |
| Status | Accepted |
| Phase | Post-P5 architectural decision; informs P6 scope |
| Related | ADR 0002 (single OrderRouter entry point), ADR 0004 (circuit breaker hard halt), ADR 0005 (24-hour activation cooldown) |
| Supersedes | — |
| Superseded by | — |

## Context

The agent runtime shipped in P3 with three intended modes:

- **B1** — read-only Q&A. The user asks a question; the agent answers using MCP read tools. No order submission.
- **B2** — suggest. The agent proposes an order; the user reviews and approves before submission. The human clicks Submit.
- **B3** — autonomous submission. The agent submits orders directly within configured limits, without per-order human approval.

P3 shipped B1 and B2. B3 was deferred to a future phase (provisionally P6).

As we approached P6 planning, three architectures were considered for "auto trading":

1. **Deterministic strategies.** A strategy.py file runs on every bar, applies hard-coded logic, emits orders. The code is deterministic. Already shipped in P2. Claude may have helped *write* the code, but Claude is not running during trading hours.

2. **Claude tunes deterministic strategies.** Periodically (overnight, weekly, on-demand), Claude reviews market data and proposes updates to strategy code or parameters. The strategies themselves remain deterministic Python. Claude is in the *authoring* loop, not the *trading* loop. Updates flow through the P5 §7 activation cooldown like any other strategy change.

3. **Claude in the per-order decision (full B3).** Claude runs during trading hours. On each bar or trigger, the system calls the Anthropic API, passes recent market state and the user's profile, and Claude's response determines whether to submit an order. The LLM is on the order path.

This ADR records the decision to **pause Architecture 3 indefinitely** and to **enforce the absence of LLM calls in the order path as a CI invariant**.

## Decision

**No LLM calls in the order path.** Specifically:

1. The order routing path — defined as `OrderRouter.submit()`, the risk engine, broker adapters, and any strategy execution code that produces orders — must not import the Anthropic SDK or call any LLM API.

2. The agent runtime (`app/agent/runtime.py`) is permitted to call the Anthropic API for user-initiated B1 and B2 interactions. The user's prompt is the trigger; the agent's response is advisory or pending user approval.

3. Scheduled, advisory uses of the Anthropic API are permitted outside the order path: morning brief narration (P5.5 §2), strategy review reports (P6, when scoped), drift detection reports (P6, when scoped). These produce text the user reads. They never produce orders.

4. A CI invariant (`check_no_llm_in_order_path.sh`) enforces this by grepping the order-path modules for any reference to the Anthropic SDK. The invariant joins the ten existing CI invariants from P5 + P5.5 as the eleventh.

5. Removing this invariant requires a successor ADR explaining what changed about how we trust LLM-driven decisions. The default is "this decision stands."

The phrase "Architecture 3" — meaning Claude in the per-order decision — is the deliberately-paused work. Architecture 2 remains in scope (and is the substance of P6).

## Rationale

The choice between Architecture 2 and Architecture 3 turns on five concrete risks that Architecture 3 introduces and Architecture 2 avoids.

### 1. Non-determinism breaks audit reproducibility

The P5 §8 audit log is immutable. Every order submission is recorded with full payload, outcome, and reason code. The implicit contract is that an order's reasons can be reconstructed and reviewed.

For a deterministic strategy, the reasons reduce to "the code at commit SHA X, given inputs Y, returned order Z." Replayable. Debuggable. Defensible.

For an LLM submission, the reasons reduce to "the model with these weights, given this prompt, with this temperature setting and these random seeds, produced this response." Anthropic's models update over time; the same prompt today may produce a different decision tomorrow. The audit log captures the prompt and the response, but not the *reasoning* that connected them, and the response itself isn't reproducible.

A trading day that goes badly is harder to root-cause when "Claude decided to short SPY at 09:35" is the audit entry. With a deterministic strategy, the audit points to a code path and you can read the path. With an LLM submission, the audit points to a prompt and a response, and the meaningful question — "why did the model produce *that* response?" — is unanswerable.

### 2. LLMs can be socially engineered past their own constraints

P5's gates assume an adversary that is either (a) malicious external code (handled by the credential and broker isolation layers) or (b) a careless human (handled by typed-ticker confirmation, the 24-hour activation cooldown, the typed-account-label circuit breaker reset). The gates are designed for the threat models we understand.

An LLM in the order path adds a new threat surface: prompt injection or chain-of-reasoning that talks the model into actions outside its intended bounds. The user types "review my positions" and a malicious document the agent fetches contains text that influences the next order decision. The defenses against this are immature compared to the defenses against the threats P5 already gates.

A useful framing: a human can be talked into a bad decision but generally not within the millisecond timescale of an order. An LLM can be talked into a bad decision *and* execute that decision within the order's natural latency. The asymmetry matters.

### 3. Latency is incompatible with bar-by-bar dispatch

Anthropic API calls typically take 1-5 seconds end-to-end. The P4 §8 work ships bar dispatch at 1-second resolution for active strategies. An LLM call per bar would either (a) bottleneck the dispatch loop, missing bars during the call, or (b) require parallel reasoning across many concurrent API calls, multiplying cost and complicating cancellation semantics.

This isn't insurmountable — buffered dispatch, batched reasoning, asynchronous trigger evaluation are all possible. But each workaround is its own design surface that doesn't exist with deterministic strategies. Architecture 2's review work happens on schedules of hours or days, where latency is irrelevant.

### 4. Cost scales with market activity, not user activity

The Anthropic API key in P5's current shape is user-initiated. Costs scale with how often the user opens the agent panel. The user pays for what the user uses. P3 §4's per-session $2/day cap bounds the worst case.

Architecture 3 inverts this: costs scale with bar volume across watched symbols. A trader watching 20 symbols across 5 timeframes at 1-second resolution generates 100 events per second. Even at one LLM call per minute per symbol (heavily debounced), that's 20 calls per minute, ~10,000 per trading day. At Haiku pricing this is bearable; at Opus it isn't. The cost model is unbounded in a way the user can't easily reason about.

Worse, the cost scales with market activity rather than trader intent. A volatile day generates more events and more potential decisions. The day you most want the agent reasoning carefully is the day it costs the most.

### 5. Backtesting an LLM is not the same as backtesting code

P5 §7's activation flow requires a recent backtest as one of five prerequisites. For deterministic strategies this is meaningful: the same code, given the same historical bars, produces the same orders. The backtest is a real preview of live behavior.

For an LLM-driven strategy, the backtest is informational at best. Replaying the prompts against historical bars and reading the model's responses doesn't simulate live trading, because:
- The model's behavior may have shifted between backtest time and live time.
- The model's responses depend on context that varies (the time of day in the prompt, recent context, tool availability).
- Sampling temperature means the same prompt produces different orders on different runs; you can't "test" the strategy in any robust sense.

The prerequisite checklist in P5 §7 §7.3 was designed with deterministic strategies in mind. Extending it to gate Architecture 3 well would require new prerequisites we don't know how to define yet — "the model has been live-validated for X days," "the model's outputs have been within reasonable bounds across Y backtests," etc. These are research questions, not implementation tasks.

## Consequences

### Positive

- **Audit trails stay forensically useful.** Every order in the system traces to deterministic code that can be replayed and reasoned about. The P5 §8 immutable audit log retains its full evidentiary value.
- **The CI invariant makes the decision durable.** A developer who tries to add a "quick LLM check before submission" hits a CI failure and has to write a follow-up ADR. The decision is enforced across every future PR without requiring vigilance.
- **The architectural boundary is conceptually clean.** ANTHROPIC_API_KEY is the credential for "Claude helps the user think about trading." It is not the credential for "Claude decides what to trade." That separation is easier to explain to a user, easier to defend in a regulatory context, and easier to maintain over time.
- **P6's scope shrinks to tractable work.** Architecture 2 is what P6 ships — Claude reviews, proposes, explains, and lets the user accept changes that flow through existing gates. This is ~3-4 sessions of work, not the 5-7 of full Architecture 3.
- **The user's mental model stays simple.** The agent helps; the user decides. Same framing as P3's B1+B2. No new trust framework needed.

### Negative

- **We give up a class of capabilities.** A future trader who wants the agent to react to market events faster than they can won't get that capability through this codebase. If that's a hard requirement, they're using the wrong system.
- **Some legitimate use cases are harder.** Trading strategies that depend on natural-language news feeds or earnings transcripts can't reason about that text in-band. They'd have to consume pre-processed signals (sentiment scores, structured event tags) from upstream sources. This is the right answer architecturally but it's a constraint.
- **The CI invariant has to be maintained.** When P6 ships strategy review and drift detection, those modules import the Anthropic SDK. The invariant script needs to know about them as allowed locations. New allowed locations require updating the script alongside the code, which is more friction than no invariant at all.
- **We are explicitly choosing to be conservative.** Architecture 3 is being explored in other systems; we're choosing not to compete on that capability. That choice is defensible but not free — it's an opinion about what trading software should be, not a forced move.

## Alternatives considered (not chosen)

### "Architecture 3 with strict per-order TOTP confirmation"

Idea: let Claude submit orders, but require the human to type a TOTP code for every order before it goes through.

Rejected. This defeats the purpose of autonomous submission (the human is in the per-order loop after all), adds substantial UX friction, and doesn't address the non-determinism or audit concerns. It's worse than B2 — slower and more annoying — without being meaningfully safer than B2.

### "Architecture 3 within tight pre-configured bounds"

Idea: let Claude submit orders within bounds the user pre-configures ("max one trade per day per symbol, max $500 notional, only during 09:30-10:30 ET"). The bounds limit blast radius.

Rejected. The bounds reduce the magnitude of bad outcomes but don't address the underlying questions (audit reproducibility, social engineering, non-determinism, backtest validity). They also create a false sense of safety — a user who has set "tight bounds" may be less vigilant than a user who knows the agent has full discretion, and the worst day is still ~max_daily_loss in bad orders. P5's existing risk_limits already provide this kind of bounding; layering LLM autonomy on top doesn't add safety, it adds attack surface.

### "Architecture 3 only on paper accounts"

Idea: let Claude submit orders only against paper accounts, never live. The user can experiment with autonomous behavior without real money at risk.

Rejected as P6 scope, but **acceptable for research**. The agent runtime can be extended to submit to paper accounts via a research-mode flag, with the CI invariant carving out a paper-only allowlist. This is a P7+ research project, not P6 product work. If pursued, it deserves its own ADR — the invariant's scope changes substantively.

### "Architecture 2 only, but with no CI invariant"

Idea: declare Architecture 3 out of scope informally, document it in P6's design, but don't enforce it via CI.

Rejected. Informal scoping decisions erode over time. A future PR adds an LLM call to "validate" an order before submission. The author justifies it as advisory. The next PR makes the validation block submission on failure. Three months later the order path has LLM calls and nobody noticed. The CI invariant is the discipline; the ADR is the explanation of the discipline.

## Implementation

### CI invariant

`apps/backend/scripts/check_no_llm_in_order_path.sh` is the eleventh CI invariant. It refuses any reference to the Anthropic SDK in the order-path modules. The order-path modules are an explicit allowlist, not a denylist — modules are presumed *not* to be in the order path unless they appear in:

| Order-path module | Why |
|---|---|
| `app/services/order_router.py` | The submit entry point |
| `app/risk/` | Pre-trade risk checks |
| `app/brokers/` | Broker adapters |
| `app/strategies/runtime/` | Strategy execution (if separate from `app/strategies/`) |

Allowed locations for Anthropic SDK imports (the invariant's allowlist):

| Allowed module | Why |
|---|---|
| `app/agent/` | User-initiated B1/B2 interactions |
| `app/services/morning_brief.py` | Scheduled narration (P5.5 §2) |
| `app/services/strategy_review.py` | Periodic review reports (P6, future) |
| `app/services/drift_detection.py` | Periodic drift reports (P6, future) |

The exact script is small (~30 lines of bash); it lives alongside `check_strategy_isolation.sh`, `check_broker_isolation.sh`, `check_no_env_credentials.sh`, `check_audit_immutability.sh`, and `check_workbench_mcp_readonly.sh`. The implementation pattern mirrors those.

### Wired into CI

`.github/workflows/ci.yml` adds:

```yaml
      - name: No LLM in order path
        run: bash apps/backend/scripts/check_no_llm_in_order_path.sh
```

### Documentation

This ADR. The runbooks (especially `docs/runbook/on-call.md` and `docs/runbook/agent.md` if added) should reference the invariant when explaining "why does the agent ask me to approve orders rather than just submit them."

### Tests

No new tests required beyond the invariant itself. The invariant *is* the test — a CI run that catches a violation is the failure mode.

## Re-evaluation

This ADR should be re-evaluated if any of these change:

- **LLM determinism improves substantially.** If LLM outputs become reproducible from prompt + seed + model version, the audit-reproducibility argument weakens. Today's models don't offer this; future ones might.
- **Live-trading-grade LLM evaluations emerge.** Today's LLM benchmarks are general-capability; there's no equivalent of "this model passed a 90-day live paper-trading evaluation with these defined metrics." If such evaluations become standard, the prerequisite-checklist argument weakens.
- **A specific high-value use case appears that Architecture 2 can't serve.** Pattern-matching to news, real-time sentiment, complex multi-asset reasoning — if a concrete workflow shows up where Architecture 2's batch-review pattern is genuinely insufficient, the cost-benefit calculation changes.
- **Regulatory framework for LLM-driven trading emerges.** Today's regulatory posture treats automated trading as either rules-based (clear audit) or discretionary (human-in-loop). LLM-driven trading sits between these; clarity here could change what's defensible.

Until then: this decision stands.

---

*ADR 0006. The architectural decision that defines what Trading Workbench is and isn't.*
