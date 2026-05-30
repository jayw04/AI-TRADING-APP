---
name: risk-engine
description: Use when working on the risk engine, risk gates, the OrderRouter, or any code that decides whether an order may be submitted. This includes files under apps/backend/app/risk/, apps/backend/app/services/order_router.py, the risk_limits table, the circuit breaker, the PDT/Intraday Margin checks, and any new risk check being added. Also invoke this skill when reviewing or modifying tests under apps/backend/tests/risk/.
---

# Risk Engine Conventions

The risk engine is the most consequential subsystem in Trading Workbench. A bug in user-facing code shows up as a confused user; a bug in the risk engine shows up as a margin call. Treat the risk engine accordingly.

## Architectural facts you must internalize before editing

### Every order passes through the risk engine

This is not aspiration; it is enforced by `check_adr0002.sh` (CI invariant for ADR 0002). The single entry point is `OrderRouter.submit()`. Manual orders, strategy-generated orders, agent-suggested orders, opt-in LLM-driven orders — every one of them. If you find yourself wanting to add a code path that bypasses the router, stop and surface it as a design question.

### The risk engine fails closed

When in doubt, reject the order. A false-positive rejection inconveniences the user; a false-negative acceptance can blow up the account. The asymmetry is enormous and irreversible. All risk checks must default to "rejection" when state is unknown.

### Risk checks compose; they do not replace

Adding a new risk check is additive. Each existing check still runs. Removing or short-circuiting an existing check requires an ADR. Even checks that "feel redundant" because another check covers the same case stay in place — defense in depth is the point.

### Risk checks are stateless functions where possible

A risk check takes the proposed order + current account state + risk limits and returns a `RiskCheckResult`. It does not maintain its own state. The check's signature should be `(order: ProposedOrder, account: Account, risk_limits: RiskLimits, market_state: MarketState) -> RiskCheckResult`. State mutations belong in services that compose checks, not in the checks themselves.

### Rejection reasons are typed and stable

Every rejection returns a typed `RejectionReason` enum value. The frontend renders these to the user; tests assert on them; the audit log records them. Adding a new rejection reason requires updating the enum, the frontend i18n strings, and the audit-log allowlist. Reusing an existing reason for a different cause confuses users and breaks tests.

## The current risk check inventory (P5)

In order of evaluation in `OrderRouter.submit()`:

1. **Typed-symbol confirmation** (live accounts only) — `LIVE_CONFIRMATION_MISMATCH` rejection if the typed ticker does not match
2. **Position-size check** — `POSITION_SIZE_EXCEEDED`
3. **Notional check** — `NOTIONAL_EXCEEDED`
4. **Gross-exposure check** — `GROSS_EXPOSURE_EXCEEDED`
5. **Daily-loss check** — `DAILY_LOSS_LIMIT_REACHED`
6. **Order-rate check** — `ORDER_RATE_EXCEEDED`
7. **Intraday risk check** (Intraday Margin Rule, replacing PDT as of FINRA 2026) — `INTRADAY_MARGIN_INSUFFICIENT`
8. **Buying-power check** — `INSUFFICIENT_BUYING_POWER`
9. **Circuit-breaker check** — `CIRCUIT_BREAKER_TRIPPED`

The order matters: cheaper checks first (typed-symbol mismatch is a string comparison; buying-power requires a broker round-trip), shared-state checks before per-order checks, and the circuit breaker last because it's the most likely to terminate the request.

## Coverage requirement

`apps/backend/app/risk/` requires ≥95% test coverage, enforced by `check_risk_coverage.py`. New risk checks must ship with tests at the same bar. The standard test shape:

- One test asserting the check accepts a clean order
- One test asserting the check rejects with the expected reason for the boundary violation
- One test asserting the check produces a stable reason code when the input is malformed
- Property-based tests for numerical edge cases (zero, negative, very large) where applicable

## When you are asked to add a new risk check

Walk through this sequence:

1. **Confirm the check belongs in the risk engine.** A check that depends on user preferences (notification settings, UI behavior) does not belong in the risk engine. A check that decides whether an order may be submitted does. If in doubt, ask the developer.

2. **Define the rejection reason** in the `RejectionReason` enum. Choose a name that describes what failed, not what the user should do about it.

3. **Implement the check as a stateless function** in `apps/backend/app/risk/`. The check imports nothing from `app/services/` (the dependency direction is risk-engine outward, not inward).

4. **Wire it into `OrderRouter.submit()`** at the correct point in the evaluation order. Document the ordering choice in a comment.

5. **Write the tests first** (or alongside the implementation, but not after). Aim for the same ≥95% bar.

6. **Update the audit-log allowlist** if the rejection reason should appear in audit entries. (Most rejections do; some are too noisy to log.)

7. **Update `docs/runbook/risk-checks.md`** with the new check's purpose and the operator response when it fires.

## When you are asked to modify an existing risk check

Read the existing tests first. The tests document the intended behavior; modifications that break tests are usually modifications that break the intent, even if the developer described them as "improvements."

If the test suite for the check is sparse (which happens with older code), the right move is to backfill tests *before* modifying behavior, so the change has a regression net underneath it.

## Patterns to avoid in the risk engine

- **Caching state across requests**. The risk engine is invoked per order; state should be fetched fresh each time. Caching introduces correctness risks (stale state allowing an invalid order through) that overwhelm any performance benefit. If a check is genuinely too slow, the right fix is to change the check, not to cache.

- **Conditional risk checks based on order source**. A risk check that runs for manual orders but not strategy orders (or vice versa) creates a path-dependent behavior the user cannot predict. Source-specific behavior belongs in policies on top of the engine, not in the engine.

- **Mixing rejection logic with side effects**. A risk check returns a result; it does not modify state, send notifications, or write to the audit log. The caller does that based on the result. This keeps the check testable in isolation.

- **"Warn but allow" semantics**. The risk engine either accepts or rejects. There is no "soft warning" state. If a condition warrants a warning, it belongs in the UI or in a separate advisory layer, not in the engine. Mixing warnings into accept/reject confuses users and corrupts the audit log's signal.

- **Using exceptions for control flow**. Risk checks return `RiskCheckResult`; they do not raise exceptions for expected rejection paths. Exceptions are reserved for genuine bugs (missing data, malformed input, system errors).

## The Intraday Margin Rule transition note

As of FINRA 2026, the PDT rule has been replaced by the Intraday Margin Rule. The `PdtAnalyzer` class in `app/risk/pdt_analyzer.py` (introduced in P5 §5) is currently being retained as a conservative interim guard — it may refuse trades that the new IML framework would now permit. A future update will replace `PdtAnalyzer` with an `IntradayMarginAnalyzer` that tracks the IML continuously.

When working in this area: do not assume the existing PDT logic is "wrong." It is conservative. Conservative-but-outdated is safer than aggressive-but-current in a risk engine. The migration to IML is a planned, deliberate change with its own ADR forthcoming.

## What "good" looks like in this domain

A risk-engine PR that lands cleanly typically has:

- A single new check with a clear, testable rejection condition
- Test coverage at or above the ≥95% bar for the file
- An audit-log allowlist update if the new rejection reason should be logged
- An update to `docs/runbook/risk-checks.md` documenting the new check
- No changes to the existing checks' behavior (those would be separate PRs)
- A walk-away gap of at least 1 hour before merge (longer for high-stakes additions like a new circuit-breaker condition)

That's the shape. Anything significantly larger than that is probably trying to do too much in one PR.
