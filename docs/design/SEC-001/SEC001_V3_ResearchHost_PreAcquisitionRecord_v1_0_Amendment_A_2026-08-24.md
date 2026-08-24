# Amendment A — SEC-001 V3 Research Host, post-acquisition source & dependency augmentation

**Amends:** `SEC001_V3_ResearchHost_PreAcquisitionRecord_v1_0.md` · **Date:** 2026-08-24
**Host:** `i-00e6b78fcabd32413` · **Status:** FROZEN before delivery · **First EDGAR request:** PROHIBITED until §6 passes

---

## 1. Standing of the original record

**The original pre-acquisition record remains historically valid and authoritative for host
creation.** It was true when signed. This amendment does not correct it and does not claim its
source inventory was wrong.

This amendment authorizes a **subsequent, purpose-limited source and dependency augmentation**
required for the SEC-001 V3 classification crawl. It supersedes the original source-inventory
constraint **only** for the explicitly identified augmentation below.

## 2. Reason for augmentation

The authorized crawl reads the frozen effective-dated SIC machinery and the fail-closed Phase-2B
classification path. Host discovery on 2026-08-24 established that these are absent from the host:

| Component | Present on host |
|---|---|
| `app/altdata/sec/client.py` (EDGAR client) | ✅ present |
| `app/altdata/mr002/**` (SIC spine, crosswalk) | ❌ absent |
| `app/research/mr002/eligibility.py` (Phase-2B) | ❌ absent |
| `httpx` (required by `client.py`) | ❌ absent |

Without them the crawl cannot execute, and a manifest binding their blob identities would be
untrue at signing.

## 3. Source custody status

**The MR-002 classification machinery authorized by this amendment is not present in `origin/main`
at the time of augmentation** (`origin/main` = `983f5c55206e7ece99411fa4b85cba16d8bbc08d`). Its
governing source identity is commit `a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8` on the remotely
custodied research-lineage ref `research/mr002-validation2-lineage`.

**SEC-001 V3 does not inherit or authorize the MR-002 program represented by that branch.** Only
the six enumerated Git blobs and their proven runtime closure are authorized for extraction and
deployment.

⭐ `a0a779f2…` is a **frozen research-lineage source commit** / **augmentation source commit**. It
is **not** "upstream" and carries no mainline authority. The branch was **not merged** — merging it
to make provenance look cleaner would conflate source custody with mainline approval and is
prohibited.

### 3.1 Remote custody, verified from an independent fresh clone

Server-side refs (`git ls-remote`, authoritative):

```
refs/heads/research/mr002-validation2-lineage          a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8
refs/tags/sec001-v3-classification-source-a0a779f^{}   a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8
```

An annotated archival tag `sec001-v3-classification-source-a0a779f` (tag object
`43dacb30aa7a6ba999b6a341d2952fa500a7c530`) pins the same commit to reduce the risk of accidental
branch cleanup. It is **not** a substitute for the commit SHA.

⛔ **Neither ref may be deleted or force-moved until the SEC-001 classification evidence package is
sealed.**

All identities below were **re-resolved from a fresh `git clone` of the remote at that tag**, not
from the laptop worktree.

## 4. Authorized augmentation — exact contents

### 4.1 `app/altdata/mr002/` — COMPLETE PACKAGE, 4/4 files

Upstream tree SHA **`84b08087b91c9e4ba36563ee0427cca007d3746f`**

| path | git blob | bytes |
|---|---|---|
| `app/altdata/mr002/__init__.py` | `506870c6fadf6cc86f9a2a1b5441fe551841f435` | 423 |
| `app/altdata/mr002/crosswalk.py` | `f3b5800836e88d6c8757693b2cd81de1342beefd` | 12,524 |
| `app/altdata/mr002/earnings_anchors.py` | `c89b9458e9034678db4b2e0e502eb4553bfdc443` | 15,078 |
| `app/altdata/mr002/sic_history.py` | `48779adaaaecfeffb9c6a32be8531f784d72058a` | 7,919 |

### 4.2 `app/research/mr002/` — PURPOSE-LIMITED PARTIAL EXTRACTION, 2/84 files

> **PURPOSE-LIMITED PARTIAL EXTRACTION — NOT A COMPLETE MR-002 PACKAGE.**
> The augmentation contains only the upstream Git blobs required to execute SEC-001 V3's authorized
> effective-dated SIC / Phase-2B classification path. Omitted MR-002 execution, validation,
> Stage-3, Phase-3 and research-program machinery is **intentionally not deployed** to the SEC-001
> V3 research host.

Upstream tree SHA **`83fe9e9540116a0361af000a493652b8368e8cac`**

| path | git blob | bytes |
|---|---|---|
| `app/research/mr002/__init__.py` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | 0 (empty blob) |
| `app/research/mr002/eligibility.py` | `b9eb4a6d9b308949b8aa56e806550564131c2daa` | 8,381 |

**Every other path under upstream tree `83fe9e95…` is intentionally omitted.** The omission is
deliberate capability minimization, **not** an accidental gap: a classification-only host must not
acquire `runner.py`, `execution.py`, Stage-3 cascade/route, Phase-3B/3C, SPQ1 or N1 machinery. The
control is **capability absent**, not *capability present but policy-denied*.

Auxiliary (non-governing) evidence artifact enumerating the 82 omitted paths and blob SHAs:
sha256 **`3bc8652d0d76ec8d4d0cd0c488b36d814a55159c2ec628c50ce177784baf7def`**. This amendment does
**not** depend on that list.

### 4.3 Frozen blob identities required by the crawl manifest

```
sic_history.py   48779adaaaecfeffb9c6a32be8531f784d72058a
crosswalk.py     f3b5800836e88d6c8757693b2cd81de1342beefd
eligibility.py   b9eb4a6d9b308949b8aa56e806550564131c2daa
client.py        6c1d7006f42f9e86121dce641af6cea525b235b8   (already on host, unchanged)
```

### 4.4 Destination

Unpacked to an immutable, provenance-visible path — **not** over the original source tree:

```
/opt/workbench/sec001-v3/frozen-src/<augmentation-archive-sha256>/
```

placed on the crawl process's `PYTHONPATH` ahead of nothing else that could shadow it.

## 5. Dependency augmentation — frozen, hash-pinned, no live resolution

**Governed interpreter:** `/opt/sec001/bin/python` — the venv that built the qualified store and ran
Gates 1–6. Python **3.12.3**, pip **26.2.1**, `PYTHONPATH=/opt/sec001-src/apps/backend`.
⛔ The host's *system* python3 is **not** the governed environment and must not be augmented.

The repository declares `httpx>=0.27` — an **unbounded lower bound**, the defect class that took
`main` red for ~21 hours (GITHUB-OPS-001 §3). There is no lockfile. The pin below is therefore
**evidence-derived** from the running `workbench-backend` container, which executes this exact
`client.py` against EDGAR successfully.

| package | version | state on governed venv |
|---|---|---|
| `httpx` | **0.28.1** | missing → wheel required |
| `httpcore` | **1.0.9** | missing → wheel required |
| `h11` | **0.16.0** | missing → wheel required |
| `anyio` | **4.14.2** | missing → wheel required |
| `sniffio` | **1.3.1** | missing → wheel required |
| `certifi` | 2026.7.22 | already present, **identical** |
| `idna` | 3.19 | already present, **identical** |
| `typing_extensions` | 4.16.0 | already present, **identical** |
| `duckdb` | **1.5.5** | already present — reached at runtime via `sic_history → sec.ingest → events.store` |

⭐ `duckdb` is recorded because the **runtime** closure of `sic_history.py` is deeper than its import
list suggests. A manifest naming only `httpx` would understate what the crawl depends on.

**Install policy:** local wheelhouse only — `--no-index --find-links <wheelhouse>`, with
`--require-hashes` where the format permits. **No dependency resolution against the live internet.**
Every wheel SHA-256 recorded. Post-install record captures Python version, pip version, installed
versions, wheel hashes, `pip check` result, and import proof for `client.py`.

## 6. Arrival gate — ALL must pass before the first EDGAR request

```
augmentation archive SHA        == frozen value in this amendment
all delivered file SHAs         == §4 manifest
sic_history.py blob             == 48779ada...
crosswalk.py blob               == f3b58008...
eligibility.py blob             == b9eb4a6d...
client.py blob                  == 6c1d7006...
httpx exact version             == 0.28.1  (and each pinned transitive version)
duckdb exact version            == 1.5.5
pip check                       == PASS
MR-002 modules import           == PASS
SEC client import               == PASS
population manifest             == unchanged
qualified store SHA/VersionId   == unchanged
coverage freeze                 == UNSPENT
MODULE-ORIGIN ASSERTION         == PASS   (see 6.1)
```

**If any one fails, do not crawl.**

### 6.1 Module-origin assertion — a formal arrival-gate invariant

Every imported module must resolve to the delivered augmentation path or the governed venv's
site-packages — **never** an editable install, a pre-existing checkout, or any other location:

```
app.altdata.mr002.sic_history        -> /opt/workbench/sec001-v3/frozen-src/<sha>/...
app.altdata.mr002.crosswalk          -> /opt/workbench/sec001-v3/frozen-src/<sha>/...
app.research.mr002.eligibility       -> /opt/workbench/sec001-v3/frozen-src/<sha>/...
app.altdata.sec.client               -> (host original source tree, blob 6c1d7006...)
duckdb                               -> /opt/sec001/lib/python3.12/site-packages/duckdb/__init__.py
httpx                                -> /opt/sec001/lib/python3.12/site-packages/httpx/__init__.py
```

⭐ **This invariant exists because it already caught a false positive.** On the operator machine the
venv's editable install hard-maps `app` to the full checkout and silently shadowed an explicit
`sys.path` insert — the closure proof was executing all 84 files while appearing to pass. Only a
path-origin assertion detected it. An "installed package list" or a bare successful import is **not**
proof; module origin is.

Additionally assert that **no `app.research.mr002.*` module other than `eligibility`** is loaded.

## 7. Runtime-closure proof (operator machine, pre-delivery)

Executed against an isolated tree containing **only** the six-file extraction:

```
[1] imports resolve from the isolated tree ONLY                 PASS
[2] Phase-2B SectorResolver.sector_etf on deterministic fixtures:
      resolved HIGH           -> (XLI,  sic_mapping_HIGH)       PASS
      fail-closed LOW         -> (None, excluded_low_confidence) PASS
      fail-closed unmapped    -> (None, unmapped_sic)            PASS
      fail-closed no PIT SIC  -> (None, no_pit_sic)              PASS
      fail-closed identity    -> (None, identity_unresolved)     PASS
[3] extra app.research.mr002.* modules loaded at runtime: NONE   PASS
[4] no default sector ever returned                              PASS
```

`eligibility.py` imports **only stdlib** (`bisect`, `dataclasses`, `datetime`); no lazy or runtime
import of any other MR-002 module occurs on the executed path. The two-file extraction is therefore
the **complete runtime closure** of the authorized Phase-2B path, not merely its import closure.

`sic_history.py` closure is deferred to the on-host proof (§6) because it reaches `duckdb`, which is
absent from the operator machine but present on the governed venv.

## 8. Scope limits — what this amendment does NOT authorize

- ⛔ **No broker credentials, no `WORKBENCH_MASTER_KEY`, no trading-runtime capability** introduced.
- ⛔ **No MR-002 program execution authorized.** Presence of `earnings_anchors.py` and `crosswalk.py`
  is package fidelity for `app/altdata/mr002/`, not authorization to run MR-002.
- ⛔ **No change** to the sealed qualified store, the PIT-200 population, the governed calendar grid,
  the universe implementation, or the coverage rules.
- ⛔ **No modification of any MR-002 file.** Delivery is byte-exact extraction; the arrival gate
  proves it.
- ⛔ No merge of `research/mr002-validation2-lineage`.
- **Purpose limited to SEC-001 SIC acquisition and classification.**

## 9. Unchanged identities

```
qualified_store_sha256      89c4680f76a556d56ccd2e055605b3925375366fca41a40910edd1b844216d39
qualified_store_version_id  CWQjPoJDRPIHcfQUjqMU1ynWyp5x4Umr
population_union_sha256     d338e65f9ece1ff74bab8f7e7e098529c8466c8074d215e5894c402b35450872
population_identity_count   1167
membership_sha256           045b634946c3206a1d6228bd388de4a9f1b9a64ac90e67620dbfa5b937627754
membership_slots            1247
grid_sha256                 baf0da7c20bed5903986c9a94ffae5f54c06cbcba23adb1242ca27e415305a51
calendar                    SEC001_V3_MONDAY_RTH_V1
universe_impl               cc27f47  (PIT_LIQUID_TOP_N_V2)
coverage_freeze             5b26ffa209a6...   state = UNSPENT
```

## 10. Pending fields — completed at build time, before delivery

- `augmentation_archive_sha256` — computed when the archive is built from the **remote-verified**
  `a0a779f2…`, never from the laptop worktree.
- `wheelhouse` per-wheel SHA-256 manifest.
- Destination path `<augmentation-archive-sha256>` resolved from the above.

**No EDGAR request may be issued until these are filled, the archive delivered, and §6 passes in
full.**
