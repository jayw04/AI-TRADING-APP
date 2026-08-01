# Preregistration Amendment 4 — manifest-bound source authority

**Scope: where source authority resides for a countersigned whole-corpus reconstruction, and one
configuration-loading defect.** The corpus, its manifest `1e269fad…`, the countersignature, the July 27
decision and the quarantine disposition are untouched. No store was mutated or re-ingested.

| | |
|---|---|
| supersedes measurement commit | `9c6a2f21bf78d11796b3f64cfbea44a44bfe6959` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| store identity | `5960a0f7c0ae5dfd5955a15e910abc109376ff511cc3d33a849a712a6eee2a09` — **unchanged** |
| reason | `AUTHORITY_INTERPRETATION_FOR_COUNTERSIGNED_RECONSTRUCTION` |
| amended | 2026-07-31 |

## 0. Governance status

```
LAYER 2 CORPUS COUNTERSIGNATURE :  REMAINS VALID
CORPUS / MANIFEST / STORE       :  UNCHANGED - NOT MUTATED, NOT RE-INGESTED
ACCOUNT 4                       :  UNCHANGED - IDLE, HOLD ACTIVE
FORWARD WINDOW                  :  CLOSED
OBSERVATION 1                   :  NOT PRODUCED, NOT AUTHORIZED
```

## 1. What failed

The July 27 governed pre-commit evaluation ran on deployed commit `9c6a2f21` and stopped at readiness:

```
STOP: NOT_READY_ADJUSTMENT_UNVERIFIED — the corporate-action source
'actions:artifact-missing' is not declared authoritative
```

`declare_action_source` establishes authority by **re-hashing the artifact recorded in
`dataset_coverage.artifact_path`**. Every coverage row of the Layer 2 store records a build-machine
path:

```
C:\LLM-RAG-APP\layer2-vintage\v2\raw\SHARADAR_ACTIONS_2_29fe246cadf640e7e1609af39f779093.zip
```

That path cannot exist on the Linux deployment host, so the check could only ever fail. The data itself
is complete and correct: 286,087 action rows, coverage 1997-12-31 .. 2026-07-27, `status ok`, linked to
a finished ingest run with matching row counts. All three datasets (SEP, TICKERS, ACTIONS) carry
build-machine paths; only ACTIONS is gated today, so only ACTIONS surfaced it.

**The 2026-07-29 remedy was unavailable.** That occurrence was fixed by re-ingesting on the host.
Doing so here would write to the governed store and move `store_file_sha256 5960a0f7…`, which is bound
by both the corpus manifest and the countersignature — repairing the provenance would invalidate the
countersigned identity it exists to protect.

## 2. The interpretation

> For a countersigned whole-corpus reconstruction, runtime authority derives from the immutable
> manifest, the countersignature sidecar, and matching store provenance. Construction-machine
> filesystem paths are audit metadata and are not required to exist on the deployment host.

This is **not a waiver of source authority**; it states where authority lives. The source ZIPs were
*construction inputs*, not runtime dependencies. A base-plus-delta deployment still holds the artifacts
it ingests, so for that construction the artifact-path re-hash remains the authority check, unchanged.

Authority for a reconstruction passes only when **all** hold:

1. the Layer 2 corpus manifest loads and its SHA-256 is exact;
2. the countersignature sidecar is valid and binds that manifest;
3. `dataset_coverage.status` is authoritative and linked to a completed ingest run;
4. coverage reaches the requested session;
5. the row's `source_identity` names the source vintage bound by the manifest;
6. dataset name and construction identity reconcile with the normalized construction;
7. no conflicting provenance row exists.

Missing, malformed, unbound or mismatched provenance still refuses. `artifact_path` is demoted to
audit metadata — it is not resolved, and it is not silently dropped from the record.

### 2.1 Structured parsing, not string comparison

`source_identity` is **parsed**, never compared whole and never substring-matched:

```
SHARADAR/ACTIONS|source_vintage_sha256=36d247f4…|export_object=…|last_refreshed_time=…|reason=…
```

Only two fields carry meaning — the `SHARADAR/<DATASET>` prefix and `source_vintage_sha256`. The rest
is audit metadata that legitimately varies; a whole-string comparison would refuse on cosmetic drift,
and a substring test would accept a partial match. Refused: malformed identities, duplicate required
keys, missing dataset prefix, missing or non-digest vintage, wrong dataset, wrong vintage.

### 2.2 Vintage agreement, not a row count

Every authoritative `status='ok'` coverage row for the dataset must name the **same** manifest-bound
vintage. Multiple rows from one governed vintage are benign; two distinct vintages are the conflict
worth refusing. A row-count invariant would have done the opposite — refusing the harmless case and
missing the dangerous one, because authority read off the newest row alone cannot see an older
authoritative row naming a different vintage.

### 2.3 Manifest knowledge stays at the composition root

`declare_action_source` does not load or interpret corpus manifests. The composition root derives a
policy from the governed construction and passes the conclusion down:

```
base-plus-delta  ->  authority_policy = None                    (artifact-path re-hash, unchanged)
Layer 2          ->  ManifestBoundAuthorityPolicy(vintage, …)   (provenance binding)
```

Production session composition and the deployment-evidence generator derive it through the **same**
function, `manifest_bound_authority_policy`, so they cannot disagree about whether a deployment's
authority basis can be established. The generator derives it in order to fail at generation rather
than produce a manifest the session path would refuse.

## 3. Scope of the generic implementation

The policy is **dataset-generic** and is tested against SEP, TICKERS and ACTIONS. Production behaviour
is unchanged: **ACTIONS remains the only readiness authority gate.** No SEP or TICKERS gate is added —
that would change readiness semantics and exceed the two blockers this increment fixes.

## 4. The configuration defect

`ForwardDeploymentConfig.ancestry_marker_path` existed on the dataclass but **was never read from the
configuration payload**, so it was silently always `None`. `preflight` calls
`verify_deployment(..., ancestry_marker=ctx.ancestry_marker)`, so with the freeze anchored at one
commit and the deployed head at its descendant, ancestry could not be evidenced and
`build_first_session_record` would refuse — a field that looked configurable and did nothing.

Now read from configuration and propagated unchanged. Absent → `None`, followed by the existing
fail-closed behaviour when ancestry evidence is required. **No environment fallback and no default
path**: a deployment that cannot point at its ancestry attestation must not have one fabricated for it.

## 5. Refusals proved by test (33 cases)

| case | outcome |
|---|---|
| inaccessible Windows path + bound vintage (sep/tickers/actions) | AUTHORITATIVE |
| inaccessible path + **mismatched vintage** | REFUSED `source-vintage-unbound` |
| inaccessible path + **malformed identity** | REFUSED `source-identity-malformed` |
| row naming a different dataset | REFUSED `source-identity-wrong-dataset` |
| two rows, same governed vintage | accepted |
| two rows, distinct vintages | REFUSED `source-vintage-conflict` |
| no authoritative row | REFUSED |
| malformed / duplicate-key / missing-vintage identities | parse refuses |
| audit metadata varies, binding unchanged | accepted |
| **no policy → artifact path still re-hashed** | REFUSED `artifact-missing` (legacy unchanged) |
| a real artifact under the legacy path | AUTHORITATIVE |
| Layer 2 without approval derives no policy | REFUSED |
| `ancestry_marker_path` loads from configuration | read |
| absent marker → ancestry fails closed | REFUSED |
| marker for a different commit pair | REFUSED |

## 6. Why the measurement identity moved again

This increment edits `app/validation/`, so the freeze is regenerated by the versioned implementation,
anchored at the last ratified measurement commit `9c6a2f21`. The ratified-increment inventory chain
continues: `previous_inventory_sha256` names the inventory the superseded freeze bound.

## 7. What is NOT authorized

Nothing here authorizes deployment, window opening, or observation recording. The evidence pack must be
regenerated from scratch after this increment is merged and redeployed. The post-evidence configuration
baseline is `e8ef4adf…`, which moved from `3855423981509122…` by the addition of exactly two governed
paths — `corpus_countersignature_path` and `ancestry_marker_path` — both required by this and the
preceding increment.

```
OBSERVATION 1  :  BLOCKED
ACCOUNT 4      :  IDLE - HOLD ACTIVE
FORWARD WINDOW :  CLOSED
```
