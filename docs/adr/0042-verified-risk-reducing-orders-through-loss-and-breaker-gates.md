# ADR 0042 — Verified risk-reducing orders pass the daily-loss and circuit-breaker gates

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Status | **Proposed — release blocker. Awaiting owner approval BEFORE risk-engine implementation begins.** |
| Phase | Cross-phase (risk engine; P5 §5 daily-loss + circuit breaker) |
| Related | 0002 (single OrderRouter), 0004 (circuit breaker), 0034 (per-account risk containment), **0038** (reducing exits exempt from gross-exposure gate), **0039** (reducing exits exempt from strategy cooldown), 0043 (loss-control architecture — *separate*), incident 2026-07-13 |

> **Principle: a risk control may stop trading, but it must not prevent verified reduction of the risk it is intended to control.**
>
> This is not a new principle. ADR 0038 already states it: *"an exposure cap must never block an exposure-reducing order… the dangerous failure mode is not letting a de-risking exit through — it is refusing one, which traps risk on the book."* ADR 0042 does not invent a rule. It finishes applying one that was only ever applied to two of the four gates.

---

## Context

### What happened

On 2026-07-13 the momentum book breached its $5,000 daily-loss limit at 09:30 ET (−$5,504). At
10:00 ET the strategy proposed **trimming SNDK and trimming LITE** — reducing its two largest
positions. Both were rejected. The book stayed at **98.1% invested through a −7% day**, and the
loss deepened to **−$7,501** — roughly **$2,000 (36%) of it accruing *after* the control fired.**

Nothing malfunctioned in the strategy. The control locked in the exposure it exists to cap.

### Why a breaker reset would not have helped

`app/risk/engine.py` evaluates the daily-loss cap at **step 9** and the circuit breaker at
**step 13**:

```
step  9:  if day_change <= -max_daily_loss:  trip(); return REJECT [CIRCUIT_BREAKER]
step 13:  if breaker_tripped:                          return REJECT [CIRCUIT_BREAKER]
```

Step 9 rejects **every order** — no side check, no exemption — and it runs *before* step 13. So
resetting the breaker changes nothing: the next order re-trips at step 9 and is rejected. The
account was **structurally unable to reduce**, by any sanctioned path.

### The exemption already exists — the loss gates were simply missed

`is_reducing_sell` is computed at `engine.py:294` and consulted by exactly one gate:

| Gate | Reducing-order exemption | Established by |
|---|---|---|
| gross exposure (step 8) | ✅ | ADR 0038 |
| strategy cooldown | ✅ | ADR 0039 |
| **daily loss (step 9)** | ❌ | — |
| **circuit breaker (step 13)** | ❌ | — |

---

## Decision

### 1. Orders are classified by projected risk effect, never by verb

**A `SELL` is not a risk classification.** A sell can open or enlarge a short. A buy can close
one. The existing `is_reducing_sell` heuristic is correct only by accident — it works because
the platform is long-only today, and it would be wrong the moment it is not.

The rule is stated in terms of **projected post-trade state**:

> Circuit-breaker and daily-loss gates shall permit orders proven, from current
> broker-confirmed positions and projected post-trade state, to reduce portfolio risk without
> opening, increasing, or reversing exposure.

### 2. Frozen classification

A proposed order — or an atomic order **group** — is `RISK_REDUCING` only when **all** hold:

1. It does not increase absolute exposure in **any** affected instrument.
2. It cannot cross through zero and establish exposure in the **opposite** direction.
3. Projected portfolio **gross exposure does not increase**.
4. Projected **leverage / margin utilisation does not increase**.
5. It **improves at least one** exposure dimension the locked account is permitted to reduce.
6. It does **not** create a new instrument, strategy sleeve, or position.
7. All post-trade **absolute hard limits** still pass.

**Permits:** sell-to-close or trim a long · buy-to-cover or trim a short · cancelling an
unfilled risk-increasing order · reducing a position while in daily-loss breach.

**Rejects:** sell-to-open · buy-to-open · a reduction that crosses zero and reverses ·
a "trim" paired with larger new exposure elsewhere · any order whose *projected* result raises
gross exposure despite looking locally defensive.

### 3. `lock_trigger` and `permitted_effect` are different things

**The daily-loss metric is historical. It cannot be repaired by a trade.**

```
lock_trigger     — the HISTORICAL condition that activates restricted mode
                   (day_change <= -max_daily_loss). Backward-looking. Immutable by trading.

permitted_effect — the FORWARD-LOOKING exposure reduction allowed while locked.
                   Evaluated against projected post-trade state.
```

Conflating them would make the classifier demand that a reducing order improve an
already-realised daily P&L — which no order can do — and every reduction would be rejected for
the wrong reason. The lock is not an objective to be traded back to; it is a mode.

### 4. One shared classifier, returning a structured decision

Steps 9 and 13 **call the same classifier**. They do not implement similar logic separately —
that is how the gross-exposure gate and the loss gates diverged in the first place.

```
risk_effect ∈ { RISK_REDUCING, RISK_INCREASING, RISK_NEUTRAL, INDETERMINATE }
decision    ∈ { ALLOW, REJECT, FAIL_CLOSED }
```

**`INDETERMINATE` fails closed.** Not "probably fine."

### 5. One coherent account snapshot

The before/after computation runs against a **single coherent snapshot** — positions, open
orders, prices, cash, buying power, and the proposed order group — whose **version/hash is
recorded**. Otherwise the system approves against one state and submits against another.

A stale or unreadable snapshot is `INDETERMINATE` → `FAIL_CLOSED`.

### 6. Partial fills and atomic groups

For an ordinary single-position trim, partial fills remain **monotonically risk-reducing**: any
prefix of the fill is still a reduction. Safe.

**Multi-leg groups are not.** If any leg *alone* could increase risk, the group must be
evaluated and executed **atomically, or rejected while locked**. A partially-filled hedge is an
un-hedged position.

### 7. Durable risk-decision ledger — same release, not a follow-up

**Rejected orders are not persisted anywhere.** The `orders` table showed *zero* rows for
account 1 on 2026-07-13, and the investigation reached the wrong conclusion **twice** before the
`signals` table gave it up by accident. Without the ledger, ADR 0042 cannot be *verified* and
the next incident cannot be reconstructed.

Append-only. Written for **allow and reject alike**. A retry **references** the prior decision;
it never overwrites it.

```
account_id · strategy_id · strategy_version · slot_claim_id · order_or_group_id
lock_state · lock_reason · risk_policy_version
before_state_hash · projected_after_state_hash
position_exposure_before/after · gross_exposure_before/after · leverage_before/after
risk_effect · decision · reason_codes · decided_at · correlation_id
```

The durable lifecycle becomes:

```
signal → order proposal → risk decision → broker submission → broker ack/reject → fill/cancel
```

Every stage persisted or reconstructible.

---

## Scope — v1 deliberately narrow

**Supported:** long-position reductions only.

- Existing long confirmed **by the broker** (not the local positions table — it lags).
- `0 < sell_qty <= confirmed_long_qty`.
- Projected position `>= 0`.
- Projected gross exposure strictly decreases.
- No linked buy, replacement, reversal, or short creation.
- Broker state and market data sufficiently fresh.
- Proposal and decision durably recorded.

**Explicitly deferred:** buy-to-cover on short books. It is *conceptually* risk-reducing and the
architecture must express it — but it stays **blocked** until the classifier safely supports
shorts. The rule is about risk effect; the v1 *implementation* is long-only. Those are different
statements and the ADR keeps them apart on purpose.

**Not in this ADR:** the loss-control architecture (separated controls, persisted session
baseline, trip classification, reconciliation, recovery preflight, hysteresis, thresholds) — that
is **ADR 0043**. And the dispatcher lifecycle (HALTED enforcement, slot claims) — that is the
incident's P0 corrective, already merged; cross-referenced, not absorbed.

---

## Rationale

**The failure mode is asymmetric.** A wrongly-permitted reduction can only move the book toward
cash — bounded, and in the conservative direction. A wrongly-*refused* reduction leaves risk on
the book while the market keeps moving, with no bound at all. Given "conservative defaults", the
exemption *is* the conservative choice.

**ADR 0004's rationale does not cover this case.** Its entire argument is bug containment —
*"a strategy that has gone wrong tends to keep being wrong."* Under that model, blocking all
orders is coherent: a buggy strategy's sells may also be wrong. But it explicitly concedes the
gap in its own Consequences: *"modulo open positions that drift between order submissions."*
2026-07-13 was not a bug. It was a market loss on a correctly-functioning strategy, and the
control's behaviour was incoherent for that case.

**Verb-based exemption was considered and rejected** as the *architectural* rule. `side == SELL`
happens to be safe on a long-only book — and would silently become a short-opening hole the day
the platform supports shorts. The rule must be about the risk effect. (The v1 implementation may
still be long-only; the *rule* may not be.)

**Raising `max_daily_loss` was rejected outright.** An audited parameter change is still
functionally a bypass when its purpose is to defeat the active protection condition — and it
re-enables buys, not merely reductions.

---

## Consequences

**Positive**
- An account in daily-loss breach can act on its own risk-reducing decisions.
- Steps 9 and 13 stop being two near-duplicate rejection sites.
- Every risk decision — allowed or refused — becomes durable, auditable evidence.
- The `is_reducing_sell` heuristic is replaced before shorts make it unsafe.

**Negative / risks**
- The classifier is now on the order hot path. It must be fast and it must fail closed.
- A snapshot-coherence bug could approve against stale state — mitigated by the recorded hash
  and by `INDETERMINATE → FAIL_CLOSED`.
- A buggy strategy in breach can now still *reduce*. Accepted: reduction is bounded by
  flattening, and ADR 0038 already accepted this exact trade-off for gross exposure.

**Neutral**
- Buys and risk-increasing sells remain blocked while locked. Nothing loosens.

---

## Release gate (owner-specified — all required before deploy)

1. Unit tests for the classifier and **every gate-ordering case**.
2. Integration through the **real** `OrderRouter` → risk-engine path.
3. **Historical replay of the exact 2026-07-13 SNDK and LITE proposals.**
4. Negative tests: buys, oversells, reversals, unknown positions, stale snapshots, short
   creation — all still blocked.
5. **Paper-account canary** under a deliberately breached daily-loss state: only a verified long
   reduction passes.
6. Proof that `HALTED` prevents dispatch and a rejected run cannot execute six times (P0).
7. Ledger evidence for **every** test case.
8. **Determinism:** replaying the same snapshot + proposal under the same policy version yields
   the same classification.

The replay must demonstrate:

```
BEFORE                                   AFTER
  SNDK trim → DAILY_LOSS reject            SNDK trim → ALLOW_VERIFIED_REDUCTION
  LITE trim → DAILY_LOSS reject            LITE trim → ALLOW_VERIFIED_REDUCTION
                                           any buy   → DAILY_LOSS reject
                                           oversell  → RISK_REDUCTION_CLASSIFICATION reject
                                           2nd run   → DUPLICATE_SLOT reject
                                           halted    → SKIPPED_HALTED
```

---

## Open questions for the owner

1. **Freshness bound.** How stale may the broker snapshot be before a reduction is
   `INDETERMINATE`? (Proposed: reject if broker positions are older than N seconds — N to be set
   by you, not guessed by me.)
2. **Cancellation.** Rule 2's "cancel an unfilled risk-increasing order" is a *cancel*, not an
   order — it does not traverse the risk engine today. Confirm it is in scope for 0042 rather
   than a separate path.
3. **Manual orders.** A human-submitted reducing sell hits the same gates. Confirm the exemption
   applies to `source_type=MANUAL`, not only `STRATEGY`.
