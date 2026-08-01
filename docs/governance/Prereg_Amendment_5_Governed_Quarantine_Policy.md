# Preregistration Amendment 5 — one shared, manifest-derived governed quarantine

**Scope: where the governed price-history quarantine resides, and its propagation to the production
session path.** The corpus, its manifest `1e269fad…`, the countersignature `1f5a7ef7…`, the July 27
decision and the quarantine disposition are untouched. No store was mutated or re-ingested. No
governed artifact was edited or regenerated.

| | |
|---|---|
| supersedes measurement commit | `9c6a2f21bf78d11796b3f64cfbea44a44bfe6959` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| countersignature sidecar | `1f5a7ef778e8d94b4323a922b3da308ef1416d4f2800ca14a8c1a222e2343b62` — **unchanged** |
| quarantine evidence | `c22b8b2f695e1c0a6de1980570dca7e7654b9aeb15f9bb0f68eac67c7f14a2f0` — **unchanged** |
| governed quarantine policy | `76fc26066fe2c2d07b99ef44c4f9509e8fa65918d1ad1aa469bc38e5fa821a6a` — **new, derived** |
| store identity | `5960a0f7c0ae5dfd5955a15e910abc109376ff511cc3d33a849a712a6eee2a09` — **unchanged** |
| reason | `SHARED_MANIFEST_DERIVED_QUARANTINE_POLICY` |
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

A bounded audit of every governed fact `corpus_manifest_v2.json` declares found exactly one with **no
consumer at all** in `app/validation`:

```
governed_quarantine   consumer: none          status: IGNORED
```

Two consequences, of which the second was not visible until the first was traced.

**(a) The production session path had no quarantine.** `session_composition` assessed data finality
with no non-decision M&A disclosure and no narrow-readiness attestation, so `assess_data_finality`
could only ever return `NOT_READY_ADJUSTMENT_UNVERIFIED` for the July 27 session. A corpus could pass
Phase C readiness and then be unable to run the very session that readiness had just cleared.

**(b) Phase C was not manifest-driven either.** `scripts/forward_validation/phase_c_readiness.py`
carried a literal:

```python
QUARANTINED_IDENTITIES = frozenset({"167284", "642054"})
```

It matched the countersigned block, so the two sides appeared to agree — **by coincidence**. Nothing
checked that they still did. This is the same defect class Amendment 2 removed from the session runner
("there is no `EXPECTED_COUNTS` and no fallback"); the constant survived that removal because it lived
in a different file. A parity test written against that arrangement would have compared a literal to a
literal, passed, and proved nothing.

## 2. The ruling

> One shared, manifest-derived quarantine policy, used by both Phase C readiness and production
> session composition. The literal is removed with no fallback.

`governed_quarantine_policy(normalized_construction, countersignature)` is the single derivation. It
produces an immutable policy carrying the permanent identities, the descriptive tickers, the anomaly
class, the governed movement dates, the governed factor types, the quarantine evidence digest, the
corpus-manifest digest and the countersignature-sidecar digest — plus `policy_sha256` over all of it,
which is the one value two consumers can compare.

Nothing is asserted that the countersignature does not transitively bind:

| policy field | governed source |
|---|---|
| permanent identities, descriptive tickers, anomaly class, wording | the manifest's `governed_quarantine` block |
| governed movement dates | the `shop_tln_quarantine` artifact, pinned by the manifest, re-hashed before it is read |
| governed factor types | classified from the ratios that artifact preserves verbatim, by the verifier's own `FactorKind` rule |
| every digest | the manifest, its sidecar, and the artifact's own bytes |

The evidence artifact is located by the **path the manifest declares for it**, never by a filename a
caller chooses: a digest binds nothing unless it names the file that was hashed.

### 2.1 The identity↔ticker pairing is proved, not assumed

The manifest states `names` and `permanent_identities` as parallel sequences; the evidence artifact
keys its records by ticker. The pairing is therefore taken from the manifest's declared order and then
**proved at the point it matters** — a measured movement carries both its ticker and its permanent
identity, resolved from the store, and readiness refuses unless the pair matches. A mis-declared
pairing can only refuse; it can never pass.

## 3. The status

```
GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT
```

It is a **governed disclosure, not a proof**, and it is the only member of `ActionStatus` describing a
factor movement rather than a declared action. It means exactly:

* movement observed;
* no reconciled authoritative action explains it;
* identity, session **and** factor are covered by the countersigned quarantine;
* the movement is excluded from trusted adjustment evidence;
* the session may proceed only under disclosed-limitation readiness.

It does **not** mean action semantics are proven, the movement is reconciled, a price adjustment was
verified, or the identity is decision-irrelevant. It is not in `SATISFIES_READINESS`, and it is
reported in a **movement** census kept separate from `checks_by_status` — a movement is not an action,
and folding it into the action census would place a non-action inside the count clause (3) reads as
the set of assessed actions.

The countersigned wording is carried verbatim rather than paraphrased:

> decision-relevant in raw construction; governed-quarantined due to unexplained vendor adjustment
> anomalies; excluded from trusted adjustment evidence; post-quarantine decision remains valid.
>
> **Must not say:** SHOP/TLN are decision-irrelevant.

## 4. What the clause now checks

Clause (6) of `_narrow_readiness_refusals` tested the permanent identity alone, against a set the
caller supplied. It now tests **identity, session and factor** against the derived policy. Identity
alone would have admitted any movement on a quarantined name — an undeclared split on a lineage the
countersignature examined only for a dividend-factor anomaly would have passed as a governed
disclosure.

The four governed movements are:

```
167284  SHOP  2025-06-26  DIVIDEND_FACTOR
167284  SHOP  2025-06-27  DIVIDEND_FACTOR
642054  TLN   2026-02-02  DIVIDEND_FACTOR
642054  TLN   2026-02-03  DIVIDEND_FACTOR
```

SHOP's 2025-06-25 movement is **not** among them: 273 sessions back from 2026-07-27 is 2025-06-25, and
the window's first session has no prior mark to move from. The count of four is a consequence of the
window, not an assumption about it.

## 5. Session-path propagation

`build_session_runtime` now derives the quarantine and the non-decision M&A disclosure from the
resolved governed construction, and loads the narrow-readiness attestation **under that quarantine**.
The attestation names a policy digest and carries no policy of its own: the consumer derives its own
from the countersigned manifest and refuses on divergence, so a tampered artifact cannot widen the set
of movements a session may disclose — it can only fail to load.

`ForwardDeploymentConfig` gains `narrow_readiness_attestation_path`. Optional in the configuration
(a construction whose corporate actions are all proven reaches `READY` and needs no narrow claim);
**mandatory at composition when declared** — an unreadable or non-binding artifact is a refusal, never
a silent fall back to the broad gate.

⚠ **The deployment configuration must set this key.** The post-evidence configuration baseline moves
again, by the addition of exactly one governed path.

## 6. Expected July 27 readiness outcome — unchanged

```
ready                          true
fully_proven                   false
has_disclosed_limitations      true
decision_validity_proven       true
full_action_semantics_proven   false
```

Both paths now produce it, and both produce the same census, the same quarantine policy digest and the
same limitation digest.

## 7. Refusals proved by test

| case | outcome |
|---|---|
| Phase C literal removed, no policy supplied | REFUSED — neither stage has a default |
| session path derives a different quarantine digest than the attestation names | REFUSED |
| correct identity, ungoverned session | REFUSED |
| correct identity, ungoverned factor | REFUSED |
| governed ticker on the wrong permanent identity | REFUSED — pairing and coverage both |
| one extra unexplained movement | REFUSED |
| edited quarantine evidence artifact | REFUSED — digest drift |
| sidecar bound to another manifest | REFUSED — on both paths independently |
| manifest declaring a different identity | REFUSED — its sidecar no longer binds it |
| both paths, all seven bound identities | EQUAL |

## 8. Audit findings recorded but NOT fixed

Per the ruling, the following are recorded and deliberately out of scope. None blocks July 27:

* `artifacts.universe_exclusions_v2` — digest-validated at load; runtime exclusions come from
  `SessionLineageFilter` over the store, not from the manifest. Possible divergence, separate question.
* `normalized_datasets` — row counts and coverage are declared and not runtime-enforced.
* `frozen_preregistration.frozen_replica_sha256` — not consumed; `build_info` records its own. The
  CRLF/LF discrepancy is already disclosed in Amendment 3.
* `two_universes_never_collapsed` — narrative; no runtime consumer.
* `store.store_file_sha256` — consumed as declared and never re-hashed, **by design**.

## 9. Why the measurement identity moved again

This increment edits `app/validation/`, so the freeze is regenerated by the versioned implementation,
anchored at the last ratified measurement commit `1c73d442`. The ratified-increment inventory chain
continues: `previous_inventory_sha256` names the inventory the superseded freeze bound.

Two governed artifacts are additionally committed under `manifests/layer2/` —
`shop_tln_quarantine.json` and `residual_relevance.json`. They are **installed, not authored**: both
hash to the values `corpus_manifest_v2.json` already pinned, and `.gitattributes` marks the directory
`-text` so no end-of-line translation can move them. They are in Git for the same reason the frozen
DGS3MO snapshot is — so every test run re-proves that the artifacts the narrow-readiness wiring READS
still hash to what the countersignature binds.

## 10. What is NOT authorized

Nothing here authorizes deployment, window opening, or observation recording. The evidence pack must be
regenerated from scratch after this increment is merged and redeployed, and the deployment
configuration must declare `narrow_readiness_attestation_path` before a session can reach the narrow
verdict.

```
OBSERVATION 1  :  BLOCKED
ACCOUNT 4      :  IDLE - HOLD ACTIVE
FORWARD WINDOW :  CLOSED
```
