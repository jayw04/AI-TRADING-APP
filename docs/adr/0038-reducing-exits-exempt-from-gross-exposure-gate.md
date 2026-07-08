# ADR 0038 — Position-reducing exits are exempt from the gross-exposure gate

| Field | Value |
|---|---|
| Date | 2026-07-08 |
| Status | Accepted (2026-07-08) |
| Phase | Cross-phase (risk engine; P5 §5 gross-exposure gate) |
| Related | 0002 (single OrderRouter), 0034 (Per-account Risk Containment), CAP-014 (pending-aware exposure, incident 2026-06-22), Platform Principles v1.0 (*Risk Containment is Local*) |

> **Principle: an exposure cap must never block an exposure-*reducing* order.** The dangerous failure
> mode in a gross-exposure gate is not letting a de-risking exit through — it is *refusing* one, which
> traps risk on the book. Fail-safe here means: when an order can only *lower* gross exposure, it passes.

## Context

The gross-exposure gate (`app/risk/engine.py`, step 8) computes:

```
projected = settled gross (Σ|position market_value|)
          + in-flight BUY notional (routed, not yet filled)
          + this order's notional  (only when it is a BUY; a SELL contributes 0)
reject GROSS_EXPOSURE if projected > max_gross_exposure
```

A SELL contributes 0 — the deliberately conservative pending-aware behavior from CAP-014 (incident
2026-06-22): a *pending* sell may not fill, so it is not *credited* toward other orders' headroom.

The unintended consequence: **once settled gross already exceeds `max_gross_exposure`, every
subsequent order — including a position-reducing SELL — is rejected**, because
`projected = gross_now (already > cap) + … > cap`. The gate cannot tell that *this* sell reduces the
very exposure that is over the cap; it fails conservative in the one direction that is actually
dangerous.

**Incident 2026-07-07 (the motivation).** Range Trader Top-5 (account 2, `max_gross_exposure` $10,000)
filled three market BUYs to **$11,077** gross — over the cap — via the NULL-`estimated_notional` entry
path (market orders priced at 0 slipped past the pending-BUY stacking guard). When the strategy's
stop-loss then fired, its SELL exits were rejected `GROSS_EXPOSURE` on **every** 5-minute cycle
(11:20–12:00 ET). The strategy **could not stop out**; the positions cleared only via an unrelated
account reset. A book that cannot exit a losing position is the worst failure an exposure gate can
cause.

## Decision

1. **A position-reducing sell is exempt from the gross-exposure gate.** A SELL that is fully covered by
   the current long position — `current_qty >= req.qty`, the *same* "not opening a short" condition the
   §6 short restriction already uses — **skips step 8** and proceeds through every other gate.
2. **Short-opening sells are NOT exempt.** A SELL whose quantity exceeds the held long (`current_qty <
   req.qty`) still hits the gross gate; and for `allow_short = false` accounts it is already rejected
   earlier by the §6 short restriction (`SHORT_NOT_ALLOWED`), so no short slips through the exemption.
3. **No new rejection reason, no schema change.** Every other gate (short restriction, position caps,
   daily-loss / circuit breaker, order-rate, buying power) still runs for the order.

## Rationale

- **An exposure cap exists to stop exposure from *growing*.** A sell that closes or reduces a long can
  only *shrink* gross. Blocking it inverts the gate's purpose and is precisely the failure that traps
  risk on a book that is already over-exposed.
- **The engine already treats de-risking sells specially.** §6 already distinguishes reduce-vs-short,
  and the LIVE pre-trade buying-power gate already passes all sells (*"SELL: always passes"*,
  `risk-gates.md`). This decision makes the gross gate *consistent* with that established treatment
  rather than inventing a new concept.
- **Fail-safe, not fail-open.** The exemption is scoped to orders that provably reduce exposure. It
  never lets a risk-*increasing* order through: a BUY is unaffected, and a short-opening sell stays
  gated (and blocked by §6 when shorts are disallowed). The exemption relies on the same `current_qty`
  the short restriction already trusts.
- **CAP-014 conservatism is preserved.** Not *crediting* a pending sell toward other orders' headroom
  (the entry-stacking fix) remains correct and unchanged. This decision is orthogonal: it is about a
  reducing sell's *own* passage, not about crediting it toward anything else.

### Alternatives considered

- **Credit the reduction** (`projected = gross_now − reduction_notional + pending_buys`). Rejected: it
  needs a reliable per-share reference price for the reduction, which market sells lack — reintroducing
  the exact NULL-notional fragility that caused the incident. And a pure reduce can never breach an
  exposure cap *regardless of price*, so the boolean exemption is both simpler and strictly correct.
- **Fix only the sizing** (shrink the strategy's per-position budget so it fits the cap). Rejected as
  *the* fix: that is the operational mitigation already applied on 2026-07-07 (range → $2k/position),
  but it treats the symptom. Any book can drift over its cap (the NULL-notional entry path, a price
  move, a lowered cap); the gate must not trap exits regardless of how the book got over the line.
- **Exempt *all* sells from the gross gate.** Rejected: a short-opening sell *increases* exposure and
  must stay gated. Scoping the exemption to `current_qty >= req.qty` makes it exactly the
  risk-reducing set.

## Implementation notes

- `app/risk/engine.py` step 8: gate the gross-exposure check on `not is_reducing_sell`, where
  `is_reducing_sell = req.side == OrderSide.SELL and current_qty >= req.qty`. `current_qty` is already
  loaded at step 7 for the position-size cap, so no extra query. A comment cites this ADR.
- No new `ReasonCode`; no audit-log allowlist change; no schema change. `app/risk/` stays ≥95%
  (`check_risk_coverage.py`); new regression tests land in `tests/risk/test_pending_aware_exposure.py`.
- Runbook `docs/runbook/risk-gates.md` gains a gross-exposure section documenting the exemption and the
  operator note.

## Consequences

- **A strategy (or manual trader) can always stop out / de-risk**, even when the account is at or over
  its gross cap. The 2026-07-07 exit-trap cannot recur.
- The gross cap remains **fully binding on every risk-increasing order** — BUYs and short-opening
  sells are unchanged.
- **Related follow-ups, deliberately NOT in this ADR** (tracked separately): (a) the per-strategy 60s
  cooldown (`OrderRouter` §6) similarly rejects reducing exits and warrants the same exemption; (b) the
  NULL-`estimated_notional` entry path lets market BUYs over-fill past the cap in the first place.
  Both are distinct fixes with their own change sets.
