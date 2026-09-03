# Strategy 9 — `SIP_LIVE` freshness execution policy (v1.0, OWNER ADJUDICATED)

| Field | Value |
|---|---|
| Status | **OWNER ADJUDICATED R1–R7 (2026-09-02) — POLICY v1.0.** Becomes the governing freshness policy for Strategy 9 `SIP_LIVE` demand when this document is merged to `main`; its SHA-256 is then the custody identity. |
| Identity | **`strategy9-sip-live-freshness-policy@v1.0`** — the exact string a B3 `freshness_policy_ref` names (B3 Decision 3). |
| Predecessor | `Strategy9_SIP_LIVE_Freshness_Execution_Policy_v0.1.md` (proposal; sha256 `1b774078f46af5cc24cf3d130f8a2514926a78725388b42c72a573810e4d6dd1`, 34,992 B). **Not mutated**; remains in custody beside this file. All derivations, evidence tables and alternatives live there; this document records the ruling and binds the answers. |
| Governs | The `SIP_LIVE` maximum age Strategy 9 may declare on a demand lease, per symbol class; the role of that reference at each consuming decision; the fail-closed behaviour on every non-`PASS` state; the authority artifact the runtime may read the value from. |
| Does **not** govern | The SIP cache refresh cadence (B3 derives cadence *from* this bound). The executor's own sealed gates (`v13_frozen_execution_limits_v8.json`) — untouched. Strategy 9 activation, PAPER restoration, orders, Account 6 credential action. |
| Anchors | Sealed limits `85e45984:ops/acct7/v13/v13_frozen_execution_limits_v8.json` — `max_quote_age_seconds: 10` (cross-asset ETF sleeve), `max_trade_age_seconds: 300` (single-stock sleeve). **No freshness number is invented by this policy.** |
| Depends on | SIP-CACHE-001 contract v1.0.1 §6/§9/§10/§12 · B3 design v0.1 (#725, `3ef19db8`) · B3 implementation (#728, `c402d5c0`) · Mechanism C matrix v0.1 (#726, `6a7f6bdd`) · ADR 0055 · ADR 0049 · v0.1 of this policy |

---

## 1. Ruling record (owner, 2026-09-02 — verbatim)

```
#729 R1 = R2 CORROBORATION
#729 R2 = P-D SLEEVE-SPECIFIC
          CROSS-ASSET = 10s
          SINGLE-STOCK = 300s, ONLY WHERE R2 CORROBORATION IS REQUIRED
#729 R3 = REDUCING ORDERS EXEMPT
#729 R4 = IEX CLOSE FALLBACK REMOVED FOR DECLARED CONSUMERS
#729 R5 = L1 FAIL CLOSED
#729 R6 = INCOMPLETE PER-SYMBOL
#729 R7 = PINNED JSON ARTIFACT + CONTRACT TEST

#729 = OWNER POLICY ADJUDICATED R1–R7 / READY FOR v1.0 CUSTODY
```

Owner reasoning recorded with each ruling (paraphrase is avoided where the owner's wording is load-bearing):

| # | Ruling | Owner's stated basis |
|---|---|---|
| R1 | **R2 corroboration.** `SIP_LIVE` is the trusted *corroborating* market-data source at the Strategy 9 risk boundary. The executor continues to transmit its already-gated `reference_price`; the RiskEngine compares that value against fresh SIP. | R1 price-of-record is **rejected** because it reverses WP3 (c). R3 fallback is **not selected** as the normal Strategy 9 mechanism. R2 remains consistent with WP3 while requiring a comparator no older than the existing cross-asset gate. |
| R2 | **P-D sleeve-specific.** 10 s for cross-asset ETF symbols; 300 s for single-stock symbols; each exactly mirrors its already-sealed execution limit. Implemented through distinct governed consumer/profile semantics where necessary; B3 already resolves the strictest per-symbol demand. | Preferable to collapsing two different execution contracts into one arbitrary number. **Qualification:** the 300-second equity registration exists **only where R2 corroboration is actually required for that equity path**. Do not create a 300-second LIVE consumer merely to make P-D symmetrical; P-D may degenerate to P-A where the equity corroboration consumer is unnecessary. |
| R3 | **Reducing orders exempt.** `PENDING_EXIT` stays outside Strategy 9 LIVE demand. | Preserves ADR 0055 D4 / Stage-A semantics rather than allowing market-data degradation to prevent risk reduction. |
| R4 | **IEX close fallback removed for declared consumers.** | Once an increasing order is governed by this policy, the cached IEX close is not an acceptable fallback reference. `STALE`, `ABSENT`, `INCOMPLETE`, `ENTITLEMENT_FAIL` must refuse rather than silently cross trust planes. |
| R5 | **L1 fail closed.** When the required `SIP_LIVE` valuation is not `PASS`, the incremental position-cap check fails closed. The L2 `SIP_EOD` exception is **not authorized**. | R3 already preserves the ability to reduce risk; there is no corresponding need to weaken valuation for increasing exposure. |
| R6 | **`INCOMPLETE` per-symbol.** An `INCOMPLETE` plane does not poison otherwise valid symbols; each requested symbol is evaluated against its own governed record. A fresh `PASS` symbol proceeds; the affected symbol refuses. | Prevents one lagging/illiquid symbol from halting an entire stage while remaining fail-closed for the symbol whose evidence is deficient. |
| R7 | **Pinned JSON artifact + contract test.** `sip_freshness_policies.v1.json`, governed identity `strategy9-sip-live-freshness-policy@v1.0`, hash bound in the registry apply record. Runtime resolves the policy only from that artifact — no `Settings` fallback, no inheritance from another consumer, no infrastructure default. Contract tests prove the values equal their sealed anchors. | — |

P-B (30 s) remains **rejected**: the sealed text defines 30 s as a re-poll *horizon*, never an allowed data age (v0.1 §4.3).

---

## 2. The bound (R2, bound to symbol class)

| Symbol class | `max_age_s` | Sealed anchor (field, value) | Registrable at v1.0? |
|---|---|---|---|
| `cross_asset_etf` — the 9-ETF `cross_asset_tsmom` sleeve (ADR 0049) | **10** | `max_quote_age_seconds: 10` | **Yes** — this is Strategy 9's actual LIVE demand (v0.1 §2.1 D3/D5, cross-asset sleeve). |
| `single_stock` — the top-40 PIT momentum equity sleeve | **300** | `max_trade_age_seconds: 300` | **Only where R2 corroboration is required for the equity path**, by a separate owner ruling naming that need. At v1.0 no such need is ruled: the equity sleeve already carries `limit_price` first in the ADR 0055 chain (v0.1 §2.2), so **no `single_stock` LIVE consumer may be registered**. The value is bound here so that, if such a ruling comes, no new number is invented. |

Semantics of the bound (unchanged from v0.1 §0, §3): the maximum elapsed time between a quote's exchange `source_timestamp` and the instant `RiskEngine.evaluate` reads it, measured on the risk engine's injected clock; per order, per symbol; never at lease publication, never at the executor's gate, never from `received_at_utc`.

This binding **does not extend, reuse for a new purpose, or otherwise alter** the 300-second stale-reference rule at the executor; the executor's regime is untouched. The 300 s value here is the same sealed limit read for the same instrument class.

---

## 3. The ten questions, bound

| Q | Question (owner brief §6) | Bound answer |
|---|---|---|
| Q1 | Which Strategy 9 decisions require `SIP_LIVE` | **D3** (`max_position_notional` valuation of an exposure-*increasing* order) for cross-asset ETF symbols, and **D5** (buying-power check, MARKET order) for the same symbols once Mechanism C makes it fail-closed. D1/D2 (executor gates) are already governed and not via the cache. D6 (sizing) is a `SIP_EOD` question, out of scope. D7 (reducing) exempt (R3). Lease reasons: `PENDING_ENTRY`, `HELD`. Demand is stage-scoped (Stage B, ≤ 45 min weekly); outside it the plane correctly reports `NO DEMAND`. |
| Q2 | Where in the order/risk path the trusted reference is required | Inside `RiskEngine.evaluate` (`OrderRouter._submit_inner` → `RiskEngine.evaluate`), at the instant of evaluation, on the risk engine's clock. The reference's **role** is corroboration (R1): the executor's transmitted `reference_price` is the price of record; `SIP_LIVE` corroborates it (`|reference − sip| / sip ≤ tolerance`, sip age ≤ bound). The corroboration tolerance is a Mechanism C / ADR 0055 amendment parameter, not a freshness value, and is not set here. |
| Q3 | Maximum permitted age | Per §2: `cross_asset_etf` 10 s; `single_stock` 300 s (registrable only under the R2 qualification). |
| Q4 | Increasing vs reducing | Increasing orders: governed by this policy. Reducing orders: **exempt** (R3); `PENDING_EXIT` is not demanded. |
| Q5 | MARKET order with no qualifying reference | With R1 = corroboration, a Strategy 9 cross-asset MARKET order carries the executor's `reference_price`; if `SIP_LIVE` for the symbol is not `PASS` the corroboration cannot be performed ⇒ **refuse `POSITION_CAP_UNPRICED`** (contract §10; ADR 0055 D3). **No fall-through to the IEX cached close** (R4). A refused order becomes a residual; the executor's own no-market-fallback rule and continuation policy are untouched. |
| Q6 | LIMIT order, limit price present, valuation stale/missing | Incremental leg at `limit_price` (ADR 0055 first link) subject to the two-leg repair `ADR0055-LIMIT-REFERENCE-EXPOSURE-001` (Mechanism C). Existing-leg reference: `SIP_LIVE` `PASS` ⇒ use it; not `PASS` ⇒ **L1 fail closed** for the cap check on the incremental leg (R5). L2 (`SIP_EOD` close) **not authorized**; L3 (status quo) is the recorded defect. |
| Q7 | Interaction with ADR 0055 fail-open / fail-closed | `max_position_notional` increasing: fail-closed, **stricter in source** (`STALE`/`ABSENT`/`INCOMPLETE`(symbol)/`ENTITLEMENT_FAIL` ≡ `None`; no IEX fall-through). Reducing: exempt. Gross-exposure estimate: **unchanged** by this policy (ADR 0040 fail-open stands until the ADR 0055 amendment rules otherwise). Buying-power MARKET: when Mechanism C makes it fail-closed (`ADR0055-MARKET-BUYING-POWER-UNPRICED-001`), it consumes the **same reference and the same bound** — one price of record per order. |
| Q8 | `STALE` / `ABSENT` / `INCOMPLETE` / `ENTITLEMENT_FAIL` | `STALE`: refuse the symbol's increasing order; plane-liveness problem; never loosen the bound. `ABSENT`: as `STALE`; never fall back to the IEX bar cache. `INCOMPLETE`: **per-symbol** (R6) — a symbol whose own record is `PASS` is valued, a symbol with no fresh record is refused; plane-level `INCOMPLETE` is surfaced in the audit transition but does not by itself refuse fresh symbols. `ENTITLEMENT_FAIL`: plane-wide latch (B3); every increasing cross-asset order refused until a subsequent successful designated-producer request; never substitute a credential. |
| Q9 | Fixed or profile-specific | **Fixed per strategy version and per symbol class; not profile-specific.** `RiskProfile` does not apply to Strategy 9. A change is a change to the execution design: new policy version → new `freshness_policy_ref` → artifact re-applied → re-registration; if the sealed anchor moves, a new sealed-limits version first. Never a `Settings` knob (B3 structural test). |
| Q10 | Exact authority/version owning the value | **This document at v1.0** under identity `strategy9-sip-live-freshness-policy@v1.0`, anchored to `85e45984:…/v13_frozen_execution_limits_v8.json`; machine-readable in `apps/backend/config/sip_freshness_policies.v1.json` (§4) whose sha256 is bound in the B3 registry apply record. If the sealed limits file is superseded, this policy is re-issued, not silently re-read. |

---

## 4. Authority artifact (R7) — specification for the implementing PR

**File:** `apps/backend/config/sip_freshness_policies.v1.json` (versioned artifact; a new value is a new policy version and a new entry, never an edit in place).

**Shape (normative):**

```json
{
  "schema_version": 1,
  "policies": {
    "strategy9-sip-live-freshness-policy@v1.0": {
      "policy_doc": "docs/design/SIP-CACHE-001/Strategy9_SIP_LIVE_Freshness_Execution_Policy_v1_0.md",
      "anchor": {
        "path": "ops/acct7/v13/v13_frozen_execution_limits_v8.json",
        "commit": "85e45984"
      },
      "role": "R2_CORROBORATION",
      "symbol_classes": {
        "cross_asset_etf": { "max_age_s": 10,  "anchor_field": "max_quote_age_seconds" },
        "single_stock":    { "max_age_s": 300, "anchor_field": "max_trade_age_seconds",
                             "registration_condition": "ONLY WHERE R2 CORROBORATION IS REQUIRED — separate owner ruling" }
      },
      "reducing_orders": "EXEMPT",
      "iex_close_fallback": "REMOVED",
      "existing_leg_not_pass": "L1_FAIL_CLOSED",
      "incomplete": "PER_SYMBOL"
    }
  }
}
```

**Contract tests the implementing PR must ship (each must be able to fail):**

1. Every `max_age_s` **equals** the named `anchor_field` value in the sealed limits file at the pinned commit (read from the custodied copy, compared as integers; a drift in either direction fails).
2. The artifact's sha256 is the one bound in the B3 registry apply record for any `strategy:9` registration; mismatch ⇒ registration invalid.
3. The production `FreshnessPolicyProvider` resolves a `freshness_policy_ref` **only** from this artifact: unknown ref, unknown version, or unknown symbol class ⇒ `None` ⇒ `FRESHNESS_UNBOUND`. It never reads `Settings`, never computes a value, never inherits another consumer's bound (extends B3's existing structural test `test_no_platform_level_live_freshness_fallback_exists`).
4. A `single_stock` registration for Strategy 9 is **refused** unless the registry entry carries an explicit owner-ruling reference for the equity corroboration need (the R2 qualification, enforced, not remembered).
5. `PENDING_EXIT` on a Strategy 9 LIVE lease is rejected at validation (R3, enforced).

---

## 5. What this ruling now permits, and what it still does not

**Permitted after this document is custodied at exact head (design / implement / qualify — not operate):**

- Mechanism C implementation review against this frozen policy: the two-leg `ExposureValuation` (`ADR0055-LIMIT-REFERENCE-EXPOSURE-001`), the fail-closed buying-power path (`ADR0055-MARKET-BUYING-POWER-UNPRICED-001`), the R2 corroboration check, the R4/R5/R6 semantics, and the ADR 0055 amendment that carries them. RiskEngine changes remain Tier 3 with ≥ 2 h walk-away and their own exact-head merge authority.
- Strategy 9 B3 consumer registration **design and implementation**: the `strategy:9` (`cross_asset_etf`) registry entry with `freshness_policy_ref = strategy9-sip-live-freshness-policy@v1.0`, governed caps (B3 Decision 2 — a separate owner value), and the `FreshnessPolicyProvider` of §4. Applying the registry to a live database is an operator act under the B3 apply script and its own authority.
- The two lanes the owner named may run in parallel: (A) Mechanism C + Strategy 9 registration against this policy; (B) Strategy-Factory result-blind census work under the lifecycle model v1.0. Neither blocks the other.

**Still not granted by this document or its custody:**

- **No Strategy 9 activation, `/start`, reload, or order.** Activation/restoration stays serialized behind Strategy 9's readiness gates and a separate owner authority.
- **No PAPER restoration authority.**
- **No order authority.**
- **No Account 6 credential action.**
- No SIP cache enablement (`sip_cache_enabled` stays `False`); no scheduled acquisition.
- No change to the sealed executor limits or to the 300-second stale-reference rule.
- No `single_stock` LIVE consumer (R2 qualification).

---

## 6. Custody

- v0.1 (proposal) and v1.0 (this ruling) are custodied together in the same PR; v0.1 is not mutated.
- This document's SHA-256 at merge is its custody identity and is what `policy_doc` in the artifact refers to. The custody/acceptance facts (merge SHA, file hash) are recorded outside this file in the program memory / custody notes, per the lifecycle model's convention.
- Change control: any change to a bound, a role, or a Q-answer is a new version (`@v1.1`, `@v2.0`), a new artifact entry, an owner ruling, and a registry re-apply.
