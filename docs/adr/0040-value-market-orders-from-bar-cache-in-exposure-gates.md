# ADR 0040 — Value MARKET orders from the bar cache in the exposure gates

| Field | Value |
|---|---|
| Date | 2026-07-08 |
| Status | Accepted (2026-07-08) |
| Phase | Cross-phase (risk engine; P5 §5 gross-exposure gate; CAP-014 pending-aware exposure) |
| Related | 0002 (single OrderRouter), **0038** (reducing exits exempt from the gross gate), **0039** (cooldown exemption), CAP-014 (pending-aware exposure, incident 2026-06-22) |

> **Principle: the exposure gates must be able to *value* every order they gate.** An order the engine
> cannot price is an order the gate cannot restrain — a hole in the guard.

## Context

CAP-014 (incident 2026-06-22) made the gross-exposure and per-position-qty gates **pending-aware**: they
count in-flight (non-terminal) BUY orders so a burst of near-simultaneous baskets can't each pass against
the same *settled* snapshot and stack leverage. The gross-*notional* gate sums `Order.estimated_notional`
over in-flight BUYs.

But `estimated_notional` was only populated from a `limit_price` or a **caller-supplied
`reference_price`**. A MARKET order with neither → `estimated_notional` is NULL → it contributes **0** to
the pending-BUY sum, and its own incoming value is 0.

**Consequence — the entry side of the 2026-07-07 exit-trap.** A strategy that submits market BUYs without
a reference price (e.g. Range Trader) defeats the CAP-014 guard: each market BUY evaluates against the
settled snapshot with a pending-BUY sum of 0, so several fill before any is counted. On 2026-07-07 Range
Trader Top-5 filled **3 market BUYs to $11,077 against its $10,000 cap**, then could not stop out. ADR
0038 / 0039 fixed the *exit* side (a reducing sell is no longer blocked by the gross gate or the
cooldown); this ADR fixes the *entry* side (stop the over-fill from happening).

The LIVE buying-power gate already prices market orders from the latest cached bar close
(`BuyingPowerChecker._fetch_latest_price`) — but the `RiskEngine` was constructed **without** `bar_cache`
(deferred "to §7"), so the gross gate had no price source at all.

## Decision

1. **Wire `bar_cache` into the production `RiskEngine`** (`lifespan.py`).
2. **`RiskEngine._estimate_notional` values a MARKET order from the latest cached bar close** when neither
   a limit price nor a caller reference price is present — the *same* source the buying-power gate uses. A
   priced market order (a) counts as `incoming` in the gross gate and (b) persists a non-NULL
   `estimated_notional`, so the **next** order's pending-BUY sum includes it — closing the stacking gap.
3. **When no price source resolves** (no bar cache, or a cold symbol), the estimate is still `None` →
   contributes 0 (the prior fail-open) — now the *rare exception*, not *every* market order.

## Rationale

- **The CAP-014 guard is only as good as the engine's ability to price in-flight orders.** An unpriceable
  market order is a hole in it. Pricing from the same bar cache the buying-power gate already uses is the
  minimal, consistent fix — both exposure gates now value market orders identically.
- **Backward-compatible.** The fallback is gated on `bar_cache` presence. Unit tests construct
  `RiskEngine(session_factory)` with no bar cache, so a market order still estimates to `None` exactly as
  before; only production (bar cache wired) gains the valuation. Tests that exercise the new path inject a
  stub bar cache.
- **Degrade, don't halt.** Not fully fail-closed — a cold-cache symbol still contributes 0 — but strictly
  better than "every market order contributes 0," and it avoids the harsh alternative of rejecting every
  market order on a cache miss (which would stop legitimate paper trading).

### Alternatives considered

- **Require every caller to pass `reference_price`.** Rejected as *the* fix: fragile — each strategy must
  remember, and the incident was precisely a caller that didn't. Callers may still pass it (preferred when
  available — it is the price the order sized against); this decision makes the gate robust when they
  don't.
- **Fail closed: reject market orders when unpriceable.** Rejected: too harsh — a cold-cache symbol would
  block legitimate paper trading. The gate should degrade, not halt.
- **Add a slippage buffer to the estimate** (like the buying-power gate's 1%). Rejected for the *exposure*
  estimate: `estimated_notional` is a valuation (also persisted and displayed), consistent with
  `qty × reference_price` (no buffer). The buying-power gate's worst-case buffer is a separate concern.

## Implementation notes

- `app/lifespan.py`: construct `BarCache` *before* the `RiskEngine` (it was created later, for the
  StrategyEngine/BacktestWorker) and pass `bar_cache=bar_cache`.
- `app/risk/engine.py`: `_estimate_notional` is now async and falls back to `_latest_close(symbol)`
  (bar cache) for market orders; the sole call site awaits it.
- No new `ReasonCode`, no schema change. `app/risk/` stays ≥95% (`check_risk_coverage.py`); tests inject a
  stub bar cache.

## Consequences

- **A burst of market BUYs can no longer over-fill past the gross cap** when the symbol has a cached price
  — the CAP-014 guard now covers market orders. Combined with ADR 0038 / 0039, the 2026-07-07 incident is
  closed on **both** the entry and exit sides.
- **Market orders now carry a persisted `estimated_notional` in production** (previously often NULL),
  improving the accuracy of every downstream consumer of that field.
- **Residual:** a cold-cache symbol still estimates to 0 (documented fail-open) — acceptable and rare;
  callers that pass `reference_price` (the sized price) bypass it entirely.
