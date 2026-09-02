# SIP-CACHE-001 — Implementation B3: governed market-data demand provider and scheduler contract (v0.1)

| Field | Value |
|---|---|
| Status | **DESIGN ACCEPTED (owner rulings 2026-09-02) — IMPLEMENTATION AUTHORIZED, OPERATIONALLY INERT** |
| Date | 2026-09-01 (drafted) · 2026-09-02 (rulings incorporated) |
| Governing contract | `TradingWorkbench_SIP-CACHE-001_Design_and_Implementation_Contract_v1.0.1.md` (sha256 `385cf6a6…`, #716) — §5, §6, §8, §9, §10, §17, §18, §19 |
| Owner rulings applied | Ruling 5 (EOD/LIVE split), Ruling 8 (governed demand sets), the B3 correction (demand = current execution/decision need), the six hardened requirements (2026-09-01), **B3 Decisions 1–5 (2026-09-02)** |
| Depends on | Implementation A (#719, `c674753f`), B1 (#720, `980ceb74`), B2 (#722, `75ebb066`) — all merged, all inert (`sip_cache_enabled = False`) |
| Authority granted by this document | Implementation of the surface in §8, **disabled by default**. It grants no scheduled acquisition, no production refresh, no RiskEngine enforcement, no Strategy 9 change. |

---

## 0. The distinction this design exists to keep structural

```
SELECTION UNIVERSE      what a strategy ranks over          (Strategy 8: ~190 names)
        ≠
MARKET-DATA DEMAND      what a strategy needs data for NOW   (held + pending entrants + exits + near-term decisions)
        ≠
HOLDINGS                what the book currently contains     (Strategy 8: 34 names)
```

Demand is **current execution/decision need**. It may include held names, pending entrants, exit
candidates, and symbols with a near-term decision. It is not the selection universe, and it is not
"positions only". The interface below makes the first unrepresentable for `SIP_LIVE` and makes the
second impossible to conflate with the third: a lease carries a *decision reason*, never a portfolio
state.

`SIP_EOD` is different by ruling: its universe is the union of what authorized EOD consumers require
**plus explicitly governed research/strategy universes where operational EOD service is required**. A
selection universe can therefore be legitimate `SIP_EOD` demand when it is registered as such; it can
never be `SIP_LIVE` demand.

---

## 1. The six accepted requirements → mechanisms

| # | Requirement | Mechanism | Structural enforcement |
|---|---|---|---|
| 1 | Governed, non-self-minted `ConsumerId` bound to a governed consumer, allowed profile(s), allowed demand reasons, symbol cap, freshness-declaration authority, lifecycle/revocation state | `sip_consumer_registrations` table + `ConsumerRegistry`, populated only from the versioned registry artifact (§2.1) by an explicit governed apply; **no discovery** | `publish()` accepts a `ConsumerGrant` object issued only by the registry; there is no string-typed `consumer_id` parameter on the publish surface |
| 2 | Demand expires prospectively; stop/revocation removes immediately, expiry is the backstop | `DemandLease` with mandatory `expires_at`; max lease duration per profile; `revoke(grant)` wired to the strategy lifecycle transitions out of ACTIVE | A lease without `expires_at` cannot be constructed (required field, validated ≥ now, ≤ now + max) |
| 3 | Demand = current execution/decision need, not selection universe, not holdings only | Every symbol in a lease carries a `DemandReason` from a closed enum; `SELECTION_UNIVERSE` and `EOD_FEATURE` are **not representable** as `SIP_LIVE` reasons; the registration's `allowed_reasons` further narrows per consumer | The `SIP_LIVE` validator rejects any lease whose reason set is not a subset of the LIVE reasons; the per-consumer LIVE cap makes a 190-name lease unrepresentable |
| 4 | Overlapping consumers → strictest governed freshness wins | `DemandUnion.for_profile()` computes per-symbol `min(max_age_s)` across active leases; plane cadence derives from the strictest symbol | Union is a pure function of active leases; there is no "loosest" or "average" path |
| 5 | Plane-wide overflow → explicit failure; no silent truncation, no arbitrary dropping, no freshness relaxation | Per-consumer cap on the registration (**required**) and plane cap in config (**required**); the *submitting* lease that would cross a cap is rejected with `CONSUMER_CAP_EXCEEDED` / `PLANE_CAP_EXCEEDED`; existing leases untouched | The union never slices, samples, or sorts-and-cuts; the only outcomes are `accepted` or `rejected(reason)` |
| 6 | Malformed/excessive lease contributes nothing and does not degrade valid consumers | Validation at submission; a rejected lease is audited with its reason and **never persisted** into the active set | The union reads only rows with `status = ACTIVE`; a rejected lease has no row |

Plus the two invariants inherited from B1 and carried forward unchanged:

- **Consumer cannot express trust inputs** — a lease has no credential, account, entitlement, feed,
  or clock field. Asserted by the same L1 structural test pattern as `api.py` (exact parameter set,
  forbidden substrings `key|secret|account|credential|entitlement|feed|producer|now|clock|as_of`).
- **"The job ran" is never readiness** — the scheduler writes to the cache; readiness is recomputed
  from `source_timestamp`, coverage, provenance and entitlement state by the existing evaluator.

---

## 2. Data model

### 2.1 Registry artifact and `sip_consumer_registrations` (governance, low churn)

**B3 Decision 1 — explicit governed registration, never discovery.** The source of truth is a
versioned artifact reviewed as code/config:

```
apps/backend/config/sip_consumer_registry.v1.json
```

Applied to the database by a governed operator script (`scripts/sip_apply_consumer_registry.py`),
which is idempotent, audits every grant issuance/revocation under the operator identity, and refuses
to run if the artifact's recorded sha256 does not match the file. At startup the platform performs
**verification only** — artifact hash vs. the applied registrations — and any mismatch renders the
demand plane `NOT READY`. Nothing is ever seeded by scanning the `strategies` table, scheduler jobs,
broker credentials, SIP-capable accounts, or running processes. Discovery-style listings may exist for
diagnostics and carry no authority.

| Column | Type | Notes |
|---|---|---|
| `consumer_id` | text PK | From the artifact, e.g. `strategy:9`, `service:risk-reference`. Never accepted from a consumer. |
| `kind` | text | `strategy` \| `service` |
| `strategy_id` | int FK nullable | Governed binding for `kind = strategy` |
| `user_id` | int FK | Owner principal (same scoping the platform already uses) |
| `allowed_profiles` | text | JSON list ⊆ `["SIP_EOD","SIP_LIVE"]` |
| `allowed_reasons` | text | JSON list ⊆ `DemandReason`; LIVE reasons only if `SIP_LIVE` is allowed |
| `symbol_cap_eod` / `symbol_cap_live` | int **NOT NULL** | **B3 Decision 2:** required per consumer; a registration entry without a cap for each allowed profile is **invalid and refused at apply time**. No infrastructure default. |
| `freshness_policy_ref` | text nullable | **B3 Decision 3:** identifies the consumer's *governed execution policy* that supplies the `SIP_LIVE` bound (e.g. `strategy9-execution-policy@<version>`). The registration says the consumer *may* request LIVE; it never states the number. |
| `artifact_sha256` / `applied_at` / `applied_by` | text / datetime / text | Governance provenance |
| `revoked_at` / `revoked_by` / `revocation_reason` | nullable | Revocation authority record |

### 2.2 `sip_demand_leases` (operational, high churn, persisted so restart does not lose demand)

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `consumer_id` | text FK → registrations | |
| `profile` | text | `SIP_EOD` \| `SIP_LIVE` — one profile per lease; a consumer needing both publishes two |
| `symbols` | text | JSON sorted list, normalized upper-case, deduplicated |
| `reasons` | text | JSON `{symbol: DemandReason}` |
| `max_age_s` | numeric nullable | LIVE only: the value **resolved from the consumer's governed policy** at publish time (Decision 3). The lease carries it; it does not originate it. A LIVE lease with no resolvable bound is refused `FRESHNESS_UNBOUND`. |
| `max_age_trading_days` | int nullable | EOD only; the separately governed trading-day tolerance (Decision 5), default from the EOD contract (1 = last completed session) |
| `effective_from` | datetime(tz) | Registry clock at acceptance (consumer cannot set it) |
| `expires_at` | datetime(tz) | **Required**; ≤ `effective_from + MAX_LEASE[profile]` |
| `status` | text | `ACTIVE` \| `SUPERSEDED` \| `WITHDRAWN` \| `REVOKED` \| `EXPIRED` |
| `superseded_by` | int nullable | Renewal chain |
| `audit_ref` | int | The `REQUESTED` audit row; `ADMITTED` / `SERVED` rows reference this lease |

**Caps and ceilings (B3 Decision 2).** No numeric defaults are written here or in code:

| Setting | Where | Absent ⇒ |
|---|---|---|
| per-consumer `symbol_cap_*` | registry artifact | registration entry **invalid** |
| `sip_live_plane_symbol_cap` / `sip_eod_plane_symbol_cap` | `config.py`, `int | None = None` | demand plane and scheduler **NOT READY**; every lease for that profile refused `PLANE_CAP_UNCONFIGURED` |
| `sip_live_min_interval_s` (producer capability floor) | `config.py`, `float | None = None` | LIVE scheduler **NOT READY** |
| `MAX_LEASE[profile]` | `config.py`, `None` | leases for that profile refused `LEASE_MAX_UNCONFIGURED` |

Platform ceiling values, when they exist, are governed separately against acquisition capacity and
subscription constraints — they are not chosen inside this implementation.

### 2.3 `DemandReason` (closed enum)

| Value | Allowed on LIVE | Allowed on EOD | Meaning |
|---|---|---|---|
| `HELD` | ✓ | ✓ | Currently held; valuation/exit decisions depend on it |
| `PENDING_ENTRY` | ✓ | ✓ | Entry decided or imminent |
| `PENDING_EXIT` | ✓ | ✓ | Exit decided or imminent |
| `DECISION_WINDOW` | ✓ | ✓ | Near-term execution decision requires current reference data |
| `EOD_FEATURE` | ✗ | ✓ | Once-per-session features/ranking inputs |
| `SELECTION_UNIVERSE` | ✗ | ✓ | Governed selection universe registered for EOD service (Ruling 8) |

The LIVE column is the structural encoding of the B3 correction: a `SIP_LIVE` lease may express
economic need in four ways and cannot express a universe at all. A registration's `allowed_reasons`
may narrow this further per consumer; it can never widen it.

---

## 3. Interface

Package: `app/market_data/sip/demand.py` (registry, lease, union) — same package as the consumer
API, same import-boundary rules (no `app.research.*`, no `alpaca.trading`, no credential resolution).

```python
@dataclass(frozen=True)
class ConsumerGrant:
    """Issued by ConsumerRegistry.grant(); opaque to the holder. Carries the registration id and a
    per-process nonce so a grant cannot be forged from a consumer_id string."""
    _registration_id: str
    _nonce: bytes

@dataclass(frozen=True)
class DemandLease:
    profile: SipProfile
    symbols: frozenset[str]
    reasons: Mapping[str, DemandReason]
    max_age_trading_days: int | None   # EOD only
    expires_at: datetime               # required; validated by the registry clock
    # NOTE: no max_age_s field. The LIVE bound is resolved by the registry from the consumer's
    # governed execution policy (freshness_policy_ref) and stamped onto the persisted lease.

class ConsumerRegistry:
    def __init__(self, session_factory, *, policy: FreshnessPolicyProvider,
                 clock: Callable[[], datetime] | None = None): ...
    async def grant(self, consumer_id: str) -> ConsumerGrant          # platform-side only
    async def publish(self, grant: ConsumerGrant, lease: DemandLease) -> LeaseReceipt
    async def withdraw(self, grant: ConsumerGrant, lease_id: int) -> None
    async def revoke(self, grant: ConsumerGrant, *, reason: str) -> int   # all ACTIVE leases
    async def expire_due(self) -> int                                   # scheduler tick

class DemandUnion:
    async def for_profile(self, profile: SipProfile) -> ProfileDemand
    # ProfileDemand: symbols: frozenset[str]; per_symbol_bound_s: Mapping[str, float] (LIVE);
    #                strictest_bound_s: float | None; lease_count: int; consumer_ids: frozenset[str];
    #                materialized_at: datetime; audit_ref: int
```

`FreshnessPolicyProvider` is the seam through which a consumer's *governed execution policy* supplies
the LIVE bound. Its only implementation in B3 is one that reads a frozen policy artifact by
`freshness_policy_ref`; for Strategy 9 that artifact does not exist yet, so the provider returns
`None` and every Strategy 9 LIVE lease is refused `FRESHNESS_UNBOUND`. **There is no default, no
inheritance from another consumer, and no best-effort path** (B3 Decision 5). `DEFAULT_LIVE_MAX_AGE_S`
in `profiles.py` is never read by the registry.

`LeaseReceipt` is `accepted(lease_id, effective_from, expires_at, max_age_s)` or
`rejected(reason: LeaseRejection)` where `LeaseRejection` is a closed enum:
`UNREGISTERED_CONSUMER · CONSUMER_REVOKED · PROFILE_NOT_PERMITTED · REASON_NOT_PERMITTED ·
EMPTY_SYMBOL_SET · MALFORMED_SYMBOL · REASON_NOT_ALLOWED_FOR_PROFILE · FRESHNESS_UNBOUND ·
EXPIRY_MISSING · EXPIRY_IN_PAST · EXPIRY_EXCEEDS_MAX · CONSUMER_CAP_EXCEEDED · PLANE_CAP_EXCEEDED ·
PLANE_CAP_UNCONFIGURED · LEASE_MAX_UNCONFIGURED · BOUND_BELOW_PRODUCER_FLOOR · REGISTRY_ARTIFACT_MISMATCH`.

**Who calls `publish`.** Not the strategy. The strategy class declares a pure method
`market_data_demand(context) -> DemandDeclaration` (symbols + reasons + profile, nothing else); the
**strategy runtime** holds the grant, validates the declaration, and publishes on the strategy's behalf
at each decision cycle. The strategy never sees a grant, a registry, a policy provider, or a
credential. This mirrors the `params_schema` contract: the strategy declares, the platform enforces.

**Answers to the thirteen design questions (owner, 2026-09-01):**

| Question | Answer |
|---|---|
| Who may publish demand | Only a holder of a `ConsumerGrant`, which only the platform runtime obtains from an applied registration |
| What identifies the consumer | The registration row; the grant is the capability, the `consumer_id` is its name |
| Symbol set | Normalized, deduplicated, capped; each symbol carries a reason from the consumer's `allowed_reasons` |
| EOD vs LIVE | One profile per lease; allowed profiles are on the registration |
| Freshness requirement | LIVE: resolved from the consumer's governed execution policy — never from the lease, never from infrastructure; EOD: trading-day tolerance |
| Lifetime | `effective_from` set by the registry clock; `expires_at` required and bounded by configured `MAX_LEASE` |
| How stale demand expires | `expire_due()` on every scheduler tick flips `ACTIVE → EXPIRED` and audits it; the union never reads expired rows |
| Removal when a strategy stops | Runtime calls `revoke()` on every transition out of ACTIVE (idle, halt, archive, breaker trip); expiry is the backstop if the runtime dies |
| Duplicate demand union | Symbol union; per-symbol bound = strictest; a consumer's second lease supersedes its first for the same profile |
| How the scheduler obtains the union | `DemandUnion.for_profile()` at the start of every refresh; materialization audited; never cached across ticks |
| Credential/feed prevention | No such field exists on `DemandLease`, `ConsumerGrant`, or `publish()`; asserted structurally |
| Bounded universe | Per-consumer cap (registry, required) + plane cap (config, required) + `MAX_LEASE` (config, required); overflow rejects the submission; absence fails closed |
| Malformed/excessive demand | Rejected at submission with a named reason; audited; not persisted; other consumers' leases unaffected |

---

## 4. Audit contract (B3 Decision 4)

Audit is via the typed `AuditLogger` API (hash-chained), recording identities and policy values,
never secrets. New `AuditAction` values, each with an on-call playbook scenario in the same PR:

| `AuditAction` | When | Distinguishes |
|---|---|---|
| `SIP_CONSUMER_GRANT_ISSUED` | registry apply creates/updates a registration | operator identity, artifact sha256 |
| `SIP_CONSUMER_GRANT_REVOKED` | registry apply or explicit revoke | reason |
| `SIP_DEMAND_REQUESTED` | every `publish()` call, before validation | **REQUESTED** |
| `SIP_DEMAND_ADMITTED` | lease accepted into the ACTIVE set | **ADMITTED** — carries resolved bound, cap headroom |
| `SIP_DEMAND_REJECTED` | any `LeaseRejection` (cap overflow, malformed, freshness-unbound, …) | reason enum value |
| `SIP_DEMAND_RENEWED` | a superseding lease admitted | old/new lease ids |
| `SIP_DEMAND_WITHDRAWN` | explicit consumer withdrawal | |
| `SIP_DEMAND_EXPIRED` | `expire_due()` transition | |
| `SIP_DEMAND_REVOKED` | lifecycle revoke | reason |
| `SIP_DEMAND_UNION_MATERIALIZED` | scheduler computes a profile union | symbol count, strictest bound, lease ids |
| `SIP_DEMAND_SERVED` | refresh wrote a fresh record for a demanded symbol/profile | **SERVED** — per lease, per refresh |
| `SIP_READINESS_TRANSITION` | per-profile readiness state changes | from/to, reason |
| `SIP_ACQUISITION_FAILURE` | producer failure affecting a demanded symbol/profile | affected lease ids, failure class (never the credential) |

**REQUESTED ≠ ADMITTED ≠ SERVED.** A published request proves that a consumer asked; an admitted
lease proves the plane accepted the obligation; only a `SERVED` row proves data was acquired for it.
Readiness for a consumer is computed from `SERVED` evidence in the cache, never from `ADMITTED`.

---

## 5. Scheduler contract — two jobs, two semantics, both disabled

Registered in `lifespan.py` with the existing pattern (`max_instances=1`, `coalesce=True`,
`replace_existing=True`, `timezone="America/New_York"`), **only** when
`settings.sip_cache_enabled and settings.sip_<profile>_refresh_enabled` — three flags, all default
`False` — **and** the required caps/floor in §2.2 are configured. The jobs are functions in
`app/market_data/sip/scheduler.py`; they call `SipProducer` (the only module permitted to construct a
`feed=sip` request) and write through `SipOperationalCache`.

| | `sip_eod_refresh` | `sip_live_refresh` |
|---|---|---|
| Trigger | Tick-and-check, interval 15 min, window 13:00–18:30 ET on calendar trading days; fires once per completed session when `now ≥ session_close + settle_margin` (calendar-derived close, so half-days are correct; never "16:00") | Interval during RTH only (calendar-derived open/close); interval = `clamp(strictest_bound_s / 2, sip_live_min_interval_s, sip_live_max_interval_s)`; **no leases → no requests, job exits idle** |
| Requested symbols | `DemandUnion.for_profile(EOD)` | `DemandUnion.for_profile(LIVE)` |
| Max acceptable age | Trading-day tolerance from the lease (calendar) | Per symbol, from the union; the plane refreshes at the strictest |
| Readiness threshold | Expected completed date present + coverage ≥ `sip_eod_min_coverage` + provenance complete | Every symbol's newest `source_timestamp` within its bound + coverage complete |
| Retry | ≤ configured attempts within the same session window, exponential backoff; never backfills a prior session | None inside a tick; the next tick supersedes |
| Entitlement failure | Producer raises `SipEntitlementError` → plane latches `ENTITLEMENT_FAIL` for **both** profiles; audited `SIP_ACQUISITION_FAILURE`; no failover, no credential substitution, no MDQ read | Same; the latch clears only on a subsequent successful **designated-producer** request |
| Restart | Readiness recomputed from stored `source_timestamp`; leases reloaded from `sip_demand_leases` and re-validated against expiry; registry artifact re-verified; job re-registered from config only | Same |
| Observability | `SipPlaneStatus` gains a `demand` section per profile: active leases, union size, strictest bound, cap headroom, rejected count + last rejection reason, cadence in force, last refresh attempt/outcome, registry artifact sha256 | Same |
| Retention | `sip_cache_retention_days` | `sip_live_retention_hours` (config, required); prune never removes the newest row of a symbol under an ACTIVE lease |
| Job identity | `id="sip_eod_refresh"` | `id="sip_live_refresh"` |
| **Successful refresh** | Expected date present **and** coverage met **and** provenance complete — evaluated by `SipReadinessEvaluator`, not by job exit status | Every leased symbol within bound **and** coverage met — same evaluator |
| Degraded / unavailable | `STALE` / `INCOMPLETE` / `ENTITLEMENT_FAIL` / `ABSENT` exactly as §9 | Same |

**Producer floor.** `sip_live_min_interval_s` is a rate-limit protection and a *capability* limit, not
a freshness policy. A lease whose bound is below `2 × floor` is rejected at submission
(`BOUND_BELOW_PRODUCER_FLOOR`) — the plane refuses to *promise* a freshness it cannot deliver rather
than accepting the lease and reporting `STALE` forever. Its value is required configuration, not a
literal in code.

**Cadence derivation is not a freshness default.** `strictest_bound_s / 2` exists only when at least one
admitted lease carries a policy-resolved bound. With no LIVE leases the job issues no requests.

---

## 6. Restart, recovery, and the things that must not happen

- A restart never promotes a stale cache to `PASS` (readiness is recomputed; nothing is inherited).
- A failed refresh is recovered by a **subsequent refresh** — never by MDQ backfill, credential
  substitution, or a relaxed tolerance.
- No silent SIP→IEX downgrade on any restart path; the SIP plane and `/app/bars_cache` stay separate.
- `ENTITLEMENT_FAIL` is plane-wide and latched; the B2 harness (#722) already proves it is reachable
  without disturbing account 7, and the scheduler inherits that proof rather than re-deriving it.
- The scheduler never runs on the developer laptop against live infrastructure (§8); enablement flags
  live in the AWS prod overlay only.

---

## 7. Tests (falsifiable — each row states the input that makes it fail)

| Test | Fails when |
|---|---|
| `test_publish_requires_grant_not_consumer_id` | `publish()` grows a string/int consumer parameter |
| `test_grant_cannot_be_forged_from_consumer_id` | a `ConsumerGrant("strategy:9", b"")` built outside the registry is accepted |
| `test_registry_applies_only_from_artifact_never_discovery` | a registration appears without a matching artifact entry, or apply consults `strategies`/credentials/jobs |
| `test_registry_artifact_hash_mismatch_is_not_ready` | a modified artifact still applies, or startup verification passes on a mismatch |
| `test_registration_without_cap_is_invalid` | an artifact entry lacking `symbol_cap_live` for a LIVE-allowed consumer is applied |
| `test_lease_surface_carries_no_trust_inputs` (L1 pattern) | any field named like `key|secret|account|credential|entitlement|feed|producer|now|clock|as_of|max_age_s` appears on `DemandLease`/`ConsumerGrant`/`publish` |
| `test_live_lease_rejects_universe_reasons` | a LIVE lease with `SELECTION_UNIVERSE` or `EOD_FEATURE` is accepted |
| `test_allowed_reasons_narrow_never_widen` | a consumer registered without `PENDING_EXIT` publishes it and is accepted |
| `test_live_cap_makes_selection_universe_unrepresentable` | a 190-symbol LIVE lease is accepted under a configured cap below 190 |
| `test_eod_accepts_registered_selection_universe` | an EOD lease with `SELECTION_UNIVERSE` from a permitted consumer is rejected |
| `test_expiry_is_required_and_bounded` | a lease with no `expires_at`, a past `expires_at`, or one beyond `MAX_LEASE` is accepted |
| `test_revoke_on_strategy_stop_removes_immediately` | after the runtime's ACTIVE→IDLE/HALT transition, the union still contains the consumer's symbols |
| `test_expiry_backstop_when_runtime_dies` | with no `revoke()` call, an expired lease still contributes to the union after `expire_due()` |
| `test_union_takes_strictest_bound` | two leases naming AAPL with 30 s and 10 s yield anything but 10 s |
| `test_live_bound_comes_from_policy_not_lease` | a bound supplied by the caller reaches the persisted lease, or the resolved value differs from the policy provider's |
| `test_freshness_unbound_refused_no_default_no_inheritance` | a consumer whose policy returns `None` gets a LIVE lease accepted, or `DEFAULT_LIVE_MAX_AGE_S` is read, or another consumer's bound is used |
| `test_plane_cap_unconfigured_is_not_ready` | with `sip_live_plane_symbol_cap = None` any LIVE lease is admitted or the scheduler registers |
| `test_plane_cap_rejects_submission_not_truncates` | union size after an overflow submission differs from before, or the accepted set is a strict subset of the submitted set |
| `test_malformed_lease_contributes_nothing` | a rejected lease has a row, or another consumer's readiness changes because of it |
| `test_audit_requested_admitted_served_are_distinct` | an `ADMITTED` row exists without its `REQUESTED` row, or `SERVED` is written on admission rather than on a cache write |
| `test_every_rejection_reason_is_audited` | any `LeaseRejection` value produces no `SIP_DEMAND_REJECTED` row |
| `test_scheduler_idle_with_no_live_leases` | `sip_live_refresh` issues any producer call with an empty union |
| `test_cadence_derives_from_strictest_and_respects_floor` | interval ≠ `clamp(strictest/2, floor, ceiling)` |
| `test_bound_below_producer_floor_rejected` | a bound below `2 × floor` is accepted |
| `test_job_ran_is_not_readiness` | a refresh that wrote stale rows yields `PASS` |
| `test_entitlement_fail_latches_plane_wide_no_failover` | any producer call carries a non-designated fingerprint after a 403, or LIVE reports `PASS` while EOD is `ENTITLEMENT_FAIL` from the same failure |
| `test_restart_reloads_leases_and_recomputes_readiness` | after simulated restart the union is empty while ACTIVE unexpired rows exist, or readiness is read from a stored verdict |
| `test_prune_preserves_newest_row_under_active_lease` | retention deletes the only current row of a leased symbol |
| `test_eod_fires_once_per_completed_session_from_calendar` | it fires on a Saturday, fires twice for one session, or uses 16:00 on a half-day |
| `test_only_scheduler_module_constructs_refresh_jobs` (AST) | any module outside `sip/scheduler.py` and `lifespan.py` references the job ids |
| `test_flags_default_false_and_jobs_absent` | the jobs appear in the scheduler with default settings |

---

## 8. Rulings received 2026-09-02 (replaces the former "decisions requested" section)

| Item | Ruling |
|---|---|
| Registration seeding | **Explicit governed registration from a versioned artifact reviewed as code/config; no discovery** (§2.1). Binding: grant → identity → allowed profiles → allowed reasons → symbol cap → freshness-declaration authority → lifecycle state. |
| Cap defaults | **No invented numbers.** Required configured caps; missing per-consumer cap ⇒ registration invalid; missing plane cap ⇒ NOT READY (§2.2). |
| Freshness placement | **Consumer execution policy owns the bound.** The lease may carry the resolved value; it may not originate it. Unbound LIVE ⇒ `FRESHNESS_UNBOUND` (§3). |
| Audit | The thirteen events in §4; REQUESTED ≠ ADMITTED ≠ SERVED. |
| NULL bound | LIVE: invalid/refused, no default, no inheritance, no best effort. EOD: trading-day tolerance model. |
| Declaration placement | Strategy declares `market_data_demand()`; runtime publishes (accepted with the design direction). |

**Implementation authority:** registry/grants, leases, validation, union, cap enforcement,
expiry/revocation, scheduler integration **in a disabled state**, observability/audit, tests. B3 comes
back as its own PR. `SCHEDULED SIP ACQUISITION ENABLED = NOT AUTHORIZED`; no production refresh is
performed as part of B3 qualification.

---

## 9. Explicit non-authorizations

This document authorizes no scheduler activation, no `sip_cache_enabled` change, no production
`--execute` of the B2 harness, no RiskEngine change, no Strategy 9 change, and no credential change.
