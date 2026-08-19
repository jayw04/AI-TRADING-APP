# MDQ-001 — Program-Start Record v0.2 (EFFECTIVE)

| Field | Value |
|---|---|
| Document version | **v0.2 — EFFECTIVE: PROGRAM START ESTABLISHED.** |
| Status | **EFFECTIVE.** The first admissible governed frozen partition exists. The 60-day review clock is running. |
| **D0** | **2026-08-19** (Wednesday) |
| Effective from | 2026-08-19 |
| Record written | 2026-08-19, post-freeze, post-adjudication |
| Program | **MDQ-001** — Algo Trader Plus / SIP Market-Data Qualification, Phase A |
| Continues | `MDQ-001_ProgramStart_Record_v0_1_DRAFT.md` — **retained unchanged as the pre-start draft.** This document is its effective continuation and finalization, not a replacement of the lineage and not a second independent start authority. |
| Basis | `MDQ-001_Registration_v1_0_DRAFT.md` (signed §8, ratified §8.1, §8.2 rulings 1–4) · `MDQ-001_Collector_Identity_Approval_2026-08-19.md` · owner deployment-execution boundary 2026-08-17 (items 6, 7) · owner ruling 2026-08-19 (promote to v0.2 rather than stamp v0.1 in place) · ADR 0051 · ADR 0050 / GITHUB-OPS-001 v1.2 |
| Governance stance | **Recording instrument, not a decision instrument.** Every value traces to an already-signed decision or to an observation made at freeze/adjudication. If this record conflicts with the registration, a signed §8 line, the ratified §8.1 block, or an owner ruling, **those control and this record is wrong.** Nothing here may adjust a K-criterion, threshold, tolerance, denominator, or evaluability clause. |
| Decision owner | Platform owner (Jay Wang) |

> **Why v0.2 and not an edit of v0.1.** The v0.1 draft states "NOT EFFECTIVE", "no admissible partition exists", and "the clock has NOT started", and it carries pre-deployment identities from `0273012` alongside 50 `«FILL-AT-FREEZE»` placeholders. All of that was **true when written**. Editing those statements in place would have made it impossible to reconstruct what was known *before* the first admissible partition — which is exactly the property a pre-commitment record exists to preserve. v0.1 is therefore frozen as history; this document supersedes its forward-looking sections and stamps the values it deferred.

---

## 1. What "program start" means — the definition preserved

> **"PROGRAM START" IS NOT DEPLOYMENT TIME AND NOT FIRST WRITE — IT IS THE FIRST ADMISSIBLE GOVERNED FROZEN PARTITION (FULL ADMISSIBILITY CHAIN).**
>
> — Owner, deployment-execution boundary item 6, 2026-08-17

**deployment ≠ timer fire ≠ first write ≠ program start.**

| Event | When it actually happened | Started the clock? |
|---|---|---|
| **Deployment** — governed code and schedule installed on `ec2-paper` | 2026-08-17 ~19:25–19:40 ET (`0273012`); re-deployed 2026-08-18 22:35–22:36Z (`86d8cbd`) | **No.** Deployment is capability, not evidence. |
| **First timer fire** | 2026-08-18 09:25:02 EDT | **No.** The wrapper's free-space guard fail-closed at `9G < 10G floor`. A timer firing proves the schedule works, not that data was acquired. |
| **First write** | 2026-08-19 09:25:05 EDT | **No.** Bytes on disk are not an admissible partition. |
| **First admissible governed frozen partition** | **2026-08-19** — frozen 20:45:03Z, adjudicated ADMISSIBLE 20:46:51Z | **YES. This and only this.** |

Binding consequences: the 60-day clock starts on the **session date** of that partition; the review date, holdout dates, and corpus window derive from that one date and are stamped **once**, in §3 below; a partition that is frozen and `verify`-clean but fails a completeness threshold is **not** a program start.

---

## 2. 2026-08-18 remains a non-event

**No governed partition of any kind exists for 2026-08-18 — not bar-only, not partial, not at all.**

Two independent fail-closed faults, in sequence: the 09:25 sampler hit the wrapper's free-space floor (`9G < 10G`), and the 16:30 EOD run — the first to reach the acquisition latch that day — failed on `IdentityError: credential fingerprint b56421a28128 != pinned 5b6f39e5198d` (the key had been rotated on the box 2026-08-17 21:32 EDT). `mdq-freeze` then reported `no partitions for 2026-08-18; nothing to freeze` and exited 0.

This is recorded in Git at commit `3ac35a7` (PR #643). The distinction is load-bearing: *"an inadmissible partition we are excluding"* and *"no partition"* are different states, and only the first leaves something a future reader could argue back into the corpus. Registration §8.2's pre-commitment excluding a hypothetical 2026-08-18 partition is **retained unchanged** — a pre-commitment discarded once it proves unnecessary is not a pre-commitment.

---

## 3. THE CLOCK — stamped once, here

| Field | Value |
|---|---|
| **D0 — first admissible governed frozen partition** | **2026-08-19** |
| Trigger | First admissible governed frozen partition (full admissibility chain) |
| Adjudication verdict | **ADMISSIBLE — exit code 0** |
| Adjudicated at | 2026-08-19T20:46:51.766898+00:00 |
| Frozen at (iex / sip) | 2026-08-19T20:45:03.678281Z / 2026-08-19T20:45:03.691156Z |
| Review window | **[2026-08-19, 2026-10-18)** — 60 calendar days |
| `review_end_exclusive` | **2026-10-18** |
| Last day in window | 2026-10-17 |
| **Holdout period** | **[2026-10-06, 2026-10-18)** = **October 6–17 2026 inclusive** (offset 48 days, length 12 days) |
| Holdout symbols | 10 of 50, materialized pre-capture: **AMZN EFA KMLM MSTR NBIS NOW TSLA XLK XLV XOM** (`mdq_phase_a_holdout.json`, sha `6c6cf03a…`) |

**These dates were pre-registered before the capture.** Computing them from D0 reproduces the pre-declared values exactly — holdout start, holdout end, and review end all match. This is a confirmation, not a derivation.

### 3.1 Admissibility evidence

| Field | Value |
|---|---|
| Report | `/opt/workbench/data/mdq_reports/mdq001_admissibility_2026-08-19.json` (mode `0444`, 76,844 bytes) |
| **Report SHA-256** | **`5f30c446808f51fec4501d0dfe914fe7385a83f331aba05e01e49a07af17afda`** |
| Mirror | `s3://workbench-backups-219024422756/mdq_reports/mdq001_admissibility_2026-08-19.json` |
| **S3 VersionId** | **`GgmfUfUOFfnkSOhpsGhF15hvtYt_eeNP`** |
| Adjudicator | `mdq-admissibility/0.1.0`, schema `mdq-admissibility-report/1` (offline, strictly read-only) |

The report was written **outside** the capture root by design: a stray file inside it would itself fail the no-unmanifested-strays condition. **The corpus was re-verified after adjudication** — both feeds `verified`, six files, no strays — so the tool's read-only claim is evidenced, not asserted.

### 3.2 Adjudication result — every condition

**`not_passing`: 0.** Both feeds ADMISSIBLE. Governing denominator `sampler_window` (requested and ruled agree); session close 16:00:00 ET supplied and matching the calendar the sampler itself stopped on.

| Measure | iex | sip | Threshold |
|---|---|---|---|
| expected_cycles | 395 | 395 | ruled |
| observed_cycles (`slot_grid`) | 395 | 395 | — |
| **completeness** | **1.000** | **1.000** | ≥ 0.98 |
| **max contiguous gap** | **1.0 min** | **1.0 min** | ≤ 10 min |
| cycles outside ruled window | 0 | 0 | 0 |
| off-grid cycles | 0 | 0 | 0 |
| close grace periods | 0 | 0 | 0 |
| median cadence spacing | 59.999999 s | 59.999999 s | 60 s ± 5.0 s |
| observed symbols | 50/50, 0 unexpected, 0 absent | 50/50, 0 unexpected, 0 absent | 50 |

First cycle 09:25:05.117024 ET; last cycle 15:59:00.000143 ET — the last slot before an **exclusive** 16:00 close. Loop detected as **fixed-rate** (the partition carries the collector's scheduled slot). Joint conditions all PASS: `universe_config_integrity`, `universe_sha_expectation`, `both_feeds_present`, `paired_cycles` (iex 395 / sip 395, `only_in_iex` 0, `only_in_sip` 0).

Per-feed PASS also on: `freeze_completed`, `manifest_well_formed`, `integrity_verify`, `no_provenance_label` (**None** — unquarantined), `captured_after_signoff`, `identity_latch_recorded`, `feed_identity_explicit`, `universe_match`, `session_recorded`, `capture_modes_complete`, `expected_files_present`, `collector_code_identity`, `quote_records_parseable`.

---

## 4. Corpus identity — the actual deployed producer

### 4.1 Effective identity (supersedes v0.1 §2.1–2.3)

| Item | Value |
|---|---|
| **Deployed commit** | **`86d8cbd5a6201a8938062c35f915604b08652fbe`** (PR #641, squash) |
| **Running image** | **`sha256:cb4e42cd1481ee9193f0a87bb6793cab6cb29093b6c58fee19efd58995871594`** |
| Image built | 2026-08-18T18:35:36-04:00 |
| Container created | 2026-08-18T22:36:26Z — **50 s after the build**, evidencing recreation rather than a stale container |
| Collector version | `mdq-collector/0.1.0` |
| Manifest schema | `mdq-capture-manifest/1` |
| `alpaca_py` version | `0.44.0` |

**Collector code identity** — the five approved files, their full LF-normalised SHA-256 values, the LF-normalisation rule, and the runtime reconciliation are frozen in the distinct artifact **`docs/design/MDQ-001_Collector_Identity_Approval_2026-08-19.md`** (approved 2026-08-19 10:27 EDT, before the freeze, with the partition still open and unread; merged at `3ac35a7`). **That artifact controls and is not duplicated here.** Its governed identity is the tuple *version + commit + five blob hashes*, never the bare version string.

`collector_code_identity` scored **PASS** in the 2026-08-19 adjudication against `mdq-collector/0.1.0`.

### 4.2 Superseded pre-start state — historical provenance only

> ⚠ **The following is retained for provenance and is NOT the effective corpus identity.** It describes what was deployed before the first admissible partition existed.

v0.1 §2.1–2.3 identify **`027301223d8e88ce616e90a2d6831d689f2964f0`** as the deployed producer, with a four-file collector set later corrected to five, and collector hashes `ddb088e8…` (CLI), `9545b231…` (`collector.py`), `211b3b18…` (`identity.py`), `da6c0036…` (`__init__.py`), `22c3405e…` (`store.py`).

That deployment was **replaced on 2026-08-18** by `86d8cbd` (PR #641), which changed the sampler from fixed-delay to fixed-rate scheduling. **No corpus ever accrued under `0273012`** — the only session it could have produced (2026-08-18) is the non-event of §2. Of the pre-start hashes, only `store.py` (`22c3405e…`) is genuinely unchanged across both deployments; every other file has a new identity. v0.1's `«FILL-AT-FREEZE»` placeholders are **resolved by §4.1 and by the approval artifact**, and are not to be filled in v0.1.

---

## 5. Frozen capture identity

### 5.1 Universe

| Field | Value |
|---|---|
| Deployable artifact | `apps/backend/config/mdq_phase_a_universe_symbols.json` |
| File SHA-256 (LF) | `0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4` |
| **Derived `universe_sha256`** | **`a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563`** |
| Symbol count | 50 |
| On-box copy | `/opt/workbench/data/mdq_config/mdq_phase_a_universe_symbols.json`, mode `444` |

Both manifests declare exactly this `universe_sha256`, and both `universe_config_integrity` and `universe_sha_expectation` passed.

### 5.2 Session scope, cadence, capture modes

Sampler window **09:25:00 ET inclusive → official NYSE close exclusive**, cadence **60 s**, `expected_cycles = #{k ≥ 0 : start + k·cadence < end}` ⇒ **395** on a normal 16:00 close, 215 on a 13:00 early close, 0 on a non-session. The 04:00–16:00 ET interval is the **bar census scope** and is *not* the sampler denominator (registration §8.2 ruling 1). Capture modes: `rest_quote_sampler_v1` + `rest_eod_bars_v1`; a partition missing either is scope-mismatched.

### 5.3 Schedule and timezone identity

| Unit | SHA-256 | Schedule |
|---|---|---|
| `mdq-sample.timer` | `07ffeaf5d948c11eb701dd1369fade3b31763a48485eebeaf8f5ab3dc693f478` | `Mon..Fri 09:25:00 America/New_York` |
| `mdq-eod.timer` | `5192158dfab5a30f86584cd9a3dd97c7df938f0ca7acd8cabf6df15bf3851a5d` | `Mon..Fri 16:30:00 America/New_York` |
| `mdq-freeze.timer` | `b9b4dbaa97e1f50d1217e4ba38ef848f09b851e3c5a769a09f3e6426f9c5cab8` | `Mon..Fri 16:45:00 America/New_York` |
| `mdq-sample.service` | `181429e78fe4e06ecf954cd33e518118997c0bfb0dcd91cc46cefee772989968` | — |
| `mdq-eod.service` | `486bd5e21596ef56bda9cb30d03e5e67983e33f98fe32c3ff6c43e60dcd85868` | — |
| `mdq-freeze.service` | `200d9f1feb24e4e866c717428f1365513082be5b8e09b1be45fb9edea025f26a` | — |
| `mdq-alert@.service` | `35c6ded5e91044612252232fbbed616627fee0d56001cad2c6b677d70a05b9c7` | — |
| `mdq_run.sh` (wrapper) | `109931ef063d3cf43b7af16a9873f29f947b602b167a404e085265c9ce6b2642` | fail-closed guards |

All timers `AccuracySec=10s`, `Persistent=true`. **Host TZ `America/New_York` (EDT, −04:00), NTP synchronised; container TZ `UTC` by design.** Units and wrapper are **box-resident and not in Git** — committing them is a separate owner decision.

### 5.4 Capture root, permissions, durability

| Field | Value |
|---|---|
| Host capture root | `/opt/workbench/data/mdq_capture` (mode `755`, `root:root` — designated-writer / read-only-consumer) |
| Container path | `/app/data/mdq_capture` |
| `WORKBENCH_MDQ_CAPTURE_ROOT` | `/app/data/mdq_capture` |
| Bind | `/opt/workbench/app/data → /app/data`, where **`/opt/workbench/app/data` is a symlink to `/opt/workbench/data`** — verified: the same manifest hashes identically through all three paths |
| Mirror | `s3://workbench-backups-219024422756/mdq_capture/` |
| Mirror permission | instance role can **PUT but not DELETE** — the box cannot destroy mirrored bytes |
| Free-space floor | `max(10 GB, 20%)`, pre-write, abort-and-alert |

### 5.5 The 2026-08-19 partition — byte identity

| Feed | File | SHA-256 | Bytes | S3 VersionId |
|---|---|---|---|---|
| sip | `manifest.json` | `bf2d1c184e4aa78b271ae0cbe94df9c6ff3dcdfd3bcae5fb04d628362ecf8c22` | 1,467 | `fS2Dh7neWNbxMKlAW4a.TUTUdkATLiMz` |
| sip | `quotes/samples.jsonl` | `98e115503342c33cd55003da059d89d26b769c512699c8d6d518cb886e254a43` | 5,741,742 | `ALnsc7i0zbddptjXCkdb_PcdsAczQxPo` |
| sip | `bars/bars_1min.parquet` | `943c743c20f390047abd37b0d7ea2ba48cfa07e8bd0a58695f6898772b22990e` | 992,232 | `LYaPClaNoWpgt74Q7ZghcoVcXaUekJrc` |
| iex | `manifest.json` | `151e20add9d62a7c8167c75c581f8c7c972997134873b1fec20fc5a751116336` | 1,467 | `oJwgldSWjGsoGanevq8768ZYCt6J95Pv` |
| iex | `quotes/samples.jsonl` | `e1c2eb87ebb6b6a244811364f1ce7b8f60be7b81f696684dd36ead5736b2fe4c` | 5,731,641 | `X_yrTc77n_HONivIMQAw4GjOhnLs7R3n` |
| iex | `bars/bars_1min.parquet` | `288e310b26b164c80518693db70a9f4679178397dbddfc61598c24722384c272` | 561,217 | `k.K0dukEtGN0IMjZsOC23w_24vEQMpQN` |

### 5.6 Acquisition identity (fail-closed latch)

| Field | Value |
|---|---|
| Credential fingerprint | `b56421a28128` |
| Account number | `PA3BGKRLH2AP` |
| Provider / entitlement | `alpaca` / `algo_trader_plus (account-7 login)` |

Recorded in both manifests and PASS on `identity_latch_recorded`. The fingerprint was re-pinned from `5b6f39e5198d` on 2026-08-18 (owner-authorised) after the key was rotated on the box 2026-08-17 21:32 EDT. **`account_number` did not move and must not** — a move there is a different acquisition identity and a different event entirely.

---

## 6. Post-start implementation findings — verdict unaffected

Four stale or mismatched strings appear in the frozen 2026-08-19 adjudication JSON. **None affects the verdict; all scored conditions passed on their measured values.** The frozen report is **not** to be rewritten — it is evidence, and evidence is not edited.

| # | Finding | Characterisation |
|---|---|---|
| 1 | `approved_collector_code_identity` listed under "Still unratified after this ruling" | **Stale descriptive metadata**, contradicted by the pre-freeze approval of 2026-08-19. `UNRATIFIED_AFTER_RULING` is a static module constant that ratification cannot reach. **Scoring itself was PASS.** |
| 2 | `session_close_source` = `SUPPLIED BY CALLER, PROVENANCE UNSTATED` | **Provenance-reporting deficiency, not an admissibility failure in this run** — the required close was supplied and the scored conditions passed. `cmd_admissibility` never passes `session_close_source` and no CLI flag exists for it, so the string appears whether the close is calendar-resolved or explicit. |
| 3 | `cadence_match.note` = "cmd_sample is FIXED-DELAY" | **Stale diagnostic prose**, directly contradicted by the same report's measured **fixed-rate** detection and slot-grid evidence. |
| 4 | `session_close_utc` contains `2026-08-19T16:00:00-04:00` | **Field-label / serialization mismatch.** The instant is correct (16:00 ET = 20:00Z); a field named `_utc` should serialize UTC or be renamed. Arises from the explicit `--session-close` path building an ET-aware datetime. |

All four are **non-verdict-affecting for the frozen 2026-08-19 report.** Their correction is a **Tier-2** change under `app/research/**` requiring an image rebuild, and is **deferred until the next authorised rebuild after disk capacity is addressed** (currently 11 GB free against a 10 GB floor; the 2026-08-18 rebuild alone consumed ~2.2 GB).

---

## 7. Effective state

| Track | State |
|---|---|
| **Capture / corpus accrual** | **ACTIVE.** Daily governed capture continues on the frozen schedule. |
| **60-day MDQ review clock** | **ACTIVE from 2026-08-19.** Review window `[2026-08-19, 2026-10-18)`. |
| **Holdout** | Quarantined until its governed release point. `[2026-10-06, 2026-10-18)`. Exploration **never** reads holdout symbols. |
| **Value extraction / MOM-SIP-0 / CEE / DISC-001 / feature library** | **BLOCKED**, pending owner ratification of the disposition rule **`≥2 evaluable + exactly 1 PASS → HOLD`**. |

> **This record does not sign the unresolved verdict row.** The `≥2 evaluable + exactly 1 PASS → HOLD` disposition remains **unratified** and is a separate gate. Registration §7.2 forbids revising a disposition rule once exploration begins, so that signature must **precede** the first exploratory read. Nothing in this document may be read as granting it.

---

## 8. What this record does NOT do

1. It does **not** amend, reopen, or reinterpret the registration's signed §8 block, ratified §8.1, or §8.2 rulings 1–4.
2. It does **not** adjust any K-criterion, threshold, tolerance, denominator, or evaluability clause.
3. It does **not** approve the adjudicator's code identity (`mdq-admissibility/0.1.0`) — a separate governance question, deliberately outside the approved collector five.
4. It does **not** ratify `cadence_tolerance_seconds` (5.0 s remains a tool default) or `session_close_calendar_artifact`.
5. It does **not** sign the `≥2 evaluable + exactly 1 PASS → HOLD` disposition.
6. It does **not** authorise any exploratory read of the corpus.
7. It does **not** rewrite the frozen adjudication JSON, and does not edit v0.1.

---

## 9. Authority

This record is effective on the facts it stamps. Where it conflicts with the registration document, a signed §8 line, the ratified §8.1 block, an owner ruling, or the collector-identity approval artifact, **those control.**

| Item | Reference |
|---|---|
| Pre-start draft (retained, unchanged) | `MDQ-001_ProgramStart_Record_v0_1_DRAFT.md` |
| Collector identity (controls) | `MDQ-001_Collector_Identity_Approval_2026-08-19.md` |
| Registration (controls) | `MDQ-001_Registration_v1_0_DRAFT.md` |
| 2026-08-18 non-event | commit `3ac35a7` (PR #643) |
| Producing commit | `86d8cbd5a6201a8938062c35f915604b08652fbe` (PR #641) |
