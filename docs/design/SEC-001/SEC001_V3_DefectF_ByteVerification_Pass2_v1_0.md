# SEC-001 V3 — Defect F Byte Verification, Pass 2 v1.0

## FULL MANIFEST-TO-DISK HASH VERIFICATION OF THE PRESERVED v1.4 FAILURE STATE

**Status:** Pass 2 of the owner's 2026-08-25 post-snapshot authorization. **Read-only verification
only.** No remediation, no deletion, no deduplication, no reconstruction, no successor design.
Supersedes nothing; the Pass-1 record stands unmodified in its INTERIM state, as directed.

Times in **US Central (CDT, UTC−5)**; sealed Z values retained alongside.

---

## 1. Execution

| item | value |
|---|---|
| source | read-only copy `vol-0e526053c6bef5887`, restored from `snap-01a33687b1588626b` |
| mount | `/mnt/evidence` — `ro,nodev,noexec,relatime,norecovery`, **re-verified after the run** |
| host | `i-034baf111469c310c` (temporary investigation host) |
| original volume | `vol-0cf17223018c3a1c6` — **never mounted, never written** |
| runtime | 65.0 min, 24 parallel readers |

The first attempt ran single-threaded at ~4.5 MB/s — snapshot lazy-load latency, not throughput —
and was projected at ~6 h. It was stopped and relaunched with parallel reads; the computation and
comparison logic are identical and the comparison remains serial and deterministic. The discarded
attempt had already verified 1,500 files with zero mismatches.

---

## 2. RESULT — 100% manifest-to-disk agreement

```
checked_records                31,646        matched_records         31,646
mismatched_records                  0        records_with_missing_file    0
files_hashed                   31,030        files_matched           31,030
files_mismatched                    0        files_missing                0
length_mismatch_records             0
parser_body_equals_artifact    31,646        parser_body_differs          0
bytes_hashed           94,290,412,113
mismatches.jsonl                    0 lines
```

Every complete manifest record's recorded `sha256` equals the SHA-256 of the bytes actually on disk
at its `artifact_path`. Every recorded `byte_length` equals the actual length. `parser_body_sha256`
equals the artifact digest for **all** 31,646 records — the parser-facing bytes and the retained
artifact are the same object throughout.

---

## 3. Defect G — **CLOSED / REFUTED**

Pass 1 established that the 616 duplicated accessions each carry two records claiming the *same*
digest, but could not show that the single surviving on-disk object actually *is* that digest.
Pass 2 closes the gap:

```
collision_paths_total                          616
collision_paths_verified_against_shared_digest 616
collision_paths_failed                           0
```

> **Defect G is refuted, not merely narrowed.** The path collision is real — 616 accessions were
> written twice to one accession-keyed path — but it destroyed no evidence. Each shared object
> hashes to the digest both of its records claim. No record's retained decision evidence is
> non-reconstructable on this account.

This is the disposition Pass 1 could not reach and explicitly deferred.

---

## 4. Torn manifest boundary — bounded, and its artifact VERIFIES

```
manifest_total_bytes                        42,348,544
last_complete_record_end_offset             42,347,719
trailing_bytes_after_last_complete_record          825   <- exactly the fragment, nothing else
fragment_sha256      38cd5aa375c6da3944d3ae8379aa02ef59e0ebea2c0a7501f2248b7eda098095
complete_prefix_sha256
                     772bc5ad538b198d9e981d504e3757ee160e88cd690402a245684db09a4ccbf2
```

`complete_prefix_sha256` is a verifiable digest over the 31,646 complete records **only**, so the
admissible portion of the manifest now has a stable identity independent of the damaged tail. The
825-byte fragment is preserved exactly and was read, never modified, completed, or reconstructed.

**Association from the fragment's own surviving contents** (authorized; no reconstruction):

| field | value |
|---|---|
| `accession` | `0000833444-23-000030` |
| `acquisition_status` | `HEADER_INDEX` |
| `byte_length` / `parser_body_length` | 24,490 / 24,490 |
| `parser_body_sha256` | `b12d0337…e913dda9` |
| artifact on disk | 24,490 bytes, sha256 **`b12d0337…e913dda9`** — **EXACT MATCH** |
| artifact status | present as an **orphan** (not referenced by any complete record) |

The fragment truncated after `request_accept_encoding`, so its own `sha256` field was never written
— but `parser_body_sha256`, which sorts earlier, survived, and it matches the artifact byte-for-byte.

> **The record that ENOSPC destroyed still has a fully written, digest-verifiable artifact.** The
> artifact was written and closed *before* the manifest line was appended, and the append is what
> failed. This is direct confirmation of the write-order that Pass 1 could only infer.

---

## 5. Byte-class census — the consumption is intrinsic to retention, not incidental

```
class                              bytes            files     share
published_decision_artifacts  94,290,412,113       31,030    99.525%
orphan_finalized_artifacts       385,549,314           59     0.407%
decision_byte_manifest            42,348,544            1     0.045%
observations                      19,411,593          369     0.020%
temporary_artifacts_tmp            2,883,584           49     0.003%
crawl_state                          100,021            1
build_segments                        99,418          369
runner_control_and_logs               70,360            4
TOTAL_accounted               94,740,874,947       31,882
```

Reconciles exactly with Pass 1: published + orphan `.bin` = 94,290,412,113 + 385,549,314 =
**94,675,961,427**, the retained-bytes figure Pass 1 measured independently.

**99.53% of the epoch is published decision artifacts.** Logs, control files, state, build segments
and temp files together are **0.003%**. Against ~39.5 MB actually required to reach the SIC
decisions, the published corpus is a **~2,385× amplification**.

> **Answering the question this pass existed to settle:** the ~89 GiB consumption is **not** an
> incidental storage problem and **not** attributable to any class other than retained decision
> bytes. It is produced by the interaction of an intentional evidence invariant (retain the exact
> bytes behind every decision) with an acquisition bound that was never enforced on the response.
> The retention invariant is sound; **Defect F is an implementation defect, not a consequence of
> the frozen acquisition design.** Bounded acquisition would have retained tens of megabytes.

---

## 6. Incidental observation — unit/observation counts reconcile

374 terminal units resolve to **368 distinct CIKs** (a CIK may carry more than one ticker, and
`unit_key` is `CIK:TICKER`). Observation files number **369** = 368 completed CIKs + 1 for the
in-flight unit `0000833444`. `build/segments` likewise holds 369. No anomaly; recorded so the
369-vs-374 difference is not later mistaken for missing output.

---

## 7. What Pass 2 confirms, and what it does not

**Confirmed:**

- Pass 1's storage interpretation survives contact with the bytes — attribution, the 557
  reconciliation, and the write-atomicity reading all hold.
- The Pass-1 hypothesis held back as provisional is now supported: **no published `.bin` is
  corrupt**, and the only damaged object in the entire 94.7 GB epoch is the 825-byte manifest tail.
  Even that record's artifact is intact and verifiable.
- Defect G: closed/refuted.

**Not established, and out of scope here:**

- ⛔ Nothing about the **correctness of the SIC classifications** themselves. Pass 2 proves the bytes
  on disk are the bytes the manifest claims; it does not evaluate what those bytes mean. Byte
  integrity is not evidentiary sufficiency.
- ⛔ No assessment of pinned-client streaming capability (the §4.2.1 prerequisite).
- ⛔ No coverage, no economics.

**Unchanged by this pass:** the 374 units remain preserved nonconforming acquisition evidence. Byte
integrity does **not** make them admissible — they were produced under a violated acquisition bound,
and the successor epoch still starts at **0/1,167**.

---

## 8. Program state

```
v1.4 crawl        HALTED at 374/1,167       successor credit  0
coverage          NOT EVALUATED             economics         NOT EVALUATED
5b26ffa2...       UNSPENT
Defect F          OPEN - repair not authorized; streaming prerequisite unresolved
Defect G          CLOSED / REFUTED
Defect-F ruling   UNTRACKED, UNCOMMITTED, unmodified
```

The Defect-F ruling's §7.1 now has its full disposition: original hypothesis → investigated →
mechanism refuted by Pass 1 → byte-level closure by Pass 2. Per the owner's direction that history
is to be **preserved as a sequence, not rewritten**, that lineage belongs in the ruling when it is
finalized. **No edit to the ruling has been made.**
