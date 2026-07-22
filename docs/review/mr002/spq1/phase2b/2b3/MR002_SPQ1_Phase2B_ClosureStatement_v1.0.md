# MR-002 Workstream C — SPQ-1 Phase 2B — Closure Statement

**Phase 2B: COMPLETE.**

> Phase 2B establishes deterministic, PIT-governed development signal production and evidence integrity
> only. It makes no claim regarding profitability, statistical significance, robustness, portfolio
> utility, or production readiness.

## Bound evidence identities

| item | value |
|---|---|
| Phase 2B-2 evidence commit | `1cc98f55b71c5fa9751f4c7ea3df79f585804158` |
| evidence tree | `5efb62ec5a4304e09ef40c28260142b97cfe10c7` |
| governing run specification | RunSpecification **v1.1** |
| run-spec SHA-256 | `fd19aef5230bac56bc82be1efb1be55ba3fe5d4f9daae33608f49ebbfd4554c3` |
| frozen orchestration identity | `bb029a96…` (unchanged across all of Phase 2B) |
| full-run runner identity | `9f913a76…` |
| collision-rule module identity | `d827cc42…` |
| dev-snapshot content identity | `1c6a5121…` |
| canonical merge SHA-256 | `1d6defec…` |

The 13-artifact inventory and their SHA-256 values are frozen in
`MR002_SPQ1_Phase2B_2B3_ArtifactInventory_v1.0.json`.

## Final unit + disposition census

- 1,700 development sessions · 82 governing-month shards · **425,000** long-side request units.
- Reconciles exactly (`expected == actual == 425,000`); missing = 0; orphan = 0; dup request keys = 0;
  dup resolved permanent-security/session keys = 0; shard-fact reconstruction `Σ(session × member) = 425,000`.

| disposition | count |
|---|---|
| SIGNAL_DECISION_RECORD_EMITTED | 320,771 |
| INELIGIBLE | 40,457 |
| INTEGRITY_STOP | 50,399 |
| REFUSED_CODE_OR_DATA_IDENTITY | 13,373 |

## Terminal-key terminology clarification (per adjudication)

The Phase 2B-2 `UnitReconciliation` field `distinct_resolved_terminal_keys` counted **all** terminal
keys (including `UNRESOLVED:<symbol>`). Clarified and recorded in
`MR002_SPQ1_Phase2B_2B3_TerminalKeyClarification_v1.0.json`:

| field | value |
|---|---|
| distinct_terminal_keys (all) | 425,000 |
| distinct_accepted_resolved_permanent_security_session_keys | 375,728 |
| unresolved terminal keys (`UNRESOLVED:<symbol>`) | 49,272 |
| sum check | 375,728 + 49,272 = 425,000 |
| duplicate_resolved_permanent_security_session_keys | 0 |

The completed run is **not** regenerated for this nomenclature clarification.

## Collision amendment + census

Rule `MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1` (run-spec v1.0 `747875e3` → v1.1 `fd19aef5`).
Recomputed from the actual enumeration: **35 groups / 70 affected requests / 3 distinct symbol sets /
max cardinality 2** — AGN/AGN1→PSEC-198103 (12), CB/CB1→PSEC-199850 (2), DD/DD1→PSEC-199769 (21).
Reconciles: affected 70 == collision-caused ambiguous 70. RefusalCensus cause-split: 70 non-injective
collision vs 50,329 single-request lineage ambiguity (= 50,399 total). All claimants unresolved
integrity-stops; none produced a decision record; claimed permsecs diagnostic-only.

## Deterministic replay + restart

Independent pass-B replay equal on every required governed output (decision / disposition / session /
security / refusal / collision census hashes, per-shard content hashes, publication-core, snapshot
identity, record counts, canonical ordering); fresh materialization / enumeration / guard / ledger /
clean output; no reuse. Restart: completed-shard overwrite blocked; resume identical; remerge identical.
`gate_all_pass = true`; `hard_stop = false`; validation/OOS reads = 0; unknown/deprecated codes = 0.

## Authorization boundary going forward

Phase 2B-3 performed governance closeout only. **Not authorized** (unchanged): forward-return join,
performance evaluation, ranking/economic interpretation, A/B/C comparison, significance/DSR, parameter
tuning, portfolio construction, execution simulation, validation access, OOS access, order-path
integration, production promotion. **Validation/OOS remain SEALED AND UNREAD.**

Awaiting final Phase 2B closure adjudication.
