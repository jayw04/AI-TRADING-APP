# ADR 0002 — Single order entry point

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-05-20 |
| Phase | P0 (documents invariant; enforcement code lands P1+) |

## Context

Three callers can want to place orders on this system:

1. **The human trader** clicking the order ticket in the React UI.
2. **The strategy engine** acting on a signal from a registered strategy (P2+).
3. **The Claude Code agent layer** — either dev-time (the trader running an MCP-attached Claude Code session) or runtime (a P6+ Agent Strategy invoking Anthropic with the MCP server as its tool surface).

If each of these gets its own code path to Alpaca, we will eventually have three places that need risk checks, audit logging, idempotency guards, kill-switch wiring, and reconciliation hooks. We'll get those right in two of the three. The third will be the one that loses real money.

## Decision

**Every order — regardless of which caller initiated it — flows through a single `OrderRouter` module on the backend. There are no exceptions, including for the agent.**

```
[UI ticket]    ──┐
[Strategy]     ──┼──▶ OrderRouter ──▶ RiskEngine ──▶ Alpaca Adapter ──▶ Alpaca
[Agent (MCP)]  ──┘                       │
                                         └──▶ AuditLog
```

Concretely:

- The MCP server **does not have a `place_order` tool that talks to Alpaca directly.** Its order-related tool(s) call into the backend's REST API (e.g., `POST /api/v1/orders`) which dispatches to `OrderRouter`. No backdoor.
- The strategy engine **calls `OrderRouter` in-process**, not `alpaca_client.submit_order(...)` directly. The Alpaca client lives behind `OrderRouter`.
- The UI **always** goes through `POST /api/v1/orders` — there is no "fast path" or "dev-only path."
- `OrderRouter` is the only module imported by anything that ends up calling `alpaca_client`. Anyone else trying to import the alpaca client directly is a code-review red flag.

`OrderRouter` is also the single point where:
- Pre-trade risk checks fire (position limits, exposure caps, kill-switch).
- An order intent is persisted to the DB **before** Alpaca is called (so a crash mid-call still leaves a record).
- The audit log row is written with `actor_type` ∈ {`user`, `strategy`, `agent`} so post-hoc analysis can always answer "what initiated this order."

## Why this is non-negotiable for the agent path

The design doc's G6 says: *"Provide robust risk controls (pre-trade and post-trade) that cannot be bypassed by the agent."* If the agent has any code path to Alpaca that skips `OrderRouter`, G6 is violated. So:

- The MCP server's tool descriptions intentionally do not include "submit an order to Alpaca." They include "propose an order" (advisory; returns a draft for the human to approve) and, in P6+ Agent Strategy mode, "request an order" which the backend processes through the same pipeline as any other strategy signal.
- The shared-secret auth on `/api/v1/internal/*` is not the security boundary against the agent; the *tool surface* is. The agent can only ask for things the MCP server exposes, and the MCP server doesn't expose order placement that bypasses the router.

## Consequences

- **Good:** one place to add risk checks. One place to wire the kill switch. One place to instrument. One place to audit.
- **Good:** when something weird happens to a position, "who initiated this?" has exactly one answer ledger to read.
- **Bad:** there's a tempting shortcut every time an emergency tool needs to be written ("just call Alpaca directly from this admin script"). Resist. If it needs to place an order, it goes through `OrderRouter`. If the router blocks it for a reason that needs overriding, the right answer is to make the override an explicit input to the router, not to bypass it.
- **Bad:** modules import `OrderRouter`, which imports the Alpaca client. If you need to mock Alpaca in tests, the seam is the Alpaca client interface, not the router. Don't write tests that mock `OrderRouter` itself — that just verifies the test setup, not the system.

## Status of implementation

P0 has **no order code yet** — this ADR is the invariant we're committing to *before* code lands so the constraint shapes the design rather than getting retrofitted. First real implementation lands in P1 §11 (Manual Trading MVP).

When the first `app/orders/router.py` lands, this ADR's diagram should match the actual call graph. If it ever stops matching, either the diagram is wrong or the code is wrong — one of them needs fixing immediately.

## References

- Design Doc §2.1 G6 (risk controls cannot be bypassed by the agent)
- Design Doc §2.1 G7 (complete queryable audit log)
- Design Doc §4.4 (canonical strategy → router → risk → Alpaca flow)
- Design Doc §6 (Agent surface: B1 advisory, B2 propose-and-approve, B3 Agent Strategy)
- ADR 0001 §"MCP server as a separate process"
