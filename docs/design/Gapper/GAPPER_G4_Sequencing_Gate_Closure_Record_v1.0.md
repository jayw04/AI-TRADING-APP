# GAPPER — G4 §9 Sequencing Gate: Owner Closure Record

| Field | Value |
|---|---|
| Record | **Gate closure record** — a governance artifact binding an owner ruling to an exact gate |
| Version | v1.0 |
| Gate | **G4 — GAPPER v2.1.1 §9 sequencing ruling** |
| Ruling date | **2026-08-22** |
| Owner disposition | **CLOSED — prerequisite satisfied** |
| Governing artifact | `docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx`, SHA-256 `2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d` |
| Related | `GAPPER_Research_Design_v2_1_1_ApprovalRecord_v1.0.md` (approval, Stage 0 only) · `GAPPER_Stage0_Prep_Scoping_Memo_v0_1.md` (preparation scoping) |

> **The ruling.** **G4 CLOSED — prerequisite satisfied before GAPPER Stage-0 authorization.** MR-002
> execution-order Steps 1–2 were completed **2026-08-10**; MR-002's later termination without an economic
> verdict does **not** reopen or invalidate that prerequisite. **No evidence transfers between the
> programs.** This is a confirmation of an already-satisfied dependency, **not a decoupling waiver.**

---

## 1. Why this record is in Git

The v2.1.1 approval record established the precedent: a governing GAPPER decision lives in
`docs/design/Gapper/` so it is reviewable in a PR diff and readable during an incident with no AWS
dependency (ADR 0050; that record's own §7). The ATP implementation plan carries the operational
state of this gate, but the plan is **gitignored** — no PR, no CI, no review, no branch protection.
An owner ruling that closes a gate is *governing*, so it is recorded here and the plan references it.

## 2. The governing dependency, quoted exactly

From the approved design, **§9, paragraph [172]** (read read-only; artifact hash re-verified unchanged
before and after the read):

> "MR-002 continues on its independent v1.3 path; GAPPER never delays it. The binding constraint across
> the platform right now is OWNER capacity, not developer capacity: MR-002 execution-order Steps 1–2
> (physical recovery control; operational-custodian naming) are owner acts gating six prerequisites.
> Therefore Stage 0 of GAPPER begins only after MR-002 Steps 1–2 are complete. After v2.1.1 owner
> approval, developer-side Stage-0 preparation (dataset-contract drafting, reconstruction scripts against
> the development store) may proceed in parallel; owner adjudications may not compete."

**What the prerequisite actually is.** The stated condition is the *completion of two owner acts*, and
its stated rationale is *owner-attention scheduling* ("owner adjudications may not compete"). It is not
a condition that MR-002 produce an economic verdict, and it is not an evidential dependency. The design
forbids evidential dependency in both directions:

- §4 ¶[15] — "GAPPER-001 and MR-002 are independent peer alpha programs. They share governance machinery
  and research infrastructure; **they never share performance evidence.**"
- §10 ¶[176] — "No MR-002 evidence in any GAPPER package, and no GAPPER evidence in MR-002; concepts and
  machinery transfer, **verdicts never do.**"

It follows that MR-002 terminating without an economic verdict deprives GAPPER of nothing it was ever
entitled to.

## 3. Finding of fact — the prerequisite was met before termination

MR-002 execution-order **Steps 1–2 completed 2026-08-10**, twelve days before MR-002 terminated:

| Step | Content | State |
|---|---|---|
| **1** | WP-A — physical recovery control | **CLOSED.** A1–A6 executed 2026-08-10; archive on encrypted removable media, verified **from the medium** after a full disconnect/reconnect cycle; 13/13 objects, bound identity matches, PASS, offline. `INDEPENDENT_OFFLINE_RECOVERY_COPY = CREATED` |
| **2** | Operational-custodian naming | **NAMED — Jay Wang.** Explicit dual appointment recorded in **both** `MR002_ExternalRecoveryCopy_Submission_v1.0.md` §7 (recovery-media) and `MR002_OperationalCustodian_Appointment_v1.0.json` (operational). Self-attestation disclosed |

The MR-002 termination of 2026-08-22 is therefore **subsequent to, and independent of,** the satisfaction
of this prerequisite. A later event in a peer program cannot retroactively unsatisfy a condition that was
already met.

## 4. What this ruling does NOT do

This closure is narrow. It removes **one sequencing gate**. It does not authorize anything the approval
record withholds, and it grants no evidential relief.

- **§252 authorization scope is untouched.** Forward accrual, validation, confirmatory consumption, paper
  trading, and RANK-001 candidacy each still require their own separate, later owner authorization.
- **§8.1 operational readiness is untouched.** It gates *forward accrual*, not Stage 0, and remains
  binding on its own terms — including the probation window on the repaired collection path, whose clock
  has still not started (`WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED` defaults off; PR #407 unmerged).
- **§3 acceptance conditions are untouched.** Stage 0 may not pass on field size alone, and no unexplained
  `eligible_panel → eligible_count` collapse is permitted.
- **No evidence transfers.** Nothing from MR-002 may enter a GAPPER package, in either direction.
- **This is not a waiver.** Had Steps 1–2 been incomplete, this record would not exist; a decoupling would
  have required a different and more consequential ruling.

## 5. The controlling constraint is now data sufficiency, not governance

A preparation census run on 2026-08-22 under preparation authority — **non-verdict, no execution token
consumed** — measured the available corpus against the §3.1 dataset contract:

| Measure | Value |
|---|---|
| Candidate symbol-dates | 1,820 across **68 distinct calendar days** (2026-03-24 → 2026-06-30), 57 symbols |
| **Sufficient event-days** | **4** against a contract target of **250** (shortfall 246) |
| `premarket_bars` | available 5 · partial 631 · **absent 1,184**; median premarket bar count **0** |
| `quote_data` / `halt_data` / `locate_ssr_data` | **0 available / 1,820 absent** — all three categorically missing |
| `contract_complete` | **false** — `source_vendor = UNSET_OWNER_DECISION` |

**The shortfall is structural, not a data-quality problem.** The corpus spans 68 distinct days, so no
improvement in fidelity on the existing cache can reach a 250-event-day target. Only a dataset improvement
can. The five sufficient candidate-dates are additionally all April-2026 mega-cap technology names
(AMD, INTC, NFLX, NOW, NVDA) — a concentration that would fail §3.1's "materially different environments"
term independently of the count.

⛔ **This census is a preparation output and is not a Stage-0 disposition.** It identifies a Stage-0
data-sufficiency blocker. It is not a Stage-0 HOLD, PASS, or FAIL, and must never be cited as one.

**Evidence pin** (ADR 0050 bulk; S3-resident, not in Git):

```text
label            PREPARATION CENSUS / NON-VERDICT
repo_path        docs/implementation/evidence/gapper_stage0/gapper_stage0_census_2026-08-22_09717497.json
report sha-256   d5a3d89f6fe3b9dd5e33f6667d1505013ec007d508470ca15beaa846204448d5
byte_length      1272442
s3_version_id    oGhkxbbN1ugg7lcXs.V8XG0T8y0ks0wd
object_key       artifacts/governed/repo-docs/1.0/docs/implementation/evidence/
                 gapper_stage0/gapper_stage0_census_2026-08-22_09717497.json
manifest         manifests/s3/docs/implementation.inventory.json
harness commit   74d569daa6f46c61cd502d8faa119aa1edb2f6a3   (PR #662)
run_id           0971749798f7471293079b0e6c51ecf0
write_class      reconstruction
design anchor    2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d
schema           gapper_stage0/census_report/v1
```

The published bytes are the exact bytes measured and described; the report was **not** regenerated before
publication.

## 6. `source_vendor` — owner decision, deliberately left UNSET

**`source_vendor` remains `UNSET_OWNER_DECISION`.** It must **not** be populated merely to make
`contract_complete` true.

The approved design names no feed identity anywhere — it contains zero mentions of SIP, IEX, consolidated,
vendor, or feed — so the §3.1 `source/vendor` term is an open pre-execution governed decision recorded
outside the DOCX (amending the DOCX would void the approval). The preparation census ran against the
existing local cache and reconstruction inputs, which demonstrably do not meet the contract standard:
4 sufficient event-days of 250, zero quote/halt/locate coverage, and a daily spine ending 2026-06-16.

**Setting a vendor name against this dataset would convert a genuine missing-contract condition into a
metadata fiction.** When a replacement dataset is actually selected, `source_vendor` becomes a prospective
owner decision bound to that exact dataset identity, coverage period, field set, PIT semantics, and
provenance — and the preparation census is **re-run** against it.

⛔ **The 2026-08-22 census may not be reused as a Stage-0 result after the source changes.**

## 7. Resulting GAPPER state

| Item | State |
|---|---|
| **G4 sequencing gate** | ✅ **CLOSED** (this record) |
| Stage-0 preparation harness | Built (`74d569d`); custody PR **#662** in flight |
| Preparation census | ✅ **COMPLETE — non-verdict** |
| Stage-0 data sufficiency | ⛔ **BLOCKED** — 4/250 sufficient event-days; contract incomplete |
| Stage-0 execution | Technically permitted after G4, but presently **NOT EVALUABLE** under the available dataset |
| **Re-entry condition** | Governed dataset improvement **+** prospective `source_vendor` decision **+** re-run of the preparation census |

**A governed Stage-0 execution should not be spent to rediscover 4/250.** The preparation harness has
already established the prerequisite failure without issuing a verdict — which is precisely what the
interlock exists to make possible. The economically useful next GAPPER action is **dataset acquisition and
qualification**, not running the same insufficient corpus through a formally authorized Stage 0.

## 8. Open GAPPER controls, unchanged by this ruling

| Control | State |
|---|---|
| **PR #407** — box-native gapper screener (GAP-NATIVE-001, ADR 0041) | **DO-NOT-MERGE.** 4 owner decisions open. Merging starts no §8.1 probation clock — the enabling flag defaults off |
| **PR #511** — `INVALID-EVIDENCE / NO_SELECTION_CONTRAST` guard | **OPEN.** Until merged, the void v1 `DOES-NOT-TRANSFER` verdict path remains human-invokable |
| `scripts/repair_premarket_gate_provenance.py` | Contradicts the §5.5 principle that provenance cannot be repaired retroactively. Warrants a **separate removal/quarantine review** |

## 9. Provenance of this record

| Field | Value |
|---|---|
| Basis | Owner ruling, 2026-08-22, on the §9 dependency text reproduced verbatim in §2 above |
| Verification performed | Design artifact hash re-verified before and after the read (`2706c4dc…d73d`, 26,062 bytes, unchanged); three-way identity match against the approval record and the S3 manifest pin (Version ID `H7EeSrGbBrZexyk0bcuj7cG2FZBcSd6D`); MR-002 Steps 1–2 completion confirmed against the WP-A closure and the operational-custodian appointment record |
| Timestamp basis | UTC. ET clock times are **not** derived on the developer workstation — local TZ conversion there returns UTC and would misreport |
| Record location | Git (`docs/design/Gapper/`), per ADR 0050: governing, must be readable under pressure without an AWS dependency |
