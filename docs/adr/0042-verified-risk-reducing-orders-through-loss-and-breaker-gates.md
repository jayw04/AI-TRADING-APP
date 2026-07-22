# ADR 0042 — Verified risk-reducing orders pass the daily-loss and circuit-breaker gates

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Status | **Accepted — Release Blocker** (approved with binding amendments, 2026-07-13; rev 2) |
| Phase | Cross-phase (risk engine; P5 §5 daily-loss + circuit breaker) |
| Related | 0002 (single OrderRouter), 0004 (circuit breaker), 0034 (per-account risk containment), **0038** (reducing exits exempt from gross-exposure gate), **0039** (reducing exits exempt from strategy cooldown), 0043 (loss-control architecture — *separate*), incident 2026-07-13 |

> **Revision note (rev 2).** Approved with binding amendments. The owner's three answers and one
> added concurrency requirement are incorporated below as §§ A–D and are **normative**, not
> commentary. Implementation authorisation is granted *by* this revision. The strategy remains
> halted until implementation, migration, decision-ledger verification, concurrency controls,
> and the full acceptance suite have passed.

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

A sell is eligible **only to the extent that it reduces an existing long position without
crossing through zero**, and only up to `available_reducible_quantity` (§ D).

**Also in v1:** `ORDER_CANCEL`, through the dedicated cancellation path (§ B) — classified, not
waved through.

**Explicitly deferred:** buy-to-cover on short books. It is *conceptually* risk-reducing and the
architecture must express it — but it stays **blocked** until short-position handling is
separately implemented and approved. The rule is about risk effect; the v1 *implementation* is
long-only. Those are different statements and the ADR keeps them apart on purpose.

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
9. **Snapshot coherence (§ A):** a cached snapshot is refused while locked; a snapshot behind an
   already-observed broker event is `INDETERMINATE`; a state change between classification and
   submission forces one fresh re-evaluation and never reuses the prior decision.
10. **Concurrency (§ D):** two concurrent reducing sells against the same long **cannot** both be
    approved and cross through zero. Version conflict forces reclassification.
11. **Cancellation (§ B):** cancelling a pending buy-to-open passes; cancelling a pending
    **sell-to-close** is REJECTED while locked (it removes a protective reduction); a cancel with
    unresolved partial fills is `INDETERMINATE`.
12. **Source neutrality (§ C):** an identical reducing sell classifies identically from
    `STRATEGY` and `MANUAL`, and a manual order cannot self-assert a risk effect.

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

## Binding amendments (normative — owner ruling, 2026-07-13)

### § A — Snapshot rule: no stale-cache allowance while locked

**There is no "N seconds old" threshold.** Registering one would have been the wrong shape of
answer: it treats staleness as a tunable when the requirement is *causal completeness*.

While a daily-loss or circuit-breaker lock is active, a reducing-order exemption requires a
**new broker reconciliation initiated for that decision**. A previously cached positions object
is **insufficient regardless of its nominal age**.

The snapshot must contain:

- positions and quantities
- open orders and **remaining** quantities
- partial fills and pending executions
- the prices used for projected exposure
- cash, margin and buying power where relevant
- the broker **event cursor / sequence / reconciliation timestamp**

It must be **causally at or beyond every broker event already observed locally**. A snapshot
that is merely *recent* but behind a fill we have already seen is not coherent — it is a
different account.

Before submission, require **either**:

- an **unchanged broker/account version token**, or
- an **account-level serialization lock** plus an immediate consistency check.

If the broker read fails, reconciliation is incomplete, an order or fill is unresolved, or the
state changes between classification and submission:

```
risk_effect = INDETERMINATE
decision    = FAIL_CLOSED
```

**One** fresh re-evaluation may occur. The previous decision is **never** reused.

### § B — Cancellation rule: in scope, dedicated path, no blanket pass

Cancellation is **not automatically reducing**, and must not be waved through.

A first action type is introduced:

```
ORDER_SUBMIT | ORDER_CANCEL | ORDER_REPLACE
```

A cancellation is `RISK_REDUCING` **only when** removing that open order *weakly reduces the
account's worst-case projected exposure* **and** improves at least one relevant risk dimension.

| Cancel of a pending… | Classification |
|---|---|
| buy-to-open | normally **REDUCING** |
| sell-to-open | normally **REDUCING** |
| **sell-to-close** | potentially **RISK-INCREASING** — it removes a protective reduction |
| **buy-to-cover** | potentially **RISK-INCREASING** — same reason |
| anything with unresolved partial fills | **INDETERMINATE** |

Cancelling a protective reduction is exactly the move that traps risk on the book. It stays
blocked while locked.

Cancellations route through the **same shared classifier and the same append-only ledger**, via
a dedicated cancellation execution path — they do not travel steps 9/13 as ordinary orders.

### § C — Manual-order rule: source-neutral

The exemption applies to `source_type = STRATEGY` **and** `source_type = MANUAL`.

**Trapped risk is equally dangerous regardless of who initiated the reduction.**

Manual actions receive **no broader privilege**. They must use the same coherent snapshot, pass
the same long-only v1 reduction rules, be recorded in the same ledger, fail closed when
indeterminate, and remain blocked when neutral or increasing.

> A human operator **cannot** label an order "reducing" and bypass classification. There is no
> operator-asserted risk effect.

### § D — Concurrency and exposure reservations (added requirement)

The classifier must evaluate projected state **including all open orders and already-approved
exposure reservations**.

Without this, **two concurrent sell reductions can each look safe against the same long position
and together cross through zero, creating a short** — the precise failure the zero-crossing rule
exists to prevent, arrived at by a route the single-order check cannot see.

For long-only v1:

```
available_reducible_quantity =
      current_long_quantity
    - filled_but_not_reconciled_reductions
    - open_reducing_sell_quantity
    - reserved_reducing_quantity
```

An approved sell quantity **must not exceed** that amount.

> ### §D amendment — 2026-07-22: overlapping pending-reduction representations
>
> **The formula above is superseded by the one in this amendment.** It treated
> `open_reducing_sell_quantity` and `reserved_reducing_quantity` as disjoint. Under the
> implemented reservation lifecycle they overlap: an approved reduction remains represented by a
> HELD reservation after broker submission while the corresponding broker order is also open, and
> a reservation keeps its **full original quantity** until its order goes terminal, so a partial
> fill is represented a third time by the position the fill already shrank. Subtracting these in
> full double-charges the same reduction and can refuse legitimate de-risking — the failure this
> ADR exists to prevent, reproduced by
> `tests/orders/test_adr0042_end_to_end.py::test_reductions_cannot_be_stacked_past_the_position`
> (three 200-share trims against a 500 long: the **second** was refused
> `EXCEEDS_REDUCIBLE_CAPACITY`).
>
> Only the portion of broker-open reducing quantity not already represented by a held
> reservation is charged as additional in-flight exposure, and the already-filled portion of a
> held reservation — which the broker position has already absorbed — is added back so it is
> charged exactly once:
>
> ```
> unreserved_open_reducing_quantity =
>     max(0, open_reducing_sell_quantity - reserved_pending_quantity)
>
> reserved_pending_quantity =
>     max(0, reserved_reducing_quantity - reserved_filled_quantity)
>
> claimable_reducible_quantity =
>     max(
>         0,
>         current_long_quantity
>         + reserved_filled_quantity          # already absorbed by the position
>         - unreserved_open_reducing_quantity
>     )
>
> available_reducible_quantity =
>     max(
>         0,
>         claimable_reducible_quantity
>         - reserved_reducing_quantity
>     )
> ```
>
> The atomic claim guard uses the **claimable** basis:
>
> ```
> reserved_qty_accumulator + requested_reduction_qty
>     <= claimable_reducible_quantity
> ```
>
> because the accumulator carries the claims on its own left-hand side.
>
> **`filled_but_not_reconciled_reductions` is still charged, not dropped.** It is charged by the
> broker position itself: the snapshot's position is a live broker read that already reflects
> every fill, and the open order contributes only its *remaining* quantity (`qty − filled`). The
> `reserved_filled_quantity` term exists precisely so that this position-side charge is not
> *duplicated* by the still-full reservation. It is measured from observed `Fill` rows joined to
> HELD reservations and **capped per reservation at that reservation's own quantity**, so an
> over-fill cannot manufacture capacity. An aggregate estimate such as
> `reserved − open_orders` is explicitly rejected: it cannot distinguish a FILLED reservation
> from a NOT-YET-SUBMITTED one, and adding back the latter would over-permit.
>
> Unreserved broker-open reductions remain charged in full, so a sell placed straight at the
> broker is still counted. The zero-crossing and no-short guarantees are unchanged; this
> amendment corrects an invalid arithmetic assumption inside the existing architecture and does
> not alter the reservation lifecycle, the locus of capacity authority, or the risk model.

**Classification, reservation and ledger insertion must be atomic**, under either a per-account
transactional lock or optimistic concurrency on the snapshot/account version. A version conflict
**forces reclassification** — it must never proceed on the earlier approval.

Broker-native `reduce_only` may be used where genuinely supported and verified, but it **does
not replace** the account-level classifier and ledger.

### Required locked-mode behaviour

```
REDUCING       ALLOW through the daily-loss and circuit-breaker gates,
               subject to all absolute post-trade hard limits
INCREASING     REJECT
NEUTRAL        REJECT while locked, unless separately registered
INDETERMINATE  FAIL_CLOSED
```

The daily-loss value is a **historical lock trigger**. A permitted reduction is **not** required
to improve already-realised P&L.

---

## Approval record

| | |
|---|---|
| **Decision** | **APPROVED WITH BINDING AMENDMENTS** |
| **Status after amendment** | Accepted — Release Blocker |
| **Implementation authorisation** | Granted, conditional on this revision incorporating §§ A–D |
| **Approved by** | Jay Wang (owner), 2026-07-13 |
| **Strategy state** | momentum-portfolio remains **HALTED** until implementation, migration, durable decision ledger, concurrency controls and the full acceptance suite have passed |

Daily-loss and circuit-breaker controls may prohibit new or increased exposure, but **must not
trap existing exposure by rejecting a verified risk reduction.** Classification is on projected
post-action account risk — not BUY/SELL terminology, not strategy identity, not human-versus-
automated origin.
