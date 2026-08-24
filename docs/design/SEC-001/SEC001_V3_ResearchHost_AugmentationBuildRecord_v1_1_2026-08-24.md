# SEC-001 V3 Research Host — Augmentation Build Record v1.1

**Date:** 2026-08-24 · **Host:** `i-00e6b78fcabd32413` · **Status:** FROZEN before delivery
**Supersedes:** Build Record v1.0 (`92f3eb7`) — *delivered, **rejected by Arrival Gate***. v1.0 is
**not edited**; it stands as the record of the rejected delivery.
**Authorized by:** Amendment A `32bc34e…` + Amendment B `91d1f1b…` (remediation)

---

## 1. Why v1.1 exists

v1.0's archive was built from a Windows checkout with `core.autocrlf=true`; the tar captured
CRLF working-tree bytes and the Arrival Gate rejected it on byte identity (Amendment B §2). Content
was identical, delivery was not. v1.1 rebuilds the **same six blobs** from **Git objects**, so the
checkout conversion layer cannot participate.

## 2. Build method — Git objects, not working tree

Each file's bytes are obtained by `git cat-file blob <sha>` from the fresh clone of the remotely
custodied `a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8`. Working-tree bytes are never read.

### 2.1 Automated pre-package check (Amendment B §2.1 corrective action)

Every staged file is hashed as a Git blob and compared to its expected identity **before** the tar is
created. Packaging is refused on any mismatch. Result:

| file | blob | bytes | CRLF |
|---|---|---|---|
| `app/altdata/mr002/__init__.py` | `506870c6fadf…` | 415 | 0 |
| `app/altdata/mr002/crosswalk.py` | `f3b5800836e8…` | 12,257 | 0 |
| `app/altdata/mr002/earnings_anchors.py` | `c89b9458e903…` | 14,746 | 0 |
| `app/altdata/mr002/sic_history.py` | `48779adaaaec…` | 7,719 | 0 |
| `app/research/mr002/__init__.py` | `e69de29bb2d1…` | 0 | 0 |
| `app/research/mr002/eligibility.py` | `b9eb4a6d9b30…` | 8,204 | 0 |

**PRE-PACKAGE CHECK: 6/6 PASS, zero CRLF — packaging authorized.**

Compare v1.0, where `sic_history.py` was 7,919 B (200 CRLF pairs) and `eligibility.py` 8,381 B (177
pairs). The gate is no longer the first place a conversion defect can be detected.

## 3. Artifacts

```
augmentation_archive_v1_1         sec001v3_aug_v11.tar
augmentation_archive_sha256       049ac67990d314560417aa2d810ac0eea81a62cfd77fbfce0340136b0e8a8add
augmentation_archive_size         51200
destination_path                  /opt/workbench/sec001-v3/frozen-src/049ac679/
superseded_archive_sha256 (v1.0)  670b2b3fb9fdcc2520a8493e02bf826cd15fa9ec607f4ced0653ffd71d036e98  REJECTED
```

Deterministic tar: entries sorted, `mtime=0`, `mode=0644`, `uid=gid=0`, empty `uname`/`gname`, GNU
format — reproducible from the same six Git objects.

### 3.1 EDGAR client replacement payload (Amendment B §4.3)

```
source            git cat-file blob 6c1d7006f42f9e86121dce641af6cea525b235b8
                  (from the same remotely verified custody, NOT an operator working tree)
bytes             3382
git blob          6c1d7006f42f9e86121dce641af6cea525b235b8
sha256            7d74eda48df1910277b9745700a5368636ef8f5437991d33689d22e53a2fbe90
CRLF              0
target            /opt/sec001-src/apps/backend/app/altdata/sec/client.py
replaces          258c570dee3023a26591c4f7aec1c6b9f861e081  (3,169 B, preserved as forensic evidence)
```

⛔ **Only this one original host file is replaced.** No other file delivered by the original host
acquisition may change.

## 4. Wheelhouse — unchanged from v1.0, already installed and verified

The five pinned wheels were acquired, hashed and installed offline under v1.0 and are **not**
re-acquired. `pip check` returned no broken requirements; `httpx 0.28.1` and `duckdb 1.5.5` were
confirmed by module origin at the failed gate.

```
anyio-4.14.2      9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494
h11-0.16.0        63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86
httpcore-1.0.9    2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55
httpx-0.28.1      d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad
sniffio-1.3.1     2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2
wheelhouse_manifest_sha256      debed17da6d8365c5ea68c6d8cb3763d970b1399d6f4137183cc3bf9939f7fe4
wheelhouse_requirements_sha256  042a4d18703923cd6bfe873c0210a3c9e0157e4cff1d4292315d8ef7f53aa166
```

## 5. Environment of record

```
governed_interpreter  /opt/sec001/bin/python      python 3.12.3   pip 26.2.1
duckdb 1.5.5 · certifi 2026.7.22 · idna 3.19 · typing_extensions 4.16.0   (pre-existing, untouched)
```

## 6. Next — full Arrival Gate rerun from zero

Per Amendment B §4.6, **no previously green check carries credit**. The entire gate reruns, including
module-origin assertions and Phase-2B fixtures, plus the post-replacement client verification and
deterministic client fixtures (Amendment B §5) issuing **no network traffic**.

```
qualified_store_sha256      89c4680f76…   version_id CWQjPoJDRPIHcfQUjqMU1ynWyp5x4Umr
population_union_sha256     d338e65f9e…   identities 1167
membership_sha256           045b634946…   slots 1247
grid_sha256                 baf0da7c20…   calendar SEC001_V3_MONDAY_RTH_V1
universe_impl               cc27f47
coverage_freeze             5b26ffa209a6...    state = UNSPENT
```

**No EDGAR request until the complete gate passes.**
