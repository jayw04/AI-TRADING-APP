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

## 4. Restore test — and two real bugs it caught

**Verdict: PASS.** The test re-reads the archive from disk, re-hashes every blob, re-walks the
graph from `index.json`, and confirms the top-level digest equals the binding with no missing
or unreachable objects.

The test earned its place by failing twice before it passed:

1. **It reported all 13 objects missing.** The blob-path check required a leading slash
   (`/blobs/sha256/`) while tar arcnames are relative, so it matched nothing and would have
   reported PASS-shaped emptiness had the assertions been weaker.
2. **It crashed walking the graph.** An image *config* blob has its own top-level `config` key
   (container Env/Cmd) which is not an OCI descriptor. The walk now follows only real
   descriptors.

Both were defects in the verifier, not the archive. Recording them because a restore test that
has never failed is not evidence that it works.

### Regression tests — both defects now pinned

`scripts/mr002_custody/test_recovery_verifier.py`, **13/13 passing**, no AWS and no network:

| Defect / requirement | Test |
|---|---|
| Path normalization | `test_regression_path_normalization_variants` (relative and `./` forms) |
| Path normalization — false assurance | `test_regression_empty_archive_never_passes` |
| Descriptor type-confusion | `test_regression_config_blob_is_not_walked_as_a_descriptor_graph` |
| Descriptor type-confusion — robustness | `test_regression_malformed_descriptor_does_not_crash` |
| Pathname vs digest | `test_misnamed_blob_is_rejected` |
| Unreferenced objects | `test_unreferenced_object_is_rejected` |
| Missing objects | `test_missing_referenced_object_is_rejected` |
| Wrong image entirely | `test_wrong_bound_identity_is_rejected` |
| Wrapper hash | `test_wrapper_hash_mismatch_is_rejected` |
| Malformed layout | `test_missing_index_json_is_rejected` |
| Scope discipline | `test_verifier_never_claims_to_satisfy_requirement_7` |

The type-confusion fixture carries a config blob with a real top-level `config` key
(`Env`/`Cmd`), which is precisely the shape that once raised `KeyError: 'digest'`.

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

## 7. Custodian record — TO BE COMPLETED BY THE OWNER

Deliberately left blank. Naming a custodian is the owner's act, and per the earlier
adjudication a named operational custodian is still unresolved.

| Field | Value |
|---|---|
| Human custodian | *(to be named — a real accountable individual)* |
| Media identifier | *(non-sensitive label only — no serial numbers)* |
| Physical storage class | *(e.g. offline removable, normally disconnected)* |
| Encrypted at rest | *(yes/no — method only, never the key)* |
| Creation date | 2026-07-22 (archive), *(media write date)* |
| Last verification date | *(from §5, run against the medium)* |
| Review cadence | *(recommend quarterly)* |
| Normally disconnected | *(yes/no)* |
| Any copy cloud-synchronized | Staging copy: **no**. Medium: *(to be recorded)* |

**Never record in this table:** encryption keys, passwords, recovery phrases, device serial
numbers, or precise physical storage locations.

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
