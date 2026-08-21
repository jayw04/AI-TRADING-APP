# DISC-MDQ-001 — Discovery Ledger Production Acceptance Record

**Host:** `ec2-paper` (`i-084f47fe4e69192e9`, workbench-paper, us-east-1)
**Acceptance run (UTC):** `2026-08-21T21:32:05Z` · **container recreated** `2026-08-21T21:29:34Z`
**Governing criterion:** ATP v1.4.1 Implementation Plan v0.13 §4.10.7 — the twelve-item acceptance gate
**Result:** **PASS**

> **No exploratory MDQ partition was opened and no CEE condition was computed during operational
> acceptance.**
>
> **Production ledger path pinned: `/opt/workbench/data/mdq_discovery/ledger.jsonl`. Scratch paths were
> used for acceptance testing; no synthetic exploratory act was written to the production ledger.**

⛔ **This record does NOT authorize CEE.** Authorization to open the first governed partition is a
separate owner act. What is established here is that the ledger + artifact configuration is operational
and fail-closed on the actual read path.

---

## 1. Pre-conditions — the freeze gate, verified before any box change

Owner-specified: do not touch the box before the 16:45 ET freeze completes, verifies, and mirrors.
Each condition was established from live facts; a timer firing was explicitly **not** treated as
authorization.

| Gate | Evidence | Result |
|---|---|---|
| Current time | box `2026-08-21T17:16:55-0400` (`21:16:55Z`) | PASS |
| Freeze | `mdq-freeze.service` **success (0)**, fired 16:45:02 EDT; both feeds carry a manifest, `frozen_at 2026-08-21T20:45:03Z` | PASS |
| Verify | **Independently re-hashed** every file against its manifest rather than trusting the unit journal — iex 2/2, sip 2/2, **0 mismatches**, `VERIFY_OK` both | PASS |
| S3 mirror | **6 objects** under `s3://workbench-backups-219024422756/mdq_capture/{iex,sip}/2026-08-21/`, every object size reconciled byte-for-byte against the local manifest | PASS |

Capture alerts log carried **no entry for 2026-08-21** (latest entries 2026-08-18).

---

## 2. Deployed code identity

| Item | Value |
|---|---|
| `.deploy_src_sha` | `50efc2fb8f8eb8d3b3a3fcdc000e5d181121e807` |
| Previous deployed sha | `a2659be76d2e4663bc816fac2537b480ffa2469f` (#653) |
| Delta | **7 files, research-plane only** — no migration, no compose, no Dockerfile, no deploy script ⇒ boot `alembic upgrade head` is a no-op |
| Backend image | `sha256:dc17f4b3187aeff898daaf03bfc801cd2e2e52748c3bbdfe68118020e2de7336` |
| Container created | `2026-08-21T21:29:34.184834621Z` |
| `ledger.py` **inside the running container** | `aa3f01d49fc1f710d5eed6ba72c42e9e0e502488967159f6b1fb4cdef4f1ecb9` |
| Program versions | `mdq-exploration-policy/0.1.0` · `mdq-feature-reader/0.1.0` · `mdq-discovery-ledger/0.1.0` |
| DISC-001 screen | `DISC-001-WATCHLIST v0.3.0` — **unchanged** |

**Byte-exact deployment.** The delivery tarball was built with `core.autocrlf=false` / `core.eol=lf` and
verified against Git before upload: **all 2,234 files byte-identical to their blobs at `50efc2f`**,
0 mismatches. Archive `sha256 9efae8c3335143735a9030d83b508fee45f4213ca434fa4d1743687f5aa456cc`,
6,166,127 B, sha re-verified **on the box** before extraction.

⚠ **Finding — deploy-time EOL conversion.** The default `git archive` on this Windows workstation
(`core.autocrlf=true`) injects CRLF into every file **not** covered by `.gitattributes`, which pins only
`*.sh`, `*.service`, `*.timer`. A default archive would have placed `ledger.py` with 670 CR bytes and
`mdq_phase_a_holdout.json` as the CRLF variant `7247ad59…` rather than the governed `7832ff38…`. It would
still have *functioned* — Python reads CRLF source, and `_sha256_lf()` normalises before comparing pins,
which is exactly why that function exists — but the deployed bytes would not have equalled the commit,
and every hash in this record would have needed an "up to EOL conversion" caveat. **Follow-up:** extend
`.gitattributes`, or standardise `-c core.autocrlf=false` in the deploy recipe.

**Pre-deploy safety.** Online DB backup taken via the running container before extraction:
`/opt/workbench/data/workbench.predeploy-50efc2f.sqlite`, `PRAGMA integrity_check` → `ok`.

---

## 3. Governed artifact identities

Both artifacts deployed to `/opt/workbench/data/mdq_config/` (container view `/app/data/mdq_config/`),
identical ownership and permissions:

| Artifact | sha256 (LF) | Bytes | Mode | Owner |
|---|---|---|---|---|
| `mdq_phase_a_holdout.json` | `7832ff38d77c7e2034c1d3a07d784534df693882a4651620e47971b8a0477010` | 2098 | `444` | `root:root` |
| `mdq_phase_a_universe_symbols.json` | `0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4` | 376 | `444` | `root:root` |

The holdout artifact is newly deployed this session; it was derived from the **Git blob** at `50efc2f`
(not from the CRLF working tree) and its hash equals the post-stamp identity recorded when PR #651
stamped it. Install was guarded to refuse on a pre-existing file, sha mismatch, size mismatch, or any
CR byte (`staged_bytes=2098 cr_bytes=0 lf_bytes=32`).

Cross-checks at install:

- artifact's `universe_symbols_sha256` == the universe file actually present → **True**
- canonical symbol hash == published `holdout_symbols_sha256` == pinned `320a8c3b…` → **True**
- period holdout `2026-10-06 .. 2026-10-18` (exclusive)

The universe artifact was untouched (`mtime 2026-08-17`), and its raw hash still matches the pin the
box-resident capture wrapper enforces (`mdq_run.sh`, `sha256 109931ef063d3cf43b7af16a9873f29f947b602b167a404e085265c9ce6b2642`, unchanged).

---

## 4. Positive proof — the same `from_config` + ledger-init path CEE will use

File presence and standalone hashes are recorded above as **supporting evidence only**. Acceptance is
the code path:

- `verify_governed_artifacts()` → `attestation.verified = True`
- attested universe == pin `0c57bd71…`; attested quarantine == pin `320a8c3b…`
- period provenance `artifact_stamped_and_matches_rule` — read from the **stamped** artifact, not derived
- period bounds `[2026-10-06, 2026-10-18)`; universe carries **50** symbols
- `MdqExplorationPolicy.from_config()` → **constructed quarantine IS the governed ten**:
  `AMZN, EFA, KMLM, MSTR, NBIS, NOW, TSLA, XLK, XLV, XOM`
- `AuthorizedScope` carries `holdout_symbols_sha256 = 320a8c3b…`
- authorizing `[AMD, INTC, TSLA, XOM]` on `2026-08-20` → allowed **exactly** `AMD, INTC`;
  `TSLA` and `XOM` denied `denied_holdout_symbol`
- authorizing `AMD` on `2026-10-07` (inside the period holdout) → **authorizes nothing**,
  `denied_holdout_period`
- `DiscoveryLedger.open()` → initialises, genesis is `ledger_opened`, chain verifies, opening record
  carries the verified attestation
- code identity recorded in the record: `source_sha = 50efc2fb8f8eb8d3b3a3fcdc000e5d181121e807`

---

## 5. Negative proof — item 11 is enforced, not merely satisfied

All cases operated on **copies** in a scratch directory. The deployed governed artifacts were re-hashed
afterwards and confirmed **unchanged**.

| Case | Required | Observed |
|---|---|---|
| **N1** wrong holdout hash (quarantine moved, artifact re-published so it is internally consistent) | FAIL | `PolicyError: the quarantined symbol set has moved` — **no ledger file created** |
| **N2** missing holdout artifact | FAIL | `FileNotFoundError` — **no ledger file created** |
| **N3** holdout/universe inconsistency (artifact pins a universe it was not drawn from) | FAIL | `PolicyError: holdout artifact was drawn from a different universe file` — **no ledger file created** |
| **N4** correct governed pair | PASS | attestation verified; ledger initialises |
| **N5** *(added)* forged `ArtifactAttestation` with `verified=True` and wrong pins | FAIL | `LedgerInitError: attested universe … is not the pinned Phase-A universe` — **no ledger file created** |

N5 was added beyond the four-case matrix because the four cases prove the **loader** rejects bad
artifacts; N5 proves the **gate** re-checks the pins rather than trusting a flag handed to it.

**Boundary assertions:** exactly two ledger files were created across the whole run (the positive case
and N4) ⇒ every negative case wrote none. Every record written anywhere was a `ledger_opened` record;
**zero** `partition_read` records exist. No `MdqFeatureReader` was constructed and no MDQ partition was
opened at any point.

---

## 6. Production ledger path

| Item | Value |
|---|---|
| Host path | `/opt/workbench/data/mdq_discovery/ledger.jsonl` |
| Container path | `/app/data/mdq_discovery/ledger.jsonl` (resolves exactly; no symlink drift) |
| Directory | `uid 0 gid 0`, mode `755`, **not world-writable**, created host-side with explicit ownership |
| Ledger file | mode `644`, `root:root`, **not world-writable** |
| Process identity | `euid 0 egid 0` (the backend container runs as root) |
| File | 1677 B, **1 record**, `sha256 e0398d78201e7f8bb718a6cb0bd8bef43c56349744f4b03dbd17b6510a4b2af5` |

**Genesis record** — a production-control initialization event, not a research act:

```
seq         : 1
event       : ledger_opened
recorded_at : 2026-08-21T21:32:05.593610+00:00
prev_hash   : 0000000000000000000000000000000000000000000000000000000000000000
row_hash    : a1aecc44b28611e8543aee122746fe382493ffb01a4f1d264bd1e635a70f099c
entry_ref   : DISC-MDQ-001#1:a1aecc44b28611e8
source_sha  : 50efc2fb8f8eb8d3b3a3fcdc000e5d181121e807
universe    : 0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4
quarantine  : 320a8c3b634d68ee907400c39900abdb6fbc259d8f6e6213a914e915f6797be0
verified    : True
note        : PRODUCTION-CONTROL INITIALIZATION. Genesis record written during the
              plan v0.13 4.10.7 operational acceptance on ec2-paper. This is NOT an
              exploratory act: no governed partition was opened, no condition was
              examined, and no feature was computed. The first legitimate research
              consumer (CEE) appends from here.
```

**Event-type census of the production ledger:** `{'ledger_opened': 1}` —
`conditions_examined: 0`, `partition_read: 0`.

Initializing was verified as safe **against `origin/main` before doing it**: `open()` appends only
`LEDGER_OPENED` (`ledger.py:379`); `PARTITION_READ` is written solely by `record_partition_read` (:471)
and `CONDITION_EXAMINED` solely by `record_condition` (:525); `conditions_examined()` (:667) counts only
the latter. A genesis record therefore contributes **zero** to the multiple-comparisons denominator and
implies no corpus read.

### Scope of the append-only guarantee — stated, not overstated

- The ledger **code** has no overwrite or delete path: a single `_append` using `os.O_APPEND`,
  `LEDGER_PUBLIC_API` pinned by test, and any edit or removal of a record breaks the hash chain and
  fails the next `open()`.
- It does **not** prevent an OS-level `rm` or truncate by root or by the service user. Durable custody
  would require an append-only file attribute (`chattr +a`, compatible with `O_APPEND`) or an off-box
  mirror. **Neither is applied**; applying one is a separate owner decision.

---

## 7. Free-space evidence — re-run by the deployed guard's actual formula

Governing formula `floor = max(10 GiB, 20% of filesystem capacity)`; realized rule as the wrapper
computes it (`df -B1G` rounds up, integer division):

| Quantity | Value |
|---|---|
| `size_gb` | 58 |
| `avail_gb` | 37 |
| `floor` | 11 |
| `avail_bytes` | **38,862,598,144** |
| effective threshold | **10,737,418,240** (fails iff `avail_bytes <=` this) |
| margin | **28,125,179,904** |
| **Guard** | **PASS** |

`avail_bytes` before the rebuild was 41,011,937,280 ⇒ the redeploy cost **~2.15 GB**.
Docker: images 4.674 GB (2.42 GB reclaimable), **build cache 7.41 GB (5.865 GB reclaimable)**.

⚠ **A redeploy is a capture-availability event.** Docker and the MDQ capture root remain the **same
mount (`/`)**. The next sampler is **Monday 2026-08-24 09:25 ET**; a further free-space check is owed
**before** it, even though the margin is currently ample. Quote the formula and the exact byte
threshold, never a remembered GB figure.

---

## 8. Service and capture state after deployment

- `healthz` → `{"status":"ok","db":"ok","checks":{"database":"ok","master_key":"ok","broker_registry":"ok","scheduler":"ok","circuit_breakers_clear":"ok"}}`
- `scheduler_health_check.py` → `OK: single armed host 'ec2-paper'`, **exit 0** (the arm invariant)
- Containers: `workbench-backend` recreated and healthy; `workbench-frontend`, `agent`, `workbench-mcp`,
  `workbench-mcp-1` untouched and up
- MDQ timers armed, next fire **Mon 2026-08-24** — `mdq-sample 09:25`, `mdq-eod 16:30`,
  `mdq-freeze 16:45` ET
- Capture alerts log: no new entries; latest remain 2026-08-18

---

## 9. Disposition

| Item | State |
|---|---|
| Ledger code | **CLOSED** — merged `50efc2f` (#654), in Git custody |
| Phase-B production readiness | **OPERATIONAL** — this record |
| Production ledger path | **PINNED** — `/opt/workbench/data/mdq_discovery/ledger.jsonl`, genesis initialized |
| CEE | ⛔ **STILL NOT AUTHORIZED** — a separate owner act |

**Owed next:**

1. Free-space / guard check before the Monday 2026-08-24 09:25 ET sampler.
2. Owner decision on durable ledger custody (`chattr +a` and/or off-box mirror).
3. Follow-up on deploy-time EOL conversion (§2).
4. Research sequencing is unchanged: repeat the DISC∩MDQ population census later in the week rather
   than reacting to each daily snapshot; broad DISC-MDQ stays held; MOM-CORE viable-but-narrow (5
   names); GAP observation-only; MOM-NEAR / OVERSOLD not evaluable.
