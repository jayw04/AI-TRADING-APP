# RANGE-002 owner ruling: sign-off assignments (DRAFT WITH BLANKS)

| Field | Value |
|---|---|
| Status | **DRAFT. NOT A RULING UNTIL THE OWNER FILLS IT AND MERGES IT.** The owner fills the blanks and merges; the agent does not fill, sign, approve or merge. |
| Prepared | 2026-10-12, Lane G, from `RANGE-002_Signoff_Scope_by_Gate_v0.1.md` (same directory) |
| Base | `origin/main` `9d90d96c` read; PR #740 not merged |
| Pre-filled | Only the assignments the owner has already ruled (R5). Everything else is blank. A blank means "not decided", never "none". |
| Evidence needed for any clause | A signed acceptance record committed to Git (path in `[acceptance record path]`). An assignment is not an acceptance. |

## 0. Standing rules (pre-filled from the owner's rulings; owner to confirm by merging)

0.1 **A role marked PENDING counts as VACANT for every gate** until a signed acceptance record for that role is committed to Git.

0.2 **No sign-off counts GENUINE before PR #740 (all-pairs distinct sign-off check) is merged on `main`.** After it merges, a sign-off counts GENUINE only if, in addition, a record binds the person's acceptance to the spec hash. #740 authenticates nobody (VIR V-5.2).

0.3 **No AI agent holds a role, signs, or fills a row** (R9). Claude Code is the code author (R5) and prepares drafts and evidence only.

0.4 **The owner may not hold or waive `signoff.independent_validator`** (REG s6.1 ruling 5; SoD-A, SoD-C).

0.5 **Liaison**: 梁云鹏 (Liang Yunpeng) holds no sign-off of any kind and no independence-bearing role (the owner's relative).

0.6 **Typing a name into a VACANT sign-off field does not make it GENUINE.**

## 1. Role assignments already ruled (R5), recorded for reference

| # | Role | Person | Gate authority | Acceptance state | [acceptance record path] | [date] |
|---|---|---|---|---|---|---|
| 1.1 | Code author | Claude Code (agent) | none; may not approve, self-review or merge | n/a (agent) | n/a | n/a |
| 1.2 | Non-author code reviewer | Jay Wang (owner); dual role disclosed | evidence for MERGE; not a validator sign-off | owner act | n/a | [date: ______] |
| 1.3 | Independent validator | 陈友潼 (Chen Youtong) | gate sign-off (`signoff.independent_validator` and validator attestations) | **PENDING (VACANT)** | [acceptance record path: ______] | [date: ______] |
| 1.4 | Trading expert | 方炳雄 (Fang Bingxiong) | **PROPOSED** holder of `signoff.trading_expert`; pending owner ruling (clause 2.1) and acceptance | **PENDING (VACANT)** | [acceptance record path: ______] | [date: ______] |
| 1.5 | Risk / loss-control reviewer | 肖学焦 (Xiao Xuejiao) | advisory; **no gate sign-off** | **PENDING (VACANT)** | [acceptance record path: ______] | [date: ______] |
| 1.6 | Liaison | 梁云鹏 (Liang Yunpeng) | none | n/a | n/a | n/a |

## 2. Holderless sign-off groups (one clause each; all blanks)

Each clause states the sign-off, the spec source and the owner's decision fields. The agent lists candidates in the scope document; no candidate is chosen here.

**2.1 `signoff.trading_expert`; A1 s10 trading-expert row; D19 candidate-set review; D05/D14 exit-mechanics input; D10 comparator relevance review** (rows 2, 19, 20, 22, 24; SCH:476-481, A1:101-107, REG:94, SHEETS:198).
Owner decision on whether 方炳雄 (Fang Bingxiong) holds the gate sign-off `signoff.trading_expert` (R5 proposes; this clause rules):
- [ ] confirmed as holder   [ ] not confirmed   [ ] other: ______
- [holder: ______]
- [acceptance record path: ______]
- [date: ______]
- Statements still required for independence (VIR V-2.6, V-2.7): [record path: ______]
- If 方炳雄's advisory role in the #758 `RoleAppointments` file is to become a gate role, the owner amends that file: [amendment path: ______]

**2.2 Research lead** (`governance.roles`; D08; D13 research-lead half) (rows 11, 12; REG:94; SHEETS:195-206; AMD:23). Not required for a screen-profile spec (exempt, AMD:157).
- [holder: ______]
- [acceptance record path: ______]
- [date: ______]

**2.3 D13 economic-thesis co-signature** (trading-expert half; research-lead half in 2.2) (row 12; PLAN:329; SCH:450, 461-466). Full profile only.
- [holder (trading-expert half): ______]
- [acceptance record path: ______]
- [date: ______]

**2.4 Exposure-ledger contact auditor and ledger custodian** (WP0.6; V-2.3 reconciliation) (rows 7, 16; PLAN:326; REG:87; RG:726).
- [holder (contact auditor): ______]
- [holder (ledger custodian): ______]
- [acceptance record path: ______]
- [date: ______]

**2.5 Genesis ceremony operator, witness and manifest-PR reviewer** (rows 8, 9; REG:113; REG s2.2 items 2-4). Operator and witness are two different humans; the witness is not the operator; no AI.
- [holder (operator): ______]
- [holder (witness): ______]
- [holder (manifest-PR reviewer): ______]
- [acceptance record path: ______]
- [date: ______]

**2.6 Verifier of validator independence and of the engine author list; named verifiers in the V-8 table** (rows 13, 15, 18; VIR:35, 51, 104-121). If the owner authored or directed the engine, independence is relative to that; a self-verified row is marked "self-attested" (VIR:56).
- [holder (eligibility verifier): ______]
- [holder (author-list verifier): ______]
- [self-attested rows, if any: ______]
- [acceptance record path: ______]
- [date: ______]

**2.7 C12 accountable person; WP0.8 "human who confirmed the final logic"; WP0.10-0.12 technical reviewers** (rows 25, 26, 28; REG:111; PLAN:328, 330-332).
- [holder (C12 accountable person): ______]
- [holder (WP0.8 confirming human): ______]
- [holder (WP0.10 / WP0.11 / WP0.12 reviewers): ______]
- [acceptance record path: ______]
- [date: ______]

**2.8 Criteria 2 and 3 reviewers of the non-equivalence statement** (row 21; REG:98; PLAN:325). Not on the screen path.
- [holder (trading-expert reviewer): ______]
- [holder (validator reviewer): ______]
- [acceptance record path: ______]
- [date: ______]

**2.9 Level 2 key administrator "who is none of the signers"** (row 18; VIR:38). Level 2 not built; deferred.
- [holder: ______]
- [acceptance record path: ______]
- [date: ______]

## 3. Independent validator acceptance and eligibility (row 3, 13)

3.1 Eligibility of 陈友潼 verified by a party other than the validator and the engine author (VIR V-3):
- [holder (verifier): ______]
- [acceptance record path: ______]
- [date: ______]

3.2 Appointment act by the owner (AMD R-b; REG:117):
- [appointment record path: ______]
- [date: ______]

## 4. Minimum sign-off set through the first descriptive run (STEP-6)

Scope document section 5. The owner states which items are required before the first governed P3A run on real data. Pre-filled column is the repository's mechanical or ruling-based requirement; the "owner ruling" column is blank.

| # | Item (rows) | Repository basis | Owner ruling: required / waived (with reason) | [holder: ______] | [acceptance record path: ______] | [date: ______] |
|---|---|---|---|---|---|---|
| 4.1 | `signoff.owner` (1) | T (FRZ:80-82) | ______ | ______ | ______ | ______ |
| 4.2 | `signoff.trading_expert` (2) | T (FRZ:80-82), see 2.1 | ______ | ______ | ______ | ______ |
| 4.3 | `signoff.independent_validator` (3) | T (FRZ:80-82) and ruling 5 | ______ | ______ | ______ | ______ |
| 4.4 | D01 `exposure_signed` and signed ledger (6, 7) | T (RG:408-420, 726) | ______ | ______ | ______ | ______ |
| 4.5 | Genesis ceremony and manifest triple (8, 9) | T (FRZ:73-79) | ______ | ______ | ______ | ______ |
| 4.6 | Attempt limits (10) | T (FRZ:79; RG:756-760) | ______ | ______ | ______ | ______ |
| 4.7 | Required spec values: D17, D18, D19, D03, D11, D15, parts of D05/D14 (20, 24) | T (screen required list) | ______ | ______ | ______ | ______ |
| 4.8 | Validator appointment (13) | G (AMD:89) | ______ | ______ | ______ | ______ |
| 4.9 | C12 environment and vendor answers (28, 30) | G (AMD:83; REG:111) | ______ | ______ | ______ | ______ |
| 4.10 | Adoption of s6 criteria, s6b separation, s7 baseline (29) | G (AMD:124, 170) | ______ | ______ | ______ | ______ |
| 4.11 | Merge of the screen-profile change (31) | G (AMD:49, 160) | ______ | ______ | ______ | ______ |
| 4.12 | Run authorization and trial-ledger row (32) | G/T (RG:756-760; AMD:94) | ______ | ______ | ______ | ______ |
| 4.13 | VIR V-2.1, V-2.2, V-2.3, V-2.6 and the V-8 selection table (14-18) | V (VIR:45) | ______ | ______ | ______ | ______ |
| 4.14 | A1 signature (19) | REG s5.1 line 392; not listed in AMD R-a..R-g | ______ | ______ | ______ | ______ |
| 4.15 | G10-REDUNDANCY policy (22) | PROPOSED, alternative BLANK | ______ | ______ | ______ | ______ |
| 4.16 | WP0.10-0.12 / hypothesis lineage (26) | PLAN:330-332; REG s51 item 17 | ______ | ______ | ______ | ______ |
| 4.17 | Sign-off packet (27) | REG s7.3; AMD:96 | ______ | ______ | ______ | ______ |

4.18 **Deferred to later gates** (owner confirms or amends; rows 11, 12, 21, 23, 25, 33 and the validator confirmation of D06/`select_exit`): [confirmed: ______] [amendments: ______]

4.19 Screen profile version in effect (v1 or v2): [version: ______] [adoption record path: ______] [date: ______]

## 5. Record of the owner's ruling

| Field | Entry |
|---|---|
| Owner (name) | |
| Date | |
| Statement that blanks left empty mean "not decided" | |
| Commit / merge reference (owner merges; the agent does not) | |
| Walk-away interval observed | |
