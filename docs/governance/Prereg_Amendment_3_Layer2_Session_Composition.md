# Preregistration Amendment 3 — Layer 2 native session composition

**Scope: the measurement-instrument binding and the governed-construction loader only.** PREREG v1.0,
the Layer 2 corpus countersignature and its Amendments 1 and 2 otherwise stand unchanged. The governed
corpus, its manifest `1e269fad…`, the July 27 decision and the quarantine disposition are untouched.

| | |
|---|---|
| supersedes measurement commit | `d13310a32227c67163250566eca719d5f734dd53` |
| ratified measurement commit | `7c2ca104f5a6fce3d085ccea06c192068e8b62a1` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| reason | `AUTHORIZED_MEASUREMENT_INSTRUMENT_EVOLUTION_REQUIRED_FOR_LAYER2_SESSION_COMPOSITION` |
| amended | 2026-07-31 |

## 0. Governance status

```
LAYER 2 CORPUS COUNTERSIGNATURE :  REMAINS VALID
CORPUS / MANIFEST / DECISION    :  UNCHANGED
FAILED ITEM                     :  the deployed SESSION-COMPOSITION path,
                                   NOT the corpus construction and NOT readiness
ACCOUNT 4                       :  UNCHANGED - IDLE, HOLD ACTIVE
FORWARD WINDOW                  :  CLOSED
OBSERVATION 1                   :  NOT AUTHORIZED
```

## 1. What failed

Amendment 2 closed the readiness-attestation defect, and Phase C passed on the deployed commit
`7c2ca104` for session 2026-07-27. That produced a false impression of end-to-end readiness.

`Layer2CorpusManifest`, `load_layer2_corpus_manifest` and `load_any_corpus_manifest` were implemented
and tested, but the **only** caller in the tree was the readiness runner
(`scripts/forward_validation/phase_c_readiness.py`). The production session path did not reach them:

```
session_composition.build_session_runtime
  -> _resolve_governed_construction
       -> _declared_base_cutoff            reads payload["base_coverage_through"]  -> KeyError
       -> governed_corpus.resolve_governed_construction
            -> load_corpus_manifest        base-plus-delta ONLY                    -> refusal
```

A Layer 2 reconstruction has no `base_coverage_through`, no base artifact and no delta chain, so both
call sites refused it. **Readiness understood the deployed construction; session composition could not
compose against it.** The gap was invisible because the two paths were only ever exercised separately.

The same defect existed in `scripts/generate_deployment_evidence.py`, which called
`load_corpus_manifest` and therefore could not describe the installed construction either. It was found
by attempting to regenerate the deployment evidence pack on the host.

## 2. What is changed

1. `resolve_governed_construction` loads through `load_any_corpus_manifest` and normalizes both kinds
   through the existing `NormalizedCorpusConstruction`.
2. The base-plus-delta path is **unchanged**: same loader, same validation, same declared-identity
   contract, same emitted provenance, byte-for-byte the same deployment corpus block.
3. No base cutoff is synthesized. A reconstruction's coverage is carried as
   **`governed_coverage_through`**, never as `base_coverage_through`, and its expected delta-session
   list is `()` because it has no delta chain.
4. A reconstruction never emits base/delta provenance keys — **not even as nulls**. A null
   `base_corpus_sha256` in governed evidence reads as "there was a base and we failed to record it",
   which is a different and false statement.
5. One producer, `governed_corpus.deployment_corpus_block`, builds the deployment manifest's `corpus`
   block. The generator WRITES it and `resolve_governed_construction` RECOMPUTES it for comparison, so
   the two sides cannot drift into declaring and checking different things.

## 3. The countersignature sidecar

`corpus_manifest_v2.json` carries `"countersignature": null` and the construction-time status
`PROPOSED — NOT COUNTERSIGNED, NOT DEPLOYED`. Those are properties of the artifact at the moment it was
**built**. A construction cannot countersign itself; approval necessarily comes afterwards.

Rewriting the manifest to record the approval would change its digest and invalidate every binding
already built around `1e269fad…`. The approval is therefore recorded in an immutable external sidecar,
`manifests/layer2/corpus_countersignature_v1.json`, which **names the manifest digest**:

```
corpus_manifest_sha256      1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064
complete_package_sha256     72b98dbb40f8eadae16e91799062dd378f43b64738e814176a839aa3601817c5
amendment_1_sha256          7a18d3c07dfcb3894dda2ca55f644152a4ac257d828f09c5164d2440b495d273
amendment_2_sha256          ca7eb42363622d10dc1566bc56ccbbdd5f1b5299c53ba124c2fc8a9b7d20f56a
countersignature_status     CONDITIONALLY_COUNTERSIGNED
deployment_status           AUTHORIZED_ONLY_AFTER_RUNTIME_AND_READINESS_GATES
supersedes_manifest_sha256  a69ad50ffc3c6925b3c9b6c8fd1c2adc7143ef9d5c98e9378e1c3ea21ca75c49
```

The runtime **requires** the sidecar for a Layer 2 construction and verifies that it binds the exact
manifest digest loaded. The embedded `null` means *not self-countersigned*; it can neither override a
valid sidecar nor substitute for a missing one, and both directions are pinned by test.

Amendment 2 is bound here as well as Amendment 1, so the sidecar carries the complete governance chain
rather than a prefix of it. Amendment 2 governs the readiness-attestation contract and was resolved by
the implementation deployed at `7c2ca104`; it does not alter the corpus countersignature.

Runtime enforcement of the sidecar is deliberately limited to four properties: canonical sidecar
integrity, exact corpus-manifest binding, countersignature status, and the supersession relationship.
The governance-document digests are recorded references and are not re-hashed at runtime.

## 3a. Two scopes that must not be conflated

| scope | approves | validity |
|---|---|---|
| corpus countersignature | the reconstructed corpus and its coverage | any session **within governed coverage** |
| readiness attestation | one assessed session | that **exact** session only |

An earlier draft of this increment refused any session but 2026-07-27 inside
`resolve_governed_construction`. **That was wrong and has been removed.** It collapsed the corpus
approval into the attestation's session scope and would have denied a legitimately covered session its
own readiness run. The corpus-level bound is coverage — a session the corpus stops before is still
refused — and the session binding stays on the attestation and the receipt, where
`phase_c_readiness.py` refuses a persisted attestation whose `session_date` is not the session being
evaluated.

This does not reopen 2026-07-24, whose separate readiness result stands:
`INELIGIBLE_UNRESOLVED_ADJUSTMENT_EVIDENCE`.

## 4. Newline forms — a recorded clarification

The frozen replica identities recorded in the countersignature package were produced from the original
**Windows-form (CRLF)** bytes. The deployed runtime is **LF**. The two are equivalent under the approved
newline-normalized measurement identity `PATH_SORTED_SHA256_CRLF_TO_LF_V1`; byte equality is separately
governed by `manifests/forward/measurement_bytes.json`, which is stored in git's own LF form and
verified against it.

This applies to the governance documents too: the digests recorded in the sidecar are of the CRLF bytes
as countersigned. Amendment 1 in LF form hashes to
`bf1913b5962f3daad0cb4b079b80749ba099f072b27158d9fd99683c8cdbb21e`. The sidecar records the newline
form explicitly so a later session does not "correct" a mismatch that is not one. **The governance
documents are recorded references, not runtime-verified artifacts** — the runtime verifies only that
the sidecar binds the loaded manifest.

The `frozen_preregistration` note inside `corpus_manifest_v2.json` claims its stage-4 replica digest is
"IDENTICAL on the superseded host runtime and in this worktree". Against an LF runtime that holds under
normalization, not byte-for-byte. The manifest is **not** rewritten for this: its digest is load-bearing,
and the clarification belongs here.

## 5. Refusals proved by test

| case | outcome |
|---|---|
| Layer 2 composes with a valid sidecar | PASS |
| Layer 2 with no sidecar configured | REFUSED |
| sidecar configured but absent | REFUSED |
| sidecar bound to a different manifest | REFUSED |
| sidecar bound to the SUPERSEDED manifest | REFUSED, diagnosed as superseded |
| sidecar approving a different supersession | REFUSED |
| unrecognized `countersignature_status` | REFUSED — not treated as approval |
| non-canonical sidecar bytes | REFUSED |
| another **covered** session against the same corpus | composes — coverage, not session identity |
| a session beyond governed coverage | REFUSED |
| embedded `null` as a substitute for the sidecar | REFUSED |
| embedded `null` overriding a valid sidecar | does not — composition succeeds |
| reconstruction emitting base/delta provenance | never, asserted key-by-key |
| deployment manifest still declaring base-plus-delta | REFUSED as incomplete |
| generator block vs session-path block | identical, by shared producer |
| base-plus-delta behaviour | unchanged, incl. byte-stable block shape |

The Layer 2 fixtures install the **real committed artifacts**, so every CI run re-proves that
`corpus_manifest_v2.json` and its sidecar still hash to the values every downstream binding names.

## 6. Why the measurement identity moved

This increment edits `app/validation/`, which is the measured tree. The measurement freeze therefore
refuses until it is regenerated — the control working as designed, not a side effect to be suppressed.
The freeze is regenerated by the versioned implementation
(`scripts/forward_validation/generate_measurement_freeze.py`) over the staged tree, anchoring ancestry
at the last ratified measurement commit `7c2ca104`.

⚠ **The supersession chain advances, and the inventory advances with it.** Amendment 2 ratified
`d13310a` superseding `764883b5`, and its inventory listed the 28 increments across that range. This
amendment ratifies `7c2ca104` superseding `d13310a`, so `manifests/forward/ratified_increments.json`
now lists only the increments in `d13310a..7c2ca104` — 28 entries become 1 in this diff.

The file is the **incremental** inventory for the current freeze range, and the schema now says so
rather than leaving it to be inferred. `version` is `1.1` and it carries:

```
inventory_scope             INCREMENTS_SINCE_THE_IMMEDIATELY_PRECEDING_FREEZE
previous_inventory_sha256   3c324a25b7c72cab602ca33c184d10f8d1508d6c20544ea7e60e7cb0870850a4
current_freeze_range        d13310a32227c67163250566eca719d5f734dd53
                            .. 7c2ca104f5a6fce3d085ccea06c192068e8b62a1
current_increment_count     1
```

**The inventories form a chain.** `previous_inventory_sha256` is exactly the value the superseded
freeze manifest bound as `ratified_increment_inventory_sha256`, so following the links backwards
reconstructs the full ratified history from any point. The one-entry file does not replace or erase
the 28-entry inventory; it succeeds it and names it.

⚠ That link is hashed in **LF form**. The inventory is authored as LF and git stores the LF blob, but
`.gitattributes` checks JSON out as CRLF on Windows regardless of `core.autocrlf` — the working-tree
file here hashes to `66be269c…` while the governed blob hashes to `3c324a25…`. Hashing the working
bytes would have made the chain link platform-dependent and wrong on exactly one of the two platforms.
The generator normalizes before hashing, which is the same newline discipline recorded in §4.

## 6a. What this amendment ratifies

1. Layer 2-aware production session composition.
2. The shared deployment corpus block, produced by one function and recomputed for comparison.
3. External countersignature-sidecar enforcement.
4. Layer 2 support in deployment-evidence generation.
5. Preservation of the legacy base-plus-delta representation, byte-for-byte.
6. The new measurement-tree identity.

## 7. What is NOT changed and NOT authorized

Nothing here authorizes deployment, window opening, or observation recording. The deployment evidence
pack on the forward host remains **incomplete and fail-closed** and is to be regenerated from scratch
after this increment is merged and redeployed — never resumed from the partially generated pack.

```
DEPLOYMENT IDENTITY :  FAIL-CLOSED - REBUILD AFTER MERGE AND REDEPLOY
OBSERVATION 1       :  BLOCKED
ACCOUNT 4           :  IDLE - HOLD ACTIVE
FORWARD WINDOW      :  CLOSED
```
