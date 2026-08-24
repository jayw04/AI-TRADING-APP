# SEC-001 V3 Research Host — Augmentation Build Record v1.0

**Date:** 2026-08-24 · **Host:** `i-00e6b78fcabd32413` · **Status:** FROZEN before install/extraction

Binds the authorization in **Amendment A** to the **exact bytes produced under it**. Amendment A is
already frozen and remotely custodied at `32bc34e…`; it is **not** modified to carry values learned
afterwards. Chronology is preserved as:

```
Amendment A   = authorization
Build Record  = exact bytes produced under that authorization   <- this document
Arrival Gate  = proof those exact bytes are what actually execute
```

---

## 1. Binding identities

```
authorizing_amendment_commit  32bc34e9d337719a29e767c8f22c986f1e98fc49
augmentation_source_commit    a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8
augmentation_source_ref       research/mr002-validation2-lineage  (remotely custodied, NOT merged)
augmentation_source_tag       sec001-v3-classification-source-a0a779f
                              tag object 43dacb30aa7a6ba999b6a341d2952fa500a7c530
altdata_mr002_tree            84b08087b91c9e4ba36563ee0427cca007d3746f   (4/4 files)
research_mr002_tree           83fe9e9540116a0361af000a493652b8368e8cac   (2/84 files)
aux_omission_manifest_sha256  3bc8652d0d76ec8d4d0cd0c488b36d814a55159c2ec628c50ce177784baf7def
coverage_freeze               5b26ffa209a6...        state = UNSPENT
```

⭐ `a0a779f2…` is a **frozen research-lineage source commit**, not mainline authority and not
"upstream". SEC-001 V3 does not inherit or authorize the MR-002 program.

## 2. Source augmentation archive

Built from an **independent fresh clone of the remote at the archival tag** — never from the operator
worktree. Clone `HEAD` verified `a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8` before the archive was
produced.

```
augmentation_archive          sec001v3_aug.tar
augmentation_archive_sha256   670b2b3fb9fdcc2520a8493e02bf826cd15fa9ec607f4ced0653ffd71d036e98
augmentation_archive_size     51200
destination_path              /opt/workbench/sec001-v3/frozen-src/670b2b3f/
```

The archive is **deterministic**: entries sorted, `mtime=0`, `mode=0644`, `uid=gid=0`, empty
`uname`/`gname`, GNU format — so the SHA is reproducible from the same six blobs.

### 2.1 Contents — six files, byte-exact Git blobs

| path | git blob | bytes |
|---|---|---|
| `app/altdata/mr002/__init__.py` | `506870c6fadf6cc86f9a2a1b5441fe551841f435` | 423 |
| `app/altdata/mr002/crosswalk.py` | `f3b5800836e88d6c8757693b2cd81de1342beefd` | 12,524 |
| `app/altdata/mr002/earnings_anchors.py` | `c89b9458e9034678db4b2e0e502eb4553bfdc443` | 15,078 |
| `app/altdata/mr002/sic_history.py` | `48779adaaaecfeffb9c6a32be8531f784d72058a` | 7,919 |
| `app/research/mr002/__init__.py` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | 0 (empty blob) |
| `app/research/mr002/eligibility.py` | `b9eb4a6d9b308949b8aa56e806550564131c2daa` | 8,381 |

`app/altdata/mr002/` is **complete (4/4)**. `app/research/mr002/` is a **PURPOSE-LIMITED PARTIAL
EXTRACTION (2/84)** — every other path under tree `83fe9e95…` is intentionally omitted (capability
minimization; see Amendment A §4.2).

## 3. Wheelhouse — quarantined acquisition

Downloaded on the research host with `/opt/sec001/bin/python` into a **quarantine directory**, with
**no install performed at acquisition time**:

```
pip download --dest /opt/sec001-build/wheelhouse --only-binary=:all: --no-deps \
    httpx==0.28.1 httpcore==1.0.9 h11==0.16.0 anyio==4.14.2 sniffio==1.3.1
```

`--no-deps` is load-bearing: `certifi`, `idna` and `typing_extensions` are already measured and
pinned on the governed environment, and pip must not be permitted to replace or upgrade them while
constructing the wheelhouse.

**Inventory gate: exactly 5 wheels, 0 sdists — PASS.** All five are `py3-none-any` (pure Python), so
the host's `aarch64` architecture imposes no platform-wheel constraint.

| file | bytes | sha256 |
|---|---|---|
| `anyio-4.14.2-py3-none-any.whl` | 125,813 | `9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494` |
| `h11-0.16.0-py3-none-any.whl` | 37,515 | `63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86` |
| `httpcore-1.0.9-py3-none-any.whl` | 78,784 | `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` |
| `httpx-0.28.1-py3-none-any.whl` | 73,517 | `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad` |
| `sniffio-1.3.1-py3-none-any.whl` | 10,235 | `2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2` |

```
wheelhouse_manifest_sha256      debed17da6d8365c5ea68c6d8cb3763d970b1399d6f4137183cc3bf9939f7fe4
wheelhouse_requirements_sha256  042a4d18703923cd6bfe873c0210a3c9e0157e4cff1d4292315d8ef7f53aa166
wheelhouse_requirements_bytes   496
```

### 3.1 Install policy — entirely offline, from these pinned bytes only

```
pip install --no-index --find-links /opt/sec001-build/wheelhouse \
            --require-hashes --no-deps -r <hash-locked requirements>
```

No index, no live resolution, no dependency substitution. Install occurs **only after** this record
has remote custody.

## 4. Environment of record

```
governed_interpreter        /opt/sec001/bin/python
python                      3.12.3
pip                         26.2.1
duckdb                      1.5.5      (pre-existing; reached at RUNTIME via
                                        sic_history -> sec.ingest -> events.store)
certifi                     2026.7.22  (pre-existing, NOT touched)
idna                        3.19       (pre-existing, NOT touched)
typing_extensions           4.16.0     (pre-existing, NOT touched)
PYTHONPATH (build)          /opt/sec001-src/apps/backend
```

⛔ The host's **system** `python3` is not the governed environment and is not augmented. It has
neither `duckdb` nor `httpx`, and must not acquire them.

## 5. Unchanged research identities

```
qualified_store_sha256      89c4680f76a556d56ccd2e055605b3925375366fca41a40910edd1b844216d39
qualified_store_version_id  CWQjPoJDRPIHcfQUjqMU1ynWyp5x4Umr
population_union_sha256     d338e65f9ece1ff74bab8f7e7e098529c8466c8074d215e5894c402b35450872
population_identity_count   1167
membership_sha256           045b634946c3206a1d6228bd388de4a9f1b9a64ac90e67620dbfa5b937627754
membership_slots            1247
grid_sha256                 baf0da7c20bed5903986c9a94ffae5f54c06cbcba23adb1242ca27e415305a51
calendar                    SEC001_V3_MONDAY_RTH_V1
universe_impl               cc27f47   (PIT_LIQUID_TOP_N_V2)
```

Nothing in this build touches the sealed store, the PIT-200 population, the governed calendar grid,
the universe implementation, or the coverage rules.

## 6. Next — arrival gate (Amendment A §6, §6.1)

Extraction and install are authorized only after this record is remotely custodied. The arrival gate
must then prove **content and origin** before the first EDGAR request:

- six delivered Git blob hashes match §2.1
- archive SHA matches `670b2b3f…`
- five wheel hashes match §3
- `pip check` PASS
- module origins resolve to `frozen-src/670b2b3f/…` and `/opt/sec001/lib/python3.12/site-packages/…`
- exact Phase-2B runtime fixture PASS; no extra `app.research.mr002.*` loaded; no default sector
- sealed store identity and PIT population identities unchanged
- `5b26ffa2…` still **UNSPENT**

⭐ The module-origin assertion is mandatory, not advisory: on the operator machine an editable
install silently shadowed an explicit `sys.path` insert, so a closure proof executed all 84 files
while appearing to pass. A successful import is not proof of provenance; `__file__` is.
