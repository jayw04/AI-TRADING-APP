# MR-002 — WP-C / WP-D Custodian Submission v1.0

**Date:** 2026-08-11
**Custodian:** Jay Wang (operational custodian, `MR002_OperationalCustodian_Appointment_v1.0.json`)
**Authority:** `MR002_PrerequisiteProduction_Authorization_v1.0.json` (WP-C, WP-D, 2026-08-10),
sequenced by `MR002_ExecutionSequencing_Direction_v1.0.json` (D-S2, 2026-08-11)

**Result: P6, P7, P8, P9 and P11 are SATISFIED as runtime instances.**
Current-state register: `phase3bc/MR002_Phase3BC_RuntimePrerequisiteRegister_v1.1.json`.

Standing state is unchanged: `validation_authorization = false`, `_rev = 0`, the single
validation opening is **unconsumed**, OOS is **under DENY**, and WP-F is **not authorized**.

---

## 1. The finding that reshaped the work

WP-C and WP-D were specified as if a sealed store already existed. It did not.

- No MR-002 sealed bucket existed in account 219024422756.
- `mr002-custody-trail` carried `DataResources: []` — management events only. S3 data events
  were not partially configured; they were **absent**.
- The validation and OOS partitions were **date-range slices inside one DuckDB file** on the
  developer workstation (`apps/backend/data/mr002_research.duckdb`, no partition column).

So every "required property" in `MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json`
— separate validation/OOS storage boundaries, read credentials unavailable to ordinary
development execution, append-only access audit — was unmet. The seal in force on 2026-08-10
was **procedural** (nobody had read the rows), not enforced.

Two consequences followed, and both changed the order of work:

1. **WP-D physically precedes half of WP-C.** P7 and P8 are statements about a store's access
   log; they cannot be produced before the store exists. The executed order was
   **P9 → P6 → store + P11 → P7 → P8**, not the numeric order.
2. **Enforcing an OOS DENY requires splitting OOS rows into their own objects.** An IAM policy
   cannot deny a date range inside a file. The store build therefore included a custodian-run
   export of the frozen corpus into per-partition objects.

---

## 2. What was produced

| ID | Record | Identity |
|---|---|---|
| **P9** | `phase3bc/MR002_ValidationStructuralManifest_v1.0.json` | `ce276f58…` |
| **P6** | `phase3bc/ValidationPartitionContentCommitment_v1.0.json` | `574854a8…` |
| **P11** | `phase3bc/MR002_ValidationAccessControlPreconditions_v1.0.json` | `71b4d842…` |
| **P7** | `phase3bc/ValidationPartitionAccessHistory_v1.0.json` | `b125b4d0…` |
| **P8** | `phase3bc/ValidationSealVerificationReport_v1.0.json` | `3b59a4fd…` |
| — | `phase3bc/MR002_SealedStoreExportManifest_v1.0.json` | `c2f47fb6…` |
| — | `phase3bc/MR002_SealedStoreUploadManifest_v1.0.json` | `3834ba80…` |

All five prerequisite records are marked `RUNTIME_INSTANCE`. The Phase 3A files of the same
names are specification templates and remain untouched.

**Producers** (226 tests, ruff clean, mirrored into `custody_review/`):
`sealed_partition_commitment.py` · `sealed_store_export.py` · `sealed_store_upload.py` ·
`access_control_snapshot.py` · `seal_verification.py`

### P9 — structural manifest (produced before sealing)

850 validation sessions, `2019-10-03 .. 2023-02-16`, matching the frozen design exactly.
Schema identity `45c6607d…`. Per-table row counts, date bounds, distinct-security counts,
per-column null summaries; 12 factor series (`SPY` + 11 sector ETFs) with 850/850 session
coverage each. Latest source date `2026-07-10`.

The producer independently **reproduced the registered `governed_session_list_sha256`
`b873421516ba…` over 3,400 sessions** and refuses if it does not. That is an independent
corroboration of the calendar, not a restatement of it.

### P6 — content commitment

Validation partition content `7b0c74cd…` over **567,354 rows**. Development and OOS partitions
and the reference layer are committed in the same pass, because the store build had to be
verifiable against them.

The commitment carries a **completeness proof**: 2,224,181 in-window observation rows are
committed across exactly three partitions, reconciling row-for-row against 2,670,656 total
rows less 446,475 pre-2013 warm-up rows and **zero** rows after the governed window. The
producer refuses if any table fails to reconcile — including the case of a NULL availability
date, which would otherwise leave a sealed row uncommitted while every hash still matched.

### P11 — access controls in force

- Bucket `s3://workbench-mr002-sealed-219024422756` (us-east-1): versioned, SSE-S3 + bucket
  keys, public access blocked, TLS-only, permanent deletion of sealed object versions denied.
- CloudTrail S3 data events enabled at **2026-08-11T14:47:40Z**, *before any partition object
  existed*; first upload at 14:50:08Z.
- Dedicated principal `arn:aws:iam::219024422756:role/mr002-validation-reader`, validation-only
  identity policy, explicit bucket-policy DENY on `oos/`.

Decisions, by **policy simulation**:

| Principal | validation | oos | development | reference |
|---|---|---|---|---|
| `mr002-validation-reader` | allowed | **explicitDeny** | allowed | allowed |
| account `admin` (ordinary development) | **explicitDeny** | **explicitDeny** | allowed | allowed |

The second row is the control-spec property "read credentials unavailable to ordinary
development execution", proven rather than asserted: the most privileged ordinary principal in
the account cannot read either sealed partition.

### P7 / P8

`validation_access_events_before_authorization = 0` and `oos_access_events_before_validation
= 0`, over a verifying hash chain of 37 events on the sealed store — 12 sealing writes to the
sealed prefixes, **zero reads**. P8 additionally recomputed the validation content commitment
independently and matched `7b0c74cd…`.

---

## 3. A design constraint worth recording

**Verifying an upload by reading it back would have destroyed P7.**

CloudTrail records a `GetObject` as a data event whether it succeeds or is denied. A read-back
check on the validation prefix — or a "let's prove the DENY works" attempt on `oos/` — would
have written the exact pre-authorization sealed-partition event that P7 and P8 must show is
zero, permanently, in an append-only log.

So integrity was established without any read:

- **Before upload:** every object was re-read *from local disk* and its canonical content hash
  recomputed against P6. All 22 objects round-tripped exactly through Parquet.
- **On upload:** each object carried a precomputed SHA-256 that S3 validated server-side.
- **DENY proof:** IAM policy simulation over the identity policy and bucket policy together.

Three modules carry a test asserting they contain no S3 read call at all.

---

## 4. Disclosures

These are stated because a reviewer should not have to discover them.

1. **Custodian direct execution.** The owner authorized the operational custodian to execute
   the row-reading producer directly rather than the WP-A build-and-hand-over pattern. The
   producer is fixed, reviewed, deterministic and audit-bound, and the emitted records carry
   the custodian identity, the authority, and the producer's own SHA-256. Value-blindness is
   enforced by test: sealed universe membership never appears in any emitted record.

2. **P7 coverage begins 2026-08-11T14:47:40Z.** It covers the sealed store from before any
   object existed in it. It does **not** cover the period during which the corpus existed only
   as a file on the workstation; no store-level log existed then and none can be manufactured
   now. That earlier period rests on the procedural seal in prereg v1.0.4
   (`sealed_data_read = false`), which is a weaker basis and is not restated as if audited.

3. **The reference layer is not sealed.** `crosswalk`, `predecessor_overrides`,
   `security_sector_overrides` and `sic_mapping` are interval-valid registries whose validity
   spans all three windows by construction, so they cannot be sliced by availability date.
   They are committed and pinned, but they are **not sealed partition objects, not under the
   OOS DENY, and not covered by the validation-only read restriction** — and some of their rows
   have intervals extending into the sealed windows. This follows the corpus design that was
   already countersigned in the sealed manifest; it is disclosed, not newly decided.

   Their exact identities are bound into the execution contract in
   `phase3bc/MR002_Phase3BC_RuntimePrerequisiteRegister_v1.1.json` → `reference_layer`
   (`reference_content_sha256 = a89bf82dce335806547f37a1b91947566442914156b66f2bfab6f60a332d44ff`,
   plus per-table content hash, object key and S3 version ID), so WP-F can reproduce them rather
   than trust a filename. Drift in any of those hashes is a change to the reference layer the
   validation run reads and must be treated as such.

4. **`universe` straddles both window boundaries.** Rows are classified by `universe_month`.
   October 2019 (serving validation sessions from 10-03) classifies as *development*, and
   February 2023 (serving OOS sessions from 02-17) classifies as *validation*. Neither
   direction creates lookahead — a month's universe is formed from trailing liquidity — but the
   rule is mechanical and stated rather than left implicit.

5. **P8's ledger reconciliation is trivial.** No authorized run has occurred, so the
   OpenedObjectLedger is empty and the reconciliation is 0 == 0. The record says so. It becomes
   a substantive check only for the Phase 3C run.

6. **Operational side effect.** Adding data events to `mr002-custody-trail` is a
   `PutEventSelectors` call, which the existing control-plane detection rule monitors — an SNS
   alert to `jay.w0416@gmail.com` is expected and is not an incident. Management-event coverage
   was explicitly re-verified after the change, because `put-event-selectors` replaces the
   selector set and silently losing management events would have disabled the ECR custody
   detection this trail exists for.

7. **Local staging deleted.** The 64 MB local export copy was removed after upload, mirroring
   WP-A A6. The frozen snapshot itself is untouched: `24e5153c…` before and after every read.

---

## 5. What was NOT done

- **P10 was not captured.** Frozen at code complete by owner direction D-S1. No escape hatch
  was added around the WP-B resolver and the 17-binding requirement was not weakened.
- **Requirement 7 remains `IMPLEMENTED_PENDING_C_R7_VERIFICATION`.** Not upgraded.
- **WP-F was not built or run.** It remains unauthorized until P6–P11 are all satisfied.
- **No credential was released.** The reader role is unassumable: its trust policy names a
  run-host role that does not exist.
- **No validation or OOS partition value was read, computed on, or emitted.**
- **`validation_authorization` was not touched**, and no D3 submission was made.

---

## 6. Next, per the owner's sequence

1. Provision **and qualify** the real Phase 3C execution host (D-S4) — OS/container runtime,
   architecture, network/IAM boundary, evaluator-image resolution through the WP-B resolver.
   Its instance-profile role is what the reader role's trust policy must then name.
2. Capture **P10** there prospectively, inside the bound image (D-S5), and seal it.
3. Only then authorize **WP-F** (C1–C10 + C-R7 + P10 reproducibility).
4. D3 resubmission with a **fresh** adjudicated CAS anchor — the register has changed, so
   `088d700b…` is staler than ever and must not be silently satisfied against.

**Standing rule SR-HOST-1 applies from here:** host replacement before validation invalidates
P10 and requires a fresh capture and a re-run of grant-readiness verification.
