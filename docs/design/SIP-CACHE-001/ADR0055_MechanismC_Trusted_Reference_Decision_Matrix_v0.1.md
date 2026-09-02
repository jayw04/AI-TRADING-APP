# ADR 0055 Mechanism C — trusted-reference resolver: call path, decision matrix, and test matrix (v0.1)

| Field | Value |
|---|---|
| Status | **DESIGN ACCEPTED (owner rulings 2026-09-02) — NO RiskEngine IMPLEMENTATION AUTHORIZED** |
| Date | 2026-09-01 (drafted) · 2026-09-02 (rulings incorporated) |
| Blocked on | (1) Strategy 9's governed `SIP_LIVE` maximum execution-reference age — **this document does not invent that number**; (2) repair of the two defects in §5 (`ADR0055-LIMIT-REFERENCE-EXPOSURE-001`, `ADR0055-MARKET-BUYING-POWER-UNPRICED-001`) via ADR 0055 amendment |
| Governing inputs | ADR 0055, ADR 0040, ADR 0038, SIP-CACHE-001 v1.0.1 §6, §10, §12; owner Rulings 6 and 7 (2026-09-01); the limit-price distinction (2026-09-01); Mechanism C rulings 4A/4B and the test-matrix additions (2026-09-02) |
| Code measured | `app/risk/engine.py` (`_reference_price` L679, `_estimate_notional` L705, `_latest_close` L715, gate 7 L283–360, gate 8 L361–401, gate 12 L537), `app/risk/buying_power.py` L95–110, `app/risk/risk_effect.py` L455–470, `app/risk/types.py` `OrderRequest.reference_price` |
| Authority granted | **None.** |

---

## 0. Frozen trust chain

```
Strategy / order
  → OrderRequest                       (caller intent; reference_price = caller HINT, never trusted)
    → RiskEngine
      → TrustedReferenceResolver       (inside the risk boundary; the ONLY place "trusted" is assigned)
        → SipConsumerService           (B1 surface: no credential, feed, or clock is expressible)
          → SIP_LIVE PASS price        (usable price + provenance; any other state = no price)
```

Two permanent inequalities, each with a structural consequence:

| Inequality | Consequence in code |
|---|---|
| **caller `reference_price` ≠ trusted market reference** | `OrderRequest.reference_price` keeps its current meaning: a valuation *hint* for consumers that have no governed source. The resolver records it as `CALLER_HINT` and it can never carry the `TRUSTED` classification. No new caller-supplied trusted field is added (Ruling 6). |
| **limit price ≠ trusted current market valuation** | A limit price bounds *what this order can fill at*. It does not say what the shares already held are worth. Where a decision depends on current market exposure, a limit price may bound the incremental leg but cannot substitute for the market valuation of the existing position. Ruling 4A makes this a defect to repair, not a preference: **existing position → trusted current market reference; incremental BUY quantity → limit price only where the rule intentionally evaluates committed order notional at the limit. Never collapse the two into one reference.** |

Ruling 6 also fixes: **market orders are never converted to limit orders** to solve valuation.

The test invariant that spans every row below:

```
CALLER-SUPPLIED PRICE INFORMATION  ≠  TRUSTED MARKET VALUATION
```

---

## 1. Where the engine puts a number on an unfilled order today

| # | Decision path | Question it answers | Current source | Behaviour when no source resolves |
|---|---|---|---|---|
| P1 | Gate 7 — `max_position_notional`, order **increases** position | Will the *resulting position* exceed the cap at current value? | `_reference_price`: `limit_price → caller reference_price → bar-cache close (IEX) → None` | **Fail-closed** `POSITION_CAP_UNPRICED` (ADR 0055) |
| P2 | Gate 7 — order **reduces** position | (not valued) | — | Exempt by `increases_position` guard (ADR 0038 principle) |
| P3 | Gate 8 — gross exposure, incoming BUY notional | How much gross does this order add? | `_estimate_notional` = same chain × qty | **Fail-open** contributes 0 (ADR 0040 preserved by ADR 0055 §Decision 2) |
| P4 | Gate 8 — reducing SELL | (not valued) | — | Exempt (ADR 0038) |
| P5 | Stored `Order.estimated_notional` → pending-BUY sum in later gate-8 evaluations | What in-flight exposure is already committed? | Same chain at submission time | NULL contributes 0 |
| P6 | Gate 12 — pre-trade buying power (LIVE accounts only) | Worst-case cash required | LIMIT/STOP_LIMIT: `limit_price × qty`; STOP: `stop × qty × 1.02`; MARKET: bar-cache close × qty × 1.02 | **Fail-open** returns 0 (`buying_power.py:105`) — **`ADR0055-MARKET-BUYING-POWER-UNPRICED-001`**, §5 |
| P7 | Loss-control classification (`risk_effect.py`) | Is this a permitted reduction, and how big? | `action.price or pos.price` (held mark) — **not** the resolver | Classified from position + side first; price only quantifies a permitted reduction |

Measured fact carried from SIP-CACHE-001 §12: the "bar-cache close" tier is `/app/bars_cache`,
**IEX-fed**. The trusted reference the position cap depends on today is IEX-sourced.

---

## 2. Decision matrix — limit price vs trusted current market reference, per path

Legend for "limit price role": **BOUND** = valid as a conservative bound on the incremental leg only;
**VALID** = the check is about the order's own price and the limit is the right input; **NOT A
SUBSTITUTE** = must not stand in for market valuation.

| Path | Depends on current market exposure? | Limit price role | Trusted market reference required? | Mechanism C target | Non-PASS behaviour (increasing) | Reducing orders |
|---|---|---|---|---|---|---|
| **P1** position cap, increasing | **Yes** — values `resulting_qty` (existing + Δ) | **BOUND on Δ only.** BUY limit: fill ≤ limit ⇒ `Δ × limit` is a conservative upper bound for the new leg. SELL-to-open-short limit: fill ≥ limit ⇒ the limit is a *lower* bound and is **not** conservative. The existing shares are worth the market, not the limit. | **Yes** for the existing component whenever `current_qty ≠ 0` (Ruling 4A); for a fresh open (`current_qty = 0`, BUY limit) the limit alone is a conservative valuation of the whole resulting position | Resolver supplies `TRUSTED` market reference for declared consumers; valuation = `|existing| × trusted + |Δ| × max(trusted, limit)` for BUY; `|resulting| × trusted` for short-opening SELL | **Preserve fail-closed**: no `TRUSTED` value ⇒ `POSITION_CAP_UNPRICED` (Ruling 6). Fresh-open BUY limit with `current_qty = 0`: **owner decision Q2** (§6) | Untouched — exempt |
| **P2** position cap, reducing | No | n/a | No | None | n/a | Exempt stays exempt; resolver may *record* a reference for evidence, never gates |
| **P3** gross gate, incoming BUY | Partly — it is the *increment* that is valued; the aggregate comes from `Position.market_value` (broker sync), not the resolver | **VALID** for a BUY limit (fill ≤ limit ⇒ conservative upper bound on the increment) | Only for MARKET orders | Resolver supplies the MARKET-order value; limit orders unchanged | **Preserve fail-open** (ADR 0040 unchanged): unpriced increment contributes 0. Mechanism C does not alter this without an ADR 0040 amendment | Exempt |
| **P4** gross gate, reducing SELL | No | n/a | No | None | n/a | Exempt |
| **P5** stored `estimated_notional` | Same as P3 | Same as P3 | Same as P3 | Same value as P3, plus provenance columns (`reference_source`, `reference_age_s`) so a later audit can reconstruct what the gate saw | NULL contributes 0 (unchanged) | n/a |
| **P6** buying power (LIVE only) | Yes for MARKET | **VALID** — worst-case cash for a limit BUY *is* the limit | MARKET only | **Ruling 4B:** an exposure-increasing MARKET order with no trusted current price must **not** become zero economic cost — the repaired path fails closed under the buying-power rule. MARKET valuation moves onto the resolver in the same ADR 0055 amendment | Repaired: fail-closed (was fail-open) | Reducing orders keep their independently governed exemption where appropriate |
| **P7** loss-control quantification | Uses the held mark | Not consulted | Not via the resolver | None — ADR 0043 owns this path | n/a | Permitted reduction |

**The rows that change behaviour are P1 (source and valuation shape, per 4A), P5 (provenance), and
P6 (fail-open → fail-closed, per 4B).** P3 keeps ADR 0040's fail-open by design; changing it is a
different ADR.

---

## 3. Resolver design

```python
class ReferenceSource(StrEnum):
    SIP_LIVE = "sip_live"          # TRUSTED: SipDataView.state is PASS under the consumer's bound
    IEX_CLOSE = "iex_close"        # bar-cache close; NOT trusted for a requires_sip consumer
    CALLER_HINT = "caller_hint"    # OrderRequest.reference_price; never trusted
    LIMIT_BOUND = "limit_bound"    # limit price used as a bound on the incremental leg only

@dataclass(frozen=True)
class TrustedReference:
    price: Decimal
    source: ReferenceSource
    trusted: bool                  # True only for SIP_LIVE PASS
    source_timestamp: datetime | None
    age_s: float | None
    readiness_state: SipReadinessState | None   # the SIP verdict that produced it, for evidence
    bound_s: float | None          # the consumer's governed bound applied

@dataclass(frozen=True)
class ExposureValuation:
    """Ruling 4A: two quantities, never collapsed."""
    existing_leg: TrustedReference | None      # market valuation of shares already held
    incremental_leg: TrustedReference | None   # bound on the order's own leg (limit or trusted)

class TrustedReferenceResolver:
    def __init__(self, sip: SipConsumerService | None, bar_cache, *, policy: ReferencePolicyProvider): ...
    async def resolve(self, req: OrderRequest) -> TrustedReference | None
    async def value_resulting_position(self, req: OrderRequest, current_qty: Decimal) -> ExposureValuation
```

**Per-consumer policy, not global** (SIP-CACHE-001 §10). `ReferencePolicyProvider` maps the order's
origin (`source_type`, `source_id` → strategy id → B3 consumer registration) to:

| Consumer class | Policy | Chain the resolver runs |
|---|---|---|
| Registered `requires_sip` consumer (Strategy 9 once its bound exists) | `SIP_LIVE` only, bound resolved from the consumer's **governed execution policy** (the same `FreshnessPolicyProvider` seam B3 uses — the bound is never stated in infrastructure) | `SIP_LIVE PASS → TRUSTED`; any other state → `None` (no IEX fallback, no caller hint promotion) |
| Consumer registered with an **explicit, governed** IEX fallback | Declared per consumer with its economic rationale recorded | `SIP_LIVE PASS → TRUSTED`, else `IEX_CLOSE (untrusted)` |
| Unregistered consumer (manual orders, strategies without a SIP declaration) | Legacy | Existing chain unchanged: `limit → caller hint → IEX close → None` — classified `trusted = False` throughout |

The resolver **does not accept a bound from the caller**, a feed, a credential, an account, or a
clock: it reads the bound from the consumer's governed policy and the clock from the injected
`SipConsumerService` (B1 invariant carried into the risk boundary). Strategy 9's bound being absent
is the fail-closed state until its execution policy supplies it — the resolver returns `None` for
every increasing order from that consumer, which is `POSITION_CAP_UNPRICED`. That is the correct
behaviour for "no governed freshness value exists yet", and it is why nothing here can be implemented
today without either inventing the number or shipping a gate that refuses everything.

**Wiring.** `RiskEngine.__init__` gains an optional `reference_resolver`; `lifespan.py` constructs it
with the `SipConsumerService` built from the same session factory. `RiskEngine._reference_price` is
refactored to delegate, preserving its signature so every existing gate keeps one valuation source
(ADR 0055 re-evaluation trigger: "a future gate should adopt `_reference_price()` rather than invent a
fourth valuation"). Gate 7 additionally calls `value_resulting_position()` so the existing and
incremental legs are valued separately (4A).

**Evidence.** The `risk_checks` context for gates 7/8/12 records `reference_source`,
`reference_trusted`, `reference_age_s`, `readiness_state`, `bound_s`, and — for gate 7 — both legs of
the `ExposureValuation`. A future audit can then reconstruct whether a refusal was a cap breach, a
pricing outage, or a stale SIP plane — three different operator responses.

---

## 4. Test matrix (specified now; implemented with Mechanism C)

Fixture: a `requires_sip` consumer whose governed policy supplies bound **B** (a test value,
explicitly not a policy value), `current_qty = 100`, cap sized so a 50-share increase breaches at
price 100 but not at 90.

**Coverage grid** — every SIP state is demonstrated independently and crossed where applicable:

| State | increasing × MARKET | increasing × LIMIT | reducing × MARKET | reducing × LIMIT |
|---|---|---|---|---|
| `PASS` | T1 | T7, T10 | T6a | T6b |
| `STALE` | T2 | T8, T9 | T6a | T6b |
| `ABSENT` | T3 | T3b | T6a | T6b |
| `INCOMPLETE` | T4 | T4b | T6a | T6b |
| `ENTITLEMENT_FAIL` | T5 | T5b | T6a | T6b |

| # | Case | Order | Expected | The input that makes it fail |
|---|---|---|---|---|
| T1 | SIP `PASS` | increasing MARKET BUY 50 | valued at the SIP price; breach ⇒ `POSITION_CAP_NOTIONAL`; no breach ⇒ pass; evidence `source=sip_live trusted=True` | evidence shows `iex_close`, or the decision differs from the SIP-priced arithmetic |
| T2 | SIP `STALE` (age > B) | increasing MARKET BUY | `POSITION_CAP_UNPRICED`; **no IEX fallback consulted** (call recorder on `bar_cache.get_latest_bar` = 0) | a decision other than UNPRICED, or any bar-cache call |
| T3 / T3b | SIP `ABSENT` | increasing MARKET BUY / increasing LIMIT BUY with `current_qty = 100` | `POSITION_CAP_UNPRICED` (limit does not value the held 100) | same |
| T4 / T4b | SIP `INCOMPLETE` (plane coverage short, this symbol present) | increasing MARKET / LIMIT BUY | fail-closed ⇒ `POSITION_CAP_UNPRICED` — **owner decision Q3** whether a per-symbol PASS inside an INCOMPLETE plane is usable | acceptance without the ruling |
| T5 / T5b | SIP `ENTITLEMENT_FAIL` | increasing MARKET / LIMIT BUY | `POSITION_CAP_UNPRICED`; gate 8 still evaluates with increment 0 (ADR 0040 preserved) | gate 8 refuses on GROSS because of the missing price, or the order passes gate 7 |
| T6a / T6b | **every** non-PASS state | **reducing** SELL 40, MARKET / LIMIT | passes gate 7 (exempt) and gate 8 (reducing exempt); resolver may be called for evidence only — **"reducing order with missing market reference"** (owner item 5) | a refusal on either gate |
| T7 | SIP `PASS` | increasing **LIMIT** BUY 50 @ limit < market, `current_qty = 100` | `ExposureValuation.existing_leg` = trusted × 100; `incremental_leg` = `max(trusted, limit) × 50`; a limit below market cannot lower the resulting valuation — **"existing position + BUY limit below market"** (owner item 3, 4A) | held shares valued at the limit, or the two legs collapsed into one price |
| T8 | SIP `STALE` | increasing LIMIT BUY, `current_qty = 100` | `POSITION_CAP_UNPRICED` — the limit does not substitute for market valuation of held shares | the limit alone permits the order |
| T9 | SIP `STALE` | increasing LIMIT BUY, `current_qty = 0` (fresh open) | per **Q2**: either UNPRICED (strict) or valued at the limit (conservative bound) — test pins whichever the owner rules | the other behaviour |
| T10 | SIP `PASS` | LIMIT SELL-to-open-short | valued at trusted, not at the limit (limit is a lower bound for a short fill) | valuation at the limit |
| T11 | MARKET vs LIMIT | any | **no** order-type mutation anywhere in the router or engine (assert the broker adapter receives the submitted type) | a MARKET request reaching the adapter as LIMIT |
| T12 | caller supplies conflicting `reference_price` | SIP `PASS` at 100, caller hint 50, increasing MARKET BUY | gate values at 100; evidence records `caller_hint=50, source=sip_live` — **owner item 1** | the hint reaches the cap arithmetic |
| T13 | trusted reference `STALE`, caller supplies a fresh-looking hint | increasing MARKET BUY, hint timestamped "now" | `POSITION_CAP_UNPRICED` — the hint is never promoted to trusted for a `requires_sip` consumer regardless of how fresh it claims to be — **owner item 6** | the hint permits the order |
| T14 | strategy holds its own SIP-capable credential (acct 5/6 fingerprints from the census) | increasing MARKET BUY | resolver never calls `credentials_for_mode` for the order's account; `SipConsumerService` has no path to accept one (B1 L1 test re-asserted from the risk side); refusal is `POSITION_CAP_UNPRICED` if the plane is not PASS — the strategy's entitlement changes nothing — **owner item 2** | any pricing call bearing a non-designated fingerprint, or a decision that differs from T2 |
| T15 | bound not supplied by the governed policy | increasing MARKET BUY | `POSITION_CAP_UNPRICED` and a structured reason `FRESHNESS_UNBOUND` in evidence; no infrastructure default is consulted (`DEFAULT_LIVE_MAX_AGE_S` never read) | the placeholder constant is read, or the order passes |
| T16 | unregistered consumer (manual order) | increasing MARKET BUY | legacy chain, `trusted=False`, behaviour byte-identical to today's tests | any change to the 17 ADR 0055 tests' outcomes |
| T17 | evidence | any refusal | `risk_checks` context carries source/trusted/age/readiness/bound and both valuation legs | a refusal with no provenance |
| T18 | clock | any | no public path on the resolver or engine accepts a valuation time (L1 pattern) | a `now`/`as_of`/`clock` parameter on the public surface |
| T19 | **unpriced exposure-increasing MARKET order, buying-power path** (LIVE account) | MARKET BUY, no trusted price | fail-closed under the buying-power rule; required notional is never 0 — **owner item 4, 4B** | `BuyingPowerDecision.sufficient=True` with `required_notional=0` |
| T20 | reducing MARKET order, buying-power path, no trusted price | MARKET SELL covered by the long | retains the governed reducing exemption | a refusal of a covered reduction |

---

## 5. Defects recorded (owner rulings 2026-09-02)

### `ADR0055-LIMIT-REFERENCE-EXPOSURE-001`

```
= IDENTIFIED
= EXISTING POSITION VALUED USING ORDER LIMIT
= EXPOSURE UNDERSTATEMENT POSSIBLE
= REPAIR REQUIRED BEFORE MECHANISM-C ACTIVATION
```

Gate 7 values `resulting_qty` (held + incremental) at `_reference_price`, whose first tier is
`limit_price`. A resting BUY limit below market therefore values the **held** shares at the limit and
understates current exposure. Repair: `ExposureValuation` with two legs (§3); held shares always at the
trusted current market reference; the limit bounds only the incremental leg where the rule
intentionally evaluates committed order notional at the limit. This is a behaviour change beyond
source substitution and lands via ADR 0055 amendment.

### `ADR0055-MARKET-BUYING-POWER-UNPRICED-001`

```
= IDENTIFIED
= FAIL-OPEN
= REPAIR REQUIRED
```

`BuyingPowerChecker._estimate_worst_case_notional` returns `Decimal("0")` for a MARKET order when no
cached price resolves (`buying_power.py:105`, comment: "fail open"). LIVE accounts only, so dormant
today, but an exposure-increasing market order with no trusted valuation must not become zero
economic cost. Repair: route MARKET valuation through the resolver and fail closed under the
buying-power rule; reducing orders keep their governed exemption where appropriate. Same ADR 0055
amendment.

### Also noted, unchanged

The IEX-fed tier remains the only source for every consumer that is not SIP-registered. That is
correct under §10 (per-consumer declaration), but it means Mechanism C improves Strategy 9's gate
without touching the manual-order consequence ADR 0055 already records.

---

## 6. Decisions still open

- **Q1** Confirm the three consumer classes in §3 and that "explicit governed IEX fallback" is a
  per-consumer registration attribute with a recorded economic rationale, never a default.
- **Q2** Fresh-open BUY limit (`current_qty = 0`) under a non-PASS plane: strict UNPRICED, or valued
  at the limit as a conservative bound? Recommendation: **strict** for `requires_sip` consumers.
- **Q3** Is a per-symbol PASS inside an `INCOMPLETE` plane usable for that symbol? Recommendation:
  **no** for gate 7 (contract §10: fail closed on anything except PASS for the declared profile).

## 7. What remains blocked

**Everything in §3 and §4 is implementable only after (1) Strategy 9's execution policy freezes the
`SIP_LIVE` maximum age and (2) the ADR 0055 amendment carrying the two §5 repairs is custodied.** Until
then: no `RiskEngine` change, no Strategy 9 change, no resolver in production, and
`POSITION_CAP_UNPRICED` semantics remain exactly as ADR 0055 merged them. The design interval is used
to specify the repaired semantics exactly and to write the §4 tests prospectively.
