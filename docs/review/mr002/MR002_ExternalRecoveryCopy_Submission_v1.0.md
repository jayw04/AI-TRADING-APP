# MR-002 External Offline Recovery Copy — Submission v1.0

**Date:** 2026-07-22
**Authority:** Detection-package adjudication of 2026-07-22, which authorized one work
package: *External Offline Recovery Copy.*
**Disposition:** Archive produced, digest-verified, restore-tested, and offline-verifiable.
**Physical placement remains an owner action.** Stop point reached.

---

## 1. What this closes, and what it does not

Detection can report that the bound image disappeared. It cannot bring it back. This package
produces the artifact that can.

It does **not** yet complete the recovery control: an archive sitting in a staging directory on
the same workstation is not an independent failure domain. **Recovery from ECR loss remains
UNSATISFIED until the owner completes §6.**

---

## 2. Two-level identity

| Level | Value |
|---|---|
| **Semantic identity (governing)** — inner OCI index | `sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9` |
| **Wrapper identity** — outer archive | `sha256:c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a` |

The **inner index is the binding.** The outer hash identifies this packaging and is not a
governing identity. If the two ever disagree about what matters, the inner index wins.

**Packaging is deterministic.** tar mtime/uid/gid/uname/gname are zeroed, so re-exporting the
same objects reproduces the identical outer hash — verified by two independent runs producing
`c3cf3b9e…` both times. This lets you re-derive the wrapper hash yourself rather than taking
mine on trust.

⚠ This is *packaging* determinism over already-fixed bytes. It is **not** a build
reproducibility claim. The P5 binding remains **instance identity**: the image must never be
rebuilt and assumed equivalent.

---

## 3. How the archive was built

Walked directly from the registry — **nothing was taken from the local Docker daemon, and
nothing was rebuilt.** Every manifest and every blob was verified against its own SHA-256 at
download time; a mismatch aborts.

**13 objects, all digest-verified:**

| Kind | Count | Notes |
|---|---|---|
| index | 1 | the governing bound object |
| manifest | 2 | linux/amd64 runtime + BuildKit attestation |
| config | 2 | one per manifest |
| layer | 8 | 7 runtime + 1 attestation |

Format is a standards-conformant **OCI image layout** (`oci-layout`, `index.json`,
`blobs/sha256/*`) packed as uncompressed GNU tar — 44,410,880 bytes. The `index.json` reference
carries the bound digest, so the archive is self-describing.

Full per-object inventory: `docs/review/mr002/MR002_ExternalRecoveryCopy_v1.0.json`.

---

## 4. Post-build verification — and the bugs it caught

**Verdict: PASS.** The authoritative post-build gate is now `verify_archive()` — the *same*
hardened verifier the custodian runs offline, so the archive is never blessed at build time by a
weaker check than the one it must later survive. A separate build-only cross-check additionally
confirms the archive's object set equals exactly what was downloaded and digest-verified from
the registry (**PASS**); the weaker `restore_test()` has been deleted outright so it cannot be
reintroduced as a gate.

The test earned its place by failing twice before it passed:

1. **It reported all 13 objects missing.** The blob-path check required a leading slash
   (`/blobs/sha256/`) while tar arcnames are relative, so it matched nothing and would have
   reported PASS-shaped emptiness had the assertions been weaker.
2. **It crashed walking the graph.** An image *config* blob has its own top-level `config` key
   (container Env/Cmd) which is not an OCI descriptor. The walk now follows only real
   descriptors.

Both were defects in the verifier, not the archive. Recording them because a restore test that
has never failed is not evidence that it works.

### Regression tests — both defects pinned, plus strict descriptor validation

`scripts/mr002_custody/test_recovery_verifier.py`, **15/15 passing**, no AWS and no network:

| Defect / requirement | Test |
|---|---|
| Path normalization | `test_regression_path_normalization_variants` (relative and `./` forms) |
| Path normalization — false assurance | `test_regression_empty_archive_never_passes` |
| Descriptor type-confusion | `test_regression_config_blob_is_not_walked_as_a_descriptor_graph` |
| Descriptor type-confusion — reachable | `test_regression_malformed_descriptor_inside_reachable_graph_is_rejected` |
| Size-to-content agreement | `test_size_to_content_disagreement_is_rejected` |
| Media-type agreement | `test_media_type_disagreement_is_rejected` |
| Pathname vs digest | `test_misnamed_blob_is_rejected` |
| Unreferenced objects | `test_unreferenced_object_is_rejected` |
| Missing objects | `test_missing_referenced_object_is_rejected` |
| Wrong image entirely | `test_wrong_bound_identity_is_rejected` |
| Wrapper hash | `test_wrapper_hash_mismatch_is_rejected` |
| Malformed layout | `test_missing_index_json_is_rejected` |
| Scope discipline | `test_verifier_never_claims_to_satisfy_requirement_7` |

The type-confusion fixture carries a config blob with a real top-level `config` key
(`Env`/`Cmd`), which is precisely the shape that once raised `KeyError: 'digest'`.

⚠ The malformed-descriptor test was **rewritten**. The earlier version passed only because the
junk object was *unreferenced* — the unreferenced-object check caught it, while a malformed
descriptor **inside the reachable graph** would still have been silently skipped. The manifest is
now rewritten so the bad descriptors are genuinely reachable, and the test asserts all four
rejection reasons individually.

---

## 4a. Custody classification

Stated truthfully, per the recovery adjudication. The workstation archive is **not** promoted
to "offline" merely because it sits outside the cloud-sync root.

| Classification | Current state |
|---|---|
| `PRIMARY_CUSTODY_COPY` | ECR by immutable digest |
| `STAGED_ONLINE_RECOVERY_COPY` | this archive — routinely connected workstation, unencrypted |
| `INDEPENDENT_OFFLINE_RECOVERY_COPY` | **NOT YET CREATED** |
| `INFORMAL_RUNTIME_COPY` | local Docker cache — **not credited** |

Also recorded machine-readably in `MR002_ExternalRecoveryCopy_v1.0.json`.

---

## 5. Offline re-verification

```
python scripts/mr002_custody/export_recovery_copy.py --verify <path-to>/mr002-evaluator-p5-recovery.tar \
    sha256:c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a
```

The optional second argument asserts the wrapper hash. The verifier implements the full
custodian review procedure — **a successful extraction is deliberately not sufficient to pass**:

- wrapper archive hash verified against the expected value
- **every blob pathname checked against its content digest** (keying only by computed hash
  would silently accept a misnamed blob)
- complete reachability traversal from the bound index
- **unreferenced unexpected objects rejected**
- bound semantic digest matched exactly against P5
- nonzero object-count assertion
- **every reachable descriptor strictly validated** for object type, digest syntax
  (`^sha256:[0-9a-f]{64}$`), media type, and size
- **size-to-content agreement** — a declared size contradicting the blob fails
- **media-type agreement** — a descriptor's declared type must match the content's own
- explicit failure on missing, duplicated, malformed, or mistyped graph objects

Uses **no network and no AWS access** — proven by running it with credentials, profile, region,
and home directory stripped from the environment:

```
outer (wrapper)  : sha256:c3cf3b9e...
inner (semantic) : sha256:60b15568...
objects present  : 13   referenced: 13
bound identity   : MATCHES
VERDICT: PASS  (offline; no network, no AWS; NOT an execution gate)
```

This is what the custodian runs against the medium at each scheduled review. It works
air-gapped. **It is not an execution gate and does not satisfy Requirement 7.**

### Correction applied 2026-07-25 — the offline path no longer requires the AWS SDK

The disclosed limitation that `--verify` still needed `boto3` **installed** is now closed. The
module imported the SDK at module scope for the export path, so on a genuinely clean machine the
custodian's procedure failed at **import**, before any verification logic ran — the one check
performed against the medium was unavailable precisely where it is most needed. Stripping
credentials from the environment, as demonstrated above, does not exercise this: it proves the
verifier makes no AWS *calls*, not that it runs without the SDK *present*.

The import now lives at its single point of use inside the export path. The verification path is
pure standard library, and `--verify` is dispatched before that path is ever reached.

Re-verified on a workstation with **no `boto3` and no `botocore` installed at all** — the exact
condition that previously failed — against the real staged archive:

```
outer (wrapper)  : sha256:c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a
inner (semantic) : sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9
objects present  : 13   referenced: 13
bound identity   : MATCHES
VERDICT: PASS  (offline; no network, no AWS; NOT an execution gate)   exit 0
```

Pinned by `test_offline_verification_does_not_require_the_aws_sdk`, which reimports the module
from source with `boto3`/`botocore` forced unimportable and runs a full verification through it,
so the guarantee holds even in an environment where the SDK happens to be installed.

This restores **invariant 4** to its full meaning: the offline verifier depends on neither
registry access nor the client library used to reach it. Verification logic, archive bytes, both
identities, and the object graph are **unchanged** — this is an import-placement and test change
only. No custody status changes: independent offline custody and account-loss recovery remain
**UNSATISFIED**, Requirement 7 remains **SPECIFIED_NOT_IMPLEMENTED**, and
`validation_authorization` remains **false**.

⚠ Separately noted, not a defect: `custody_monitor.py` legitimately requires the SDK — it is an
AWS-side Lambda, not part of the custodian's offline procedure — so its tests do not collect on
an SDK-free workstation. The offline path must never acquire that dependency; the monitor may.

---

## 6. Owner actions still required — the control is NOT yet complete

I produced and verified the archive. I cannot write removable media, and I must not handle
encryption secrets. Remaining:

- [ ] Encrypt the archive at rest on the destination medium (owner-held key; **do not** record
      the key, passphrase, or recovery phrase in any governance artifact)
- [ ] Write to genuinely independent removable media
- [ ] Confirm the medium is **normally disconnected**
- [ ] Run the §5 offline verification **from the medium** and record the verdict
- [ ] Complete the custodian record in §7
- [ ] Delete the staging copy at `C:\LLM-RAG-APP\mr002_recovery_staging\`, or explicitly accept
      it as a second online copy

### Staging disclosure

The staging directory is **outside the git repository** and **outside the OneDrive root**
(`C:\Users\jayw0_ithkvux\OneDrive`), so it is **not cloud-synchronized**. The 44 MB archive was
deliberately **not committed to git**. It is, however, an unencrypted copy on a routinely
connected workstation, which is why deleting or explicitly accepting it is on the list above.

### The laptop image copy is still not creditable

The local Docker daemon copy remains **not** an independent offline copy: it is routinely
online, unencrypted, and reachable with credentials available from the same workstation. Per
the adjudication it must not be credited unless deliberately isolated, encrypted, and removed
from routine online use.

---

## 6a. Governing invariants (ratified by the recovery-verifier adjudication)

These are the standing invariants of the recovery-verification path. Any future change that
would violate one is a stop-the-change event.

1. There is **exactly one** authoritative archive-verification implementation
   (`verify_archive()`).
2. Archive creation **fails** unless that verifier returns PASS.
3. Offline media review invokes the **same** verifier — no weaker build-time variant exists.
4. The build-time registry cross-check is **additional evidence, not an offline dependency**;
   the offline verifier never requires registry access.
5. **Every reachable OCI descriptor** is schema- and content-validated (type, digest syntax,
   media type, size, size-to-content agreement, media-type agreement).
6. **No unreferenced object** is accepted.
7. **Empty traversal cannot pass.**
8. Review copies must remain **byte-identical** to their authoritative sources
   (enforced by `test_review_copies_in_sync.py`, exclusions governed by an explicit allowlist).
9. No review-copy change can affect the bound `evaluator/` §4 inventory.
10. **No passing recovery verification satisfies Requirement 7 or authorizes execution.**

---

## 7. Custodian record — COMPLETED BY THE OWNER 2026-08-10

**Status: COMPLETE.** Recovery-media custodian appointed by the owner (Jay Wang) on
2026-08-10, following the A1–A4 media write and the §5 verification run against the medium.

| Field | Value |
|---|---|
| Human custodian | **Jay Wang** (owner) — recovery-media custodian |
| Media identifier | MR-002 recovery, offline (non-sensitive label) |
| Physical storage class | offline removable, normally disconnected |
| Encrypted at rest | **yes** — VeraCrypt volume-level, AES / SHA-512 *(method only)* |
| Creation date | 2026-07-22 (archive), 2026-08-10 (media write) |
| Last verification date | **2026-08-10T22:24:15Z** — §5 verifier run against the medium, VERDICT: PASS |
| Review cadence | quarterly |
| Normally disconnected | **yes** — medium dismounted and physically disconnected 2026-08-10; absence confirmed by device enumeration |
| Any copy cloud-synchronized | Staging copy: **no**. Medium: **no**. |

**Never record in this table:** encryption keys, passwords, recovery phrases, device serial
numbers, or precise physical storage locations. *(None are recorded above.)*

### Verification evidence, 2026-08-10

Run from the medium, not from staging. Offline: no network, no AWS.

| Check | Result |
|---|---|
| Outer (wrapper) digest | `sha256:c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a` |
| Inner (semantic) digest | `sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9` |
| Objects | 13 present / 13 referenced |
| Bound identity | **MATCHES** |
| Verdict | **PASS** |

Verdict record (outside the repository, per ADR 0050 — generated evidence is not Git-resident):
`C:\LLM-RAG-APP\MR002_WPA_A4_Verdict_20260810.txt`. Reproducible at any time by re-running
`scripts/mr002_custody/recovery_media_workflow.ps1 -Step A4` against the mounted medium.

### A6 — staging disposal, completed 2026-08-10

Both unencrypted copies were deleted from `C:\LLM-RAG-APP\mr002_recovery_staging\` — the 42.4 MB
`mr002-evaluator-p5-recovery.tar` **and** the unpacked `mr002-evaluator-p5-oci/` directory
(84.7 MB → 0 MB of plaintext evaluator). Only `MR002_ExternalRecoveryCopy_v1.0.json`, the record,
remains. Deletion was gated on the medium copy verifying PASS **after a full
disconnect/reconnect cycle**, not merely at write time.

⟹ `INDEPENDENT_OFFLINE_RECOVERY_COPY` = **CREATED**. Recovery from ECR loss is **SATISFIED**.
WP-A is closed and Execution Order Step 1 is complete.

### ⚠ This appointment does not resolve the operational custodian

The role named above is the **recovery-media** custodian, accountable for the encrypted
offline archive: the physical medium, its disconnection, and its scheduled offline
re-verification.

It is **not** the **operational** custodian, which is accountable for the sealed validation
partition — producing P6–P9 and P11 as runtime evidence and attesting the partition was never
opened. That is a separate appointment made at Execution Order Step 2, recorded in
`MR002_OperationalCustodian_Appointment_v1.0.json`.

The owner has appointed **the same individual to both roles**, which is reasonable at this
scale — but only because it is recorded explicitly in **both** places. Naming a custodian here
never, by itself, satisfies Step 2.

### Scope

Governing invariant 10 applies unchanged: no passing recovery verification satisfies custody
Requirement 7 or authorizes execution. `validation_authorization` remains **false** at `_rev 0`.

---

## 8. Boundaries honored

| Prohibited | Status |
|---|---|
| Modify the custody ECR repository | **NOT DONE** — read-only API calls only |
| Implement Requirement 7 | **NOT DONE** |
| Enable S3 Object Lock | **NOT DONE** |
| Apply the proposed IAM role | **NOT DONE** |
| Begin P6–P13 | **NOT DONE** |
| Access validation, OOS, or sealed data | **NOT DONE** |
| Publish keys, passphrases, serials, or physical locations | **NOT DONE** |
| Treat the laptop copy as independent | **NOT DONE** — explicitly discredited in §6 |

The custody repository was verified unchanged throughout: the daily monitor continues to report
11/11 PASS and the single-artifact invariant holds.

---

## 9. Standing state

P5 SATISFIED · custody requirements 1–6 SATISFIED · CloudTrail and event detection implemented ·
scheduled monitor implemented · **Requirement 7 SPECIFIED_NOT_IMPLEMENTED** · **recovery from
ECR loss: archive produced and verified, physical placement pending — still UNSATISFIED** ·
P6–P13 unchanged · validation partition closed · single opening unconsumed · OOS under DENY ·
`validation_authorization = false`.

**Stop point reached.**
