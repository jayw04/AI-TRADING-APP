# RANGE-002 Sign-off scope by gate v0.1 (Lane G)

| Field | Value |
|---|---|
| Status | **ANALYSIS / DRAFT. NOT A RULING. NOT ADOPTED.** It classifies, lists and states what the repository establishes. It appoints no one, accepts no role, fills no sign-off and adopts no value. |
| Date | 2026-10-12 |
| Input | The 33-row table in `RANGE-002_Signoff_Reconciliation_v0.1.md` (worktree `C:\LLM-APP\wt-r002-b`, PR #758 branch `docs/range002-lane-b-signoff-table`, commit `dd106de5`). Row numbers below are that table's numbers. |
| Checkout read | `C:\LLM-APP\wt-r002-g` = `origin/main` `9d90d96c` (contains no screen profile). Screen-profile code verified read-only in `C:\LLM-APP\AI-TRADING-APP`, branch `feat/range002-screen-kernel`, HEAD `1ecf811b` (`spec/schema.py` has screen profile v1 and v2; not merged to main). A-SCREEN amendment read from the untracked file in `C:\LLM-APP\AI-TRADING-APP`; its own Status says "NOT ADOPTED BY ANY AUTHENTICATED RECORD". |
| Role assumptions (owner rulings R5, as given) | Code author: Claude Code (agent). Non-author code reviewer: Jay Wang (owner; dual role disclosed). Validator: 陈友潼 (Chen Youtong), gate sign-off, PENDING acceptance. Trading expert: 方炳雄 (Fang Bingxiong), PROPOSED gate holder for `signoff.trading_expert`, PENDING owner ruling and acceptance. Risk/loss-control reviewer: 肖学焦 (Xiao Xuejiao), advisory, NO gate sign-off, PENDING. Liaison: 梁云鹏 (Liang Yunpeng), no sign-offs, the owner's relative, ineligible for any independence-bearing role. |
| Standing rules applied | **PENDING counts as VACANT for every gate.** **No sign-off may be counted GENUINE until PR #740 (all-pairs distinct sign-off check) is merged on main.** On `origin/main` `9d90d96c`, `git log` contains no #740 commit; REG s6.1 line 430 and s51 item 29 record it as OPEN, not merged. |
| Anything not established from a repository file | marked **UNKNOWN** |

Abbreviations: REG = `RANGE-002_P0_Decision_Register_v0.2.md`; VIR = `RANGE-002_Validator_Independence_Requirements_v0.1.md`; PLAN = `RANGE-002_Implementation_Plan_v0.5.md`; A1 = `RANGE-002_Design_Addendum_A1.md`; SHEETS = `RANGE-002_P0_Decision_Sheets_v0.1.md`; VNEXT = `RANGE-002_P0_Decision_Package_vNext_v0.1.md`; HARD = `RANGE-002_Governance_Hardening_Design_v0.1.md`; AMD = `RANGE-002_A-SCREEN_Amendment_v0.1.md`; SCH = `apps/backend/app/research/range002/spec/schema.py`; MAN = `.../spec/manifest.py`; RG = `.../governance/results_guard.py`; FRZ = `apps/backend/scripts/research/range002/freeze_spec.py`. All evidence files are under `docs/implementation/evidence/range_002/`. Line numbers are file lines in the checkout named above.

Naming collision to avoid: REG s51 (line 2706) has a heading "Step 6 - audits, feasibility and thesis" (the owner-ordered signing list of 32 items). That "Step 6" is a signing-order group (D01, D03, D05, D09, D12, D13, D14, D07). It is **not** the gate "STEP-6" used in this document. Here STEP-6 is the owner's instruction term: the first descriptive run on real data under a P3A capability.

---

## 1. Gate definitions (G1)

The repository's own gate columns are in REG s5.1 (lines 384-404): "(a) real freeze, (b) first enrollment, (c) P1 start, (d) first P3a run, (e) distinct-role PR merge"; abbreviations REG:15 (FRZ, ENR, P1, P3A, MRG). The seven names requested map as follows.

| Gate | One-line definition, grounded | Where defined |
|---|---|---|
| MERGE | Merge to `main` of a reviewed change that later gates depend on: the screen-profile change (guard-adjacent: Backend FULL, ADR 0043 gate, Linux acceptance, two-hour walk-away, eligible non-author reviewer), the distinct-role check PR #740 (REG "MRG"), or the schema candidate (REG s51 item 30). | AMD:49, 160, 164 (s8 blocker 1); REG:15; REG s5.1 col (e) lines 389-404; REG s51 items 29-30 |
| FETCH-AUTH | Authorization for the first bulk historical data pull (P1 start, PR 5): vendor storage/use answers obtained, isolated research environment (C12) named, licence and budget decided. "Do not fetch or store bulk history until (1)-(3) are answered." | AMD:83 (s4), AMD:166 (s8 blocker 3); REG:15 ("P1 = first data pull, PR 5"); REG:111 (C12); REG s5.1 col (c) lines 395-396, 404; PLAN:341 (WP1.2, isolated environment only) |
| FREEZE | A real `freeze_spec` run: spec with every required field non-null, genesis and attempt limits equal to the owner-approved manifest, `signoff.owner/trading_expert/independent_validator/date` non-blank, `spec_sha256` computed over everything except `signoff`. (Genesis enrollment ENR is the prerequisite that produces the id.) | FRZ:73-93; SCH:476-481, 539-549; REG:15, 79; REG s5.1 col (a)-(b) lines 389-404; PLAN:334 (P0 exit gate) |
| STEP-6 DESCRIPTIVE RUN | First governed P3A run on real 2016-2019 data (DEVELOPMENT_SELECTION partition) under a results-guard capability: spec frozen and signed, exposure ledger signed and bound, genesis registry = spec = manifest, attempt limit available, trial-ledger row written first. Stage 1 descriptive screen only; it cannot select a formal winner, authorize P3B or claim qualification. | RG:370, 408-420, 672-682, 726, 756-760; AMD:94 (R-g), AMD:122 (s6b stage 1); PLAN:324 (WP0.4), PLAN:587-589 (WP4.1 P3a) |
| VALIDATION | Anything that produces an inferential or confirmatory verdict: stage 2 statistical selection (bootstrap, max-statistic test, selection rule), P3b confirmation (2020-2021), P4 single-use holdout, with the validator's confirmation of statistics. | AMD:123, 128 (s6b stage 2, s6c); REG:92, 99 (D06, validator confirms numbers); PLAN:599-613 (WP4.1 P3b, P4) |
| PROMOTION | P5 paper / P6 live approval: P5 account policy and marker, sole P6 approver, executor and shadow run. | AMD:184 (s9); REG:93 (D07); SHEETS:24 and REG:94 (owner = sole P6 approver) |
| OTHER | Not needed by any of the above: post-run records, or items that the repository places at P0 exit or build time only and that no tool or screen-path clause reads. | PLAN:750 (`approval_log.md`); REG s5.1 |

Order stated by the owner's instruction: MERGE, FETCH-AUTH, FREEZE, STEP-6, VALIDATION, PROMOTION. In AMD s8 the order of work is items 1-8 (lines 162-171); whether bulk fetch precedes or follows the screen-spec freeze on the screen path is not fixed by any document (REG s5.1 puts D03/D11 at freeze (a) and "vendor, licence, budget before any pull" at P1 (c)); UNKNOWN.

Profile caveat for FREEZE. A row classified FREEZE may be required **only for a full-profile freeze**; the column "Screen path" says which. `governance.roles`, `governance.economic_thesis_sha` and `p5.*` are in `SCREEN_V1_EXEMPT` (feature branch SCH:555-573) and are not required for a screen-profile spec (AMD:157, :46).

---

## 2. Classification of all 33 rows (G1)

"Screen path" key: **T** = refused by tooling (`freeze_spec`/guard) for a screen-profile spec; **G** = required by an owner ruling or AMD clause, no tool checks it; **V** = VIR recommends for any real freeze, the owner's V-8 selection decides (blank today); **?** = the repository does not say whether it applies on the screen path (UNKNOWN, owner scope ruling needed); **N** = not needed to reach a STEP-6 run.

| # | Requirement (short) | Earliest gate | Clause (file:line or section) | Screen path |
|---|---|---|---|---|
| 1 | `signoff.owner` non-blank | FREEZE | FRZ:80-82; SCH:476-481, 539-549; RG:370; REG:94 (D08 "FRZ (T)") | T |
| 2 | `signoff.trading_expert` non-blank; A1 s10 trading-expert row | FREEZE | same as row 1; A1:101-107; REG:94 | T |
| 3 | `signoff.independent_validator` non-blank | FREEZE | same as row 1; REG:117 (ACC-R1L1b "FRZ (G)"); REG s6.1 line 430 | T (field) and G (genuine validator) |
| 4 | `signoff.date` present, not future | FREEZE | FRZ:83-85; SCH:539-549 | T |
| 5 | `signoff.spec_sha256` = recomputed hash (tool) | FREEZE | FRZ:86-93; SCH:476-481 | T (tool computes) |
| 6 | D01 `governance.exposure_signed` binding the ledger sha | FREEZE | RG:408-420; REG:87 ("FRZ (T)"); REG s5.1 line 393; feature-branch `SCREEN_V1_REQUIRED` and `SCREEN_V2_REQUIRED` both list it | T |
| 7 | Exposure ledger signed (WP0.6 contact audit incl. AI-session history) | FREEZE | RG:726 (`require_signed`); REG:87; REG s5.1 line 393 ("T + G (audit)"); PLAN:326, 334 | T (ledger signed) and G (audit) |
| 8 | Manifest triple `approved_registry_genesis_id/approved_by/approved_on` | FREEZE | FRZ:73-79; MAN:92-115; REG:114 (M-gen "FRZ (T), P3A (T)"); REG s5.1 line 402 | T |
| 9 | Genesis enrollment: M-loc, M-ops (operator and witness), written authorization | FREEZE (via ENR, the prerequisite that creates the genesis id) | REG:113; REG s2.2 items 2-4 (lines ~149-158); REG s5.1 line 401 col (b) | G |
| 10 | P3a/P3b attempt limits in manifest = spec | FREEZE | FRZ:79; RG:756-760 (`_check_attempt_limit`); REG:115-116 ("FRZ (T), P3A (T)") | T |
| 11 | D08 `governance.roles` and SoD option | FREEZE (full profile only) | SCH `governance.roles`; REG:94, 95; REG s5.1 line 399; AMD:157 and SCREEN_V1_EXEMPT list it as exempt | N (field exempt). The three `signoff` names it feeds are rows 1-3 |
| 12 | D13 economic thesis sha, research lead + trading expert | FREEZE (full profile only) | SCH:450, 461-466; PLAN:329; REG:105; AMD:157 (exempt) | N |
| 13 | Independent-validator eligibility and appointment act | FREEZE | REG:117; REG s6.1 line 430 ("before formal P0 approval or real specification freeze"); AMD:89 (R-b), AMD:165 (blocker 2) | G |
| 14 | VIR V-2.1 roster, three different individuals | FREEZE | VIR:34, recommended minimum VIR:45 | V |
| 15 | VIR V-2.2 validator attests no authorship of engine/spec/freeze tooling | FREEZE | VIR:35, :45, :51 | V |
| 16 | VIR V-2.3 validator attests no prior exposure, reconciled with ledger | FREEZE | VIR:36, :45 | V |
| 17 | VIR V-2.6 conflicts-of-interest per signer; V-2.7 relationship disclosure | FREEZE | VIR:39-40; minimum list VIR:45 names V-2.6 only, not V-2.7 | V (V-2.6); V-2.7 not in the recommended minimum |
| 18 | VIR V-8 owner selection table; V-2.4/2.5/2.8/2.9/2.10 | FREEZE | VIR:104-121 (V-8 "Required for real freeze? Yes/No/Waived"); VIR:41-43; V-2.4/2.5 "once Level 2 exists" VIR:45 | V (table). Level 2 items: N (not built, VIR V-6) |
| 19 | Addendum A1 signature (owner, trading expert, validator) | FREEZE | REG s5.1 line 392 (A1 "G (and the schema assumes A1)", col (a)); REG:86 ("FRZ (G...), P1, P3A"); PLAN:334; A1:101-107 | ? (AMD R-a..R-g, lines 88-94, do not list A1; O-3 adopts "the existing P3a (2016-2019)", AMD:25) |
| 20 | Statistics/criteria block D06, D18, D17, D19, D02 | FREEZE | REG:88, 92, 105-109 (each "FRZ (T)"); REG s5.1 line 394 | T for D17 `p3.criteria`, D19 `exits.*`, D18 `gates.basis/trade_unit` (in v1 and v2 required lists). D06 `stats.bootstrap.*` and D02 `stats.hypothesis_family`: required in v1, **deferred in v2**. Validator confirmation of D06/select_exit: N for stage 1 (REG:92, 99; AMD:128 "before an inferential verdict") |
| 21 | D09 non-equivalence record, C2 overlap, reviewers of criteria 2 and 3 | FREEZE (REG treats as a G at real freeze and at P0 exit) | REG:98-99; REG s5.1 line 397; PLAN:325, 334 | N (value `registration.related_programs` is required in v1 and deferred in v2; the reviewers' findings are P0 exit only) |
| 22 | G10-REDUNDANCY comparator policy pre-registration (item 12A) | STEP-6 (conditional; PROPOSED, not binding) | REG s51 line 2729 (under G10-C1 blocks the real freeze; under G10-C2/C3 blocks first P3a authorization by process); VNEXT A2.2 line 178, A2.9 lines 300-310 (binding alternative BLANK) | ? |
| 23 | D07 P5 policy and `p5.account_id` resolution; validator reviews schema change | MERGE (of the schema candidate, REG s51 items 4 and 30) and full-profile FREEZE | REG:93; REG s51 items 4, 24, 30; SCH P5 block; AMD:157 (exempt); REG s5.1 line 394 | N |
| 24 | Owner-valued decisions D03, D04, D05, D10, D11, D12, D14, D15, D16 | FREEZE | REG:89-91, 96-113 ("FRZ (T...)" per row); REG s5.1 lines 394-395 | T for the subset in the screen required list (D03 `universe.n`/`data.vendor`, D11 `data.fetch_mode`, D15 `costs.*`, parts of D05 and D14); N for D04, D10, D12, D16 (`gates.yearly/win_rate/max_dd`, `stats.regime.*`, `diagnostics.taxonomy` exempt) |
| 25 | WP0.8 AI provenance record with the human who confirmed final logic | FREEZE (P0 exit; REG treats signed WP0.5-0.12 artefacts as G at real freeze) | PLAN:328; PLAN:334; REG s5.1 line 403 | N (no screen-required field is an AI-provenance path; PLAN:328 says "linked from the spec": UNKNOWN whether any spec field carries it) |
| 26 | WP0.10 feasibility, WP0.11 lineage, WP0.12 order contract | FREEZE (G at real freeze) | PLAN:330-332, 334; REG s5.1 line 403; REG s51 item 17 (D01 evidence names `hypothesis_lineage.yaml`) | ? (WP0.11 is D01 evidence, so likely needed with row 6; the others N) |
| 27 | Sign-off packet: SHA-256 of exact bytes of every signed document | FREEZE | REG s7.3 (lines 501-519); PLAN:334; REG s5.1 line 398 (C10 "G") | ? (no tool checks it; AMD:96 requires sign-offs "genuine, attributable and bound to the spec hash", which the packet is the only defined mechanism for) |
| 28 | C12 named isolated research environment and accountable person | FETCH-AUTH | REG:111 ("Named before PR 5 / WP2.6"); REG s5.1 line 396 col (c); PLAN:341; AMD:93 (R-f) | G |
| 29 | Adoption of A-SCREEN criteria s6, separation s6b, statistics s6c, baseline s7 | FREEZE (criteria and baseline values are spec fields); s6b adoption is needed at STEP-6; s6c at VALIDATION | AMD:26, 31, 92 (R-e), 124, 128, 170 (blocker 7); REG:107-109 | G |
| 30 | Vendor storage/use answers (store, AWS host use, sharing, adjustment, delisted) | FETCH-AUTH | AMD:83, :93, :166 (blocker 3); REG:89 (D03 evidence F5); REG s5.1 line 404 | G |
| 31 | Review and merge of the screen-profile change | MERGE | AMD:49, 160, 164 (blocker 1); CLAUDE.md walk-away discipline | G |
| 32 | Owner authorization to execute the first governed P3A run; run registered first with trial-ledger row | STEP-6 | RG:756-760; AMD:94 (R-g), :35 (O-3 conditional in principle); PLAN:327 (WP0.7) | G (the owner act); trial-ledger row T |
| 33 | Audit pack / `approval_log.md` | OTHER | PLAN:750 | N (post-run) |

### 2.1 Counts per gate (earliest gate; row-level)

| Gate | Rows | Count |
|---|---|---|
| MERGE | 23, 31 | 2 |
| FETCH-AUTH | 28, 30 | 2 |
| FREEZE | 1-21, 24-27, 29 | 26 (of which 11, 12 are full-profile only) |
| STEP-6 DESCRIPTIVE RUN | 22 (conditional, PROPOSED), 32 | 2 |
| VALIDATION | none at row level | 0 |
| PROMOTION | none at row level | 0 |
| OTHER | 33 | 1 |
| Total | | 33 |
| Unclassified | none | 0 |

Why VALIDATION and PROMOTION are 0: the 33-row table was built for freeze and first-run readiness, so each of its rows has an earlier gate. VALIDATION and PROMOTION appear only as **elements inside rows** (the validator confirmation of D06 / `select_exit` / max-statistic test in rows 20 and 29; validator review of D07 and the P5 marker in row 23; the sole P6 approver slot in row 11). Those elements are deferred and listed in section 5.

Row-level choices that are judgment calls (stated so they can be overruled): row 23 as MERGE rather than FREEZE (REG s51 item 4 requires the schema candidate "reviewed and merged before any freeze"; REG s5.1 line 394 puts D07 at the real freeze); row 24 as FREEZE although its D03/D11 elements are also needed at P1 (REG s5.1 line 395 shows both); row 21 as FREEZE (REG s5.1 line 397 shows G at real freeze; the register's PR 4 build gate is earlier but is not one of the seven gate names); row 22 as STEP-6 because the binding alternative is BLANK (it would be FREEZE under G10-C1).

---

## 3. G2: the 18 rows that depend on a role with no eligible holder

The 18 rows are the B3 set of the reconciliation (its section 4 last paragraph): 2, 7, 8, 9, 11, 12, 13, 15, 16, 18, 19, 20, 21, 22, 24, 25, 26, 28. They group into holderless sign-off groups H1-H8 below. Nothing is chosen. Under R5, **PENDING counts as VACANT**, so every candidate below leaves the sign-off VACANT until a signed acceptance record is committed to Git.

Standing clauses used in every group:
- Owner may not be validator: REG s6.1 line 430 (ruling 5), REG:94 "Four distinct humans; no AI role"; VIR V-5.1 SoD-A and SoD-C (lines ~70-76).
- No AI may hold a role or sign: REG s7 preamble (R9); PLAN D13 "not authored by an agent"; REG s2.2 item 3.
- Liaison cannot hold any independence-bearing role (R5). The reconciliation (B3-9) already notes the genesis witness seat.
- The software distinct-string check is "a typo and copy-paste guard only, never evidence of independence" (VIR V-1 line 26; V-5.2); on main it does not exist at all until #740 merges (grep "distinct" in `app/research/range002` finds no check).

### 3.1 Groups

| Group | Rows | Sign-off as the spec defines it | Independence requirement (clause) | May the OWNER hold it? | Eligible candidates under R5 (listed, not chosen) |
|---|---|---|---|---|---|
| **H1** `signoff.trading_expert` and the A1 s10 "Trading-expert reviewer (D19)" row; trading-expert review of D19, D05/D14 exit mechanics, D10 comparator (rows 2, 19, 20, 22, 24) | 2, 19, 20, 22, 24 | A non-blank string in `signoff.trading_expert` (SCH:476-481; FRZ:80-82); in A1 s10 the row "Candidate set reviewed (D19)" (A1:101-107); in A1 item 2 "the trading expert proposes, and the owner signs" the closed set of at most 8 exits (A1:24). | SoD-A "three distinct humans ... for owner / trading expert / validator" (VIR V-5.1); REG P-1 (owner provisional, unsigned) "removes SoD-B as a candidate"; SoD-B "Inexpressible" under the all-pairs distinct rule (VIR V-5.2; V-9 item 1 asks the owner to confirm); SHEETS:198 "flag if the owner is also the trading-expert reviewer: then D19 candidate review is not independent of the final approver"; REG:94 "Four distinct humans". | **No**, under REG P-1 / SoD-A and SHEETS:198 (policy, unsigned; not a code refusal on main). | **方炳雄 (Fang Bingxiong): PROPOSED holder of `signoff.trading_expert`, PENDING owner ruling and acceptance, therefore VACANT.** Independence concerns to be resolved by statements, none on file: (i) relationship to the owner or GlobalComplyAI, LLC: UNKNOWN (VIR V-2.6, V-2.7 statements do not exist); (ii) relationship to the liaison: UNKNOWN; (iii) A1:24 has the trading expert propose the exit set and A1:101-107 has the same role review it, and the #758 role record describes Fang as exit/take-profit design reviewer "how they were chosen" (RoleAppointments row 18): whether Fang authored any candidate is UNKNOWN (A1 says the exit change "originated in a fund-manager review of 2026-10-09", A1 line ~99, no person named); (iv) the #758 record says Fang is ADVISORY, NO gate sign-off: the proposed R5 holder role conflicts with that text until the owner rules. Not candidates: Chen Youtong (validator; the same person in two sign-off slots fails all-pairs distinct, VIR V-5.2), Xiao Xuejiao (advisory, no gate sign-off under R5), Liang Yunpeng (barred), Claude Code (R9). |
| **H2** Research lead (`governance.roles`; D08) and the research-lead half of D13 | 11, 12 | A named human in `governance.roles` (SCH:451; REG:94; SHEETS:195-206). D13: thesis "signed by research lead and a trading expert", human-written, sha in `governance.economic_thesis_sha` (SCH:450, 461-466; PLAN:329). | "Four distinct humans" (REG:94); research lead distinct from validator (SoD-C, VIR V-5.1; SHEETS:198: "must not be the research lead or the person who wrote the engine"); SHEETS:24 owner = sole P6 approver, so the research lead is another human. | **No** for the research-lead slot under REG:94 / SHEETS:24 (the owner is the P6 approver slot). Not barred as an additional signatory by any repo text (reconciliation row 12). | No person is assigned. AMD:23 (O-1): "Research Lead appointment pending; 陈友潼 ... not Research Lead". Under R5 no one is named. Not candidates: Chen Youtong (AMD:23), Liang Yunpeng (barred), Claude Code (R9). Fang Bingxiong could be listed for the D13 trading-expert half only if the owner so rules (PENDING). Xiao Xuejiao: advisory under R5, no gate sign-off. **Candidate for the research-lead slot: none identified in the repository.** Exempt under the screen profile (feature-branch `SCREEN_V1_EXEMPT`; AMD:157). |
| **H3** Contact auditor / ledger custodian (WP0.6, V-2.3 reconciliation) | 7, 16 | A signed WP0.6 audit "who, when, what was seen" including AI-session history (PLAN:326); ledger `signoff {signed_by, signed_on}` (RG:726); D01 owner signs the conclusion, "validator co-sign recommended" (REG:87, REG s51 item 17). HARD s3.3 (line 282, design only): classification "a signed owner act, with an independent-validator co-sign recommended". | The audit is of the owner's and agents' own contact; a self-audit is not independent (REG:87 names no auditor). VIR V-2.3: verified by "Owner; ledger custodian" (line 36). | Owner signs D01 and the ledger (REG:87; RG:408-420) **yes**; owner as the sole auditor of own contact: not independent (no clause forbids it; REG:87 names no auditor; UNKNOWN who is intended). | Chen Youtong as co-signer: PENDING, and he must not have prior exposure (V-2.3), so he cannot audit what he attests not to have seen; whether he can co-sign is UNKNOWN (REG recommends it). Non-author reviewer Jay Wang is also the owner. No other person under R5. Liang barred. Claude Code may prepare the ledger draft (R9: may not sign). |
| **H4** Genesis ceremony operator and witness; manifest-PR reviewer | 8, 9 | Two different humans: an operator and "a witness who is not the operator" (REG:113); no AI (REG s2.2 item 3); `approved_by` = the owner's name as in signed D08 (REG:556 per reconciliation; REG s2.2 item 6); manifest filled in one reviewed git change (REG s2.4 line 174, REG:114). | Witness not the operator (REG:113). REG s2.2 item 6 recommends D08 roles named first so the validator exists for the ceremony review. | **Partly.** Owner authorizes (REG s2.2 item 4) and may fill one of the two seats; not both (REG:113). | Operator/witness: Jay Wang (one seat at most); Chen Youtong (PENDING; wording of REG s2.2 item 6 suggests he reviews the ceremony, not operates it; UNKNOWN); Fang Bingxiong (PENDING; UNKNOWN whether a gate-holder may be a witness); Xiao Xuejiao (advisory; no clause bars a witness seat; UNKNOWN). Liang barred from the witness seat (R5). Manifest-PR reviewer: Jay Wang is the non-author reviewer under R5 and is also the approver (`approved_by`): dual role; a different reviewer is not named. |
| **H5** Verifier of validator independence and author list; V-8 named verifiers | 13, 15, 18 | VIR V-2.2 verified "by Owner, using a repo author list produced by someone other than the validator" (line 35); V-3: "Owner, or a party other than validator and engine author" (line 51); V-8 table "Named verifier" (lines 104-121). | VIR line 51: "The owner may be conflicted; if the owner authored or directed the engine, independence is relative to that"; "self-attested" mark when self-verified (line 56). | The owner is the named verifier in VIR:35. Whether the owner authored or directed the engine is UNKNOWN (the code author is Claude Code under R5; the directing role of the owner is not recorded). Owner may not be the validator. | Jay Wang (named in VIR:35; conflict flag VIR:51). Fang Bingxiong or Xiao Xuejiao as the "party other than validator and engine author": PENDING and have no gate sign-off for Xiao; whether an advisory role may verify is UNKNOWN. Liang barred. The reconciliation (B3-7) finds the row fillable only as "self-attested" under current assignments. |
| **H6** Research environment accountable person (C12); WP0.10-0.12 technical reviewers; WP0.8 "human who confirmed the final logic" | 25, 26, 28 | C12: "Name the approved isolated non-production research environment and the accountable person ... not `ec2-paper`" (REG:111). WP0.8: "the human who confirmed the final logic" (PLAN:328). WP0.10-0.12: signed, "reviewers per WP" (PLAN:330-332, 334). | R9 (a human, not an agent). WP0.8: UNKNOWN who is intended; VIR V-2.2 suggests the confirming human should be distinct from the validator. C12: no clause names an independence requirement for the accountable person. | C12 accountable person: **yes** by no clause barring (REG:111 says "Owner" decides). WP0.8, WP0.10-0.12: not barred by repo text; UNKNOWN. | C12: Jay Wang (owner; no other named). WP0.8 and WP0.10-0.12: Jay Wang; Fang Bingxiong (exit design only, PENDING); Xiao Xuejiao (risk parameters only, advisory). Chen Youtong should not hold WP0.8 (V-2.2 reasoning). Liang barred from independence-bearing roles; whether C12 accountable person is independence-bearing: UNKNOWN. |
| **H7** Criteria 2 and 3 reviewers of the non-equivalence statement | 21 | "Signed findings by the trading-expert reviewer and the independent validator with evidence cited, countersigned by the owner" (REG:98; PLAN:325). | Two named reviewers other than the owner; owner countersigns. | Owner countersigns **yes**; owner as one of the two reviewers: no (REG:98). | Trading-expert half: Fang Bingxiong (PROPOSED, PENDING). Validator half: Chen Youtong (PENDING). Not on the screen path (row 21). |
| **H8** Level 2 key administrator "who is none of the signers" | 18 | VIR V-2.5, line 38 ("Verified by: Validator, plus key administrator who is none of the signers"). Level 2 not built (VIR V-6; REG s6.2). | Not a signer. | n/a (not built; not a Level 1 precondition per VIR:45). | None assigned. Deferred. |

### 3.2 Per-row mapping of the 18

| Row | Group | Sign-off element with no eligible holder | Level of reliance on the missing holder |
|---|---|---|---|
| 2 | H1 | `signoff.trading_expert` | required by guard even on the screen path |
| 7 | H3 | contact auditor / ledger custodian | required (ledger signed) |
| 8 | H4 | manifest-PR reviewer and `approved_by` (owner) | required |
| 9 | H4 | ceremony operator and witness | required |
| 11 | H2 | research lead (`governance.roles`) | full profile only |
| 12 | H2 | research lead and trading expert for thesis | full profile only |
| 13 | H5 | eligibility verifier (not the owner if the owner directed the engine) | G, required for a genuine validator |
| 15 | H5 | author-list verifier | V |
| 16 | H3 | ledger custodian reconciling V-2.3 | V |
| 18 | H5, H8 | named verifiers; key administrator | V (table); Level 2 deferred |
| 19 | H1 | A1 trading-expert row | scope UNKNOWN |
| 20 | H1 | D19 candidate-set review | D19 value required; review G |
| 21 | H7 | criteria 2/3 trading-expert finding | not on screen path |
| 22 | H1 | comparator-set relevance review | PROPOSED only |
| 24 | H1 | D05/D14 exit mechanics input | G |
| 25 | H6 | human who confirmed final logic | not on screen path |
| 26 | H6 | WP0.10-0.12 technical reviewers | partly UNKNOWN |
| 28 | H6 | C12 accountable person | G, FETCH-AUTH |

---

## 4. Screen profile: what it exempts versus what the guard itself requires (G3 input)

Verified in `C:\LLM-APP\AI-TRADING-APP\apps\backend\app\research\range002\spec\schema.py` at branch HEAD `1ecf811b` (not on `origin/main`):

| Item | What the code does | Cite (feature branch) |
|---|---|---|
| Sign-off fields | `missing_signoff_fields()` is unconditional: it lists `signoff.owner`, `signoff.trading_expert`, `signoff.independent_validator` when blank and `signoff.date` when absent, for every profile. A screen profile exempts none of them. `freeze_spec` raises `SignoffMissingError` on any. | SCH `missing_signoff_fields` (lines ~730-740); FRZ:80-82 |
| Guard sign-off check | `spec.is_signed is not True` refuses an unsigned spec for every profile, before the profile check. | RG:370 (main), 387 (feature branch) |
| What the screen profile exempts (v1) | 18 fields: `governance.economic_thesis_sha`, `governance.roles`, `p5.*` (4), `diagnostics.taxonomy`, `gates.max_dd/win_rate/yearly`, risk caps other than `per_trade_pct` (`risk.daily_loss_limit`, `fill_risk_tolerance`, `gross_cap`, `max_concurrent`, `max_participation`, `per_name_cap`), `stats.regime.*` (2). | SCH:555-573 |
| What v1 requires | 48 fields incl. `governance.exposure_signed`, `governance.registry_genesis_id`, `p3.criteria`, `p3.max_p3a/b_attempts`, `exits.*`, `stats.*`, `registration.related_programs`, `universe.n`, `data.vendor`, `data.fetch_mode`, all `execution.*`, `costs.*`, `controls.*`. | SCH:505-554; AMD:40-41 |
| What v2 additionally defers or marks unmodelled | DEFERRED (not read by guard or kernel; required before statistical selection or advancement): `controls.*` (4), `exits.complexity_order`, `registration.related_programs`, `stats.*` (7). UNMODELLED (may stay null): 8 `execution.*` fields and `fill.slippage_model`. v2 required list: 25 fields. | SCH:579-640 |
| What the guard itself requires at P2/P3A regardless of profile | Spec frozen and signed (RG:370); known profile (RG:387-391); screen profile limited to (P2, REPLAY_RNG001) and (P3A, DEVELOPMENT_SELECTION) (RG:693-698); registry genesis = spec genesis = approved manifest genesis (RG:672-682); exposure ledger signed and bound by sha (RG:408-420, 726); attempt limits set and equal to manifest (RG:756-760); trial-ledger row first (R-g, AMD:94). | RG lines as cited |
| What no code checks | Whether the three sign-off strings belong to three humans (only #740 adds a distinct-string check, still "authenticates nobody", VIR V-5.2); whether the validator is independent; whether any person accepted a role. | VIR:26, 51; REG s6.1 line 430 |

Which profile version is in force is UNKNOWN: AMD:40 describes v1; the feature branch also contains v2; neither is adopted or merged.

---

## 5. G3: minimum sign-off set through STEP-6, and the deferred remainder

"Through step 6" means: MERGE (screen-profile change), FETCH-AUTH (bulk pull), FREEZE (a screen-profile spec), then the STEP-6 authorization. The sets below use the rows' numbers and the "Screen path" column of section 2. They state what the repository requires; they do not decide it.

### 5.1 Firm minimum (T or G; 18 rows)

| Row | Item | Basis |
|---|---|---|
| 1, 2, 3, 4 | the three `signoff` names and date | T, even in the screen profile (section 4) |
| 5 | `spec_sha256` | tool |
| 6, 7 | D01 `exposure_signed` and the signed ledger | T (RG:408-420, 726) |
| 8, 9 | manifest triple; genesis ceremony | T (FRZ:73-79); ENR prerequisite |
| 10 | attempt limits | T |
| 20 (subset) | D17 `p3.criteria`, D19 `exits.*` values, D18 `gates.basis/trade_unit` (v1: also D06/D02) | T |
| 24 (subset) | D03 `universe.n`/`data.vendor`, D11 `data.fetch_mode`, D15 `costs.*`, parts of D05 and D14 in the required list | T |
| 13 | validator eligibility and appointment act | G (AMD:89 R-b; REG s6.1 line 430) |
| 28, 30 | C12 environment; vendor storage/use answers | G, FETCH-AUTH |
| 29 | adoption of s6 criteria and s7 baseline (s6b before any result viewed) | G (AMD:124, 170) |
| 31 | review and merge of the screen-profile change (eligible non-author reviewer) | G, MERGE |
| 32 | run authorization and trial-ledger row | G/T, STEP-6 |

Rows with holderless elements inside this set: 2, 7, 8, 9, 13, 20 (D19 review), 24 (D05/D14 input), 28. Rows 3, 13 and 31 are also gated on PENDING acceptance (Chen Youtong; Jay Wang as non-author reviewer). Row 31's reviewer eligibility is UNKNOWN where the owner directed the change (AMD:49 "eligible non-author reviewer"; VIR:51 by analogy).

### 5.2 Conditional on the owner's V-8 selection (5 rows)

14, 15, 16, 17 (V-2.6), 18 (the V-8 table itself). VIR:45 recommends V-2.1, V-2.2, V-2.3 and V-2.6 "as minimum for any real freeze"; the V-8 table (VIR:104-121) is blank, so whether each is required, waived with reason, or by whom verified is UNKNOWN. Holderless elements: 15, 16, 18 (H3, H5).

### 5.3 Owner scope ruling needed; repository does not say (4 rows)

| Row | Question | Why UNKNOWN |
|---|---|---|
| 19 | Must A1 be signed before a screen-profile freeze? | REG s5.1 line 392 and PLAN:334 require it at a real freeze and P0 exit; AMD R-a..R-g (lines 88-94) do not list it; O-3 uses the P3a partition that A1 defines; REG P-3 forbids signing A1 "merely because the code assumes it" |
| 22 | Does G10-REDUNDANCY apply to a screen run? | PROPOSED, binding alternative BLANK (VNEXT A2.9) |
| 26 | Are WP0.10-0.12 (and WP0.11 lineage as D01 evidence) needed? | REG s51 item 17 lists `hypothesis_lineage.yaml` as D01 evidence; the rest are P0 exit items |
| 27 | Is a sign-off packet required for a screen freeze? | no tool checks it; AMD:96 "genuine, attributable and bound to the spec hash" |

### 5.4 Deferred remainder (6 rows at row level, plus elements)

| Row | Needed only for |
|---|---|
| 11 (`governance.roles`, SoD option; P6 approver slot) | full-profile FREEZE, VALIDATION (P4), PROMOTION (P6 approver) |
| 12 (D13 economic thesis) | full-profile FREEZE |
| 21 (non-equivalence record, C2 reviewers) | PR 4 build and P0 exit (full) |
| 23 (D07 / P5 marker and schema candidate) | full-profile FREEZE, PROMOTION (P5) |
| 25 (WP0.8 AI provenance) | P0 exit (full) |
| 33 (audit pack) | OTHER, post-run |

Deferred **elements** inside firm rows: validator confirmation of D06 numbers and of `select_exit` / max-statistic test (REG:92, 99; AMD:128) -> VALIDATION; D06 `stats.bootstrap.*`, D02 `stats.hypothesis_family`, `controls.*`, `exits.complexity_order` under profile v2 only -> required again before statistical selection; D04, D10, D12, D16 values -> full profile; VIR V-2.4, V-2.5, V-2.8, V-2.9, V-2.10 and Level 2 keys -> not built.

Ledger of the 33 rows: firm 18 (rows 1-10, 13, 20, 24, 28-32) + conditional 5 (14-18) + scope-unknown 4 (19, 22, 26, 27) + deferred 6 (11, 12, 21, 23, 25, 33) = 33.

### 5.5 What the minimum set cannot do under R5

- `signoff.trading_expert` (row 2) is required by the guard even in the screen profile. Under R5 its only proposed holder (方炳雄) is PENDING, so the slot is VACANT; and until #740 merges, no sign-off may be counted GENUINE.
- `signoff.independent_validator` (row 3) is required by the guard and by ruling 5. 陈友潼 is PENDING, so VACANT.
- `signoff.owner` (row 1) is the owner's own act; no role gap, but is not counted GENUINE until #740 merges.
- A typed name satisfies the code (three non-blank strings), but R5 and AMD:88 ("three distinct strings are a software check, never permission to fabricate sign-offs") mean typing a name in a VACANT slot does not make it GENUINE.

---

## 6. G5: RoleAppointments file and the #758 dependency on #740

### 6.1 Does the tracked file name 陈友潼's role?

**Yes.** `docs/governance/RANGE-002_RoleAppointments_2026-10-12.md` is tracked on the PR #758 branch (`git ls-files` in `C:\LLM-APP\wt-r002-b` lists it at commit `dd106de5`). Section 1, line 16: 陈友潼 (Chen Youtong) | Independent validator | GATE (`signoff.independent_validator` and the validator attestations) | independence "NOT ESTABLISHED. Eligibility is subject to verification; no verifier record exists in Git. The owner cannot waive it." | Acceptance **PENDING**. Section 3.1 (lines 29-36) holds his acceptance block, blank. Its rule (line 7): "A role marked PENDING is VACANT for every gate until a signed acceptance record exists in Git."

Two statements in that file are **superseded by the R5 rulings** and would need revision if the owner adopts R5: line 18 and line 24 call 方炳雄 "ADVISORY. No gate sign-off" and say `signoff.trading_expert` "has no eligible holder"; R5 proposes him as gate holder of `signoff.trading_expert` (PENDING). The same appears in the reconciliation, section 4 (B3-1, B3-4) and rows 2, 19, 20, 22, 24 "Assigned holder" cells. Under R5 those cells change from "NONE ASSIGNED" to "PROPOSED, PENDING", but the slot remains VACANT because PENDING counts as VACANT.

### 6.2 PR #758's dependence on #740

What the #758 files say: the reconciliation states the check "is PR #740 (head `8792e043`, OPEN, not merged)" and that distinctness "is not enforced on main" (its line 8). Its status rule (line 11) sets GENUINE 0 and STALE-HASH 0 "because no record binding to any hash exists". The RoleAppointments file and the reviewer briefs do not mention #740 (grep).

Under the R5 standing rule (no sign-off counted GENUINE before #740 merges), the dependence is:

| Item | Before #740 merges (now) | After #740 merges |
|---|---|---|
| GENUINE count | 0 by rule (and also 0 on the facts: no spec, ledger or acceptance record exists) | still 0 until a record binds to a hash; #740 only lifts the rule that forbids counting |
| Table scope note (line 8) "No pairwise-distinct check exists ... on main" | true | **false; must be rewritten**: freeze refuses identical (after normalization) and invisible-character role strings (VIR V-5.2, V-7.1) |
| Row 2 "Can OWNER hold it": "Not blocked by code on main" | true | the same string for owner and trading expert would be refused by the tool; the NO from REG P-1/SHEETS:198 stands as policy, and now also as a refusal for identical strings only |
| Rows 1-3 (three sign-off names) | MISSING / MISSING / PENDING-ACCEPTANCE | eligible to be counted GENUINE only after a real record binds to the spec hash; row 3 still needs the acceptance record |
| Row 4, 5 | MISSING | unchanged (no spec) |
| Counts "PENDING-ACCEPTANCE 4 (rows 3, 15, 16, 31)" | as stated | unchanged: acceptance is not a code property |
| "18 rows with no eligible holder" | 18 | unchanged: the holder gap is by role assignment (PENDING = VACANT), not by #740 |
| Distinctness "AMD R-a (line 88) ... non-empty and distinct" | not enforced | enforced at freeze for strings; still `authenticates nobody` (VIR V-5.2) |

**Stays PENDING / VACANT regardless of #740:** every row that rests on a person's acceptance (rows 3, 13 appointee, 15, 16, 17 validator element, 19-23 and 29 validator elements, 31 reviewer); the `signoff.trading_expert` holder (R5 proposal, PENDING); the research lead, ceremony operator/witness, ledger custodian, eligibility verifier and C12 accountable person (no holder named); every row that depends on a hash that does not yet exist (frozen spec, ledger, manifest, genesis id, A1 bytes SHA, sign-off packet). #740 changes only the software check and the rule that forbids counting; it does not create a holder, an acceptance record, or a hash.

Other dependency to note: REG s51 item 30 requires the schema candidate to be "rebased on #740" (merge order); and REG:117 says the follow-up merges "only on the owner's explicit instruction, with the walk-away interval".

---

## 7. UNKNOWN register

1. Whether bulk fetch precedes or follows the screen-spec freeze (section 1).
2. Which screen profile version (v1 or v2) is intended; neither is adopted or merged.
3. Whether A1, WP0.11, WP0.12 and the sign-off packet are required on the screen path (section 5.3).
4. Whether the owner authored or directed the engine, which controls the validity of the owner as verifier (VIR:51) and as non-author reviewer (AMD:49).
5. Eligibility, relationships and independence of Chen Youtong, Fang Bingxiong and Xiao Xuejiao relative to the owner, GlobalComplyAI, LLC, and each other (no VIR V-2.6/V-2.7 statements exist).
6. Whether Fang Bingxiong authored or proposed any exit candidate (A1:24, A1 line ~99 "fund-manager review").
7. Whether an advisory role may serve as ceremony witness or as the "party other than validator and engine author".
8. Who audits the owner's and AI sessions' contact (REG:87 names no auditor).
9. The G10 binding alternative (VNEXT A2.9 BLANK).
10. The PR #740 merge date; the base `origin/main` here is `9d90d96c` and was not re-fetched (no network).
