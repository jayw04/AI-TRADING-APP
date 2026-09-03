# Strategy 9 — `SIP_LIVE` freshness execution policy (v0.1, PROPOSAL)

| Field | Value |
|---|---|
| Status | **PROPOSAL FOR OWNER ADJUDICATION — NO VALUE FROZEN.** This document freezes nothing. It derives candidate bounds from Strategy 9's own governed execution mechanics and states the consequences of each so the owner can rule. |
| Identity (once ruled) | `strategy9-sip-live-freshness-policy@v1.0` — the string a `freshness_policy_ref` will name (B3 Decision 3). v0.1 is not registrable. |
| Governs (once ruled) | The `SIP_LIVE` maximum age Strategy 9 may declare on a demand lease, its semantics at each consuming decision, and the fail-closed behaviour on every non-`PASS` state. |
| Does **not** govern | The SIP cache refresh cadence (B3 derives cadence *from* this bound, never the reverse). RiskEngine code (Mechanism C, `#726`). Strategy 9 activation. The executor's own sealed gates (`v13_frozen_execution_limits_v8.json`). |
| Authority granted | **None.** No Strategy 9 LIVE registration, no `FreshnessPolicyProvider` implementation, no RiskEngine change, no cache enablement. B3 continues to refuse Strategy 9 LIVE demand with `FRESHNESS_UNBOUND` until v1.0 of this policy is ruled and pinned. |
| Depends on | SIP-CACHE-001 contract v1.0.1 §6 / §9 / §10 / §12 (`main`) · B3 design v0.1 (#725) · Mechanism C matrix v0.1 (#726) · ADR 0055 (`main`) · ADR 0049 (`main`) · sealed limits `85e45984:ops/acct7/v13/v13_frozen_execution_limits_v8.json` · WP3 price-mechanism evaluation 2026-08-31 v1.0 (**local, uncustodied** — see §1.4) |
| Owner rulings honoured | 2026-08-21 "I would not change the 300-second stale-reference rule" · 2026-08-31 `SIP_LIVE` max age NOT frozen in the contract, set by the Strategy-9 execution policy · 2026-09-02 B3 D3/D5: bound originates in the consumer's governed policy; NULL ⇒ refused · 2026-09-02 §6-§7: do not infer the number from cache refresh frequency; evidence first |

---

## 0. Why this document exists, and what "freshness" is here

`SIP-CACHE-001` v1.0.1 §6 deliberately left the `SIP_LIVE` maximum age blank: *"The bound is
consumer-specific and must be chosen by the actual Strategy-9 execution policy"* (lines 298-303) and
its open-items register carries `SIP_LIVE maximum age value — DEFERRED` (line 653). B3 made that
structural: the bound reaches a lease only through a `FreshnessPolicyProvider`, and the production
provider returns `None` for everyone, so no Strategy 9 LIVE lease can be admitted today.

Freshness, for this policy, is **the maximum elapsed time between a quote's exchange
`source_timestamp` and the instant a Strategy 9 exposure decision is evaluated against it**, after
which the reference is no longer acceptable for that decision. It is measured on the evaluating
component's injected clock (B1 invariant: the consumer cannot supply the clock), never from
`received_at_utc`, never from job completion (contract §6 lines 305-307).

Three things it is **not**:

1. Not the cache refresh interval. B3 computes cadence as `clamp(strictest_bound / 2, floor, ceiling)`
   *from* the bound. Reading the relationship backwards would let infrastructure settle a risk question.
2. Not a waiting horizon. The sealed limits are explicit: *"The deadline bounds HOW LONG the executor
   WAITS for a qualifying quote. It never relaxes what qualifies. A 21-second-old quote fails at t=25s
   exactly as it fails at t=4s."* (`v13_frozen_execution_limits_v8.json:101`).
3. Not a valuation-accuracy tolerance alone. §4.1 shows valuation error from staleness is small at every
   candidate bound; the bound's load-bearing function is **coherence with the executor's gate** and
   **liveness of the plane** (a stale reference is evidence the plane is broken, and the consumer must
   stop).

---

## 1. Evidence base

Every number below is cited to a governed or sealed source. Nothing is estimated from the SIP plane.

### 1.1 Strategy 9's execution mechanics (what actually submits orders)

| Fact | Value | Source |
|---|---|---|
| Construction | v1.3 "C40": equity sleeve = fixed top-40 PIT momentum names, `w = min(1/40, 0.04)`; cross-asset sleeve = 9-ETF `cross_asset_tsmom`; blend 0.40 / 0.60 | ADR 0049 Decision items 1-2 |
| Order path | sizing → bounded threshold (exits exempt) → `ctx.submit_order` → OrderRouter (ADR 0002) | ADR 0049 "Exact transformation sequencing" |
| Cadence | Weekly Monday rebalance (template cron `0 14 * * mon`; live schedule 10:40 ET) | `strategies_user/templates/combined_book.py:77`; MondayRebalance 2026-08-31 observation |
| Live book | 51 positions reconciled; strategy 9 IDLE v1.4.0; gross cap $100,000 | Strategy9_ActivationAuthority_Reconciliation_2026-08-31_v1.0 |
| Staged execution | Stage A exits (risk-reducing, no turnover cap, 45 min) → Stage B cross-asset (45 min) → Stage C equity entries (60 min); broker re-reconciliation within $1.00/position between stages | sealed limits `:129-143` |
| Order pacing | 1.0 s between submissions; max individual order $25,000 | sealed limits `:106-107` |
| Attempts / fill window | 2 attempts × 120 s fill window; failure ⇒ `HALTED_REQUIRES_REVIEW`; **no market-order fallback** | sealed limits `:41`, `:73-74` |
| **Cross-asset ETF sleeve gate** | reference = consolidated **SIP** top-of-book quote midpoint; `max_quote_age_seconds: 10`; `max_half_spread_bps: 25`; drift vs manifest ≤ 1.5 %; order type **market, day**; `limit_price` not sent | sealed limits `:51-58`; WP3 evaluation §1 table |
| **Single-stock sleeve gate** | reference = latest **IEX** trade; `max_trade_age_seconds: 300`; no spread gate; drift ≤ 1.5 %; order type **marketable limit, day**, collar 50 bps (`round(ref × 1.0050, 2)` / `× 0.9950`); `limit_price` **sent** | sealed limits `:60-69` |
| Transient re-poll | single stock ≤ ~8 s; cross-asset 30 s **wall-clock deadline** — *"NEVER AN ALLOWED QUOTE AGE"* | sealed limits `:86-99`, `:179` |
| Feed regime | `execution_quote_feed: sip`, `execution_trade_feed: iex`; moving the single-stock trade reference to SIP *"would need its own governed approval"* | sealed limits `:42-49` |
| Owner ruling on the 300 s rule | *"I would not change the 300-second stale-reference rule. That gate is doing its job."* Extending it is one of the five forbidden fixes of 2026-08-20. | sealed limits `:392` |
| Production evidence | 2026-08-20 Stage A: two stale-reference failures (MS, PH) halted the stage at 5.9 % after 32 exits filled; the gate has fired live | sealed limits `:353`, `:392`; ADR 0054 (local) |

Consequence for scope: **Strategy 9 already carries a complete, sealed, owner-ratified freshness regime
at the executor.** The executor reads SIP quotes with its own explicit `feed=sip` requests. This policy
does not touch that regime. What Strategy 9 lacks is a *freshness-bounded trusted reference at the
risk-engine boundary* — §1.2.

### 1.2 The decision that lacks a bounded reference (ADR 0055 on `main`)

`RiskEngine._reference_price` resolves `limit_price → reference_price (>0) → latest cached close (>0)
→ None` (ADR 0055 §Decision 1; `app/risk/engine.py:696-703`). Consequences per gate:

| Gate | Missing price | Source |
|---|---|---|
| `max_position_notional`, order **increases** exposure | **fail-closed** — `POSITION_CAP_UNPRICED` | ADR 0055 Decision 3; `engine.py:314-359` |
| `max_position_notional`, order **reduces** exposure | exempt (`increases_position` guard) | ADR 0055 Decision 4 |
| gross-exposure estimate | **fail-open** — unpriced MARKET contributes 0 (ADR 0040 preserved) | ADR 0055 Decision 2 |
| buying-power check, MARKET order | **fail-open** — required notional collapses to `Decimal("0")`; own `_fetch_latest_price`, not the shared chain | `app/risk/buying_power.py:102-105`; Mechanism C `ADR0055-MARKET-BUYING-POWER-UNPRICED-001` |

Two measured defects make the chain's last link untrustworthy for Strategy 9:

- **The cached close has no age bound.** `_latest_close` → `bar_cache.get_latest_bar` queries the last
  two days of 1-minute bars and returns the last row; neither caller inspects `bar["t"]`
  (`bar_cache.py:167-193`, `engine.py:715-729`). A bar up to ~48 h old is accepted as the trusted
  reference. The cache is IEX-fed (contract §12 line 469).
- **The equity sleeve is already covered; the cross-asset sleeve is not.** Because single-stock orders
  carry `limit_price`, the first link resolves and the executor's gated price reaches the risk decision.
  Cross-asset orders are `market` with no `limit_price` and no `reference_price`, so they fall through
  to the unbounded cached close — or to `None` ⇒ `POSITION_CAP_UNPRICED` ⇒ residual ⇒ stage halt.
  (WP3 evaluation §1: *"The gap is the cross-asset ETF sleeve only."*)

### 1.3 What the contract already binds a declaring consumer to

Contract v1.0.1 §10 (lines 417-426): a consumer declaring `SIP_LIVE` states its maximum acceptable age,
**fails closed on anything except `PASS`** for that profile, and has **no implicit fallback to IEX**;
a legitimate IEX fallback must be explicitly designed, registered and governed *for that consumer*.
§9: `STALE` / `INCOMPLETE` / `ENTITLEMENT_FAIL` / `ABSENT` all produce the same consumer obligation —
stop. §12: supplying `SIP_LIVE` into `_reference_price` is a consumer integration behind §19's
separate review and *"would additionally require deciding whether a SIP-sourced reference price
changes the fail-closed semantics of `POSITION_CAP_UNPRICED`"* (lines 476-479).

### 1.4 The unresolved mechanism question (WP3, uncustodied)

`docs/design/LOW-PIT/Strategy9_WP3_PriceMechanism_Evaluation_2026-08-31_v1.0.md` exists **only in the
local worktree** (untracked; sha256 `5cdb8167…`, 111 lines) — it is cited here as context, not as
governing authority. It evaluates three ways to get the executor's trusted price into the ADR 0055
decision: (a) a `reference_price` field on the request contract — *recommended*; (b) carry it as
`limit_price` — changes cross-asset execution semantics; (c) the shared SIP cache — *"⛔ Wrong tool for
this need … the risk gate must value the order using the same price the executor gated on."* No
mechanism has been selected; that is an owner ruling.

This policy is written so that it is **necessary under every outcome of that ruling** (§2.3): whichever
mechanism carries the price of record, `SIP_LIVE` is the only bounded-age, entitlement-explicit trusted
source the platform will have for the roles the cache can legitimately play — and the bound must be
governed before any of them is implemented.

---

## 2. Q1 — Which Strategy 9 decisions require `SIP_LIVE`

### 2.1 Decision inventory

| # | Decision | Component | Price today | Needs `SIP_LIVE`? |
|---|---|---|---|---|
| D1 | Cross-asset quote gate (age ≤ 10 s, half-spread ≤ 25 bps, drift ≤ 1.5 %) | v13 executor, direct `feed=sip` request | SIP mid, executor-owned | **No** — already SIP, already governed, not via the cache |
| D2 | Single-stock trade reference (age ≤ 300 s) → 50 bps collar → `limit_price` | v13 executor, direct `feed=iex` request | IEX trade | **No** — explicitly IEX by sealed scope note; changing it is its own approval |
| D3 | `max_position_notional` valuation of an exposure-**increasing** order | `RiskEngine._reference_price` | equity: `limit_price` (D2's price) · cross-asset: unbounded IEX cached close or `None` | **Yes, cross-asset sleeve** — this is the gap |
| D4 | Gross-exposure pending-notional estimate | `RiskEngine._estimate_notional` | same chain, fail-open | Benefits; not required by this policy (fail-open ruling is ADR 0040/0055's, revisited only in Mechanism C) |
| D5 | Buying-power check, MARKET order | `BuyingPowerChecker` | IEX cached close, fail-open to 0 | **Yes, once Mechanism C makes it fail-closed** — same reference, same bound as D3 |
| D6 | Portfolio sizing (`investable × weight`) at decision time | strategy template | latest daily close bar | **No** — a `SIP_EOD` question (trading-day tolerance), out of scope here |
| D7 | Exposure-**reducing** orders (Stage A exits) at D3/D5 | RiskEngine | exempt / fail-open | **No** — §5 |

**Conclusion.** Strategy 9's `SIP_LIVE` demand is the set of **cross-asset ETF symbols for which an
exposure-increasing order may be evaluated during the rebalance**, plus — after Mechanism C — the same
set for the buying-power check. Reasons on the lease: `PENDING_ENTRY` (a planned add) and `HELD` (an
existing position whose incremental add is being valued). `PENDING_EXIT` is not demanded (§5).
`SELECTION_UNIVERSE` is unrepresentable on LIVE by construction (B3).

Demand is **stage-scoped and short-lived**: Stage B lasts ≤ 45 min once a week; the lease should be
published when the manifest is armed and withdrawn/expired when the stage completes. Outside that
window Strategy 9 has no LIVE demand, and the plane correctly reports `NO DEMAND`.

### 2.2 Why the equity sleeve is excluded

For single-stock orders `limit_price` is first in the ADR 0055 chain, so the risk engine already values
the order at the executor's gated price (age ≤ 300 s by the sealed rule). Adding a `SIP_LIVE` demand for
~40 equity names would (i) add load without changing any decision, and (ii) create the exact
divergence WP3 warns about — a second, independently timed price beside the one the executor gated on.
If the owner later rules that equity orders should *also* be corroborated by the cache, that is a
separate registration with its own bound (policy alternative P-D provides for it).

### 2.3 The role of the cache — must be ruled before the number means anything

| Role | What `SIP_LIVE` is at D3/D5 | Implied bound logic | Compatible with WP3 (c) rejection? |
|---|---|---|---|
| **R1 — price of record** | The risk engine values cross-asset orders *on the cache*; the executor's gated price is not transmitted | Bound must be **as tight as the executor gate it stands beside** (≤ 10 s), otherwise the risk engine and the executor gate on different prices | **No** — this is mechanism (c), which WP3 rejected; listed for completeness |
| **R2 — corroboration** | Executor transmits its gated `reference_price` (mechanism (a)); the risk engine **checks** it against the cache: `|reference − cache| / cache ≤ tolerance`, cache age within bound | Bound must be tight enough that the comparison is meaningful (a 5-minute-old comparator cannot corroborate a 10-second gate): ≤ 10 s for cross-asset | Yes |
| **R3 — bounded fallback** | Executor transmits `reference_price`; the cache is consulted **only when the request carries no `limit_price` and no `reference_price`** (a manual/other-source order, or a defect) | Bound is a *risk-policy* age for a last-resort reference, not an execution gate: the sealed 300 s reference rule is the natural anchor | Yes |

The B3 lease carries **one** `max_age_s` per consumer per profile. R2 and R3 can coexist only if the
bound satisfies both (i.e., the tighter one) or if Strategy 9 registers two consumers (§4.3, P-D).

---

## 3. Q2 — Where in the order/risk path the trusted reference is required

`OrderRouter._submit_inner` (`app/orders/router.py:156-374`): account load → typed-ticker confirmation
(MANUAL+LIVE) → per-strategy cooldown → LIVE guard → adapter resolution → whole-share rounding →
**`RiskEngine.evaluate` (`router.py:255`)** → persist `PENDING_RISK → PENDING_SUBMIT` → broker submit.
The router touches no market data; pricing is entirely inside `RiskEngine.evaluate`.

Therefore the reference must satisfy the bound **at the instant `RiskEngine.evaluate` runs**, measured
on the risk engine's clock. Three consequences the implementation must honour:

1. **Not at lease publication.** A lease admitted at 10:39 ET says nothing about a quote's age at
   10:52 ET. The B1 `SipConsumerApi` read is per call, with the bound applied to `source_timestamp`
   against the injected clock.
2. **Not at the executor's gate.** The executor gated the price ≤ 10 s / ≤ 300 s before *submission*;
   the risk engine evaluates milliseconds after submission in the normal path, so the two are nearly
   coincident — but they are two readings, and only the risk engine's reading is governed here.
3. **Per order, per symbol.** A rebalance is ~50 orders paced 1 s apart across up to 45 min per stage.
   The bound is evaluated for each order's symbol as it arrives; plane-level readiness is context, not
   the per-order verdict (§9, INCOMPLETE).

---

## 4. Q3 / §7 — The maximum permitted age, derived from Strategy 9's mechanics

### 4.1 What staleness actually costs at D3 (order-of-magnitude, not S9 fill evidence)

A stale reference mis-values the order by roughly the return over the age. Using the diffusion
approximation σ_age ≈ σ_annual × √(age / 5,896,800 s) (252 sessions × 6.5 h):

| age | σ_annual = 20 % (broad ETF) | σ_annual = 40 % (commodity / momentum single name) |
|---|---|---|
| 10 s | 0.026 % | 0.052 % |
| 30 s | 0.045 % | 0.090 % |
| 60 s | 0.064 % | 0.128 % |
| 300 s | 0.143 % | 0.286 % |

Two-sigma at 300 s is ≈ 0.3–0.6 %. The rebalance fires ~70 min after the open, where intraday
volatility is above the daily average; a 1.5–2× uplift keeps every entry under 1 %. Compare the
tolerances Strategy 9 already accepts around the same price: a 50 bps collar and a 1.5 % drift gate.

**Reading:** at every candidate bound the valuation error is small against the cap decision it feeds.
Valuation accuracy therefore does **not** discriminate between 10 s and 300 s. What discriminates is
**coherence** (does the risk engine see the price the executor gated on, or a materially different
one?) and **liveness** (how quickly does a broken plane stop the consumer?). Both point at the sealed
executor gates as the only non-arbitrary anchors.

⚠ This table is a derivation, not evidence from Strategy 9 fills. The v13 executor instruments
`broker_to_platform_terminality_lag` and `fill_ingestion_lag` (`v13_execution_core_v3.py:269-286`),
but the recorded values live in S3/host evidence, not in the repository, and were not read for this
proposal (§14).

### 4.2 Why no single number can be justified from evidence alone

The two sleeves are governed at **10 s** and **300 s** for the *same kind of decision* (a trusted
reference before an order), and the owner has ruled the 300 s figure is doing its job. Any single
platform-wide number either contradicts one sealed gate or invents a third figure. That is precisely
the "unmotivated constant" the contract refused to write (§6 line 300). So this proposal offers
alternatives anchored in those sealed values, with consequences, and asks for a ruling (§7 of the
owner's brief).

### 4.3 Policy alternatives

| ID | Bound | Anchor | Consequences |
|---|---|---|---|
| **P-A** | **10 s**, single consumer `strategy:9`, all LIVE demand | The cross-asset sleeve's sealed `max_quote_age_seconds` — the tightest gate Strategy 9 already lives under | Coherent with D1 for every cross-asset order; conservative default (CLAUDE.md). Plane cadence `clamp(5 s, floor, ceiling)` for ≤ 9–15 symbols during Stage B only; producer floor must be ≤ 5 s (`BOUND_BELOW_PRODUCER_FLOOR` otherwise — a *plane* readiness fact, never a reason to loosen the bound). Any plane hiccup > 10 s ⇒ `STALE` ⇒ increasing cross-asset orders refused ⇒ residual ⇒ continuation policy may halt the stage. **That is a data-plane-induced halt, and it is the intended fail-closed behaviour**; the remedy is plane liveness, not a looser bound. |
| **P-B** | 30 s | The cross-asset transient re-poll **wall-clock horizon** | **⛔ REJECTED by this proposal.** The sealed text says the horizon is never an allowed age (`:101`, `:179`). Adopting it as an age would invert a ruling the executor already enforces. Listed so it cannot be adopted by accident. |
| **P-C** | **300 s**, single consumer | The single-stock sleeve's sealed `max_trade_age_seconds`, owner-affirmed 2026-08-21 | Defensible **only for role R3** (bounded last-resort reference): valuation error ≤ ~0.6 % (2σ); cadence 60 s (ceiling-clamped); minimal load. **Under R1/R2 it is incoherent**: the risk engine may value a cross-asset order on a price up to 290 s older than the one the executor gated at ≤ 10 s — the WP3 divergence. Does not extend the 300 s rule; reuses it for a different decision (state this explicitly in the ruling so it is not read as the forbidden "extending the 300s threshold"). |
| **P-D** | **Sleeve-specific: 10 s for cross-asset ETF symbols, 300 s for single-stock symbols** | Mirrors the sealed limits one-for-one | Highest fidelity; no invented number; each symbol's bound equals the gate already applied to it. Requires either two registrations (`strategy:9-cross-asset`, `strategy:9-equity` — both `strategy_id = 9`; `validate_artifact` permits it) or a per-symbol-class policy artifact; B3's union already takes the per-symbol strictest. Equity registration exists only if the owner wants R2 corroboration for equities (§2.2); otherwise P-D degenerates to P-A with a documented reason. |

**Recommendation (not a selection).** P-D is the only alternative that neither invents a number nor
contradicts a sealed gate. If the owner prefers one consumer and one number, **P-A** is the
conservative default and is coherent under every role. **P-C is acceptable only if the owner rules
role R3.** P-B must not be chosen. Whatever is ruled, the implementing `FreshnessPolicyProvider` must
read the value from a pinned artifact whose values are **tested equal to the sealed limits they
mirror**, so the number cannot drift from its anchor.

---

## 5. Q4 — Increasing versus reducing orders

**Reducing orders require no `SIP_LIVE` reference at the risk boundary.** ADR 0055 Decision 4 exempts
them from `POSITION_CAP_UNPRICED` (anti-stranding, ADR 0038), and the sealed limits classify Stage A
exits as *"risk-reducing; always allowed"* with no turnover cap. The executor's own D1/D2 gates still
apply to exits — those are executor requests, not cache reads, and are unchanged.

Therefore: Strategy 9 LIVE demand reasons are `PENDING_ENTRY` and `HELD` (valuing the *incremental*
leg of an add against the *existing* position — §7); **`PENDING_EXIT` is not demanded**. A future
ruling that reductions must also be freshly valued (e.g. for gross-exposure accounting) would add
`PENDING_EXIT` with the same bound; nothing here forecloses it.

---

## 6. Q5 — Market-order behaviour when no qualifying reference exists

For an exposure-increasing **MARKET** order with no `limit_price` and no `reference_price`:

| `SIP_LIVE` for the symbol | Proposed behaviour | Basis |
|---|---|---|
| `PASS` (age ≤ bound) | Value at the cached SIP reference; apply the cap | contract §10 |
| `STALE` / `ABSENT` / `INCOMPLETE`(symbol missing) / `ENTITLEMENT_FAIL` | **Refuse: `POSITION_CAP_UNPRICED`.** No fall-through to the IEX cached close for a declared consumer. | contract §10 "no implicit fallback to IEX"; ADR 0055 Decision 3 |

**Q5a — the decision the owner must take:** today the chain's last link (`latest cached close`) *would*
supply an unbounded-age IEX price. Contract §10 says a declaring consumer has no implicit IEX
fallback. This proposal recommends that **for a registered `SIP_LIVE` consumer, the cached-close link
is not an acceptable trusted reference for exposure-increasing orders** — it has no age bound and no
entitlement identity. Consequence: during a plane outage Strategy 9's cross-asset adds are refused
where today they would pass on a stale bar. That is the intended direction of ADR 0055's
re-evaluation trigger (*"explicit source/freshness semantics"*, lines 174-176).

Alternative for adjudication: keep the cached-close link but **give it an age bound equal to this
policy's bound** (the bar's `t` is available and currently discarded). That closes the 48-hour hole for
every strategy, not only Strategy 9, but keeps an IEX price in a SIP consumer's path and so contradicts
§10 unless registered as an explicit fallback. Either way the executor's own no-market-fallback rule is
untouched: a refused order becomes a residual, and the continuation policy decides.

---

## 7. Q6 — Limit orders: limit price present, current valuation stale or missing

ADR 0055 values the whole order at `limit_price` (first link). Mechanism C recorded
`ADR0055-LIMIT-REFERENCE-EXPOSURE-001`: for an order that *adds to* a held position, valuing the
**existing** shares at the order's limit mis-states exposure (a resting BUY limit below market
understates it). The repair proposed in #726 is a two-leg `ExposureValuation`: incremental leg at
`limit_price`, existing leg at a trusted **market** reference.

This policy's contribution is the freshness rule for the existing-position leg:

| Existing-leg reference | Proposed rule |
|---|---|
| `SIP_LIVE` `PASS` for the symbol | use it |
| `SIP_LIVE` not `PASS` | **Alternative L1 (recommended, conservative):** fail closed for the cap check on the incremental leg — same consequence as §6. **Alternative L2:** value the existing leg at the last `SIP_EOD` `PASS` close (bounded error = one session's move; the cap is on the total, so a day's drift on the held leg is an accepted approximation), incremental leg at `limit_price`. **Alternative L3 (status quo, defective):** value both legs at `limit_price`. |

L2 is the only place this proposal contemplates a non-LIVE reference, and only for the *held* leg —
because that leg is a position that already exists and whose staleness cannot create a new order. It
must be an explicit ruling; absent one, L1 applies. Note this interacts with Mechanism C Q2
("fresh-open limit") and belongs in the ADR 0055 amendment, not in B3.

---

## 8. Q7 — Interaction with ADR 0055 fail-open / fail-closed rules

| ADR 0055 boundary | Today | Under this policy (Strategy 9 as declared consumer) |
|---|---|---|
| `max_position_notional`, increasing | fail-closed on `None` | **unchanged in direction; stricter in source**: `STALE`/`ABSENT`/`ENTITLEMENT_FAIL` are treated as `None`; no IEX cached-close fall-through (§6, Q5a) |
| `max_position_notional`, reducing | exempt | unchanged (§5) |
| Gross-exposure estimate | fail-open (ADR 0040) | **unchanged by this policy.** Whether a declared consumer's unpriced order should still contribute 0 is a Mechanism C / ADR 0055 amendment question. Where a `PASS` reference exists it is used, which only improves the estimate. |
| Buying-power, MARKET | fail-open to 0 (`buying_power.py:105`) | Mechanism C `ADR0055-MARKET-BUYING-POWER-UNPRICED-001` says fail closed. When it does, **the same reference and the same bound apply** — one price of record per order (ADR 0055's own principle), so the checker must consume `_reference_price`, not its own fetch. |

Nothing here reopens the fail-open ruling at the gross-exposure boundary; it is named so the owner can
see the boundary is untouched.

---

## 9. Q8 — Behaviour on `STALE` / `ABSENT` / `INCOMPLETE` / `ENTITLEMENT_FAIL`

Contract §9/§10 already fix the consumer obligation: fail closed on anything but `PASS`. What this
policy adds is the **Strategy 9 consequence** and the **operator reading** for each, and one
per-symbol nuance.

| State (per profile `SIP_LIVE`) | Strategy 9 consequence at D3/D5 | Operator reading | Never do |
|---|---|---|---|
| `STALE` (age > bound) | increasing cross-asset order refused `POSITION_CAP_UNPRICED`; residual; continuation policy decides | plane liveness problem (producer cadence, rate limit, transport) — check `SIP_ACQUISITION_FAILURE` and cadence | loosen the bound; re-submit as manual to "get it through" |
| `ABSENT` (store unavailable) | as `STALE` | infrastructure | fall back to IEX bar cache |
| `INCOMPLETE` (coverage < 1.0) | **per-symbol**: a symbol whose own record is `PASS` is valued; a symbol with no fresh record is refused. Plane-level `INCOMPLETE` is surfaced in the audit transition but does not by itself refuse symbols that are fresh. | which symbols are missing (`SIP_DEMAND_SERVED.missing`) | treat plane `INCOMPLETE` as blanket refusal (over-halts) **or** as blanket pass (under-protects) |
| `ENTITLEMENT_FAIL` | plane-wide latch; every increasing cross-asset order refused until a subsequent successful **designated-producer** request | account 7 SIP entitlement; producer identity | substitute a credential; rotate account 7 "to test"; read the MDQ archive |

**Q8a for adjudication — the `INCOMPLETE` nuance is Mechanism C Q3.** The alternative (strict
plane-level: any `INCOMPLETE` refuses every LIVE-valued order) is simpler and stricter but would halt a
whole stage because one illiquid symbol's quote lagged. This proposal recommends the per-symbol
reading because the decision the bound protects (§3) is per order, per symbol — but it is a ruling.

---

## 10. Q9 — Fixed or profile-specific

**Fixed per strategy version and per sleeve; not profile-specific.** Strategy 9 has no risk-profile
tiers — `RiskProfile` (`app/strategies/risk_profiles.py`) is the momentum vol-target dial for
strategies 4/5 and does not apply. The bound follows the *instrument class's sealed gate*, which is a
property of the execution design, not of a user preference. A change to the bound is a change to the
execution design: new policy version → new `freshness_policy_ref` → registry artifact re-applied →
re-registration, and (if the anchor moves) a new sealed limits version first. It is not a settings
knob and must never appear in `Settings` (B3's structural test forbids it).

---

## 11. Q10 — Exact authority and version owning the value

| Layer | Owner |
|---|---|
| **The number and its semantics** | **This document at v1.0**, after owner ruling on §13, under identity `strategy9-sip-live-freshness-policy@v1.0`. Anchors (P-A/P-C/P-D) are the sealed limits `v13_frozen_execution_limits_v8.json` at `85e45984`; if that file is superseded, this policy is re-issued, not silently re-read. |
| **Machine-readable value** | A pinned artifact `apps/backend/config/sip_freshness_policies.v1.json` (proposed) mapping `policy_ref → {symbol_class → max_age_s}` with the anchor citation per entry; sha256 pinned in the registry apply record. A contract test asserts each value **equals** the sealed-limits value it mirrors. |
| **Runtime seam** | A `FreshnessPolicyProvider` implementation that resolves `freshness_policy_ref` **only** from that artifact; unknown ref or version ⇒ `None` ⇒ `FRESHNESS_UNBOUND`. It never reads `Settings`, never computes a value, never inherits another consumer's bound. |
| **Registration** | `config/sip_consumer_registry.v1.json` entry for `strategy:9` (or the two P-D entries) carrying `freshness_policy_ref = strategy9-sip-live-freshness-policy@v1.0` and governed caps (B3 Decision 2 — caps are a separate owner value, also absent today). |
| **Change control** | New value ⇒ new policy version ⇒ new artifact entry ⇒ owner ruling ⇒ registry re-apply. The B3 registry audits the apply (`SIP_CONSUMER_GRANT_ISSUED` with artifact sha). |

Until v1.0 exists: **B3 continues to refuse Strategy 9 LIVE demand with `FRESHNESS_UNBOUND`**, and no
`FreshnessPolicyProvider` other than `NoFreshnessPolicy` may exist under `app/` (structural test).

---

## 12. Relationship to Mechanism C and the WP3 mechanism ruling

- **Mechanism C (#726) stays design-only.** This policy supplies the freshness input Mechanism C needs
  for `ADR0055-LIMIT-REFERENCE-EXPOSURE-001` (existing-leg reference, §7) and
  `ADR0055-MARKET-BUYING-POWER-UNPRICED-001` (§8). Mechanism C may move to implementation review only
  after this policy is ruled *and* ADR 0055 is amended.
- **WP3 mechanism (a)/(b)/(c)** decides *what carries the executor's price*. This policy decides *what
  the cache must satisfy in whatever role it is given* (§2.3). Ruling R2 or R3 here presupposes
  mechanism (a) or (b) delivers the price of record; ruling R1 would re-open WP3's rejection of (c) and
  should not be made implicitly through a freshness number.
- **`SIP_EOD`** for D6 (sizing on daily closes) is a separate declaration with trading-day tolerance and
  is not addressed here.

---

## 13. Decisions requested from the owner

| # | Decision | Alternatives | Proposal's recommendation |
|---|---|---|---|
| R1 | Role of `SIP_LIVE` at the Strategy 9 risk boundary (§2.3) | R1 price-of-record · R2 corroboration · R3 bounded fallback | R2 or R3 (both consistent with WP3); R1 only with an explicit reversal of WP3's (c) rejection |
| R2 | The bound (§4.3) | P-A 10 s · P-C 300 s (R3 only) · P-D sleeve-specific · ~~P-B 30 s~~ | P-D; else P-A. P-B rejected. |
| R3 | Reducing orders exempt from `SIP_LIVE` requirement (§5) | exempt · not exempt | exempt (ADR 0055 D4 / Stage A rule) |
| R4 | Cached IEX close as a reference for a declared consumer's increasing orders (§6, Q5a) | removed for declared consumers · retained with an age bound · retained as-is | removed for declared consumers |
| R5 | Existing-leg valuation when `SIP_LIVE` not `PASS` (§7) | L1 fail closed · L2 `SIP_EOD` close · L3 status quo | L1; L2 only by explicit ruling |
| R6 | `INCOMPLETE` semantics (§9, Q8a = Mechanism C Q3) | per-symbol · strict plane-level | per-symbol |
| R7 | Authority artifact form (§11) | pinned JSON artifact + contract test · value embedded in policy doc only | pinned artifact, values tested equal to the sealed anchor |

A ruling on R1 and R2 is sufficient to issue v1.0 and unblock the first Strategy 9 LIVE registration
design (still no activation authority). R3–R7 may be ruled with the ADR 0055 amendment.

---

## 14. Evidence gaps (stated, not papered over)

- No Strategy 9 **fill-latency distribution** was read; the v13 telemetry values are in S3/host
  evidence, not in Git. §4.1 is a diffusion approximation.
- Account 7's configured `max_position_notional` and gross-exposure limits were **not read** for this
  proposal; the headroom argument in §4.1 is generic. Reading them is a box query, out of scope for a
  policy draft.
- No measured **SIP quote-age distribution** from the designated producer exists: the B2 one-shot harness
  is merged but its `--execute` path is self-refusing and has not run in production. P-A's feasibility
  (sustained ≤ 5 s cadence) is therefore asserted from Alpaca's published batch-quote capability, not
  measured.
- The WP3 evaluation cited in §1.4 is **uncustodied**. If it is superseded, §2.3 must be re-read.

---

## 15. What this document does not authorize

No Strategy 9 activation, `/start`, reload, or order. No registry entry for `strategy:9`. No
`FreshnessPolicyProvider` beyond `NoFreshnessPolicy`. No RiskEngine or `buying_power.py` change. No
SIP cache enablement (`sip_cache_enabled` stays `False`). No change to the sealed executor limits. No
change to the 300-second stale-reference rule. Custody of this document grants none of the above.
