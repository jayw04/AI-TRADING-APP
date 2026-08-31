# SIP-CACHE-001 — Operational SIP Data Plane: Design & Implementation Contract

  ----------------------------------------------------------------------------------------------------------
  Field                               Value
  ----------------------------------- ----------------------------------------------------------------------
  **Document version**                **v1.0 — initial governed contract**

  **Status**                          **DESIGN / IMPLEMENTATION CONTRACT — READY FOR CUSTODY / OWNER
                                      ACCEPTANCE.** This document grants no deployment, activation,
                                      order, or strategy authority. Every operational gate remains
                                      explicit and is named in §3 and §18.

  **Disposition**                     **CREATE / REQUIRED DATA ENABLER** (owner ruling 2026-08-31).
                                      This is not a qualification exercise: the operational SIP plane
                                      was measured and does not exist. See §2.

  **Canonical repository path**       `docs/design/SIP-CACHE-001/TradingWorkbench_SIP-CACHE-001_Design_and_Implementation_Contract_v1.0.md`

  **Repository**                      `github.com/jayw04/AI-TRADING-APP`

  **Discovery basis**                 SIP-CACHE-001 read-only qualification executed **2026-08-31**
                                      against the live `ec2-paper` runtime and `origin/main`. All
                                      measurements in §2 are dated point-in-time observations, not
                                      continuously maintained assertions. Re-measure before relying
                                      on any of them.

  **Governing predecessors**          ATP v1.0.3 (`AlgoTraderPlus_v1_4_1_ImplementationPlan_v1_0_3.md`,
                                      SHA-256 `10043a1bc6e8aafecca9dfd46c0547b75fe6eaf763506d31dca9a8189de95605`)
                                      — §6.3, §9.1, §9.2, §9.3, §12. ADR 0055 (position cap requires a
                                      trusted reference price). ADR 0003 (credential encryption at rest).
                                      ADR 0002 (single OrderRouter).

  **Authority hierarchy**             Frozen registrations / sealed evidence / accepted ADRs / explicit
                                      owner rulings > this contract > subordinate task lists. Successful
                                      implementation, a green CI run, a deployed cache, or a PASS
                                      readiness evaluation **never** grants live mutation, consumer
                                      integration, or strategy activation by implication.
  ----------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 0. Frozen rulings

These are recorded as owner rulings of 2026-08-31 and are not reopened by implementation work.

| Ruling | Value |
|---|---|
| `SIP-CACHE-001 DISPOSITION` | **CREATE / REQUIRED DATA ENABLER** |
| `ATP-SIP-RETENTION` | **RETAIN / REQUIRED DATA ENABLER** |
| `MDQ SIP EVIDENCE PLANE` | **UNCHANGED / NOT A LIVE CONSUMER STORE** |
| `SIP OPERATIONAL PLANE` | **DOES NOT EXIST / IMPLEMENTATION REQUIRED** |
| `LIVE MARKET-DATA CONSUMERS` | **CURRENTLY EXPLICIT IEX** |
| `IMPLICIT FEED SELECTION` | **PROHIBITED / EXISTING CI CONTROL RETAINED** |
| `ADR0055 REFERENCE-PRICE SOURCE` | **CURRENTLY IEX VIA BAR CACHE** |
| `SIP_LIVE` | **CANDIDATE TRUSTED REFERENCE-PRICE SOURCE / NOT YET IMPLEMENTED OR AUTHORIZED FOR STRATEGY USE** |
| `SIP_EOD` | **SEPARATE DAILY DATA PRODUCT / NOT INTERCHANGEABLE WITH SIP_LIVE** |

Tracked findings carried by this contract:

| Finding | Status |
|---|---|
| `RESEARCH-PLANE-ISOLATION-CI-001` | **KNOWN / PROPERTY CURRENTLY HOLDS / LOAD-BEARING CHECKERS ABSENT / REPAIR REQUIRED BEFORE SIP LIVE-CONSUMER INTEGRATION** (§14) |
| `MARKET-PROJECTION-SIP-READER-001` | **EXISTING NON-MDQ SIP CONSUMER / TRAINING-ONLY CLAIM / ENTITLEMENT & FRESHNESS ASSUMPTIONS REQUIRE QUALIFICATION** (§15) |

------------------------------------------------------------------------

## 1. Purpose and economic/strategy consumer

The platform holds one Algo Trader Plus (SIP) entitlement. It is consumed today **only** by the
MDQ-001 Phase-A research collector, which produces immutable governed evidence. No operational
surface exists through which a strategy or risk gate can obtain SIP data.

The economic justification for retention, under ATP v1.0.3 §6.3 clause 1, is that a strategy expected
to trade requires SIP to avoid the known **IEX stub/spread false-reject class** — the failure mode in
which a stub bid on the IEX feed produces an implausible quoted spread and a gate refuses or
mis-values an order that is in fact ordinarily liquid.

The named prospective consumer is the **Strategy-9 execution path** and the **ADR 0055 reference-price
chain**, which today resolves through an IEX-fed cache (§2, §12). This contract builds the data plane
that would make a governed SIP dependency expressible. **It does not integrate that consumer, and it
does not authorize Strategy-9 activation** (§18).

`SIP_EOD` additionally serves daily signal/ranking generation. It is a separate product with separate
semantics and is never a substitute for a current execution quote.

------------------------------------------------------------------------

## 2. Current measured state

All observations dated **2026-08-31**, read-only, against live `ec2-paper` (`i-084f47fe4e69192e9`) and
`origin/main`. Point-in-time evidence only.

### 2.1 Entitlement identity

Discriminating SIP latest-quote probe executed inside the backend container. Keys identified by
`sha256(key)[:12]`; **no secret material was rendered or recorded**.

| Credential | Key fp | Broker account | SIP | IEX |
|---|---|---|---|---|
| `ALPACA_PAPER_` (unnumbered) | `246b05e74804` | `PA3QRX9KSPXA` | **403** | 200 |
| **`ALPACA_PAPER_6`** | **`b56421a28128`** | **`PA3BGKRLH2AP`** | **200** | 200 |

The 403 body is explicit: `subscription does not permit querying recent SIP data`.

`PA3BGKRLH2AP` is **workbench account 7 / user 7** (`combined-book@globalcomplyai.com`). Note the
`.env` offset trap: `ALPACA_PAPER_<n>_*` maps to workbench account `n+1`; `ALPACA_PAPER_7_*` is the
WSS canary and maps to **no** workbench account. **Never resolve an account from a credential variable
name** — fingerprint the key or read the broker's self-reported `account_number`.

Corroboration: all **14** sealed MDQ manifests carry `account_number = PA3BGKRLH2AP`,
`credential_fingerprint = b56421a28128`, `entitlement = "algo_trader_plus (account-7 login)"`, with
zero variance; and today's sampler logged `acquisition identity verified: account PA3BGKRLH2AP,
fp b56421a28128` at 09:25:03 EDT.

**Measurement gap, stated explicitly:** only those two credentials exist in the backend container
environment. Accounts 2–6 hold theirs Fernet-encrypted in `user_credentials` (ADR 0003) and were
**not** probed. Their non-entitlement is inferred from ATP §12 (a second subscription is not
authorized) and from the 2026-08-15 exclusivity probe — **inference, not measurement**.

### 2.2 The operational SIP plane does not exist

- **No SIP cache store of any kind.** No SIP-named store outside the MDQ archive; no quote or price
  table in the application database (only `market_projection_training_rows`,
  `market_projection_model_registry`).
- **No producer and no schedule.** The only SIP producer is the MDQ Phase-A collector. Its timers are
  `mdq-sample` 09:25, `mdq-eod` 16:30, `mdq-freeze` 16:45 EDT. There is no SIP cache timer.
- **Every live consumer is hard-pinned to `DataFeed.IEX`**, verified in the *deployed* container, not
  only in the repository:

  | Module | Line |
  |---|---|
  | `app/api/v1/market_data.py` | 77 |
  | `app/market_data/quotes.py` | 51 |
  | `app/market_data/bar_cache.py` | 428 |
  | `app/services/benchmark_snapshot.py` | 50 |
  | `app/services/bar_stream_adapter_alpaca.py` | 43 |

  `bar_stream_adapter_alpaca.py` carries the standing note that moving that stream to SIP is a
  governed migration, *not* a configuration flip.

- **The real bar cache is `/app/bars_cache`** — configuration `bars_cache_root = "bars_cache"`,
  `bars_cache_max_gb = 5.0`; **not** under `/opt/workbench/data/`. Parquet, append-only per day/month
  file, LRU eviction that never touches files modified in the last 24 hours. Observed 2.5 MB across
  roughly 15 symbols, live (5-minute partitions written 15:55 EDT). **IEX-fed.**

### 2.3 The MDQ archive boundary is currently respected

ATP v1.0.3 §12 forbids *"Direct live-consumer reads from the immutable MDQ archive"* (verbatim).
Verified: **no** module outside `app/research/` imports `app.research.capture` or
`app.research.mdq_eval`, and the order path imports neither. The property **holds today** — see §14
for why it holds by convention rather than by enforcement.

### 2.4 Governed MDQ corpus (evidence plane, unchanged)

Seven sealed/admitted partitions: `2026-08-19, 08-20, 08-21, 08-25, 08-26, 08-27, 08-28`. `2026-08-24`
is the sole lost trading day in that interval. The `2026-08-31` partition was open and sampling at
time of observation; a partition is FROZEN only when `manifest.json` is present.

------------------------------------------------------------------------

## 3. Authority and non-authority boundaries

**This contract authorizes:** design custody; implementation of a local operational SIP cache, its
producer, its readiness evaluator, and their tests; and the proofs enumerated in §19 up to and
excluding consumer integration.

**This contract does not authorize** — see §18 for the full enumeration — any change to the MDQ
collector, any credential switching, any consumer integration, any Strategy-9 activation, or any order
authority.

A successful cache deployment is **not** activation authority. Consumer integration is a **separate
review** (§19), and Strategy-9 integration is a **separate WP3 decision** taken after it.

------------------------------------------------------------------------

## 4. Two-plane architecture

The single entitlement feeds two planes that must never merge.

```
                         ┌─────────────────────────────────────────────┐
   Alpaca SIP            │  EVIDENCE PLANE  (exists, unchanged)        │
   (account 7,      ────▶│  MDQ Phase-A collector → sealed partitions  │
    fp b56421a28128)     │  immutable · frozen manifest identity tuple │
        │                │  consumers: K calculators (read-only)       │
        │                └─────────────────────────────────────────────┘
        │                                    ╳  no live-consumer read (ATP §12)
        │                ┌─────────────────────────────────────────────┐
        └───────────────▶│  OPERATIONAL PLANE  (does not exist)        │
                         │  explicit SIP fetcher → local cache →       │
                         │  readiness evaluator → governed consumer    │
                         └─────────────────────────────────────────────┘
```

The target topology is:

`Alpaca SIP → explicit SIP fetcher → local operational cache → SIP readiness evaluator → governed strategy consumer`

and explicitly **not**:

`MDQ immutable archive → live strategy`

The two planes share an entitlement and a credential identity. They share **nothing else** — not
storage, not schedule, not admissibility semantics, not mutability. The evidence plane is sealed and
adjudicated; the operational plane is refreshed and disposable. A defect in the operational plane must
never be repaired by reading the evidence plane, and a gap in the evidence plane must never be repaired
from the operational cache.

------------------------------------------------------------------------

## 5. SIP_EOD contract

**Definition.** A snapshot of the last *completed* trading day, derived from explicit `feed=sip`
requests, refreshed after the close.

**Intended consumers.** Daily signal generation, ranking, and features that are computed once per
session boundary and consumed on the following session.

**Readiness basis.** Expected completed trading date present, plus required symbol coverage. Freshness
for `SIP_EOD` is expressed in *trading days*, never in seconds.

**Trading-date semantics.** The expected date is the most recent completed session on the authoritative
market calendar. Weekend and holiday handling must derive from that calendar — never from wall-clock
arithmetic, and never from "yesterday". A missing Saturday is not a gap.

**Prohibition.** `SIP_EOD` is never a current execution quote (§18). A consumer requiring a current
price must declare `SIP_LIVE` and satisfy its readiness independently.

------------------------------------------------------------------------

## 6. SIP_LIVE contract

**Definition.** Current-session quote/reference data obtained from explicit `feed=sip` requests, with
a bounded maximum age.

**Intended consumer.** Order-time spread and reference-price validation — the ADR 0055 boundary (§12).

**Maximum age is deliberately NOT frozen in this document.** The bound is consumer-specific and must
be chosen by the actual Strategy-9 execution policy, then registered per consumer (§10). Writing a
number such as 15 s or 60 s here before that policy exists would freeze an unmotivated constant into a
governing artifact and invite the "a number written in a document becomes a fixed point" failure. The
schema and evaluator **must** carry the bound as a per-consumer parameter from the first commit; only
its *value* is deferred.

**Freshness is measured from `source_timestamp`**, the exchange/provider timestamp — never from
`received_at_utc`, and never from job completion. A job that ran successfully proves nothing about the
age of the data it fetched.

------------------------------------------------------------------------

## 7. Cache schema and provenance

Every cached observation is individually attributable. **No secret material is stored** — credential
identity is recorded as a fingerprint only.

| Field | Requirement |
|---|---|
| `symbol` | required |
| `feed` | required, literal `sip`. Never inferred, never defaulted. |
| `source_feed_identity` | required — the feed the provider reports having served, recorded independently of what was requested, so a silent server-side substitution is detectable |
| `source_timestamp` | required — provider/exchange timestamp; the sole basis for freshness |
| `received_at_utc` | required — local acquisition timestamp; diagnostic only |
| `price` / `bid` / `ask` / sizes | as applicable to the record type |
| `trading_date` / `session` | required |
| `provider` | required, literal `alpaca` |
| `entitlement_identity` | required — stable identifier of the entitlement in force |
| `credential_identity_fingerprint` | required — `sha256(key)[:12]` of the credential that actually possessed the SIP entitlement at acquisition. **Never the key or secret itself.** |
| `cache_schema_version` | required |
| `quality_classification` | recommended — freshness/quality band assigned at write time |

`source_feed_identity` and `entitlement_identity` are the two fields added on owner instruction. They
exist so that a record can never be silently misattributed: a record claiming `feed = sip` whose
`source_feed_identity` disagrees is a defect that must surface, not a value that is quietly accepted.

------------------------------------------------------------------------

## 8. Producer and scheduling contract

- The producer is a **new, dedicated** component. It is **not** the MDQ collector, does not share its
  code path, and does not write into the MDQ capture root.
- Every request states `feed=sip` explicitly (§13).
- `SIP_EOD` refreshes after the close on completed trading days only.
- `SIP_LIVE` refreshes on a cadence consistent with the strictest registered consumer bound (§6),
  during regular hours.
- A failed refresh **degrades readiness** (§9). It never falls back to IEX, never substitutes a
  credential, and never reads the MDQ archive to fill the gap (§18).
- The producer must not run on the developer laptop against live infrastructure; the runtime is AWS.

------------------------------------------------------------------------

## 9. Readiness state machine and freshness semantics

`SIP-CACHE-READINESS` is evaluated **per profile** (`SIP_EOD`, `SIP_LIVE`). The state set is shared;
the policies are not.

| State | Meaning |
|---|---|
| `PASS` | Expected trading date present; SIP entitlement probe succeeds; data age within the profile's tolerance; required symbol coverage satisfied. |
| `STALE` | Previous trading date only, or `source_timestamp` outside tolerance. |
| `INCOMPLETE` | Expected date present but coverage below requirement. |
| `ENTITLEMENT_FAIL` | An explicit SIP request fails because access is unavailable. |
| `ABSENT` | Cache or data store unavailable. |

Policy differences:

- **`SIP_EOD`** — tolerance expressed in trading days against the authoritative calendar; coverage
  measured against the declared symbol set.
- **`SIP_LIVE`** — tolerance expressed as a strict maximum age from `source_timestamp`, parameterized
  per consumer, value deferred per §6.

A single global readiness verdict is **prohibited**. A `PASS` on `SIP_EOD` says nothing about
`SIP_LIVE` and must never be read as though it did.

Success is **not** "the scheduled job ran". A job that completes while returning stale or partial data
is `STALE` or `INCOMPLETE`, not `PASS`. The evaluator must be capable of returning a non-`PASS` state
on real inputs; a readiness check that cannot fail proves nothing.

------------------------------------------------------------------------

## 10. Consumer declaration and fail-closed rules

- A consumer requiring SIP declares `requires_sip = true` **and** the profile it depends on
  (`SIP_EOD` or `SIP_LIVE`), and for `SIP_LIVE` its maximum acceptable age.
- Such a consumer **fails closed on anything except `PASS`** for its declared profile.
- **No implicit fallback to IEX.** A consumer that may legitimately proceed on IEX must have that
  fallback explicitly designed, registered, and governed for that consumer — including what it means
  economically for that strategy to trade on IEX. Absent such a registration, readiness failure stops
  the consumer.
- Declaration is per consumer, not global. One consumer's registered fallback never extends to another.

------------------------------------------------------------------------

## 11. Credential rotation and entitlement handling

The SIP entitlement, the MDQ acquisition identity, the Strategy-9 broker binding, and (after
implementation) operational cache access all resolve today through **account 7**. A rotation therefore
touches four things at once. This is a real operational risk and is **not** to be solved by credential
switching.

Prospective rotation procedure:

1. Pre-rotation entitlement verification.
2. Controlled rotation.
3. Record the exact new credential fingerprint.
4. SIP entitlement re-verification against the new fingerprint.
5. Cache readiness verification.
6. MDQ identity treatment **under its own governance rules** — the capture identity tuple is part of
   the frozen manifest governance surface.

If a rotation splits a governed MDQ corpus, **preserve that truth**. Do not substitute credentials to
manufacture continuity. ATP §12 forbids credential switching to recover a failed MDQ slot, and this
contract extends the same prohibition to cache acquisition (§18).

------------------------------------------------------------------------

## 12. ADR-0055 reference-price integration boundary

ADR 0055 resolves the per-share price for gates that must value an unfilled order through a single
chain: `limit_price → reference_price (>0) → latest cached close (>0) → None`. Historical cost is
deliberately excluded. Missing price is fail-open inside gross exposure (ADR 0040 preserved) and
**fail-closed** for `max_position_notional` when the order increases exposure
(`POSITION_CAP_UNPRICED`), with reducing orders exempt.

**Measured today:** `latest cached close` resolves through `/app/bars_cache`, which is **IEX-fed**.
The trusted reference price the position cap depends on is therefore IEX-sourced.

ADR 0055's own re-evaluation triggers already name the remedy — the caller-side `reference_price`
plumbing it *deliberately deferred*, "with explicit source/freshness semantics". `SIP_LIVE` is the
candidate for that source.

**Boundary:** this contract builds the data plane only. Supplying `SIP_LIVE` into
`RiskEngine._reference_price` is a **consumer integration**, gated behind §19's separate review, and
would additionally require deciding whether a SIP-sourced reference price changes the fail-closed
semantics of `POSITION_CAP_UNPRICED`. A future gate that needs to value an unfilled order adopts the
existing `_reference_price()` chain rather than inventing a fourth valuation.

------------------------------------------------------------------------

## 13. Existing feed-pinning CI control — referenced, not duplicated

`apps/backend/scripts/check_marketdata_feed_pinning.sh` is a **pre-existing control**, wired at
`.github/workflows/ci.yml:382`. It AST-checks that every Alpaca data request/stream constructor in the
scanned trees receives an explicit, non-`None` `feed=`, and forbids environment-driven feed defaults
(the retired `ALPACA_DATA_FEED` knob).

Its stated rationale is precisely the hazard this contract must not reintroduce: *a subscription
entitlement (Algo Trader Plus) can silently switch an implicit IEX path to SIP with no code change.*

This proves one major SIP hazard is **already enforced**: entitlement alone cannot change feed
semantics, because no governed constructor is permitted to omit the feed. The check deliberately does
not care *which* feed is named — that is a governance question, which is what §5, §6 and §10 answer.

**Do not duplicate this control.** Cite it. The SIP-CACHE-001 deliverable "proof that SIP and IEX
cannot be selected implicitly" is discharged by this existing check plus the schema's
`source_feed_identity` field (§7), which catches server-side substitution the AST check cannot see.

------------------------------------------------------------------------

## 14. Research-plane isolation dependency

`RESEARCH-PLANE-ISOLATION-CI-001` = **KNOWN / PROPERTY CURRENTLY HOLDS / LOAD-BEARING CHECKERS ABSENT
/ REPAIR REQUIRED BEFORE SIP LIVE-CONSUMER INTEGRATION**

The MDQ archive boundary (§2.3) currently holds **by architecture and convention**, not by
enforcement. The two checkers named in `CLAUDE.md` among the load-bearing CI invariants —
`check_research_plane_order_path_isolation.sh` and `check_research_plane_no_broker_capability.sh` —
**do not exist in the repository**.

Measured explanation, 2026-08-31:

- The ADR that specifies them, *"ADR 0051 — Platform planes, the evidence→allocation authority
  boundary, and research-plane capability limits"*, is **untracked local work**, not merged to `main`.
  It *proposes* both checkers as future work (generalizing the existing
  `check_altdata_order_path_isolation.sh`); it does not record them as built.
- `origin/main` carries a **different** ADR under the same number: *"ADR 0051 — Shared factor
  adjudication and the readiness coverage gate"*. This is an unresolved **ADR-number collision**, and
  a governance item in its own right.
- The absence is already recorded independently at
  `deploy/aws/manifests/factor_repair_b94838b6.json:25` — *"does not exist at b94838b6. Recorded as
  UNAVAILABLE AT TARGET / NOT A DEPLOYMENT GATE FOR THIS EPOCH; no replacement checker was invented"* —
  and in the LOW-PIT registration dependency map. This is a known gap, not a new discovery.

**Scope ruling:** the enforcement repair is **not** bundled into SIP-CACHE-001. It is recorded here as
a dependency. **Repair is required before SIP live-consumer integration** (§19 step 7), because that
step introduces a new operational data plane adjacent to a boundary currently protected only by
convention. Implementation and proof of the cache itself may proceed without it.

------------------------------------------------------------------------

## 15. Market-projection SIP-reader disposition

`MARKET-PROJECTION-SIP-READER-001` = **EXISTING NON-MDQ SIP CONSUMER / TRAINING-ONLY CLAIM /
ENTITLEMENT & FRESHNESS ASSUMPTIONS REQUIRE QUALIFICATION**

`app/services/market_projection/dataset.py` issues `feed=DataFeed.SIP` at lines 104 and 135. It is the
**only** SIP reader outside `app/research/`. Its docstring asserts training-only use — live inference
is IEX, reconciled by a 30-day train/serve diagnostic, with persistence in a research script so that
"nothing here touches a request path". It nevertheless resides in `app/services/`, outside any enforced
research-plane boundary (§14).

It also hardcodes `SIP_RECENT_MARGIN_MIN = 16`, documented as compensating for a **free-plan**
15-minute SIP historical delay.

**This is recorded as a finding, not adjudicated as a defect.** Two questions must be resolved before
it is permitted to share the new cache:

1. Is its persisted/training data actually intended to be operational SIP data, or is it a
   training-only artifact that should remain separate?
2. Does the 16-minute delayed-SIP assumption remain correct under the ATP entitlement?

**Do not simply remove that margin** because today's account-7 credential has recent SIP access. First
determine **which credential and which job actually produce that dataset**, and **what contract the
existing training data assumes**. If the dataset was built through a credential that is now
unentitled, its provenance — not merely its margin constant — is the open question.

------------------------------------------------------------------------

## 16. Persistence, restart, and recovery

- The cache survives process restart. Readiness after restart is **recomputed from stored
  `source_timestamp` values**, never assumed from the presence of files or from a previously recorded
  verdict.
- A restart never promotes a stale cache to `PASS`.
- Recovery from a failed refresh is a **subsequent refresh**, not backfill from the MDQ archive, not a
  credential substitution, and not a relaxed tolerance.
- Eviction and retention policy must be explicit and must not silently delete data a registered
  consumer still depends on.
- Cache corruption or unavailability is `ABSENT`, which is a fail-closed state for any declaring
  consumer (§10).

------------------------------------------------------------------------

## 17. Tests and observability

Tests must include, at minimum:

- Each readiness state reachable on realistic inputs — including a constructed `ENTITLEMENT_FAIL` and
  a constructed `STALE`. **A readiness test that cannot fail is not evidence.** For every test, state
  what input would make it fail.
- Profile independence: `SIP_EOD` `PASS` while `SIP_LIVE` is `STALE`, and the converse.
- Fail-closed behavior for a declaring consumer on each non-`PASS` state.
- Absence of implicit fallback: a SIP readiness failure never yields IEX data to a `requires_sip`
  consumer.
- Provenance completeness: no record persists without `feed`, `source_feed_identity`,
  `source_timestamp`, `entitlement_identity`, and `credential_identity_fingerprint`.
- Restart persistence: readiness recomputed, not inherited.
- Boundary test: the cache path performs no read of the MDQ capture root.

Observability: readiness state per profile, age distribution against tolerance, coverage against the
declared symbol set, entitlement probe outcome, and the credential fingerprint in force. Logs and
evidence records must never expose credentials or secrets.

------------------------------------------------------------------------

## 18. Explicit non-authorizations

This contract explicitly forbids:

- **No fallback from SIP to IEX** merely because SIP readiness fails.
- **No reads from immutable MDQ partitions by live consumers.**
- **No mutation of the MDQ collector**, its `capture_modes`, channels, schedule, universe, credential,
  or manifest identity tuple.
- **No credential switching** to rescue cache acquisition — or a failed MDQ slot.
- **No assumption that ATP entitlement changes feed semantics.** Entitlement is access, not meaning.
- **No Strategy-9 activation or order authority** arising from implementing the cache.
- **No treating `SIP_EOD` as a current execution quote.**

Additionally not authorized by this document: a second Algo Trader Plus subscription; any MDQ order or
broker capability; adding SIP `s`/`l` (halt/LULD) channels to the governed collector; and any
relaxation of universe, credential, readiness, or evidence semantics to make a criterion pass.

------------------------------------------------------------------------

## 19. Implementation and acceptance sequence

Each step completes before the next begins. **The sequence stops before Strategy-9 integration.**

1. **Design custody** — this contract merged.
2. **Implementation** — producer, cache, readiness evaluator.
3. **Tests** — §17, all green, with falsifiability stated.
4. **Scheduled refresh proof** — unattended refresh observed on a real trading day.
5. **Cache persistence / restart proof** — readiness correctly recomputed after restart.
6. **SIP readiness proof** — each state demonstrated, including a **controlled** `ENTITLEMENT_FAIL`
   proof that does **not** revoke, rotate, corrupt, or otherwise disturb the production SIP
   entitlement. A credential that is legitimately unentitled already returns the provider's
   entitlement failure — the unnumbered credential's measured `403 "subscription does not permit
   querying recent SIP data"` (§2.1) is real-world evidence of exactly that response, obtained while
   the entitled account-7 credential remained untouched. **"Demonstrated" never licenses breaking the
   live entitlement to exercise the state machine.** This aligns step 6 with §17, which asks for a
   constructed `ENTITLEMENT_FAIL` in tests.
7. **Separate consumer-integration review** — gated on `RESEARCH-PLANE-ISOLATION-CI-001` repair (§14).
8. **Separate Strategy-9 WP3 decision** — not implied by any of the above.

A successful step 4–6 proves the data plane works. It does **not** constitute authority to execute
step 7, and step 7 does not constitute authority to execute step 8. This ordering exists specifically
so that a successful cache deployment cannot become accidental activation authority.

------------------------------------------------------------------------

## 20. Open items carried by this contract

| Item | Status |
|---|---|
| `SIP_LIVE` maximum age value | **DEFERRED** — set by Strategy-9 execution policy (§6) |
| `RESEARCH-PLANE-ISOLATION-CI-001` | **OPEN** — repair required before step 7 (§14) |
| ADR 0051 number collision | **OPEN** — two different ADRs share the number (§14) |
| `MARKET-PROJECTION-SIP-READER-001` | **OPEN** — two qualification questions (§15) |
| Accounts 2–6 SIP entitlement | **UNMEASURED** — inferred only (§2.1) |
| Declared symbol set / coverage requirement per profile | **OPEN** — set at implementation |

------------------------------------------------------------------------
