# SEC-001 V3 — Defect F Storage Forensics, Pass 1 v1.0

# ⚠ PASS 1 / INTERIM / PASS 2 REQUIRED ⚠

> **This document is an INTERIM record.** Its conclusions rest on filesystem metadata and
> manifest-internal consistency. **No published artifact bytes have been independently hashed
> against their recorded digests.** Until Pass 2 completes that verification, every statement here
> about artifact integrity is **provisional** and must not be cited as an established byte-level
> finding. This record is placed in custody in this interim state deliberately, and is **not to be
> rewritten** afterwards — Pass 2's findings belong in their own record.

## READ-ONLY ACQUISITION/STORAGE FORENSICS ON THE PRESERVED v1.4 FAILURE STATE

**Status:** Pass 1 of the owner's 2026-08-25 post-snapshot authorization. **Storage forensics only.**
No coverage, no economics, no Defect-G hash verification, no streaming-capability assessment — those
are pass 2 and are not started.

**Scope discipline:** the original volume `vol-0cf17223018c3a1c6` was **not** touched. All work below
was performed on a temporary volume restored from `snap-01a33687b1588626b`, attached to a separate
host, mounted read-only with no recovery.

Times in **US Central (CDT, UTC−5)**; sealed Z values retained alongside.

---

## 1. Investigation environment

| item | value |
|---|---|
| investigation host | `i-034baf111469c310c` (`sec001-v3-defectF-investigation`, t4g.medium, us-east-1c) |
| plane | `research-no-broker-capability` — no broker credentials, no EDGAR activity |
| investigation volume | `vol-0e526053c6bef5887` — 100 GiB gp3, restored from `snap-01a33687b1588626b` |
| attachment | `/dev/sdf` → `/dev/nvme1n1` |
| mount | `/dev/nvme1n1p1` → `/mnt/evidence`, options **`ro,nodev,noexec,relatime,norecovery`** |
| write test | `touch` → `Read-only file system` — **read-only confirmed** |

### Pre-mount filesystem state (superblock read, no mount)

```
Filesystem state:   clean
Journal start:      0            <- journal empty; NO recovery was required or performed
Block count:        25,951,995   (4 KiB blocks)
Free blocks:        4,279        (~17.5 MB)
Last mount time:    Mon Aug 24 00:34:56 2026 UTC
Lifetime writes:    140 GB
```

The filesystem was **clean** — the instance stop flushed and unmounted normally. `norecovery` was
therefore belt-and-braces, not a workaround for a dirty journal. **No fsck, no journal replay, no
repair, no truncation was performed at any point.**

> ⚠ **UUID collision hazard, recorded for whoever repeats this.** The restored copy carries the
> *same* filesystem UUID (`1ec57f43-1c53-452b-a2eb-d8c7dedcb7ee`) and label (`cloudimg-rootfs`) as
> the investigation host's own root, because both derive from the same base AMI. Mounting by UUID or
> LABEL can resolve to the wrong device. **Mount by explicit device path only.**

---

## 2. Attribution of the ~94.7 GB — the growth is the v1.4 crawl, and nothing else

Whole-filesystem census (96 GB total):

```
  89 G   opt/workbench/sec001-v3/crawl-v1.4/raw          <- ALL of the growth
 3.4 G   opt/sec001-data          (factor store, built Aug 23 07:34 PM CDT - PRE-DATES the crawl)
 2.5 G   usr
 774 M   var          370 M opt/sec001          356 M tmp          100 M root
```

Within the crawl tree, every other epoch is negligible:

```
crawl-v1.4/raw                       89 G
  .../source_decision_bytes          89 G   <- the retention corpus
  .../observations                   20 M
crawl-v1.4/build                    1.5 M
crawl-v1.2 (failed canary)          364 K
crawl    (v1.1 failed canary)       196 K
diagnostics/defect-a-...             44 K
driver/ (4 identities)              1.3 M
frozen-src/ (2 trees)               280 K
```

**Timestamps confine the growth to the v1.4 epoch exactly.** Artifact mtimes run from
**2026-08-24 20:55:41Z** (the ABT canary, segment 0) to **2026-08-25 04:17:30Z** (ENOSPC), with the
bulk crawl segments beginning 21:22:36Z. No file outside that window contributes materially, and no
non-crawl process wrote at scale.

> **Conclusion:** the unexpected consumption is attributable **solely** to
> `crawl-v1.4/raw/source_decision_bytes`, i.e. to Defect F. No competing explanation survives —
> not another process, not log growth, not the pre-existing factor store.

Baseline headroom: non-crawl usage is ≈7 GB of the 96 GB volume, so ≈89 GB was available when the
epoch began, and the crawl consumed all of it in ≈6 h 55 m across 374 units.

---

## 3. The 557 / 558 discrepancy — RESOLVED as **557**

```
complete, newline-terminated, parseable records   31,646
torn trailing fragment (no newline), 825 bytes         1
distinct accessions in the manifest               31,030
distinct artifact paths in the manifest           31,030   <- 1:1 with accession
.bin artifacts on disk                            31,089
all entries in the artifact directory             31,138   (= 31,089 .bin + 49 .bin.tmp)
manifest records whose artifact is MISSING             0
```

Exact reconciliation:

```
31,646 complete records
  − 616 duplicate records (same accession → same artifact path)
  = 31,030 distinct artifact paths
  +    59 orphan .bin (no manifest record)
  = 31,089 .bin on disk
31,646 − 31,089 = 557
```

> **557 is correct; 558 was an artifact of counting the torn fragment as a record.** It is a
> *partial* record, 825 bytes, with no trailing newline. `wc -l` on the preserved copy returns
> **31,646** precisely because the fragment is unterminated; a Python line iterator yields 31,647
> chunks. Both original measurements were right about different denominators, and the denominator
> that counts records is **31,646**.

---

## 4. Candidate Defect G — the mechanism I proposed is REFUTED; consequence NOT demonstrated

616 accessions carry exactly two manifest records each, sharing one accession-keyed artifact path.
So the collision is **real**. Its character, however, is not what §7.1 of the Defect-F ruling
hypothesised:

```
status pairs across the 616 duplicated accessions:
    (HEADER_TERMINATED, HEADER_TERMINATED)   361
    (HEADER_INDEX,      HEADER_INDEX)        255
    mixed index/ranged pairs                   0     <- the hypothesised mechanism does not occur

duplicate pairs recording DIFFERENT sha256                0
duplicate pairs recording the SAME sha256               616
manifest records whose artifact path is absent from disk   0
```

My §7.1 hypothesis was that *an accession acquired by both the index-headers path and the ranged
path overwrites its own artifact, so the survivor cannot match the earlier record's digest.* **No
such mixed pair exists.** Every duplicate is a repeat acquisition through the *same* path type that
produced a **byte-identical** result, and both records record the same digest — so the single
surviving artifact is consistent with both.

> **Defect G is NOT demonstrated by pass 1.** The duplication is real but currently appears benign:
> no record points at a missing artifact, and no duplicate pair disagrees about what its artifact
> should contain.

⚠ **This is a manifest-internal consistency result only.** It establishes that record A and record B
agree; it does **not** establish that the bytes on disk hash to that agreed digest. **That
verification is the actual Defect-G proof and belongs to pass 2**, which is not authorized to run
yet. Pass 1 does not close the question — it narrows it and refutes one mechanism.

---

## 5. New observations from pass 1

**5.1 — 108 orphan artifacts, all from the in-flight unit.** 108 directory entries have no manifest
record. Every one postdates the final terminal:

```
last terminal (unit 374, 0000833320:BR1)   2026-08-25 04:15:31Z
earliest orphan  0000833444-23-000030.bin  2026-08-25 04:15:44Z
latest orphan    ...0000912057-00-003391.bin.tmp  2026-08-25 04:17:30Z
orphans dated BEFORE the last terminal:    0
orphan bytes: 388,432,898   zero-byte: 47
```

The first orphan's accession matches the accession in the torn manifest fragment. These are the
acquisitions of **unit #375 (`0000833444`)**, which began after unit #374 completed and died before
its manifest lines could be appended. Accession prefixes vary (`0001047469`, `0000912057`,
`0001104659`) because an accession is keyed by the *filing agent*, not the subject company — so
prefix diversity is expected within one unit and is not evidence of a second writer.

**5.2 — 49 `.bin.tmp` files, and what they prove about the writer.** All 49 are ENOSPC casualties
confined to a 43-second window, **04:16:47Z → 04:17:30Z**, at the very end of the run. Their
existence shows the artifact writer uses a **write-to-temp-then-rename** pattern.

> **This is positive but PROVISIONAL evidence.** The temp→rename pattern is a strong indication
> that an interrupted artifact write fails safely — leaving a `.tmp` rather than publishing a
> truncated `.bin`. It is **not proof**. The inference runs from a *write pattern* to a *claim about
> published bytes*, and that gap can only be closed by independently hashing the published `.bin`
> objects against their recorded digests.
>
> ⛔ **Do NOT record "the only corrupt object in the epoch is the final manifest line" as an
> established fact on this evidence.** That conclusion is **pending Pass 2** and is stated here only
> as the hypothesis Pass 2 is designed to test.

What *is* established from metadata alone: zero `.tmp` files predate 04:16:47Z, so there is no
indication of silent write failures earlier in the run.

**5.3 — the stop record and torn line, unmodified.** Confirmed in place and untouched:

```
RUNNER_STOPPED.json   size=0   mtime 2026-08-25 04:17:30.616561905 UTC
torn fragment         825 bytes, ends mid-key at ..."response_content_enc
                      (an -index-headers.html record, request_accept_encoding "gzip, deflate")
```

---

## 6. What pass 1 did NOT do

- ❌ no hash verification of retained bytes against recorded digests (the Defect-G proof)
- ❌ no assessment of pinned-client streaming capability
- ❌ no coverage computation, no economics
- ❌ no resume, no terminal credit, no epoch repair, no successor crawl
- ❌ no modification of the stop record, the torn line, or any byte of the evidence
- ❌ no write of any kind to `vol-0cf17223018c3a1c6`

---

## 7. Standing temporary resources

| resource | disposition |
|---|---|
| `i-034baf111469c310c` | temporary investigation host — **running**, terminate after pass 2 |
| `vol-0e526053c6bef5887` | temporary read-only copy — **attached and mounted ro**, delete after pass 2 |

Left in place deliberately so pass 2 need not restore 100 GiB again. Both are tagged
`TEMPORARY-…-AFTER-INVESTIGATION`. Neither is evidence; the evidence is the original volume and the
snapshot.

---

## 8. Program state, unchanged by pass 1

```
v1.4 crawl        HALTED at 374/1,167       successor credit  0
coverage          NOT EVALUATED             economics         NOT EVALUATED
5b26ffa2...       UNSPENT
Defect F          OPEN - attribution now CONFIRMED against the filesystem
Defect G          candidate - one mechanism REFUTED, consequence NOT demonstrated, proof pending
Defect-F ruling   413 lines, UNTRACKED, UNCOMMITTED, unmodified
```

§7.1 of the Defect-F ruling will require correction before commit: it states the collision
hypothesis as though the mixed-path mechanism were the likely explanation. Pass 1 refutes that
mechanism. **That correction is not applied here** — the ruling document remains untouched pending
the owner's decision.
