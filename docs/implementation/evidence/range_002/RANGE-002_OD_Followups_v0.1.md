# RANGE-002 - OD Follow-ups v0.1 (OD-1 split classification; G10-REDUNDANCY decision sheet)

| Field | Value |
|---|---|
| Purpose | Two follow-ups kept separate from the P0 Decision Register push: (A) classify each OD-1 lineage constant individually under the owner's SPLIT ownership (D09 for research-lineage / non-equivalence constants, D03 for universe, vendor, acquisition and PIT data constants); (B) the G10-REDUNDANCY formal decision sheet (provisional id), revised to the owner's directions, with a verification of the design against the existing code and a list of conflicts |
| Date | 2026-10-10 |
| Base | `origin/main` at `1c305b8f` (PR #745 register, PR #746 backlog / schema proposal and PR #747 feasibility report merged). This file is a documentation publication candidate; its repository publication and any subsequent formal governance adoption are separate actions. It does not edit the register or any other merged document |
| Status | **DRAFT FOR OWNER REVIEW. Nothing here is a decision, a signature or an approval.** Formally approved decisions in this document: **0**. Every signature, name, date and SHA-256 field is BLANK. Everything labelled PROPOSED is a proposal only |
| Data accessed | None. Source and documents were read; no market data, provider, broker, backtest, enrollment or freeze |
| Code read | `apps/backend/app/validation/security_lineage.py`; `apps/backend/app/research/range002/{spec,governance}/` (the `apps/` tree is unchanged since `d61f313a`); the schema candidate `76730911` (branch `feat/range002-schema-batch`, local, read with `git show` only) |
| Other sources | P1/P2 Implementation Backlog v0.1 and Schema Change Batch Proposal v0.1 (merged in #746; items O-7 / OD-1 and O-13 / OD-3); Plan v0.5; Decision Sheets v0.1; P0 Decision Register v0.2 (merged in #745) |

---

## A. OD-1 - SPLIT OWNERSHIP: PER-PARAMETER CLASSIFICATION

### A.1 Owner direction

Split ownership: **D09** owns research-lineage and non-equivalence constants; **D03** owns universe, vendor, acquisition and PIT data constants. This is the owner's ruling as relayed; it is not a signed amendment of any sheet. D09's current Sheet scope is the ADR 0037 non-equivalence statement, the ORM-001 relationship, the C2 overlap limit and reviewers; D03's is universe N, PIT timing, SIP vendor and licence, data budget. Neither Sheet mentions security identity.

### A.2 Terminology

In `security_lineage.py` "lineage" means a **security's permanent identity** (vendor `permaticker` plus an effective-date interval), used to stop a reused ticker being treated as one company. In RANGE-002 governance "research lineage" means the **registry genesis** (the attempt-budget unit), and `hypothesis_lineage.yaml` (WP0.11) is the record of prior studies. All OD-1 parameters belong to the first meaning.

### A.3 Individual classification (every module-level parameter found in `security_lineage.py`)

Module-level uppercase names in the file: `SECURITY_IDENTITY_CONTRACT` (line 55), `LINEAGE_GAP_SESSIONS` (60), `LATE_START_SESSIONS` (64), `LINEAGE_BRIDGE_HOLE_MIN_SESSIONS` (70). The `LineageRefusal` members are at lines 73-87. No other constants exist in the module. Values are quoted as they exist in code; none is chosen here.

| # | Parameter | Value in code | What it governs | Classification | Reason |
|---|---|---|---|---|---|
| 1 | `LINEAGE_GAP_SESSIONS` | 20 | Longest run of consecutive governed sessions with no mark, inside the span where the active lineage's metadata says the security trades; a longer run is a structural discontinuity | **D03** | Decides which symbol-days enter the PIT universe; Plan WP1.5 (permaticker identity, delisted names) |
| 2 | `LATE_START_SESSIONS` | 20 | How late the first mark may fall behind the span the metadata claims before metadata and prices are treated as disagreeing | **D03** | Same: price/metadata agreement for universe eligibility |
| 3 | `LINEAGE_BRIDGE_HOLE_MIN_SESSIONS` | 20 | Shortest in-window hole that separates two price segments far enough apart to be disconnected; code comment: owner-approved 2026-07-29 as an INITIAL value, changing it needs review | **D03** | Same. The 2026-07-29 approval predates RANGE-002 and is not a RANGE-002 approval |
| 4 | `SECURITY_IDENTITY_CONTRACT` | `PERMATICKER_EFFECTIVE_INTERVAL_V1` | Version string of the identity rule, bound into the governed construction identity | **Split pending, owner-directed, unsigned - D03 identity representation, D09 identity equivalence** | Identity rule of the PIT universe; a pinned dependency together with items 1-3; D09's overlap and non-equivalence checks must use the same identity definition (see the vNext package A1.2c) |
| 5 | `LineageRefusal.NO_ACTIVE_LINEAGE` | member | No active lineage at the session | **D03** | Universe eligibility reason code |
| 6 | `LineageRefusal.MULTIPLE_ACTIVE_LINEAGES` | member | More than one active lineage | **D03** | Same |
| 7 | `LineageRefusal.MISSING_PERMANENT_ID` | member | Vendor data lacks the permanent identifier | **D03** | Vendor / acquisition property (Sheets F2) |
| 8 | `LineageRefusal.LOOKBACK_CROSSES_LINEAGE` | member | A symbol changed hands inside the lookback | **D03** | Ticker-reuse handling in the universe |
| 9 | `LineageRefusal.METADATA_PRICE_DISAGREE` | member | Metadata and prices disagree (uses items 1-3) | **D03** | Universe eligibility |
| 10 | `LineageRefusal.UNRESOLVED_REMAP_GAP` | member | A remap gap neither source explains | **D03** | Universe eligibility |
| 11 | `LineageRefusal.AMBIGUOUS_EFFECTIVE_INTERVAL` | member | Effective interval not unique | **D03** | Universe eligibility |

Other items found in the module that are not constants but belong to the same adoption question: `SecurityIdentityUnavailable` (line 90; the store lacks a permanent identifier, so construction fails closed rather than falling back to ticker identity): **D03** (vendor / data property). The `lookback_start` argument of `resolve_lineage` and `assess_universe` (lines 211, 325) is supplied by the caller, not a module constant; for RANGE-002 it follows the universe window, `universe.adv_window_days` (fixed at 20 in the skeleton): **D03**, not an OD-1 parameter.

### A.4 Result and unresolved items

- **D09 classification: none.** No OD-1 parameter is a research-lineage identity or related-program constant. Under the split rule ten of the eleven classified items fall to D03; the eleventh, `SECURITY_IDENTITY_CONTRACT`, is split pending (owner-directed, unsigned): D03 identity representation, D09 identity equivalence. D09 keeps the research-lineage items (registry genesis, ORM-001 relationship, C2 overlap limit and reviewers); the register lists them elsewhere.
- **Cross-references (explicit):** (i) refusals feed `data.exclusion_bound` (D03 / Q-P1-4) and the WP1.8 coverage report (D03); (ii) the value echo into the P1 data manifest is a D03 deliverable (`data_manifest.json`, Plan WP1.2); (iii) D09's non-equivalence criterion 1 uses signal history, not security identity, so it does not consume these constants; (iv) a reader should not read "lineage" in these constants as the registry genesis (A.2).
- **Unresolved, kept visible:** (a) the adoption statement itself (adopt as-is, stricter, or looser; the backlog's PROPOSED treatment is adopt as-is and echo the values so a later change to the shared module is detected by a manifest-hash mismatch) is still unsigned; (b) whether the owner nevertheless wants the adoption **statement** recorded on the D09 sheet, with D03 owning the manifest echo (a split of the same decision); that would be an explicit D09 scope extension, not covered by D09's current Sheet scope; (c) no value is proposed here beyond what exists in the code.

### A.5 Record (BLANK)

| Field | Value |
|---|---|
| Decision | Adopt, or change, the lineage refusal constants for RANGE-002 |
| Home per item | per A.3: D03 (ten items); `SECURITY_IDENTITY_CONTRACT` split pending, owner-directed, unsigned (D03 identity representation, D09 identity equivalence); any D09 recording of the adoption statement: BLANK |
| Adoption (as-is / stricter / looser) | BLANK |
| Approver | Owner |
| Pinned documents | `security_lineage.py` at a named commit; data manifest (after P1); this file. SHA-256: BLANK |
| Signature / date | BLANK |

---

## B. G10-REDUNDANCY - FORMAL DECISION SHEET (PROVISIONAL ID; PROPOSED)

### B.1 Owner directions (as relayed)

1. Preserve the correlation threshold **<= 0.85** unchanged.
2. A failed or undefined G10 **prevents advancement / promotion**.
3. The underlying P4 statistical results are **preserved**; G10 does not alter them.
4. **Pre-register the comparator policy** and **bind its SHA-256 to the frozen research identity before the first P3a authorization**.
5. Comparator membership is **either version-pinned or a deterministic preregistered membership rule**.
6. **Revalidate the required comparator evidence before P4.**
7. **Fail closed** when required evidence is missing.
8. **Do not add or reinterpret verdict statuses** (no new enum value, no changed meaning) without a separate contract review.

### B.2 Sheet

| Element | Content |
|---|---|
| ID | **G10-REDUNDANCY** (provisional) |
| Governing text | Plan s5.1 line 665: "G10 \| Redundancy \| Correlation with approved strategies <= 0.85, else flagged and not promotable \| Promotion constraint"; Plan s5.1A (gates preserve G0-G10 with denominator, missing-data handling; `UNDEFINED` never PASS); schema `gates.redundancy_corr_max` equality validator (`schema.py:432`); backlog O-13 / OD-3 (comparison set outside the spec, hashed list of strategy ids and the SHA-256 of their daily net-return series) |
| Unchanged | Threshold 0.85; G10 as a promotion constraint |
| Decision authority | **Owner decides.** **Trading-expert reviewer** reviews that the comparator policy covers the relevant approved strategies. **Independent validator** reviews the correlation method and the integrity of the evidence. Names BLANK |
| Required signatures | Owner; trading-expert reviewer; independent validator (BLANK) |
| Status | UNSIGNED. 0 approved |

### B.3 Elements

| # | Element | Requirement | Value |
|---|---|---|---|
| 1 | Comparator policy document | One pre-registered document containing: the membership definition (item 2), the correlation method (item 3), the evidence list and its required format, the failure behaviour (item 4), and the revalidation rule (item 6). Its SHA-256 is the "comparator-policy SHA-256" | **OWNER MUST DEFINE**; the platform's list of approved strategies is not in the documents read, so no list or rule is proposed |
| 2 | Membership | Either (a) a **version-pinned list**: strategy id, the version (spec hash or git commit), and the SHA-256 of each daily net-return series; or (b) a **deterministic preregistered membership rule** that produces the list from a fixed source state without discretion. No comparator may be selected, added or dropped after RANGE-002 results are observed | **OWNER MUST DEFINE** (a) or (b) and its content |
| 3 | Correlation method | Predeclared: the metric; the series (daily net return per backlog O-13); the sampling frequency; the date alignment; the treatment of days without trades in either series; the minimum overlap in days; whether the signed or the absolute correlation is compared with 0.85; the evaluation window | **OWNER MUST DEFINE** every item; no value proposed |
| 4 | Fail-closed behaviour | If any required evidence is missing or invalid (a comparator absent, a series hash mismatch, minimum overlap not met, undefined correlation), G10 is **UNDEFINED, not PASS**, and the run is **not eligible for advancement or promotion**. This is PROPOSED to follow the Plan's existing treatment of undefined PF and undefined years | Principle: PROPOSED. Details **OWNER MUST DEFINE** |
| 5 | Effect on P4 statistics | A failed or undefined G10 **does not alter** the P4 statistical gate results or the audit pack's statistical content; it is recorded as the G10 entry of the gate report and blocks advancement / promotion only | Owner direction; wording of the Plan needs a clarification (conflict K1) |
| 6 | Pre-P3a binding | The comparator-policy SHA-256 is bound to the frozen research identity **before the first P3a authorization** (see B.5 for where it can be bound) | Owner direction |
| 7 | Revalidation before P4 | Before any P4 authorization the required comparator evidence is revalidated: all pinned series present, hashes equal, method inputs valid. If revalidation fails the P4 authorization request is REFUSED (owner-directed form; a PROPOSED prerequisite requiring formal adoption: signed record plus Plan amendment; K5 guard enforcement is NOT authorized, so this is procedural until then) | Owner direction; see conflict K5 |
| 8 | Verdict statuses | **No new enum value and no changed meaning** of any `Verdict` member without a separate contract review | Owner direction |
| 9 | Exposure | Reading other strategies' 2022-2025 series is contact with that period for those programs; the D01 contact audit lists it. It is not RANGE-002 result exposure | Record in the exposure ledger (D01) |

### B.4 Evidence required

The owner's approved-strategy source state and the resulting list or rule; the daily net-return series and their SHA-256 values (from the platform's records, not from RANGE-002); the validator's review of the correlation method including a synthetic check on simulated series with known correlation (synthetic only); the trading expert's confirmation of completeness; the policy document and its SHA-256 pinned in the sign-off packet.

### B.5 Verification of the design against the existing code (conflicts first)

All citations are to files in this repository at the base; the schema candidate is `76730911`.

**Conflicts and gaps found (before any implementation is proposed):**

| ID | Conflict / gap | Exact location | Consequence |
|---|---|---|---|
| **K1** | Plan wording vs the owner direction. Plan s5.1 says "All gates must pass." and lists G10 in the same table; the owner direction is that a failed G10 does not alter the P4 statistics and only prevents advancement | `RANGE-002_Implementation_Plan_v0.5.md:649` ("All gates must pass") and `:665` (G10 row, "Promotion constraint") | Read literally, a failed G10 would make P4 not PASS. The Plan needs a clarifying sentence that G10 is evaluated and reported separately and does not change the P4 statistical outcome. This is a Plan clarification, not an enum change |
| **K2** | No enforcement point for "prevents advancement". The registry records a `RunStatus` (COMPLETED / FAILED / DEFECT / ABORTED), never a `Verdict`; `verdict.py` is imported by neither the registry nor the guard. The only advancement controls in code are the phase-predecessor table and the outright P5 refusal | `governance/run_registry.py:129-134` (RunStatus), `:545-565` (`close_run`); `governance/verdict.py:21-38`, `:53-72`; `governance/results_guard.py:425-429` (`_REQUIRED_PREDECESSORS`, P5 entry), `:672-675` (P5 refused outright) | Today nothing can advance past P4 (P5 is refused), so there is no present exposure. But the enforcement point the owner direction needs (a check at P5 authorization / activation and at the P6 decision pack) does not exist and would be new code in the later P5 work |
| **K3** | No place to bind a comparator-policy hash exists today. The spec's `Gates` carries only the fixed threshold; the schema candidate adds none; the governance manifest has an exact key set | `spec/schema.py:421-432` (main) and `:598-609` (candidate `76730911`, `redundancy_corr_max` at 609); `spec/manifest.py:52-60` (`_KEYS` exact set) | Binding requires a schema change (a new hashed field) or a manifest-schema change. Neither is a documentation-only act |
| **K4** | "Before the first P3a authorization" is enforceable mechanically only for a hashed spec field. `authorize()` requires a frozen, signed spec on every call, and the field would be inside `spec_sha256` (hash covers everything except `signoff`) | `governance/results_guard.py` (`_spec_checks`, def at `:361`, called at the start of `authorize`, signature `:601-620`); `spec/schema.py:524` (`hashable_payload`) | A hashed spec field gives the pre-P3a binding with no guard change. A sign-off-packet pin is procedural only. A manifest key is read from the executing checkout and its SHA-256 is recorded on `capability_issued` rows but not compared across rows (accepted limitation NF3) (`results_guard.py:652`, `:770-776`), so it is the weakest |
| **K5** | No hook for "revalidate before P4". `authorize()` has no comparator-evidence parameter; `PredecessorEvidence` carries only an audit pack and a selection record, and its content check covers only the embedded run id and spec hash | `governance/results_guard.py:601-620` (signature), `:211-224` (`PredecessorEvidence`), `:439` (`_check_phase_order`) | The P4 revalidation cannot be enforced without a code change (a new evidence argument and a check, and a record on `capability_issued`). Until then it is procedural |
| **K6** | Sequencing with unmerged schema work. A new hashed field raises the required P0 field count (86 with the schema candidate, to 87) and touches `schema.py` and the view / adapter, where the schema candidate and PR #740 also work | `spec/schema.py`; `governance/spec_view.py` (`FrozenSpecView` Protocol, lines 47-79) and `governance/spec_adapter.py` (`__slots__`, lines 76-88) | Must land before any real freeze and be sequenced with the candidate and #740 |
| **K7** | Hazard when evidence is found missing after P4. Refusals before `mark_capability_issued` consume nothing, but a P4 run that has already been authorized has consumed the holdout window (no reissue). A comparator-evidence defect found only after the run cannot be repaired by rerunning; G10 could only be re-evaluated offline from pinned evidence | `governance/results_guard.py:758-776` (holdout consume at 765, `mark_capability_issued` at 768) | This is why the owner's revalidation before P4 matters; it should be a hard pre-authorization step |

**Existing patterns that fit (no conflict):**

- A hash-only spec field already exists in the same block: `governance.economic_thesis_sha` (`schema.py:450`, recorded in the hash, no guard check). A field such as `governance.comparator_policy_sha256` would follow it and bind the policy hash to the frozen identity with a schema change only.
- A hash-in-spec plus guard-verified artefact pattern already exists: `governance.exposure_signed` (`schema.py:454`) is checked by `_check_exposure_binding` (`results_guard.py:408`, called at `:727`). A comparator-evidence check could follow it, but that is a guard code change.

**Does "prevent advancement without altering verdict statuses" fit the current verdict enum?** Yes, conditionally. The enum already separates the statistical outcome of P4 (`PASS_HISTORICAL_PENDING_PROSPECTIVE` or `REJECT`, `verdict.py:57-60`) from later stages (`P5`, `P6`, `verdict.py:61-71`). G10 can be recorded in the gate report (the closed per-gate result with pass / fail / UNDEFINED in backlog S13) and enforced as an additional condition at the P5 activation and the P6 decision, without a new member and without changing any member's meaning. The conditions are: K1 is resolved by a Plan clarification; and K2 is closed by new checks in the later P5 / P6 code, not in the enum. A consumer that reads only the verdict (for example `is_valid_transition(PASS_HISTORICAL_PENDING_PROSPECTIVE, P5, ...)`) would not see G10, so every advancement path must also consult the gate report; a separate contract review is needed only if someone wants the verdict itself to encode G10.

### B.6 Where the comparator-policy SHA-256 can bind (G10-C1, G10-C2, G10-C3; none selected)

Naming: the alternatives are named G10-C1 (hashed spec field), G10-C2 (manifest key) and G10-C3 (sign-off packet pin) to avoid collision with the P5 account-binding "option B". Mapping: this file's earlier "Option 1 / 2 / 3" = G10-C1 / C2 / C3; the vNext package's earlier draft "Option B" = G10-C1 and "Option A" = G10-C3.

| Name | Binding | Before first P3a authorization? | Code change | Strength |
|---|---|---|---|---|
| G10-C1 | New hashed spec field `governance.comparator_policy_sha256` (pattern: `economic_thesis_sha`) | Yes, automatically (the frozen spec is required by every `authorize`) | Schema, skeleton, tests, adapter / view only if a guard check is wanted; no guard change for the binding itself | Strongest: part of `spec_sha256` and of every capability |
| G10-C2 | New key in the governance manifest | Only by process (the manifest is edited by reviewed git change and read from the checkout) | Manifest schema (`manifest.py:52`), loader, tests | Weaker (NF3); sha recorded on `capability_issued` rows |
| G10-C3 | Sign-off packet pin | By process only | None | Procedural; nothing in the registry |

Recommendation (not a decision): G10-C1 if the schema work is still open; it is the only option that makes the pre-P3a requirement mechanical without touching the guard.

### B.7 Proposed amendment to the signing sequence (PROPOSED; NOT applied to the register)

The register's s51 has 32 numbered items (Steps 1-7). With the owner's directions the comparator policy must be hashed into the frozen identity (G10-C1) or at least pinned before the first P3a authorization, so it must be signed **before the real freeze**. Proposed amendment:

- **New item "12A", G10-REDUNDANCY policy pre-registration**, in **Step 5**, immediately after D10 (item 12). If strict numbering is wanted, it becomes item 13 and the list becomes 33 items (register items 13-32 shift to 14-33). Decides: owner; trading-expert reviewer and independent validator review. It needs D06 (Step 2: statistical conventions and validator), D18 (Step 4: trade basis, which defines the daily net-return series) and D10's equity-sampling definition (item 12) signed first.
- **What it blocks:** under G10-C1, the **real freeze** (new mandatory field) and therefore P0 exit and the first P3a authorization; under G10-C2 or G10-C3, the first P3a authorization by process; in all cases the P4 authorization (revalidation, K5), and the redundancy diagnostics of the backlog (B-17 / PR-F, which may proceed on synthetic data meanwhile).
- **New later checkpoint "P4-pre" (outside the pre-freeze list):** the comparator-evidence revalidation record, completed before any P4 authorization. It is a procedural record until the K5 code exists. It is not a pre-freeze signing item and does not change the 32/33 count.
- **Register consequences if adopted (later, not now):** the unnumbered OD-3 note in s51 is replaced by item 12A; s49.2 item 5, the OD-3 row and s52 are updated; the s14 field trace gains one field under G10-C1; a Plan clarification for K1 is proposed; no verdict enum change.

### B.8 Record (BLANK)

| Field | Value |
|---|---|
| Decision | G10-REDUNDANCY: comparator policy (membership, method, evidence, failure behaviour), binding location, revalidation rule |
| Value (owner states) | BLANK |
| Approvers | Owner; trading-expert reviewer; independent validator (BLANK) |
| Pinned documents | this file; Plan v0.5 (`c7ebaf71`); the comparator-policy document (does not exist yet). SHA-256: BLANK |
| Signature / date | BLANK |

---

## C. Invariants

0 formally approved decisions. All signatures, names, dates and SHA-256 fields are BLANK. No value is invented: the numeric values quoted are the existing constants in `security_lineage.py` (20, 20, 20), the schema threshold 0.85, and the fixed skeleton value `universe.adv_window_days` = 20. No enrollment, freeze, data access or signing occurred; no code was changed.
