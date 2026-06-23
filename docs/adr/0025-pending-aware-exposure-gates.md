# ADR 0025 — Pending-Aware Gross-Exposure and Position Gates

| Field | Value |
|---|---|
| Date | 2026-06-23 |
| Status | Accepted |
| Phase | P12 (risk-engine hardening) |
| Supersedes | — |
| Related | 0002, 0004, 0020 |
| Capability | CAP-014 — Pending-Aware Exposure Projection (Research Program Registry) |

> **Foundational principle.** Risk decisions must be evaluated against *projected*
> state — settled positions **plus** in-flight intent — not just current settled
> state. This is broader than gross exposure: the same projected-state accounting
> later extends to buying power, margin utilization, cash reservation, options
> exposure, and multi-strategy capital allocation. ADR 0025 is where the platform
> adopts it.

## Context

The risk engine (`app/risk/engine.py`) is the single pre-trade gate (ADR 0002).
Two of its caps bound how much exposure an account may take on: the per-position
cap (check 7) and the gross-exposure cap (check 8). As originally written, both
read only **settled positions** (the `positions` table) and valued **market
orders at 0** (`_estimate_notional` returns `None` when there is no `limit_price`).

Each order is routed, risk-checked, and committed to the `orders` table one at a
time, in its own engine transaction, *before* the next order is sent — and fills
lag (they arrive asynchronously on the broker trade-update stream and are
reflected in `positions` only after a sync). So a burst of orders submitted
within seconds of each other each evaluates against the *same* settled snapshot,
and market orders add nothing to the projected gross. Nothing in the engine sees
the exposure already in flight.

On 2026-06-22 this produced a real loss: the `momentum-conservative` paper book
re-ran its rebalance three times in ~2 minutes (a separate strategy-side
idempotency defect), submitting its full ~100%-invested basket three times. Each
of the 15 market BUYs passed the $100k gross-exposure cap independently, stacking
~$282k gross (~3.8×) on a $100k account. The book fell ~26% before being
manually flattened. The per-order caps were each individually correct; none could
see the cumulative in-flight exposure.

The incident required **two independent protections to fail at once**: a strategy
re-fired duplicate baskets (idempotency failure, addressed separately) *and* the
risk engine was blind to in-flight exposure (this ADR). That both failed
simultaneously is exactly what defense in depth exists to survive — fixing either
layer alone would have prevented the loss; this ADR fixes the one that must never
be bypassable.

## Decision

The gates evaluate **projected exposure**, not just settled exposure:

```
        Settled Positions        In-flight Orders (pending BUYs)
              │                          │
              └──────────────┬───────────┘
                             ▼
                    Projected Exposure   ──►   Risk Engine   ──►   Pass / Reject
                             ▲                  (gate: Projected ≤ Limit)
              market orders valued via reference_price
```

That is: `Projected Exposure = Settled Exposure + Pending Exposure`, and each gate
admits an order only while `Projected Exposure ≤ its limit`. Concretely the
gross-exposure and per-position gates count **in-flight (non-terminal) orders** in
addition to settled positions, and the engine **values market orders** from a
caller-supplied reference price:

1. `OrderRequest` gains an optional `reference_price`. For a market order the
   engine estimates notional as `qty × reference_price` (limit orders still use
   `limit_price`, which takes precedence). `reference_price` is never sent to the
   broker — it is purely a risk-valuation hint.
2. The engine persists the estimated notional on the order row
   (`orders.estimated_notional`).
3. The gross-exposure cap's *projected exposure* is `settled gross +
   Σ(estimated_notional of non-terminal BUY orders) + this order's notional
   (BUYs only)`, admitted only while `≤ max_gross_exposure`.
4. The per-position qty cap adds `Σ(qty of non-terminal BUY orders for the
   symbol)` to the resulting position quantity for BUY orders.

Sells are never *credited* against gross (a pending sell may not fill), so the
gates fail conservative. Orders with no resolvable price persist
`estimated_notional = NULL` and contribute 0 — i.e. the prior behavior, never
worse.

## Rationale

The defect is that the gates were blind to exposure that exists between
"order routed" and "fill reflected in `positions`". The fix has to close that
window at the **choke point**, because the risk engine is the single
non-bypassable gate (ADR 0002) and must protect every order source, not just the
one strategy that triggered the incident. A strategy-side guard (handled
separately) reduces the *trigger* but cannot be the *backstop*; strategies do not
self-police risk by design.

Valuing market orders requires a price. The engine cannot reliably fetch a live
quote here: the developer's environment has Norton SSL inspection that blocks
`data.alpaca.markets`, so the engine's optional `bar_cache` is not a dependable
in-path price source. The order's *originator*, however, already knows the price
it sized against. Threading that price through as a hint, and **persisting** the
resulting notional on the order row, makes the gross-exposure sum a cheap,
deterministic DB aggregation with no live-feed dependency — and keeps the engine
stateless per ADR 0002 (it reads fresh each evaluation; it caches nothing).

Counting only non-terminal orders avoids double-counting: when an order fills it
becomes terminal (dropping out of the pending sum) as its position appears in
`positions`. The two transitions arrive on the same trade-update stream, so any
overlap is transient and over-counts (conservative) rather than under-counts.

This *tightens* an existing gate; it does not remove or relax one (which would
require an ADR per the risk-engine conventions). All prior checks still run in
the same order.

**Relationship to Evidence Engineering.** This ADR is the operational analogue of
the platform's research methodology: an operational incident is analyzed with the
same *observation → hypothesis → evidence → governance* discipline used for
research programs. The root cause (in-flight blindness) was confirmed against the
incident data before any code changed, the fix ships with a regression that
reproduces the failure, and the change is promoted as a durable, named capability
(CAP-014) rather than a one-off patch. Evidence Engineering is not only how the
platform decides what to trade — it is also how it evolves its own operations.

## Implementation notes

- **Schema** (`alembic e7b2c9d4f1a6`, down-revision `a1c3e5f7b9d2`): add
  `orders.estimated_notional NUMERIC(20,4) NULL`. Purely additive; existing rows
  stay NULL (treated as 0).
- **`OrderRequest.reference_price: Decimal | None = None`** — appended last in the
  dataclass so positional construction is unaffected.
- **`RiskEngine._estimate_notional`** — market orders use `reference_price` when
  `> 0`, else `None`.
- **`RiskEngine._pending_buy_qty` / `_pending_buy_notional`** — aggregate
  `Order` rows where `status NOT IN TERMINAL_ORDER_STATUSES` and `side = BUY`.
- **`OrderRouter._persist_initial_order`** — writes
  `estimated_notional = outcome.estimated_notional`.
- **`momentum_portfolio._submit`** — passes the sizing price as `reference_price`.
  Other strategies adopt the hint incrementally; without it their market orders
  value to 0 (status quo, no regression).
- No new reason codes: the existing `GROSS_EXPOSURE` and `POSITION_CAP_QTY` fire.
- Coverage: `app/risk` stays ≥95% (`check_risk_coverage.py`); regression tests in
  `tests/risk/test_pending_aware_exposure.py`.

## Consequences

- **Positive**: a burst of orders can no longer each pass against a stale
  snapshot; cumulative in-flight exposure is bounded by the cap at submission
  time. Protects every order source (manual, strategy, agent), not just the
  incident strategy.
- **Negative**: a brief transient window (order filled but position not yet
  synced) can over-count and reject a marginal order that would have just fit —
  an acceptable conservative bias. Full effectiveness for market orders depends on
  callers supplying `reference_price`; strategies that don't yet pass it leave
  their market orders valued at 0.
- **Neutral**: order rows now carry a notional estimate, usable later for
  exposure reporting.

## Alternatives considered (not chosen)

- **In-engine live quote for market orders** (value via `bar_cache`/broker
  quote). Rejected: unreliable in the developer's Norton-inspected environment,
  adds a network round-trip to the hot pre-trade path, and couples the stateless
  engine to a market-data feed. Even if the SSL constraint disappears, a
  deterministic, stateless, fast engine is the better architecture — so rather
  than have the engine fetch quotes, a future **`PriceProvider`** (conceptual, not
  built) would let the *originator* supply better reference prices through the
  same `reference_price` seam: `reference_price ← strategy ← (future) PriceProvider`.
  The interface stays open without the engine taking on a data dependency.
- **Strategy-side idempotency only** (net targets against pending orders; durable
  rebalance guard). Necessary but insufficient: it reduces the trigger but leaves
  the centralized backstop blind. Handled as a separate change; this ADR is the
  backstop.
- **Account-level leverage/buying-power gate driven by broker state.** Heavier,
  live-only, and deferred (buying-power is dormant until the live path matures).
  This ADR delivers the protection in paper and live without a broker round-trip.

## Re-evaluation triggers

- A dependable in-path market-quote source becomes available → reconsider
  dropping the `reference_price` hint in favor of an engine-side quote.
- Observed false rejections from the fill/sync transient window become frequent
  enough to matter → revisit the non-terminal/settled overlap handling (e.g.
  reconcile by `broker_order_id`).
- Buying-power/leverage gating against live broker state lands → re-evaluate
  whether this estimate-based projection is still the primary defense.
- Pending-order latency (route → terminal) routinely exceeds a few seconds, or
  multi-strategy concurrency grows → consider **reservation-based risk
  accounting**: reserve exposure at route time and release on terminal, rather
  than re-deriving the pending sum each evaluation. Not needed at today's
  sequential, low-latency volumes.
- The Evidence Dashboard / Operational KPIs surface **risk rejections by reason**
  (`GROSS_EXPOSURE`, `POSITION_CAP_QTY`, buying-power, …) → projected-exposure
  rejections become a customer-visible KPI; watch the rate to confirm the gate is
  protecting, not over-rejecting.
