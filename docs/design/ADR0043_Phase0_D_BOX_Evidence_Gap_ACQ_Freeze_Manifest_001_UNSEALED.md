# Evidence-Gap Acquisition Freeze Manifest — UNSEALED DRAFT

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 |
| Status | **UNSEALED DRAFT — NOT AUTHORITATIVE FOR ACCESS** |
| Manifest status | `UNSEALED` |
| Parent authorization | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 **APPROVED / EFFECTIVE** |
| Bound design | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** @ `71d346d8bd5665a3037d451ec4118f70431b69df` |
| Sealed JSON path (future) | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_ACQ_Freeze_Manifest_001_SEALED.json` |
| Body SHA-256 | **NOT COMPUTED — seal not performed** |
| Record selection / capture / reconstruction | **FORBIDDEN** until seal + separate acquisition-start |

This draft precommits the **structure** of bindings required by ACQ-AUTH-001 §2.
Fields marked `REQUIRED_FILL` must be completed **before** readiness and seal.
Placeholder presence → readiness **FAIL**. Exploratory source inspection for selection
before seal remains **FORBIDDEN**.

---

## 1. Sequence gate

| Step | Status under this draft |
|------|-------------------------|
| FILL (complete all REQUIRED_FILL) | **In progress** |
| READINESS_VALIDATION | Not started |
| SEAL + COUNTERSIGN | Not started |
| SEPARATE_ACQUISITION_START_DECISION | Not started |
| SOURCE CAPTURE / SELECTION / CONSTRUCTION | **Forbidden** |

`record_selection_authorized_by_this_document`: **false**  
`exploratory_selection_before_seal`: **FORBIDDEN**  
`source_inventory_inspection_for_selection_before_seal`: **FORBIDDEN**

---

## 2. Governing refs (partially bound)

| Ref | Value |
|-----|-------|
| `authorization_id` | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 |
| `authorization_status` | APPROVED_EFFECTIVE (effective on auth publication merge) |
| `authorization_merge_commit` | `REQUIRED_FILL` after auth PR merge |
| `authorization_path` | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Acquisition_Authorization_v1.0.md` |
| `authorization_path_sha256` | `REQUIRED_FILL` at seal |
| `design_package_id` | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 v1.0 |
| `design_package_merge` | `71d346d8bd5665a3037d451ec4118f70431b69df` |
| `design_package_path` | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Design_v1.0.md` |
| `design_package_sha256` | `REQUIRED_FILL` at seal |
| `v12_closeout_id` | ADR0043-PH0-D-BOX-V12-CLOSE-001 |
| `v12_closeout_merge` | `4232c1a` |
| `closed_campaign_freeze_id` | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| `closed_campaign_freeze_body_sha256` | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| `closed_start_id` | ADR0043-PH0-D-BOX-START-002 |
| `qual001_archives` | Immutable historical only — **must not mutate** |
| `offline_baseline_commit` | `d1c2fbf0a394c66728f6cc489577ae180ccdfb03` |
| `controlling_design_id` | ADR0043-PH0-CTRL-001 v1.1 |
| `integration_design_id` | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| `prior_o34_acq_freeze` | O34-ACQ-FREEZE-001 body `80dfd8ec…` — **not mutated; not reused in place** |

---

## 3. Account-3 identity (bound)

| Field | Value |
|-------|-------|
| `workbench_account_id` | `3` |
| `broker_account_id` | `PA34USW0Q8UO` |
| `broker_environment` | `paper` |
| `july24_digest_mutation` | **FORBIDDEN** |

Limits-digest pin (reference-only, non-mutating):  
`REQUIRED_FILL` — reuse prior governed july24 pin if still authoritative, else document superseding pin without mutation.

---

## 4. HOLD and blocks (bound)

| Control | Value |
|---------|-------|
| Broker order submission | **HOLD** |
| New live fills / observations / sessions | **NOT_AUTHORIZED** |
| Prospective instrumentation / new evidence population | **NOT_AUTHORIZED** (separate ruling required) |
| Gate execution or reopening | **NOT_AUTHORIZED** |
| D-WIRE | **BLOCKED** |
| Production imports / deployed-path observation | **NOT_AUTHORIZED** |
| Canary / ENFORCE / caps / July 24 changes | **NOT_AUTHORIZED** |
| Production stack commit excluded | `b0058bf335628f8dbde09a93915314f3a1f7743b` |
| Production modification | **FORBIDDEN** |
| Mutation of QUAL-001 / FREEZE-003 archives | **FORBIDDEN** |

---

## 5. Eligibility window

| Field | Value |
|-------|-------|
| `start_inclusive_utc` | `REQUIRED_FILL` |
| `end_exclusive_utc` | `REQUIRED_FILL` |
| `bounds_policy` | start_inclusive_end_exclusive |
| `start_basis` | `REQUIRED_FILL` (must not be derived from outcome inspection) |
| `end_basis` | `REQUIRED_FILL` (must not include post-authorization fabrication opportunities) |

---

## 6. Source systems and immutable snapshots

Policy: pin read-only locations and snapshot-binding protocol **without selecting observation
rows**. Live mutable stores use capture-at-acquisition-start of exact SHA-256 / Version ID
**after** seal + start, **before** selection.

| `source_id` | Class | Location / snapshot | Status |
|-------------|-------|---------------------|--------|
| `REQUIRED_FILL` | historical market / quote | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | app audit / plan / checkpoint / terminal | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | account-3 paper prior-authority records | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | O3 replay-surface candidate sources (quotes, checkpoints, loss, recovery) | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | O4-A decision-time quote sources | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | O4-B forensic baseline (`day_change` or equivalent) sources | `REQUIRED_FILL` | `REQUIRED_FILL` |
| `REQUIRED_FILL` | O5 Tier-A sealed anchor locate corpus | `REQUIRED_FILL` | `REQUIRED_FILL` |
| SRC-GOV-GIT-IMMUTABLE | governing git / design pins | commits in §2 | BOUND via governing refs |

`mutation_after_bound_snapshot`: **STOP_INCONCLUSIVE**

---

## 7. Source-field → target-surface mappings

### 7.1 O3 (EVIDENCE-GAP-001 §4)

| Target surface | Source field(s) / lineage | Reconstruction rule | Prohibited inference |
|----------------|---------------------------|---------------------|----------------------|
| `quote_provenance` | `REQUIRED_FILL` | `REQUIRED_FILL` | No synthesis; no later-quote backfill |
| `checkpoint_tuple` | `REQUIRED_FILL` | `REQUIRED_FILL` | No evaluator defaults |
| `loss_accounting_inputs` | `REQUIRED_FILL` | `REQUIRED_FILL` | No invented loss state |
| `recovery_inputs` | `REQUIRED_FILL` | `REQUIRED_FILL` | No invented recovery path |
| `authority_inputs` | Retain / map `REQUIRED_FILL` | Account-3 scoped only | — |
| Identity | `plan_id=ord:<orders.id>` unless superseding contract bound | Deterministic | — |

Completeness: all §7.1 gap surfaces non-null for QUALIFIED O3 eligibility.

### 7.2 O4-A (EVIDENCE-GAP-001 §5)

| Target surface | Source field(s) / lineage | Reconstruction rule | Prohibited inference |
|----------------|---------------------------|---------------------|----------------------|
| Two-sided bid/ask + freshness | `REQUIRED_FILL` | At or before first-submission cutoff | No post-submit quotes; no O4-B import |
| `model_available` | `REQUIRED_FILL` | Decision-time boolean | No default-true |
| O4-B-only fields | Must remain null/absent | — | Mix → STOP |

Cutoff rule: `REQUIRED_FILL` (FIRST_BROKER_SUBMISSION_BOUNDARY family).  
Unreconstructable cutoff → exclude `MISSING_CUTOFF`.

### 7.3 O4-B (EVIDENCE-GAP-001 §6)

| Target surface | Source field(s) / lineage | Reconstruction rule | Prohibited inference |
|----------------|---------------------------|---------------------|----------------------|
| Fills / terminal completeness | `REQUIRED_FILL` | QUAL-001 family bar | — |
| `fill_loss_per_round_trip` | `REQUIRED_FILL` | Provenance-bound | No invention |
| `day_change` or accepted equivalent | `REQUIRED_FILL` | Document source + as-of + account-3 scope | No assumption-filled baseline |
| Terminal loss/accounting | `REQUIRED_FILL` | — | No O4-A-only substitution |

### 7.4 O5 locate-only

| Target | Rule |
|--------|------|
| Tier-A anchors | Locate pre-existing sealed live-fill anchors only |
| Generation | **FORBIDDEN** (orders, fills, shadow sessions, broker submit) |
| Empty set | `anchors: []` **valid** → predetermined INCONCLUSIVE |

---

## 8. Completeness, exclusions, schemas, counts

| Binding | Value |
|---------|-------|
| Completeness criteria | `REQUIRED_FILL` — per-archive QUALIFIED bars aligned to §§7.1–7.3 |
| Exclusion reason codes | `REQUIRED_FILL` — include at least: `MISSING_REPLAY_SURFACE:*`, `MISSING_CUTOFF`, `MISSING_DECISION_TIME_QUOTE`, `MISSING_FORENSIC_BASELINE`, O4B_INCOMPLETE family, plus any freeze-specific codes |
| Archive schemas (paths + SHA-256) | `REQUIRED_FILL` — new O3 / O4-A / O4-B candidate schemas (not mutation of QUAL-001 IDs) |
| Expected count reconciliation | `REQUIRED_FILL` — planned accounting **before** selection |
| Deduplication key | `REQUIRED_FILL` (default candidate: `ord:<orders.id>`) |
| Unit of observation | `REQUIRED_FILL` |
| Symbol/session clustering | `REQUIRED_FILL` |

---

## 9. O4-A / O4-B no-mix and O4-A cutoff controls

| Control | Value |
|---------|-------|
| Separate archives | **Mandatory** — no payload merge |
| Look-ahead into O4-A | **FORBIDDEN** |
| O4-A cutoff | `REQUIRED_FILL` |
| Qualification must prove no-mix | **Mandatory** |

---

## 10. Tooling and commit identities

| Tool / artifact | Path | Commit / SHA |
|-----------------|------|--------------|
| Extractor / packager | `REQUIRED_FILL` | `REQUIRED_FILL` |
| Seal / readiness tooling | `REQUIRED_FILL` | `REQUIRED_FILL` |
| Schema fixtures | `REQUIRED_FILL` | `REQUIRED_FILL` |

---

## 11. Stop conditions and predetermined INCONCLUSIVE

Carry ACQ-AUTH-001 §7. Additionally:

| Condition | Disposition |
|-----------|-------------|
| Gap surface requires fabrication | STOP / REJECTED_AS_NON-BINDABLE |
| No recoverable Tier-A O5 anchors | `anchors: []` INCONCLUSIVE (valid) |
| Any REQUIRED_FILL remains at readiness | Seal **FAIL** |

---

## 12. Explicit non-authority of this draft

This UNSEALED draft does **not**:

- authorize evidence access, selection, reconstruction, or capture  
- seal the freeze  
- issue acquisition-start  
- reopen gates or authorize D-WIRE  
- mutate FREEZE-003 / QUAL-001 archives  

Next executable governance steps: complete REQUIRED_FILL → readiness → seal/countersign →
**separate** acquisition-start.

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 UNSEALED DRAFT.*
