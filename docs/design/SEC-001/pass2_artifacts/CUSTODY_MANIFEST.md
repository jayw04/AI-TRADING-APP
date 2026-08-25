# SEC-001 V3 — Pass-2 Reproducibility Artifacts: Custody Manifest v1.0

**Ruling:** `PASS2_REPRODUCIBILITY_ARTIFACTS — CUSTODY REQUIRED BEFORE TEARDOWN` (owner, 2026-08-25).

Custody of the execution artifacts of the Pass-2 byte verification, taken from `/root/pass2` on the
temporary investigation host **before** that host and its temporary volume were destroyed.

**Scope limit — this manifest binds artifacts only.** It states no conclusion, amends nothing, and
reopens nothing. `SEC001_V3_DefectF_ByteVerification_Pass2_v1_0.md` remains the sealed record of what
Pass 2 concluded; Pass 1 stays INTERIM; the §4.2.1 determination and the Defect-F ruling are
untouched.

---

## Bound artifacts

| file | bytes | sha256 |
|---|---:|---|
| `pass2b.py` | 10,264 | `4fc9cb8d41dd57ecc489a00defc5250c46da713074f18a4a72907ac12cbadfe9` |
| `pass2_report.json` | 26,576 | `b51f26615b3e08d7a71887c7470cfe993369d0e63598cd7b098ee8db5460eecf` |
| `mismatches.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `progress.log` | 1,546 | `abf3919fa55e99615c2fb23a11f5ede64795cb494e57ac6394a33f629a4df273` |

Every digest above was verified **identical to the file on the investigation host** before that host
was torn down. Custody used `* -text -diff` so the committed blobs are byte-exact and are not
subject to end-of-line translation.

---

## Relationship to the sealed Pass-2 record

| artifact | why it is retained |
|---|---|
| `pass2_report.json` | **The decisive one.** It individually enumerates all **108** orphan/residue artifacts with per-file `sha256`, `bytes` and `mtime_utc`. The Pass-2 record states only aggregates plus the single fragment-associated artifact, so this information is **not reconstructable from that record**. Destroying it would have reduced the evidence from individually reproducible to aggregate-only. It also carries the full `verification`, `byte_classes` and `torn_manifest_boundary` blocks in machine-readable form. |
| `pass2b.py` | The exact script whose execution produced the above. Retained here so reproducibility does not depend on a separate working-tree copy. `sha256 4fc9cb8d…` is the identity referenced by the run. |
| `mismatches.jsonl` | Run output. Its **zero-byte** state — `e3b0c442…`, the SHA-256 of the empty file — is affirmative evidence that zero mismatches were recorded, rather than an absence of output. |
| `progress.log` | Execution trace (file counts, cumulative bytes, throughput). Ancillary rather than decision-bearing; retained because it is part of the actual run. |

## Provenance

- Produced by the Pass-2 run on temporary investigation host `i-034baf111469c310c`, reading the
  temporary copy `vol-0e526053c6bef5887` (restored from `snap-01a33687b1588626b`) mounted
  `ro,nodev,noexec,relatime,norecovery`.
- The Pass-2 run wrote **only** to the host's own root volume; the evidence copy was never written.
  Confirmed after the run: filesystem `clean`, `Last write time` and `Lifetime writes` unchanged from
  the values recorded before the original host was stopped.
- The original failed-epoch volume `vol-0cf17223018c3a1c6` and snapshot `snap-01a33687b1588626b`
  were not touched at any point.

## Result these artifacts attest

```
checked 31,646 · matched 31,646 · mismatched 0 · missing 0 · length mismatches 0
files 31,030 hashed / 31,030 matched · 94,290,412,113 bytes
collisions 616 total / 616 verified against shared digest / 0 failed
```
