# ADR-0043 WS5 — Terminal Disposition Record (2026-08-29)

| Field | Value |
|---|---|
| Record id | `ADR0043-WS5-TERMINAL-DISPOSITION-20260829` |
| Status | **CLOSED** — evidence preserved · volume deleted · fleet audit green |
| Workstream | ADR-0043 WS5 (`adr0043-canary-ws5-52b3ff136196`) |
| Type | Governance record — **indexing and discoverability only** |
| Date | 2026-08-29 |

---

## 1. What this document is, and what it is not

**WS5 was already closed** by the preservation and deletion proof recorded in versioned S3 and
summarised below. That closure rests on the S3-governed artifacts, their `VersionId` pins, and the
verified AWS state — **not on this file**.

This record exists so the outcome is discoverable in Git alongside the authorization it concludes.
**Merging it does not condition, gate, complete, or reopen the closure.** If this PR were never
merged, WS5 would remain closed on exactly the same evidence.

This document contains no implementation change, no CI or audit allowlist entry, no IAM change, and
no unrelated cleanup.

---

## 2. Terminal disposition

`vol-0710769fb6981102d` (20 GiB gp3, encrypted, `us-east-1b`, created 2026-08-03T01:05:33Z) — the WS5
evidence volume retained deliberately through the 2026-08-18 instance termination — was **deleted
2026-08-29T19:01:11Z** after its entire contents were proven represented in durable storage.

Sequence, as executed:

```
read-only inspection + census  ->  sufficiency gate FAILED (unadjudicated residue found)
  ->  owner adjudication: preserve the residue, prove it, then delete
  ->  6 files preserved to versioned S3 + read-back verified by VersionId
  ->  terminal reconciliation 8,589/8,589 files, 92,341,092/92,341,092 bytes  PASS
  ->  volume DELETED 2026-08-29T19:01:11Z  ->  InvalidVolume.NotFound
  ->  deployed fleet audit re-run: PASS on all four checks
```

Post-state verified: volume absent; account holds **zero** orphaned EBS volumes; both temporary
inspection hosts terminated with their root volumes auto-deleted; **no snapshot was created**; the
fleet audit returned green **naturally**, with no volume allowlist entry and no suppression.

---

## 3. Preservation receipt — the authoritative record

The complete provenance record, including per-file paths, sizes, SHA-256 values, source volume
identity, capture method, read-back proof, and the evidentiary interpretation, is the receipt:

| | |
|---|---|
| Bucket | `adr0043-ws5-evidence-219024422756-us-east-1` (versioned · SSE-AES256 · all public-access blocks on · `DeletionPolicy: Retain` · no lifecycle expiration) |
| Key | `residual/20260829/PRESERVATION_RECEIPT.json` |
| **VersionId** | **`1faDOhXZBpX09PmjuSiobw6O_OLL0W4I`** |
| Size | 8,749 bytes |

**Cite the `VersionId`, not the key alone.**

### Preserved objects

All six stored byte-verbatim — no rewriting, no normalisation — under `residual/20260829/`:

| File | Bytes | SHA-256 | VersionId |
|---|---:|---|---|
| `STAGE1_MARKER.json` | 644 | `fac737ba9284aee770d13ef4896dfcb104ebc31ba20b8ad4ba41811e7491440d` | `LzT64cVehcp2_wUcPpY_RbYIb6YVRxW6` |
| `build.log` | 46,211 | `f4125e1e2f889736bf77d7c1d90bc3e1d9ec8cdb181ac795052bbf5df980a199` | `CxKjKL0zepq6J4y9JIqv1LcveHh7x1YK` |
| `build-ed604d49ef9e.log` | 47,276 | `cf0ce267c2e08d7baa77e1a0ceb6f06c10d0343128238428844ec1f849346d1b` | `.suNNPkdcUV.T994qsbSJ_XXjR1K2vZh` |
| `build-1880fcdb05e3.log` | 47,355 | `0d263b6635a9d20b54686c65d6aba6efcf0b32d5f885ab2ea338895f070c1a37` | `cPwdT_14KUXcfTomcD1aXc2SSo8IP.P3` |
| `candidate-build-a91fe75c041b.log` | 47,649 | `75a7a5e0bae2f22006879457561b73af8bec366372da0bec72420c8fd8b5bbae` | `82S86RM_Pes674KsQubHReAV0JYz5qze` |
| `push.log` | 808 | `a5ed7f8ca330bf05c142bc1b9837b96749cf5a996c547ae26887d6c10519bd17` | `ePpa7yhzP4KwTdauRWWEpxfP5akM89Lh` |

Verification chain: on-volume SHA-256 → transport (tar → gzip → base64 over SSM, encoding only) →
reassembly verified against `tar.gz` SHA-256
`a72385f9f4aede9a35d9354fda428fd7894140d50dddb86b449834b2e18f2206` → per-file SHA-256 re-verified →
upload with `--checksum-algorithm SHA256` → **independent read-back by `VersionId` with
`--checksum-mode ENABLED`**, S3's own server-side checksums decoding to the same digests.

**Non-mutation:** the volume was mounted read-only behind a kernel-level `blockdev --setro`
(`--getro == 1`, a write attempt returned 0 bytes) with `mount -o ro,noload`. The whole-device
SHA-256 `70633e7a12fdff552854c77825b03e55a5542d4d60fc612ad3efa62e70d25061` was identical at
inspection start, inspection end, capture start, and capture end.

---

## 4. Full-volume reconciliation

| Population | Files | Bytes | Durable representation |
|---|---:|---:|---|
| `src/tree` | 2,125 | 21,150,808 | `source/AI-TRADING-APP-7342ebbd….tar.gz` VersionId `8ah6E5VizAZfmFfI8ihgKtuOXz8hxcXb` — byte-and-path identical |
| `src-ed604d49ef9e/tree` | 2,137 | 21,345,154 | `source/…ed604d49….tar.gz` VersionId `O_nxAkXnidHU9YYFV82h_mUPj8qq2idE` — byte-and-path identical |
| `src-1880fcdb05e3/tree` | 2,139 | 21,378,053 | `source/…1880fcdb….tar.gz` VersionId `dEDhokQBpFY8u9AyF7KM0aHX1wDnEEpu` — byte-and-path identical |
| `candidate-a91fe75c041b` | 2,181 | 28,275,967 | shallow clone, working tree clean at `a91fe75c041be25f116c9590d1574481443d2a42`, an **ancestor of `origin/main`**; untracked 0, ignored 0 |
| `evidence/stage_c_20260804T152020Z.json` | 1 | 1,167 | `stage-c/…` VersionId `zsfg8QPAWz0lVu3ldKWF3n6OCvifd6yA`, sha256 `79011ea4…463` |
| residual × 6 (preserved 2026-08-29) | 6 | 189,943 | `residual/20260829/` — see §3 |
| **Total** | **8,589** | **92,341,092** | |

Against the census: **8,589 / 8,589 files · 92,341,092 / 92,341,092 bytes · 0 unexplained artifacts ·
0 preservation gaps · 0 ambiguous residue.**

---

## 5. Evidentiary interpretation preserved with the artifacts

- **`STAGE1_MARKER.json` is not runtime proof of non-exercise.** Its four `false` flags
  (`database_created`, `application_deployed`, `migration_applied`, `broker_credential_attached`)
  are **template literals** hardcoded in the CloudFormation UserData of stack
  `adr0043-canary-ws5-52b3ff136196` (preserved at `hashes/adr0043-canary-ws5-stack.yaml`
  VersionId `mVsmPthz2hsAePEzZL2vuqdE7FN0uCDB`, lines 238–256). They are not runtime observations.
  The non-exercise finding rests on the 2026-08-18 live read-only census, recorded separately.
- **Unique field:** `bootstrap_completed_utc = 2026-08-03T01:06:26Z` is the only field not derivable
  from the preserved template. Preserved as historical metadata; this does not elevate the marker's
  evidentiary weight.
- **Secret scan:** all five transcripts scanned 2026-08-29 — **zero** pattern hits.
- **Image-digest bindings are independently preserved:**
  `sha256:37e52bc941cdbfdaad28a69ae2d2803d0625fbe964276bef734308174d94ccec` (source commit
  `7342ebbd…`) and `sha256:fc390cf5cb5fbd43d9d4c6bc256b19db9c7607a3b011d51dc8e28f740e30f31f`
  (`candidate-a91fe75c041b`) both appear in
  `ecr-inventory/ecr_adr0043-canary-ws5_inventory_20260819T003711Z.json` VersionId
  `qkFWzWL6a1jLDfrIebik2HRqEf6HkvF7`.

---

## 6. Governance boundary — do not misread this later

**`ADR0043-WSS-EVIDENCE-PRESERVATION-001` §6 is NOT amended.** That authorization covered **only**
the single Stage-C file, and the historical record continues to say exactly that. Its §6 —
*"Preserving anything beyond the single file in §1 — Not authorized"* — stands unchanged.

The six residual files were preserved under a **new owner adjudication made on 2026-08-29, after
their discovery** during the sufficiency reconciliation. They are **not** declared economically or
operationally material, and are **not** retroactively declared part of the original preservation
authorization. They were preserved because they were found as previously unadjudicated residue on an
evidence-retained volume, and preservation was the least destructive way to close that ambiguity.

Two transferable lessons, recorded because they generalise:

1. **A narrow-scope authorization does not triage a whole volume.** Because §6 limited preservation
   to one file, there was **no excluded/omitted list to evaluate** — the remaining artifacts were
   never adjudicated at all. *Unadjudicated is not the same as excluded*, and a match over the
   artifacts a process included says nothing about what it was never responsible for.
2. **The earlier gap list was incomplete.** The 2026-08-18 census named the five build transcripts
   and missed `STAGE1_MARKER.json`. The fail-closed gate is what surfaced it.

No snapshot was authorized or created. No retention exception exists. No fleet-audit allowlist entry
or suppression was added.

---

## 7. Explicitly out of scope

The following are **separate, pre-existing cleanup obligations**. They are named here only so a
future reader does not mistake them for WS5 items. **None of them qualifies, conditions, or reopens
WS5 closure**, and none is actioned by this record.

| Item | Nature | Disposition |
|---|---|---|
| Alpaca canary key `PA3E97RWHKQZ` | Security cleanup — **highest priority** | Broker-side revocation plus proof of revocation. The staged local copy was destroyed with the root volume on 2026-08-18; **destruction of the local copy is not equivalent to revocation.** |
| `ws5-transcript-rescue-role` / `-profile` | Infrastructure hygiene | Deletion candidate only after proving no instance-profile attachment, active consumer, policy dependency, or other governed use; then removed as a separate action. |
| `snap-089269153dc88d713` | Governance, not orphan status | Quarantined from generic cleanup. Needs its own explicit retain-with-policy or delete-after-sufficiency-proof adjudication before any sweep touches it. |

---

## 8. Program state

**ADR-0043 WS5: CLOSED / evidence preserved / volume deleted / fleet audit GREEN.**

Authorization lapsed unexercised (2026-08-18); compute retired; evidence custody now wholly in
versioned S3, with the originating EBS volume destroyed after proof of representation.
