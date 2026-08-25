# ADR 0055 — Position-notional cap requires a trusted reference price

| Field | Value |
|---|---|
| Date | 2026-08-25 |
| Status | Accepted (owner ruling, 2026-08-25) |
| Phase | Cross-phase (risk engine; `max_position_notional` gate) |
| Supersedes | **Partially supersedes ADR 0040** — its order-level fail-open, and *only* for `max_position_notional`. ADR 0040's gross-exposure behaviour is preserved unchanged. |
| Related | 0002 (single OrderRouter), **0038** (reducing exits exempt from the gross gate), 0039 (cooldown exemption), **0040** (value MARKET orders from the bar cache), 0042 (verified risk-reducing orders pass the loss gates), 0043 (loss-control architecture) |

> Numbering note: 0052 and 0053 are reserved by in-flight workstreams (account-7 rebinding audit;
> strategy performance epochs) and 0054 is taken by an unmerged branch. 0055 is the next free number,
> not a skip.

## Context

ADR 0040 established the principle that *"the exposure gates must be able to **value** every order they
gate. An order the engine cannot price is an order the gate cannot restrain — a hole in the guard."* It
then implemented that principle for the **gross-exposure** gate: MARKET orders are valued from a
caller-supplied `reference_price`, else the latest cached bar close, and only contribute 0 when no price
source resolves at all.

The **per-position notional cap** was never moved onto that shared valuation. It kept an older
resolution:

```python
ref_price = req.limit_price or (pos.avg_entry_price if pos else Decimal(0))
```

Measurement on 2026-08-25 established what that costs in practice:

1. `avg_entry_price` is **historical cost**, not a current price. A wrong stored value silently
   understates the projected notional. The observed Account-6 HON row carried `avg_entry_price` of
   21.05 against a true price near 224 — a ~10× understatement of the resulting position.
2. Far more consequential: when `pos is None` — **every market-order BUY opening a name** — `ref_price`
   is `0`, the projected notional is `0`, and the check passes **trivially and unconditionally**.

The second is not an edge case. Five strategy templates submit `OrderType.MARKET`, and **no template
passes a limit price**, so the fallback was the normal path for every strategy-originated order rather
than a rare degradation. A pre-trade deny control that an entire class of orders passes unconditionally
is not a control, which is difficult to reconcile with the platform's *"risk gates are non-bypassable"*
invariant.

The question this ADR answers is therefore narrow: **when the engine cannot establish a trusted price,
what should the position-notional gate do?** ADR 0040 answered "degrade, don't halt" and explicitly
rejected *"the harsh alternative of rejecting"* the order. That answer is correct for an aggregate and
wrong for a per-position cap, and the two need to be separated.

## Decision

1. **A single shared resolution chain.** `RiskEngine._reference_price(req)` resolves the per-share price
   an order is valued at, in one place, for every gate that must put a number on an unfilled order:
   `limit_price → reference_price (>0) → latest cached close (>0) → None`.
   Historical cost (`avg_entry_price`) is **not** in the chain and must not be reintroduced: it answers
   "what did we pay", not "what is it worth now".

2. **Missing price remains fail-open inside the gross-exposure calculation.** An unpriced MARKET order
   contributes no estimated pending notional there. **ADR 0040 is preserved in full at that boundary.**

3. **Missing price is fail-closed for `max_position_notional` when the order increases exposure.** If no
   trusted reference price can be established, the order is rejected with the new reason code
   `POSITION_CAP_UNPRICED`. This is the partial supersession of ADR 0040's order-level consequence, and
   it is **scoped to this gate only**.

4. **Reducing orders are exempt from that refusal**, via an `increases_position` guard
   (`resulting_qty > abs(current_qty)`), consistent with ADR 0038's anti-stranding principle. A
   reduction cannot newly breach a cap it is moving away from.

## Rationale

**The two gates answer different questions, so the same input warrants different answers.** For gross
exposure, an unknown component does not erase the known exposure already in the aggregate — the other
positions still count, the gate still restrains, and refusing every order because one component is
unpriceable would be disproportionate. For a per-position cap, treating an unknown price as zero makes
the *entire* gate vacuous for that order: there is no residual restraint left. Fail-open degrades the
first gate and eliminates the second.

**Why the `increases_position` exemption is load-bearing and not a convenience.** Valuing the
*resulting* position at a current price rather than stale cost makes this gate bite considerably harder,
and the first thing it would otherwise bite is exits. Trimming 100 shares from an oversized 500-share
holding leaves 400 still above the cap, so the reduction would be refused and the position trapped
*above* the limit — the 2026-07-13 exit-stranding class that ADR 0042 exists to prevent, and the same
principle ADR 0038 already applied to the gross gate. This was found by a test, not by foresight, which
is the argument for the exemption being explicit and pinned rather than incidental.

**Why not require every caller to pass `reference_price` instead.** ADR 0040 already considered and
rejected this as *the* fix: "fragile — each strategy must remember, and the incident was precisely a
caller that didn't." That reasoning is unchanged and is why this ADR fixes the gate rather than the
callers. Callers may still pass `reference_price`, and it remains preferred when the caller has sized
against a specific price.

**Why a new reason code.** `POSITION_CAP_NOTIONAL` means a cap was breached; `POSITION_CAP_UNPRICED`
means the cap could not be evaluated. The operator response differs — restore pricing versus resize the
order — and collapsing them would make the evidence record unable to distinguish a real cap breach from
a pricing outage.

## Implementation notes

- `apps/backend/app/risk/reason_codes.py` — adds `POSITION_CAP_UNPRICED`.
- `apps/backend/app/risk/engine.py` — adds `_reference_price()`; `_estimate_notional()` is refactored
  onto it so both gates share one source and cannot disagree about what a share is worth; the
  `max_position_notional` branch is guarded by `increases_position` and fails closed on `None`.
- `apps/backend/tests/risk/test_position_notional_reference_price.py` — 17 tests covering both failure
  modes, the fail-closed branch, the reduction exemption, and the numerical boundaries.
- No schema change. No new CI invariant. No change to any strategy template.
- Production wiring is unchanged and already sufficient: `RiskEngine` is constructed once
  (`lifespan.py:235`) and always with `bar_cache`, inside `if settings.alpaca_startup_enabled:` with no
  `else` branch — there is no production path where the engine exists without a price source.

## Production proof required before Strategy-8 reactivation

This ADR deliberately does not add `reference_price` to any strategy template, so the new refusal mode
is only as good as cached-price availability. That is checked at deploy time rather than assumed. All
six must pass on the target box before LOW-001 (strategy 8) is reactivated:

1. every current Account-6 holding resolves a bar-cache reference price;
2. the 2026-08-24 LOW-001 BUY symbols are replayed through `_reference_price()` and **all** resolve;
3. one deliberately cold *increasing* order proves `POSITION_CAP_UNPRICED` fires;
4. the equivalent *reducing* order proves it remains executable (the ADR 0038 exemption, live);
5. `avg_entry_price` is proven absent from the reference chain;
6. static LOW-001 target selection, quantities and economics are unchanged.

Items 3 and 4 are the pair that matters: a fail-closed gate is only trustworthy if the exemption that
keeps it from stranding an exit is demonstrated in the same environment, not just in unit tests.

**Live-safety evidence gathered pre-merge (2026-08-25, read-only, all accounts).** No newly rejected
current add was detected under the resolved limits: 0 of 86 positions exceed their
`max_position_notional` at current market value, the closest sitting at 16.9% of cap. ⚠ Provisional for
user 1, whose three `risk_limits` rows and their precedence were not resolved by that query; the caveat
does not block this decision, and items 1–2 above are the authoritative pre-reactivation check.

## Consequences

- **Positive.** The per-position notional cap becomes a real pre-trade control for market orders instead
  of a vacuous one. Corrupted or stale cost basis can no longer influence a risk decision — which
  isolates the activation-critical half of the platform position-accounting defect without waiting for
  the broader dual-writer cleanup. One valuation chain means two gates cannot disagree.
- **Negative.** A genuinely unpriceable increasing order is now **refused** where it previously passed.
  If the bar cache is cold for a symbol and the caller supplies no `reference_price`, that order does
  not execute. This is intended safety behaviour, but it is a new refusal mode and it is only as good as
  cached-price availability. Strategies that do not pass `reference_price` — which today is all of them
  except `momentum_daily` and `momentum_portfolio` — depend entirely on bar-cache warmth.
- **Negative.** Two sibling gates now treat "no price" oppositely. That divergence is deliberate and
  reasoned above, but it is a thing a future reader must be told rather than discover.
- **Neutral.** Existing tests that submitted MARKET orders with no price source now need one. That
  churn reflects the behaviour change honestly rather than masking it.

## Alternatives considered (not chosen)

- **Leave the gate as-is and rely on the gross-exposure gate to catch over-sizing on the next
  position-sync.** Rejected: `max_position_notional` is a *pre-trade* deny control. A control that only
  corrects after execution has already permitted the condition it exists to prevent. It also leaves a
  risk decision reading a field known to be unreliable.
- **Fail closed for both gates.** Rejected: it would overturn ADR 0040's reasoning wholesale for no
  additional protection, and would refuse orders whenever any single in-flight component is unpriceable.
- **Use `avg_entry_price` but validate it first** (e.g. reject implausible values). Rejected: it treats
  historical cost as a current-price proxy, which is the original category error, and it would not help
  the `pos is None` case at all — the dominant failure mode.
- **Add `reference_price` to every strategy template.** Rejected as the fix for the same reason ADR 0040
  rejected it. Deliberately **not** bundled here: it would expand a platform-risk repair into strategy
  implementation, and it creates a provenance/freshness contract that deserves its own tests and its own
  strategy-version ruling.

## Re-evaluation triggers

- **`POSITION_CAP_UNPRICED` fires on ordinary, liquid names in normal market hours.** That would mean
  cached-price availability — not the gate — is the defect, and the answer is the caller-side
  `reference_price` plumbing this ADR deliberately deferred, with explicit source/freshness semantics.
- **A strategy is observed sizing against a price the risk layer cannot see**, making the two layers
  disagree about the same order.
- **The dual-writer position-accounting defect is repaired** such that `avg_entry_price` becomes
  trustworthy. That would not restore it to the reference chain — it answers the wrong question — but it
  would remove one of the two motivations recorded here, and the ADR should say so.
- **A future gate needs to value an unfilled order.** It should adopt `_reference_price()` rather than
  invent a fourth valuation, and if it cannot, that is a signal the chain is wrong.
