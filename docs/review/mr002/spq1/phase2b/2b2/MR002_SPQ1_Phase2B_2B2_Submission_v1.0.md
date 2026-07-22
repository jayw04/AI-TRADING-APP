# MR-002 Workstream C — SPQ-1 Phase 2B — Increment 2B-2

## Full development-partition signal-production run + deterministic replay (clean, post-amendment)

Governing run specification **v1.1** (`fd19aef5…`, collision-rule amendment); Run ID `MR002-SPQ1-P2B-DEV-V1`.
Frozen orchestration identity `bb029a96…` **unchanged**. Two independent full passes (A + B).

### Authorized request population (long side only)

- **425,000 request units** = all `in_long_universe` members (250/governing month) × 1,700 development
  sessions. `short_only_members = 0` (verified) ⇒ short-side request units = **0** (no short-only names;
  the ~150 short members each month are already enumerated as long-side units).
- 82 governing months; session counts vary (partial first/last months). Expected units reconstructed from
  shard facts: `Σ(session_count × member_count) = 425,000 == actual == total`.

### Dispositions (recomputed, both passes identical)

| disposition | count |
|---|---|
| SIGNAL_DECISION_RECORD_EMITTED | 320,771 |
| INELIGIBLE | 40,457 |
| INTEGRITY_STOP | 50,399 |
| REFUSED_CODE_OR_DATA_IDENTITY | 13,373 |
| **total** | **425,000** |

Terminal-code breakdown: `OLS_WINDOW_INSUFFICIENT` 25,149 · `SECURITY_IDENTITY_AMBIGUOUS` 50,399 ·
`SIGNAL_INPUT_IDENTITY_MISMATCH` 13,373 · `ELIGIBILITY_EVIDENCE_MISSING` 7,742 ·
`SECTOR_PIT_IDENTITY_MISSING` 7,566.

### Request-identity collision rule (MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1)

Runner-side governed pre-production detection (frozen `run_unit` unchanged). Recomputed from the actual
enumeration — matches the registered census exactly:

| metric | value |
|---|---|
| collision_group_count | 35 |
| collision_request_unit_count | 70 |
| distinct_collision_symbol_sets | 3 |
| maximum_collision_cardinality | 2 |

| pair | claimed permsec | groups | months | session range |
|---|---|---|---|---|
| AGN / AGN1 | PSEC-198103 | 12 | 2015-03 | 2015-03-16 → 03-31 |
| CB / CB1 | PSEC-199850 | 2 | 2016-01 | 2016-01-14 → 01-15 |
| DD / DD1 | PSEC-199769 | 21 | 2017-08/09 | 2017-08-31 → 09-29 |

**Collision reconciliation (all proven):**
- `CollisionCensus.affected_request_count = 70 == collision-caused SECURITY_IDENTITY_AMBIGUOUS records = 70`.
- No collision claimant produced a decision record (all `record_identity = null`).
- No claimed permsec appears as an accepted terminal id at its collision session (**0**).
- Duplicate resolved permanent-security/session keys = **0**.
- Every affected request key has exactly one terminal outcome.
- RefusalCensus splits `SECURITY_IDENTITY_AMBIGUOUS` by cause: **70** cross-request non-injective collision
  vs **50,329** single-request lineage ambiguity (70 + 50,329 = 50,399).

### Whole-session invariant

Enforced fail-fast per shard: every session presented its complete authorized `in_long_universe` request
set (no session split across independently-detected batches). Held on all 1,700 sessions in both passes.

### Mandatory preflight (both passes, all reproduce)

v1.1 run-spec hash `fd19aef5…` · frozen `bb029a96…` · full-run runner identity · `collision_rule.py`
identity · frozen-identity-unchanged-in-amendment · dev-calendar `dev_calendar_sha256` (independent of
`RegisteredCalendar.identity`) · research/provenance DB · universe `f638dfe3…` · sic_mapping `c4e8c5e3…` ·
pit-sector `3fc538b1…` · phase1 `c9ebd7f9…` · increment-3 `42c5cee0…` · validation/OOS reads = **0**.

### Determinism (independent second pass B — all equal)

Fresh materialization + fresh guard/ledger + fresh enumeration + clean output; no reuse of pass-A shards
or merged records. Equal across A/B: decision-record hash, disposition-record hash, session/security/
refusal/**collision** census hashes, publication-core hash, per-shard content SHA-256, record counts,
canonical ordering, and the materialized snapshot content identity.

### Reconciliation / restart / gate

- Reconciles: expected == actual == 425,000; dup request keys = 0; dup resolved keys = 0; dup candidate
  ids = 0; 0 unknown / 0 deprecated codes; 0 validation/OOS reads; 0 reads beyond dev end.
- Restart: completed-shard overwrite blocked; lost shard recomputes byte-identically on resume;
  merged-after-resume == full merge.
- Canonical merge SHA-256 `1d6defec…`. **acceptance gate: all pass.**

### Boundary

Full development run + determinism replay only. **Phase 2B-3 closeout NOT authorized.**
Performance / forward-return / ranking / portfolio / execution / A-B-C / tuning / validation / OOS /
order-path / production all **NOT authorized**. Validation/OOS **sealed and unread**. Awaiting Phase 2B-2
adjudication.

### Artifacts (this directory; large decision/disposition shards out-of-git, each bound by content-SHA in the ShardManifest)

RunManifest · InputIdentityManifest · ShardManifest · OpenedObjectLedger · UnitReconciliation ·
SessionCensus · SecurityCensus · RefusalCensus · **CollisionCensus** · DeterminismReport · RestartReport ·
PublicationManifest.
