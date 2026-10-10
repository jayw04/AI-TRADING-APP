# RANGE-002 - P0 Decision Package vNext v0.1

| Field | Value |
|---|---|
| Purpose | One consolidated, prioritized P0 decision package: (A1) OD-1 completed under the split ownership; (A2) the G10-REDUNDANCY sheet completed; (A3) the unresolved P0 decisions consolidated in a prioritized matrix with signing dependencies |
| Date | 2026-10-10 |
| Starting point | `origin/main` at `1c305b8f` (PR #745 merged: P0 Decision Register v0.2 and the Validator Independence Requirements; PR #746 merged: Plan v0.5, Decision Sheets, P1/P2 Implementation Backlog and Schema Change Batch Proposal; PR #747 merged: data feasibility report and illustrative script; all unsigned drafts) |
| Staging | Documentation publication candidate. Its repository publication and any subsequent formal governance adoption are separate actions. The data feasibility report and script that section C-STAT cites by path are on `main` (PR #747), so that dependency is satisfied |
| Sources | `RANGE-002_OD_Followups_v0.1.md` (carried in this same stage; the OD-1 classification and the G10 sheet); the Backlog (`RANGE-002_P1_P2_Implementation_Backlog_v0.1.md`) and Schema Proposal (`RANGE-002_Schema_Change_Batch_Proposal_v0.1.md`), merged in #746; the schema candidate `76730911` (`feat/range002-schema-batch`, local) and the distinct-role safeguard PR #740 (`8792e043`, local), both read-only |
| Status | **DRAFT FOR OWNER REVIEW. Recommendation: NO-GO. Formally approved decisions: 0.** All signature, name, date and SHA-256 fields are BLANK. Nothing here is a decision |
| Data accessed | None. No market data, provider, broker, backtest, enrollment, freeze or signing. No code was changed |

## Status labels used throughout

| Label | Meaning |
|---|---|
| **[MERGED]** | Present on `origin/main` at `1c305b8f` |
| **[LOCAL, UNMERGED]** | Exists on a local, unpushed or unmerged branch; not on `main` |
| **[OWNER-DIRECTED, UNSIGNED]** | The owner's stated direction as relayed to the preparer; no signed record exists |
| **[PROPOSED]** | A proposal in this or a related draft; no owner direction or signature |

Nothing is "approved" unless a signed record exists against a pinned SHA-256. None exists.

## 0. What is merged and what is not

| Item | Status |
|---|---|
| Level 1 spec and governance code (PR #738, #739; code unchanged on `main` since `d61f313a`) | [MERGED] |
| Plan v0.5, Addendum A1 (draft, unsigned), Decision Sheets v0.1, hardening design, reconciliation, recon | [MERGED]. The merged Sheets already describe option B for `p5.account_binding` as PROPOSED / NOT APPROVED (owner direction, unsigned) and state that the merged schema still requires `p5.account_id` |
| P0 Decision Register v0.2 and Validator Independence Requirements v0.1 (#745) | [MERGED], unsigned drafts |
| Governance manifest (entirely unset: no genesis, no limits) | [MERGED] |
| Distinct-role safeguard (PR #740, `8792e043`) | [LOCAL, UNMERGED] |
| Schema candidate (`76730911`: 20 owner-valued new leaf paths plus `p5.account_binding`; per-candidate `rank` withdrawn) | [LOCAL, UNMERGED] |
| P1/P2 Implementation Backlog and Schema Change Batch Proposal (#746) | [MERGED], design only, unsigned |
| OD follow-ups file (carried in this stage) | [PROPOSED] document; published with this package |
| Data feasibility report and its illustrative script (#747) | [MERGED], analysis only, unsigned; cited by path |
| Plan wording amendments (C-DR, P5, G10 clarification, A1 s3) | [PROPOSED], not applied to any document |
| SoD-A + SoD-C; limits 1 / 1; no automatic defect-only retry; option B for P5; E1 step 1; A1 P3a/P3b architecture subject to reconciliation and review | [OWNER-DIRECTED, UNSIGNED] |
| Registry genesis | not enrolled; none exists |

---

## A1. OD-1 - LINEAGE CONSTANTS UNDER SPLIT OWNERSHIP (COMPLETE)

### A1.1 Rule [OWNER-DIRECTED, UNSIGNED]

D09 owns research-lineage identities, related-program relationships and non-equivalence. D03 owns universe, PIT definitions, vendor and acquisition. A constant used by more than one decision has **one controlling decision** and an explicit cross-reference from the other. This changes no merged Sheet: the merged D03 and D09 Sheets do not mention security identity, so recording the rule needs a sheet amendment that is [PROPOSED] below and unsigned. No silent governance change is made by this document.

### A1.2 Eleven constants plus two related items, individually classified

Part 1: `apps/backend/app/validation/security_lineage.py` (the OD-1 source; the only module-level constants are lines 55, 60, 64, 70, plus the enum at 73-87). Values are quoted from the code; none is chosen here.

| # | Constant | Value in code | Controlling decision | Reason | Cross-reference |
|---|---|---|---|---|---|
| 1 | `LINEAGE_GAP_SESSIONS` (60) | 20 | **D03** | Governs PIT-universe eligibility (Plan WP1.5) | D09 does not consume it |
| 2 | `LATE_START_SESSIONS` (64) | 20 | **D03** | Metadata-vs-price agreement for universe eligibility | same |
| 3 | `LINEAGE_BRIDGE_HOLE_MIN_SESSIONS` (70) | 20 | **D03** | Disconnected price segments in a window; the code comment records an INITIAL owner approval of 2026-07-29 that predates RANGE-002 and is not a RANGE-002 approval | same |
| 4 | `SECURITY_IDENTITY_CONTRACT` (55) | `PERMATICKER_EFFECTIVE_INTERVAL_V1` | **Split pending, owner-directed, unsigned - D03 identity representation, D09 identity equivalence** | Identity rule version of the PIT universe; a pinned dependency with 1-3 | same |
| 5-11 | `LineageRefusal` members (73-87): `NO_ACTIVE_LINEAGE`, `MULTIPLE_ACTIVE_LINEAGES`, `MISSING_PERMANENT_ID`, `LOOKBACK_CROSSES_LINEAGE`, `METADATA_PRICE_DISAGREE`, `UNRESOLVED_REMAP_GAP`, `AMBIGUOUS_EFFECTIVE_INTERVAL` | enum | **D03** | Universe exclusion reason codes; `MISSING_PERMANENT_ID` also relates to the F2 vendor-data feasibility check | refusals feed `data.exclusion_bound` (D03) and the WP1.8 coverage report (D03) |
| R1 (related item) | `SecurityIdentityUnavailable` (90) | exception | **D03** | Vendor/data property: the store lacks a permanent identifier; construction fails closed rather than using ticker identity | F2 |
| R2 (related item) | `lookback_start` argument (211, 325) | caller-supplied, not a constant | **D03** | For RANGE-002 it follows the universe window, `universe.adv_window_days` | not an OD-1 constant |

Part 2: the fixed values the skeleton already carries that belong to D03 (universe, PIT, vendor, acquisition), listed so that the D03 / D09 boundary is complete. They are fixed by the Plan and the design, not decided by OD-1:

| Spec value | Fixed value | Controlling decision |
|---|---|---|
| `universe.instrument_types` | `["common_stock"]` | D03 |
| `universe.min_price` | 10.0 | D03 |
| `universe.adv_window_days` | 20 | D03 |
| `universe.rebuild` | monthly | D03 |
| `universe.include_delisted` | true | D03 |
| `data.feed`, `data.bar`, `data.session`, `data.tz` | `sip`, `1min`, `rth`, `America/New_York` | D03 (vendor / acquisition) |

Part 3: constants and values that belong to **D09** (lineage identities, related programs, non-equivalence). None is fixed in code:

| Item | State | Controlling decision |
|---|---|---|
| Registry genesis id (research lineage identity) | does not exist; manifest unset | the genesis ceremony and manifest (register s2); D09 cross-references it |
| `registration.related_programs` (ORM-001 relationship) | open | D09 |
| Numeric signal-overlap maximum (C2) | open, owner-stated, no value proposed | D09 |
| Reviewers for criteria 2 and 3 | open, names blank | D09 |
| History used for criterion 1 | open | D09 (D09-hist) |

### A1.2a How the two related items differ from the constants

| | The 11 constants | The 2 related items |
|---|---|---|
| What they are | Module-level values or enum members in `security_lineage.py` whose value or meaning is fixed in the module: three integers (60, 64, 70), one identity-rule string (55), seven `LineageRefusal` members (73-87) | `SecurityIdentityUnavailable` (90) is an exception **class**; `lookback_start` is an **argument** the caller passes to `resolve_lineage` and `assess_universe` (211, 325) |
| What an adoption decision does with them | Adopts, changes or rejects a **value or vocabulary** | Nothing to adopt as a value: R1 is a fail-closed behavior (the store lacks a permanent identifier, so construction stops instead of using ticker identity); R2 is **derived** from the RANGE-002 universe window (`universe.adv_window_days`, fixed at 20), not set by the module |
| Why they are counted separately | They are the pinned dependency that the P1 data manifest would echo | They are not echoed as values; R1 is covered by the fail-closed rule, R2 by the D03 universe definition |

### A1.2b Item-by-item justification under the split rule [RECOMMENDED; the owner does not automatically endorse assigning all 11 to D03 and rules item by item]

The split rule: D09 = research-lineage identity, related-program relationships, non-equivalence; D03 = universe, PIT, vendor, acquisition. D09's quantitative non-equivalence input is criterion 1, the overlap of (symbol, session date, direction) signal sets between RANGE-002 and a related program (Decision Sheets D09). The only way a security-identity constant touches D09 is through the **symbol key** and **which symbol-days are present** in those sets. The ORM-001 universe and whether ORM-001 uses `security_lineage.py` are not stated in the documents read: the validator and the owner must confirm; nothing below assumes either.

| # | Constant | Recommended home and reason | What D09 needs from it |
|---|---|---|---|
| 1 | `LINEAGE_GAP_SESSIONS` = 20 | **D03.** It is a threshold that decides whether a symbol-day enters the PIT universe (a price-history hole of this length marks a structural discontinuity). It says nothing about research lineage or program relationships | Only the count of symbol-days it removes, as part of the refusal tally (below) |
| 2 | `LATE_START_SESSIONS` = 20 | **D03.** A threshold for metadata-versus-price agreement at the start of a window; universe eligibility only | same |
| 3 | `LINEAGE_BRIDGE_HOLE_MIN_SESSIONS` = 20 | **D03.** A threshold separating disconnected price segments; universe eligibility only. The code records an INITIAL approval of 2026-07-29 for a different program, so RANGE-002 needs its own record | same |
| 4 | `SECURITY_IDENTITY_CONTRACT` | **Split pending, owner-directed, unsigned - D03 identity representation, D09 identity equivalence; not assigned exclusively to D03 (the owner has not approved that).** Owner's recommended direction (unsigned): D03 controls the identity **representation** used in universe / PIT data construction; D09 controls the identity **equivalence** required for lineage, overlap and non-equivalence checks; the same underlying identity must be consistent across both (A1.2c). It defines the identity key (permaticker plus effective interval) of the universe, so D03 fixes it. But D09's overlap sets are keyed by "symbol": if they used ticker strings, a ticker reused by a different issuer would be counted as overlap or non-overlap wrongly. This is the **one shared item**: split pending, owner-directed, unsigned - D03 identity representation, D09 identity equivalence; one shared contract version string, with an explicit cross-reference in each decision | The overlap record must state that the symbol key is the permanent identity under this contract (not the ticker string), and must name the contract version |
| 5 | `LineageRefusal.NO_ACTIVE_LINEAGE` | **D03.** A universe exclusion reason | Counts only; both programs' sets must treat the refused symbol-day the same way (excluded symmetrically, or reported) |
| 6 | `LineageRefusal.MULTIPLE_ACTIVE_LINEAGES` | **D03.** Ambiguity in identity, resolved by exclusion | same |
| 7 | `LineageRefusal.MISSING_PERMANENT_ID` | **D03** (vendor / acquisition property; feasibility item F2). It signals that the permanent key is unavailable | If the key is unavailable, an overlap keyed by identity cannot be computed on that data: D09 must fail closed, not fall back to tickers |
| 8 | `LineageRefusal.LOOKBACK_CROSSES_LINEAGE` | **D03** (ticker reuse in the universe). Highest relevance to D09: it marks exactly the symbol-days where ticker-keyed overlap would be wrong | Refused symbol-days must not enter either signal set under a ticker key; their number is reported with the overlap |
| 9 | `LineageRefusal.METADATA_PRICE_DISAGREE` | **D03** (data quality; uses constants 1-3) | Counts only |
| 10 | `LineageRefusal.UNRESOLVED_REMAP_GAP` | **D03** (data quality) | Counts only |
| 11 | `LineageRefusal.AMBIGUOUS_EFFECTIVE_INTERVAL` | **D03** (identity interval not unique) | Counts only |

**What D09 needs, in total [PROPOSED]:** (i) the identity-key statement of row 4 in the non-equivalence record; (ii) a **refusal tally by reason** (counts of excluded symbol-days per `LineageRefusal` member, no returns) for the history used in criterion 1; (iii) a rule that refused symbol-days are treated symmetrically for both programs or reported; (iv) fail-closed handling if the permanent key is unavailable. No constant is duplicated in D09; the tally and the key statement are inputs, not decisions.

### A1.2c Canonical security identity, historical mapping, and how D09 consumes it [OWNER-DIRECTED, UNSIGNED as to the D03 / D09 split; the SecurityId definition, the refusals and the crosswalk resolution are taken from the code and are not new rules (`security_lineage.py:13-14`, `build_universe_crosswalk.py:22-24`, `:99`); the D09 equivalence rule below is [PROPOSED]]

**Why a ticker alone cannot be the identity.** A ticker is reused across unrelated issuers and retro-mapped on rename, so a ticker string can denote two companies over time. The module's worked example: `ECHO` is EchoStar today, while Echo Global Logistics is `ECHO2` and Electronic Clearing House is `ECHO1` in the vendor master (`security_lineage.py` docstring; `scripts/forward_validation/build_universe_crosswalk.py` docstring).

**Canonical definition (from `security_lineage.py`; contract `PERMATICKER_EFFECTIVE_INTERVAL_V1`, line 55).** A security identity is the pair (vendor permanent identifier, effective-date interval), written `SecurityId = (permaticker, [effective_start, effective_end])`. The ticker is an **attribute valid for an interval**, never a key. A rename within one permaticker is legitimate and stays one security; a ticker handed to a different permaticker is a different security.

**Historical mapping requirements** (each is stated in the module, the crosswalk script or the backlog; none is a new rule):

1. Every bar series and signal record is stored and keyed by `permaticker`, with the vendor ticker valid on that interval recorded as an attribute (Plan WP1.5; `trades.csv` carries `permaticker`, Plan s7).
2. The ticker-to-permaticker mapping is resolved **per effective date** from the vendor master (TICKERS) and the corporate-action events (ACTIONS `tickerchangeto` / `tickerchangefrom`), not by ticker equality (`security_lineage.py` docstring; crosswalk "Resolution order": unique candidate, else resolve by effective interval, else `AMBIGUOUS_MULTIPLE_LINEAGES` and stop, else `UNRESOLVED_NO_PERMANENT_ID`).
3. Bars are requested from the vendor by the ticker valid on the interval; the reverse join (permaticker plus interval to vendor ticker) is **not in the repository** and is a proposed new `data/identity_map.py` (Backlog L9, merged in #746; `identity_map.py` itself is a proposal).
4. A series is never merged across two permatickers (backlog L9 test list); delisted names stay in the universe before their delisting.
5. Ambiguity is a refusal, never a guess: the seven `LineageRefusal` members; there is no "degraded" state.
6. Alias collapse (several old keys to one lineage) is identity normalization, recorded as a group (crosswalk `MAPPED_ALIAS_COLLAPSE`).

**Split [OWNER-DIRECTED, UNSIGNED].**

| | D03: identity **representation** | D09: identity **equivalence** |
|---|---|---|
| Controls | The key and interval stored in the universe and bar data; the interval mapping; the refusal reasons; the data-manifest echo of the constants | The rule by which two records count as the same security for the lineage, overlap and non-equivalence checks |
| Content | `SecurityId` as defined above; the contract version; the three session constants; the refusal vocabulary | **[PROPOSED]** Equivalence relation: two records are the same security **iff** they have the same contract version and the same `permaticker` (ticker equality is neither necessary nor sufficient); a ticker match across different permatickers is NOT equivalence; two different tickers on one permaticker ARE equivalent |
| Consistency requirement | Both contracts cite one definition: the same `SECURITY_IDENTITY_CONTRACT` version string. A change to the contract is a new record in **both** D03 and D09 | same |

**How D09 consumes it (exactly) [PROPOSED].** D09's criterion 1 compares signal sets of items `(permaticker, session_date, direction)` (not `(ticker, ...)`). For a given history D09 needs: (i) the contract version string pinned in the non-equivalence record; (ii) the identity map for the history's date range, taken from the same governed store as D03, so both programs map the same ticker-on-date to the same permaticker; (iii) the refusal tally by reason (counts, no returns) and the rule that a refused symbol-day is excluded from both programs' sets or reported, never kept under a ticker key; (iv) fail-closed handling when a permanent key is unavailable (`MISSING_PERMANENT_ID`): the overlap is not computed on that data. If the history is the exposed RNG-001 IEX 5-minute archive (D09-hist option (a)), the archive is ticker-keyed, so its symbols and dates must first be mapped through (ii); the archive's mapping coverage is then an explicit input and any unmapped symbol-day is tallied, not dropped silently. D09 defines no constant of its own for identity.

### A1.2d ORM-001 and `security_lineage.py`: determination from the repository

- **ORM-001 is a candidate program name only.** It appears in four documents: `docs/design/RNG-001_Executive_Summary.md:21` ("a separate new program (ORM-001)"), `RNG-001_Rejection_Summary_Report_2026-10-09.md:183` ("candidate ORM-001, Opening-Range Reclaim / Momentum Confirmation ... pre-registered before testing"), `docs/implementation/evidence/range_entry_logic/RNG_EntryLogic_Study_v0.2.md:206` ("candidate program ORM-001") and `docs/implementation/evidence/cap_025/CAP025_IntradayReplayFunnel_Charter_v0.1.md:62` ("first reuse on a non-range intraday strategy (ORM-001 or other)"). It is also named in the RANGE-002 Plan, A1 and Sheets as the program D09 relates to.
- **There is no ORM-001 code, spec, registration, universe definition, data source or registry entry in the repository** (a search of `apps/` for "ORM-001" and "ORM001" finds nothing).
- **Result: there is no ORM-001 code in the repository, hence no dependency on `security_lineage.py` was found**, because ORM-001 does not yet exist beyond its name. **Whether a future ORM-001 will use the same identity contract is undeterminable now.** What would settle it: ORM-001's registration or spec stating its universe, its data source and its symbol key convention; or the owner's statement under D09 (ii) (merged, shared-ledger or independent) that fixes the identity contract for both programs.
- **Who does use the module today:** the validated daily-layer programs (for example `app/universe/strategy_ownership.py:83`, `app/validation/governed_corpus.py:52`, `app/validation/data_finality.py:81`, `app/validation/session_composition.py:79`, and several `scripts/forward_validation/` scripts). They are daily-layer programs and are relevant to the D01 contact audit, not to ORM-001.
- The earlier open question (c) in A1.3 is therefore closed as "no current dependency; future dependency not determinable".

### A1.3 Result

- **Count:** 11 constants plus 2 related items (A1.2a). The earlier figure of thirteen "constants" is corrected: R1 and R2 are not constants.
- **Classification:** D03 is the recommended controlling decision for 10 of the 11 constants (rows 1-3 and 5-11). Row 4, `SECURITY_IDENTITY_CONTRACT`, is **not** assigned exclusively to D03: the owner's recommended direction (unsigned) splits it into D03 representation and D09 equivalence, with one shared definition (A1.2c). D09 controls none of the other 10 as a value. This is a recommendation; the owner rules item by item (A1.2b). The word "lineage" in these constants means a security's permanent identity, not the research lineage (registry genesis; register s2).
- **Shared constants:** one (row 4). Rule applied: one definition (the contract version) referenced by both D03 (representation) and D09 (equivalence), so the two contracts cannot diverge; everything else is a count passed to D09 as an input.
- **Unresolved (kept visible):** (a) the adoption statement (as-is, stricter, looser) is unsigned; the backlog's [PROPOSED] treatment is as-is with the three values and the identity contract echoed in the P1 data manifest; (b) the owner's earlier preference for recording the adoption on D09; (c) ORM-001: no current dependency; a future dependency is not determinable (A1.2d); (d) no value is proposed beyond the code.

### A1.4 Proposed sheet amendments (text only; [PROPOSED], not applied)

- D03 sub-item: "Security-identity (lineage) refusal constants `LINEAGE_GAP_SESSIONS`, `LATE_START_SESSIONS`, `LINEAGE_BRIDGE_HOLE_MIN_SESSIONS` and `SECURITY_IDENTITY_CONTRACT` are adopted, changed or rejected for RANGE-002 (owner states which); the adopted values are echoed in the P1 data manifest; a later change to `security_lineage.py` requires a new record."
- D09 cross-reference: "D09 consumes the symbol-day universe defined under D03 and does not define or duplicate any security-identity constant; the overlap record states the identity key (the permanent identity under `SECURITY_IDENTITY_CONTRACT`), carries the refusal tally by reason, and fails closed if the permanent key is unavailable; 'lineage' in the D03 sub-item means security identity, not the research lineage."

### A1.5 Record (BLANK)

| Field | Value |
|---|---|
| Decision | Adopt, change or reject the lineage refusal constants for RANGE-002; record the controlling decision |
| Controlling decision | D03 (per A1.2); any D09 recording: BLANK |
| Adoption | BLANK |
| Approver | Owner |
| Pinned documents | `security_lineage.py` at a named commit; D03 and D09 Sheets as amended; SHA-256 BLANK |
| Signature / date | BLANK |

---

## A2. G10-REDUNDANCY - COMPLETE DECISION SHEET (PROVISIONAL ID)

### A2.1 Directions [OWNER-DIRECTED, UNSIGNED]

Threshold stays **<= 0.85** (merged: `schema.py:432` equality validator, Plan line 665). A failed or undefined G10 **blocks advancement and promotion** while the **P4 statistical results are preserved** unchanged. The comparator policy is pre-registered and its SHA-256 bound to the frozen research identity **before the first P3a authorization**, and its evidence is **revalidated before P4**. Comparator membership is a version-pinned list **or** a deterministic preregistered rule. Missing evidence fails closed. No verdict enum value is added and no meaning changed without a separate contract review.

### A2.2 Decision authority and signatures

Owner decides. Trading-expert reviewer reviews relevance and completeness of the comparator set. Independent validator reviews the correlation method and the evidence integrity. Signatures BLANK. Status UNSIGNED.

### A2.3 Exact comparator membership and eligibility

Nothing in the repository lists the approved strategies. The sheet therefore fixes the **structure** the owner must fill and invents no member.

| # | Element | Structure required | Content |
|---|---|---|---|
| 1 | Source state | The named, immutable state from which "approved strategies" is read (for example a dated record of the platform's strategy register) | **OWNER MUST DEFINE** |
| 2 | Eligibility criteria | Written, mechanical criteria for a strategy to be a comparator (status "approved" in the source state; a defined version; a daily net-return series available over a defined window; series produced under accounting comparable to RANGE-002) | **OWNER MUST DEFINE**; no criterion value is proposed |
| 3 | Membership form | (a) **version-pinned list**, or (b) **deterministic preregistered rule** that maps the source state to the list with no discretion (for example: all strategies meeting item 2 in the source state, ordered by strategy id) | **OWNER MUST DEFINE** a or b; the example in (b) is illustrative, not proposed content |
| 4 | Version pinning | Each member carries its identity and exact version (spec hash or git commit) | per member, **OWNER MUST DEFINE** |
| 5 | Series evidence | Each member carries the SHA-256 of its daily net-return series and the series definition reference | per member, **OWNER MUST DEFINE** |
| 6 | Immutability | No member may be selected, added or dropped after RANGE-002 results are observed; strategies approved later are excluded from this evaluation (or evaluated additionally at P6, never replacing a pinned member) | the immutability rule is [OWNER-DIRECTED, UNSIGNED]; the later-approval treatment is **OWNER MUST DEFINE** |

### A2.4 Correlation calculation and missing-data handling

No source defines any of these. Each is **OWNER MUST DEFINE**; no value is proposed:

metric (for example the family of correlation measures); the series (daily net return, per backlog O-13); sampling frequency; date alignment; treatment of days with no trade in either series (zero-fill or exclude); minimum overlap in days; signed versus absolute correlation compared with 0.85; evaluation window (the P4 window or a longer one); the treatment of a comparator whose series is shorter than the window. Principle [PROPOSED]: any missing or invalid input makes G10 `UNDEFINED`, never PASS (the Plan already uses this rule for PF and for yearly consistency, s5.1A). The validator reviews the method with a synthetic check on simulated series of known correlation (synthetic only).

### A2.5 The canonical comparator manifest and its SHA-256 [PROPOSED]

One strict-JSON document, hashed with the repository's canonical-JSON hashing (`spec/hashing.py` `content_sha256`, the same function that hashes the governance manifest and the spec). Proposed shape (field names are proposals; every value is OWNER MUST DEFINE):

| Field | Content |
|---|---|
| `schema_version` | 1 |
| `policy_id` | `G10-REDUNDANCY` |
| `threshold` | 0.85 (copied from the locked schema value; the document may only confirm it) |
| `source_state` | reference and SHA-256 of the source state |
| `membership` | `{form: "list" \| "rule", rule_text or members[]}` |
| `members[]` | `{strategy_id, version_ref, series_sha256, series_definition_ref, window}` |
| `method` | metric, frequency, alignment, missing-data handling, minimum overlap, sign convention, window |
| `failure_behavior` | G10 = `UNDEFINED`; blocks advancement and promotion; P4 statistical results unchanged |
| `revalidation` | the required checks before P4 (all series present, hashes recomputed and equal, overlap met) |
| `approved_by`, `approved_on` | BLANK until signed |

The comparator-policy SHA-256 is the canonical hash of this document (excluding the two approval fields, mirroring the spec's treatment of `signoff`).

### A2.6 Required binding: G10-C1, G10-C2, G10-C3, with a recommendation

**Naming and mapping.** The three comparator-binding alternatives are named **G10-C1**, **G10-C2** and **G10-C3**, to avoid collision with the P5 account-binding "option B". Mapping to the other documents' schemes:

| Name here | What it is | This package, earlier draft | OD follow-ups file (`RANGE-002_OD_Followups_v0.1.md`, section B.6) |
|---|---|---|---|
| **G10-C1** | Hashed spec field `governance.comparator_policy_sha256` | "Option B" | "Option 1" |
| **G10-C2** | Key in the governance manifest | unnamed "third, weaker option" | "Option 2" |
| **G10-C3** | Sign-off-packet pin | "Option A" | "Option 3" |

(The P5 account-binding "option A / B / C" of the register s22 is a different scheme and is unchanged.)

| | **G10-C1: hashed spec field** | **G10-C2: manifest key** | **G10-C3: sign-off-packet pin** |
|---|---|---|---|
| Binds to | The frozen spec, so into `spec_sha256` and every capability | The governance manifest (read from the executing checkout) | The sign-off packet (a procedural record) |
| "Before the first P3a authorization" | Mechanical: every `authorize()` requires a frozen, signed spec (`results_guard.py:361` `_spec_checks`; hash scope `schema.py:524`) | By process: the manifest is changed by reviewed git change; its SHA-256 is recorded on `capability_issued` rows but not compared across rows (`results_guard.py:652`, `:770-776`) | By process only; nothing in the registry or guard records it (`results_guard.py:601-620`) |
| Precedent | `governance.economic_thesis_sha` (`schema.py:450`, hash-only) and `governance.exposure_signed` (`schema.py:454`, guard-checked at `results_guard.py:408`, `:727`) | genesis and limits are manifest values (`manifest.py:52-62`) | none |
| Code change | schema (new mandatory P0 field), skeleton, tests; guard change only for a mechanical check (K5) | manifest schema (`manifest.py:52`), loader, tests | none |
| P0 field count | +1 (86 with the schema candidate, to 87); sequence with candidate `76730911` and PR #740 | unchanged | unchanged |
| Weakness | Adds a mandatory field and a schema review | Weaker (accepted limitation NF3); mixes a research-policy hash into the owner-values manifest | Cannot detect a swapped policy; relies on the reviewer |

**Owner preference for evaluation (unsigned; no formal selection):** G10-C1 is preferred for evaluation; G10-C2 is to be evaluated for equal immutability and auditability; G10-C3 is a fallback only if its linkage cannot be bypassed. All three stay proposed alternatives. Preparer's observation: C1 is the only one that is mechanical without touching the guard and has schema precedent; C2 reaches C1's strength only if the spec also carries the same value and the freeze tool checks equality (the existing limits pattern, `freeze_spec.py:79`) or if a cross-row check compares manifest hashes; C3 has no linkage that code can check.

**Compatibility of each alternative with the current code (file:line):**

| Check | G10-C1 hashed spec field | G10-C2 manifest key | G10-C3 sign-off-packet pin |
|---|---|---|---|
| Spec freeze (`freeze_spec.py:60-79`) | Compatible: the new field is a P0 field, so `FrozenSpec.from_draft` names it if unset (`:77`); no tool change | Manifest parsed at `:73-75` (`manifest.py:162`, exact keys `:52`); the freeze cannot link the spec to the manifest policy hash unless the spec also carries it and a check like `check_limits` (`:79`) is added | Not seen by the freeze |
| Registry binding (`run_registry.py:449-462` `open_run`, `:643-649` `mark_capability_issued`) | `spec_sha256` is on the open row and the capability row, so every run records the policy transitively | `manifest_sha256` is recorded on each `capability_issued` row (`results_guard.py:770-776`) but not compared across rows (NF3); the manifest can change between P3a and P4 by reviewed git change | No registry field; `open_run` has no policy argument |
| P4 authorization sequence (`results_guard.py:601-776`) | No change; the policy is in the frozen spec that `authorize()` already requires (`:361`) | Manifest already loaded at `:652`; no policy check | None |
| Results-guard semantics | Policy bound before any capability exists (a frozen, signed spec is required on every call) | Bound only as long as the checked-out manifest is the approved one (accepted limitation NF3) | Process only; can be bypassed because nothing refuses |
| Needs code for a mechanical pre-P4 revalidation | Yes (K5) | Yes (K5) | Yes (K5) |

No selection is made. The compatibility result is that all three are compatible with the existing freeze, registry and guard sequences *as proposals* (none breaks an existing check); they differ in how much of the pre-P3a linkage code can verify.

### A2.7 Freeze, revalidation and failure behavior

1. **Frozen before the first P3a authorization.** Signed as item 12A (A3.4). Under G10-C1 the policy hash is part of the frozen spec and therefore exists before any `authorize()` can succeed. Under G10-C3 the pin is recorded in the sign-off packet before the first P3a authorization.
2. **Revalidated before P4 (availability and integrity only).** A comparator revalidation record is completed before any P4 authorization: manifest SHA-256 equals the pinned value; every series is present; every series hash is recomputed and equal; method inputs are valid. This checks **evidence availability and integrity only**; the correlation itself is **not** computed before P4 (it needs RANGE-002 results, which exist only inside a guarded run). Fields BLANK: date, checker, result, manifest SHA-256, each series hash.
3. **Failed or undefined G10.** Recorded as the G10 entry of the gate report (closed per-gate result with pass / fail / UNDEFINED); it blocks advancement and promotion (P5 activation, P6 decision pack); the P4 statistical gate results and the audit pack's statistical content are unchanged.
4. **Fail closed, in two places.** (a) Pre-P4: this is a **procedural step before the P4 authorization request, not a G10 result**. **Owner-directed form [PROPOSED prerequisite]:** if the revalidation of item 2 fails, the P4 authorization request is **REFUSED** (not made). This is a **proposed binding prerequisite that requires formal adoption: a signed record and a Plan amendment**; until then it is not in force. **K5 automated guard enforcement is NOT authorized**: the current `authorize()` has no such check, so until K5 code is separately authorized the refusal is procedural only (a human step, not a guard refusal). It exists to avoid consuming the holdout window with an unevaluable G10 (K7). (b) At gate time, inside the P4 run's post-unseal gate evaluation: missing or invalid evidence makes G10 `UNDEFINED`. These are different events (see A2.7b).

### A2.7a Semantics: threshold, missing data, pinning, advancement blocking

- **Threshold.** G10 passes when the predeclared correlation is **<= 0.85** (equality passes). The value 0.85 is the locked schema value (`schema.py:432`) and is not changed by this sheet.
- **Missing data, three distinct cases.** (i) **Missing comparator evidence** (a pinned member absent, a series hash that does not match, a manifest hash that does not match): discovered **before P4**, the P4 authorization is not requested (procedural precondition, A2.7 item 4a); discovered **at gate time**, G10 is `UNDEFINED`, never PASS. (ii) **Missing days inside a series** (a day with no trade in either series): the treatment (zero-fill or exclude) changes the correlation and is **OWNER MUST DEFINE**; no value is proposed. (iii) **Insufficient overlap** (fewer than the predeclared minimum days): `UNDEFINED`. An `UNDEFINED` result is never read as "<= 0.85".
- **Comparator pinning.** Version-pinned list: each member carries identity, exact version (spec hash or git commit) and the SHA-256 of its daily net-return series. Deterministic rule: the rule text, the source state it reads (hashed) and the hash of the list it generates. The pin is the canonical hash of the comparator manifest (A2.5). Under G10-C1 a changed policy is a new spec hash; because attempt budgets are counted per lineage and phase across spec hashes, a re-freeze does not reset them.
- **Advancement blocking vs preserved results.** Blocked: advancement past P4 (P5 activation) and promotion (the P6 decision pack). Preserved unchanged: every P4 statistical gate result, the audit pack's statistical content, and the P4 verdict (`PASS_HISTORICAL_PENDING_PROSPECTIVE` or `REJECT`). A failed or `UNDEFINED` G10 is recorded as the G10 entry of the gate report; it is not a `REJECT` and adds no verdict value.
- **Open:** whether G10 may be re-evaluated offline once missing evidence is supplied (no rerun of the holdout) is **OWNER MUST DEFINE** (K7).

### A2.7b Where G10 sits in the sequence (precise)

Basis: Plan WP4.0 (stage 1 controls, then stage 2 unseal and gate evaluation), Plan s5.1 ("evaluated by `gates.py` from the audit pack"), Plan s7 (`test_summary.json`: every gate with value, threshold, pass / fail; `diagnostics/` includes redundancy), and `authorize()` (`results_guard.py:601-776`, which contains no gate evaluation) and `close_run` (`run_registry.py:545-565`, which records `audit_pack_sha256`).

| When | Event | G10 involvement | Enforced by |
|---|---|---|---|
| **Pre-P3a** | Comparator policy authored, hashed and bound to the frozen research identity | **Policy pin only**; no evidence is evaluated | G10-C1 mechanically (frozen spec required at `results_guard.py:361`); G10-C2 / C3 by process |
| **Pre-P4** | Revalidation of comparator evidence (availability and integrity) | **Evidence revalidation only**; no correlation is computed (it would need RANGE-002 results) | Procedural today (K5 guard code NOT authorized); owner-directed form: a failure means the P4 request is REFUSED (PROPOSED prerequisite, formal adoption needed) |
| **P4 `authorize()`** | Guard checks (spec, genesis, partition, exposure, phase order, attempt, holdout, `capability_issued`) | **None**: the current sequence has no G10 check | not applicable |
| **P4 run, stage 2** | Seal opened; `gates.py` evaluates G0-G10 into `test_summary.json`, then the pack is hashed and `close_run` records `audit_pack_sha256` | **G10 is evaluated here** (post-authorization, post-run): value, or `UNDEFINED` | `gates.py` (not yet written) |
| **Post-P4** | Advancement / activation decisions (P5 activation, P6 decision pack) | **Advancement block**: a failed or `UNDEFINED` G10 blocks advancement and promotion | new P5 / P6 code (K2); today P5 is refused outright (`results_guard.py:672-675`) |

**Does the "evidence missing means no P4 request" rule turn a post-P4 gate into a pre-P4 requirement?** Only partly, and deliberately: the *evaluation* of G10 stays post-P4. What is added before P4 is a precondition on *evidence availability and integrity*, directed by the owner to avoid K7 (a holdout window consumed by a run whose G10 cannot be evaluated). It is a procedural step outside the guard, not an extension of the guard's current sequence, and it never involves a correlation value. It is a **PROPOSED prerequisite**; it becomes binding only after formal adoption (signed record plus Plan amendment). Without adoption the alternative is that P4 may run and G10 may come back `UNDEFINED`, with the holdout window already consumed.

**Confirmations.** (1) The pre-P4 comparator revalidation is a **procedural step before the P4 authorization request**; it is not a G10 result and produces no correlation. (2) **G10 is evaluated after the P4 run, from the audit pack** (`test_summary.json`), at the stage-2 gate evaluation. (3) **The owner-directed form is that a failed revalidation REFUSES the P4 request**; this is a PROPOSED prerequisite requiring formal adoption (signed record plus Plan amendment), and K5 automated guard enforcement is NOT authorized, so it is procedural until separately authorized.

**G10 failure never rewrites P4 statistical evidence.** `test_summary.json` holds each gate as its own row; G10 is one more row. The G0-G9 rows, the trade list, the controls and the pack hash are produced by the run and are not changed by G10. The pack is hashed at close (`run_registry.py:545-565`), so G10 cannot alter it afterwards; a later G10 re-evaluation (if the owner permits one, K7) must be a **separate hashed addendum**, never an edit of the pack. The P4 verdict stays `PASS_HISTORICAL_PENDING_PROSPECTIVE` or `REJECT` as the statistical gates decide (`verdict.py:57-60`); no verdict value is added or reinterpreted (K1 still needs the Plan clarification).

### A2.8 Incompatibilities with the spec / registry / verdict contract (K1-K7, re-verified at `1c305b8f`; the `apps/` tree is unchanged since `d61f313a`)

| ID | Incompatibility | Location | Resolution path |
|---|---|---|---|
| **K1** | Plan says "All gates must pass" and lists G10 in the same table as a "Promotion constraint" | `RANGE-002_Implementation_Plan_v0.5.md:649`, `:665` | Plan clarification sentence: G10 is evaluated and reported separately and does not change the P4 statistical outcome. Not an enum change. Owner decision needed |
| **K2** | No enforcement point for "blocks advancement". The registry records `RunStatus`, never a `Verdict`; `verdict.py` is imported by neither the registry nor the guard; the only advancement controls are the predecessor table and the outright P5 refusal | `run_registry.py:129-134`, `:545-565`; `verdict.py:21-38`, `:53-72`; `results_guard.py:425-429`, `:672-675` | No present exposure (P5 is refused). The check belongs to the later P5 / P6 code. Owner decision: confirm that enforcement is deferred to that work |
| **K3** | No place to bind a comparator-policy hash: `Gates` holds only the fixed threshold (also in candidate `76730911`); the manifest has an exact key set | `schema.py:421-432` (main), candidate `schema.py:598-609`; `manifest.py:52-60` | G10-C1 (schema change), G10-C2 (manifest) or G10-C3 (process). Owner decision |
| **K4** | The pre-P3a requirement is mechanical only for a hashed spec field | `results_guard.py:361`, `:601-620`; `schema.py:524` | Supports G10-C1 |
| **K5** | No hook for revalidation before P4: `authorize()` has no comparator-evidence argument; `PredecessorEvidence` carries only an audit pack and a selection record | `results_guard.py:601-620`, `:211-224`, `:439` | Procedural record until a code change (a P4 evidence check) is separately authorized |
| **K6** | A new hashed field raises the required P0 count (86 to 87) and touches the view / adapter, where candidate and #740 also work | `schema.py`; `spec_view.py:47-79`; `spec_adapter.py:76-88` | Sequence before any freeze |
| **K7** | After a P4 run is authorized the holdout window is consumed; evidence found missing later cannot be fixed by a rerun | `results_guard.py:758-776` | Revalidate before P4 as a hard step |

**Fit with the verdict enum.** Adding G10 as a separate gate-report entry and a P5 / P6 advancement condition fits the existing enum with no new member and no changed meaning (`verdict.py:57-71`). A consumer that reads only the verdict would not see G10, so every advancement path must also consult the gate report. A separate contract review is needed only if someone wants the verdict itself to encode G10.

### A2.9 Record (BLANK)

| Field | Value |
|---|---|
| Decision | G10-REDUNDANCY: comparator policy, binding option, revalidation rule |
| Binding alternative (G10-C1 / C2 / C3) | BLANK |
| Policy manifest SHA-256 | BLANK |
| Approvers | Owner; trading-expert reviewer; independent validator (BLANK) |
| Signature / date | BLANK |

---

## A3. CONSOLIDATED PRIORITIZED DECISION MATRIX

The matrix lists the unresolved P0 decisions in dependency priority. Priority 1 items unblock everything; later items depend on earlier ones. "Baseline" is the governing text. Every proposed resolution carries its status label. Nothing is approved.

### A3.1 Matrix

| Pri | Decision | Governing baseline | Proposed resolution and status | Alternatives | Dependencies | Exact owner decision needed | Signers (BLANK) |
|---|---|---|---|---|---|---|---|
| **1** | **Human roles and validator independence** (D08) | Design decision 08, s10.3; A1 s10; Register s27, s43; Validator Independence Requirements v0.1 [MERGED]; owner ruling 5 (R1-L1b) | SoD-A + SoD-C; four named role slots; independent validator required before formal P0 approval [OWNER-DIRECTED, UNSIGNED]. Safeguard PR #740 [LOCAL, UNMERGED] enforces all-pairs distinct identifier strings | SoD-B (removed: all-pairs rejection), SoD-D (contradicts ruling 5) | none; unlocks every reviewer sign-off | State the four names, the engineer list, and the validator's independence attestation (procedural confirmations V-2 of the merged document); state whether and when PR #740 merges | Owner; each named person for their own role |
| **2** | **P3a / P3b attempt-budget rules and C-DR** | Merged code: budget per (genesis, phase), consumed at `capability_issued`, no reset, `budget_reset_authorization` refused by name (`results_guard.py:601-640`); Plan R3 (101), WP4.0 step 2 (584), WP4.1 (606), s5.2 (698), s6 (710), s11.1 (848) | Limits **1 / 1**; no automatic defect-only retry; a technical defect after authorization may permanently end the phase; recovery unavailable without a separately designed, implemented and approved mechanism; an owner authorization alone cannot reset the budget [OWNER-DIRECTED, UNSIGNED]. Plan wording amendments (Register s39) [PROPOSED], not applied | Limits above 1 (owner rejects: permits outcome-driven retries); implement recovery first (design-only Level 2) | none; must precede the manifest change and P3a | Sign C-DR option (i) and the limits; approve the Plan amendments for application as a separate edit | Owner |
| **3** | **A1 vs design v0.4 (and the merged schema)** | A1 (draft, unsigned); design v0.4 as quoted; merged schema locks the A1 layout (`schema.py` Partitions; `model.py:21-47`; `verdict.py:23`, `:53-55`; `results_guard.py:425-427`; `manifest.py:62`) | Proceed with P3a / P3b subject to a written reconciliation memo and independent review of the exit-selection methodology; A1 not signed merely because the code assumes it [OWNER-DIRECTED, UNSIGNED]. Memo outline and review requirements (Register s40, s41) [PROPOSED] | Amend A1 further; fall back to v0.4 (needs the code changes listed in Register s23.3) | Roles (1); validator independence | Commission the memo and the methodology review; after both exist, sign A1 / amend / reject. Note: "v0.4" here means the research design v0.4; the Implementation Plan v0.4 is superseded by v0.5 | Owner; trading-expert reviewer; independent validator |
| **4** | **P5 account binding** (D07) | Merged schema requires non-null `p5.account_id` at freeze (`schema.py:436`); Plan WP5.1 creates the account only in P5 | Option B: hashed marker `p5.account_binding` = `deferred_to_p5_activation` plus a separate P5 activation record bound to the same `spec_sha256` [OWNER-DIRECTED, UNSIGNED; remains PROPOSED]. Schema candidate `76730911` [LOCAL, UNMERGED] implements it for review only | Option A (nullable field), Option C (unhashed block), owner-stated value (invents a placeholder) | Roles (1); precedes any real freeze | Confirm option B and the marker text; authorize the implementation PR (Workstream C) and its merge before any freeze | Owner; independent validator reviews the schema change |
| **5** | **K1-K3 and G10-REDUNDANCY** | Plan s5.1 lines 649, 665; schema `gates.redundancy_corr_max`; A2 above | Plan clarification for K1; enforcement deferred to P5 / P6 code for K2; G10-C1 / C2 / C3 evaluated for K3 (owner prefers C1 for evaluation; no selection) [PROPOSED]; comparator policy per A2 [OWNER-DIRECTED, UNSIGNED as to directions] | G10-C2 or G10-C3; no G10 policy until P6 | D06, D18, D10 equity sampling (A2 inputs); roles (1) | Rule on K1 (clarification wording), K2 (defer enforcement), K3 (G10-C1, C2 or C3); define the comparator policy; sign item 12A | Owner; trading-expert reviewer; independent validator |
| **6** | **D06 bootstrap and negative controls** | Design decision 06, s5.3; Plan WP2.5, WP2.7A, WP3.3, WP4.0; ruling C11 (method unset by design); schema `stats.bootstrap.cluster` fixed; candidate `76730911` adds control definitions | Recommendations only [PROPOSED]: stationary bootstrap over days, one-sided alpha 0.05, at least 10,000 repetitions, fixed seeds. **Block length, statistic, null procedure, seeds: no value proposed.** New controls (time-shuffle, no-information, stage-1 criteria with optional negative-control test and alpha, random-entry population): each needs an individual written definition, acceptance behavior and independent statistical review before any value | Circular or iid-cluster bootstrap; invariants-only vs invariants-plus-negative-control test | Roles (1); validator calibration (synthetic only) | State every bootstrap and control parameter; validator signs the specification and the calibration report | Owner; independent validator |
| **7** | **D02 Holm family / multiplicity** | Design s5.3, s6 (G4, G5); A1 Amendment 3; Plan WP3.3, s5.1A; ruling C6; schema `stats.adjustment` in {holm, fixed_sequence}, skeleton preset holm | Option (a): Holm over {G4, G5}, family size 2, one-sided 0.05 [PROPOSED]. P3a selection-aware max-statistic over K is separate. "m = 1" counts exit configurations, not hypotheses | (b) G4 is the family, G5 a separate gate at its own alpha (intersection-union); (c) fixed sequence | D06 | Choose (a), (b) or (c) and state the hypothesis count; confirm the preset `holm` explicitly | Owner; independent validator |
| **8** | **D17 sample size** | Design s7 (no criteria given: a gap); A1 s3; Plan s2.2, WP4.1; gates G1 300 / PF 1.30 locked | Proposed (unsigned): P3a minimum 300 trades, PF > 1.0 at base cost, STOP alpha 0.05; P3b = P4 thresholds with G1 scaled to two years (150). **Not attempt limits.** Hazard: under a single attempt an unattainable minimum is a terminal STOP; attainable count cannot be checked return-blind | STOP alpha 0.10 or 0.20; looser P3b screen; significance only | D06, D18 | State P3a min trades, PF, STOP alpha, P3b option and minimum, and the owner's acceptance of the single-attempt consequence | Owner; independent validator |
| **9** | **D19 exit candidates and complexity ordering** | A1 Amendment 1; Plan s2.2, WP4.1; schema candidate (family-level order; per-candidate `rank` withdrawn) | K = 7 set (E1; E2a/b 2R and 3R; E3a/b breakeven at +1R then trail 1.0R / 1.5R; E4a/b 50% scale-out at +1R, remainder EOD / trail 1.0R) [PROPOSED]; family-level complexity order. **Tie tolerance delta: no basis in the documents (0.05 R is an illustrative placeholder only). Within-family tie-break: unset owner-approval item; `select_exit` must fail closed on an unresolved tie** | Smaller set; owner replacement after trading-expert review (at most 8, four families) | D06, D17, D18 | State the candidate set, family order, within-family tie-break, delta, eligibility and STOP test | Owner; trading-expert reviewer; independent validator |

### A3.2 Items adjacent to the matrix (not re-decided here)

D18 (gate basis and trade unit) precedes D17; D04, D10, D11, D15, D16 and C10 have owner-ready sheets in the merged register (s33, s46); D01, D03, D05, D09, D12, D13, D14 depend on audits, feasibility and the C-EVID ruling. The merged register's 32-item list stays authoritative for these; item 12A (G10-REDUNDANCY) is a [PROPOSED] insertion below.

### A3.3 Signing dependencies

```
1 roles / validator independence  -->  everything below
2 C-DR + attempt rules            -->  manifest limits, P3a authorization
3 A1 reconciliation + review      -->  A1 signature --> D17 / D19 / D02 validity
4 P5 option B (schema PR merged)  -->  real freeze
D06 spec + calibration (6) --> D02 (7) --> D18 --> D17 (8) + D19 (9) --> A1
D06 + D18 + D10 --> G10 policy (5, item 12A) --> freeze (G10-C1) --> P3a authorization
```

### A3.4 Proposed amendment to the signing sequence ([PROPOSED]; not applied to the register)

Insert **item 12A, G10-REDUNDANCY policy pre-registration**, in Step 5 immediately after D10 (item 12). With strict numbering it is item 13 and the list becomes 33 items. It needs D06 (Step 2), D18 (Step 4) and D10's equity-sampling definition first. It blocks: the real freeze (G10-C1); under G10-C2 or G10-C3 the first P3a authorization by process; in both cases the P4 authorization (revalidation). A "P4-pre" comparator revalidation record sits outside the pre-freeze list.

### A3.5 Priority order for the owner

1 Roles and independence. 2 C-DR and attempt rules. 3 A1 reconciliation and methodology review. 4 P5 option B. 5 K1-K3 / G10. 6 D06. 7 D02. 8 D18 then D17. 9 D19. Then the merged register's ready sheets (D04, D10, D11, D15, D16, C10) and the audit-dependent decisions.

---

## B. UNRESOLVED QUESTIONS

1. Who are the four role holders, and how is the validator's independence evidenced (names, attestation, engineer list)?
2. Is "v0.4" in the owner's A1 instruction the research design v0.4 (assumed here) rather than the superseded Implementation Plan v0.4?
3. Does the owner accept D03 as the controlling decision for 10 of the 11 constants (A1.2b), and the D03-representation / D09-equivalence split with one shared definition for `SECURITY_IDENTITY_CONTRACT` (A1.2c)? (ORM-001: no current dependency; future dependency not determinable, A1.2d.)
4. Which strategies are "approved strategies" for G10, from which source state, with what eligibility criteria and series definition?
5. G10-C1, G10-C2 or G10-C3 for the comparator-policy binding, and is a Plan clarification (K1) acceptable?
6. Is enforcement of "blocks advancement" (K2) acceptably deferred to the later P5 / P6 code?
7. What are the bootstrap block length, statistic, null procedure, seeds, and the definitions of the new controls (D06)?
8. Which D02 option and hypothesis count?
9. What are the D17 minimums and STOP alpha, and does the owner accept that a missed minimum is a terminal STOP under a single attempt?
10. What are the D19 delta and the within-family tie-break?
11. What fetch-mode enumeration (D11) and what custody and retention (C10)? (merged register sheets)
12. Will PR #740 and the schema candidate merge, and in what order, before any freeze?

## C. EVIDENCE (where each claim can be checked)

| Claim | Evidence |
|---|---|
| Starting point and merged content | `git log origin/main` at `1c305b8f` (#745, #746, #747); `git ls-tree` of `docs/implementation/evidence/range_002/` |
| Code unchanged since PR #739 | `git diff --stat d61f313a origin/main -- apps` is empty |
| OD-1 constants and values | `apps/backend/app/validation/security_lineage.py` lines 55, 60, 64, 70, 73-87, 90, 211, 325 |
| Attempt, authorization and P5 behavior | `governance/results_guard.py:361`, `:408`, `:425-429`, `:601-640`, `:652`, `:672-675`, `:727`, `:758-776`; `governance/run_registry.py:129-134`, `:545-565` |
| Verdict enum and transitions | `governance/verdict.py:21-38`, `:53-72` |
| Spec fields and hash scope | `spec/schema.py:421-432`, `:436`, `:450`, `:454`, `:524`; `spec/manifest.py:52-62`; `governance/spec_view.py:47-79`; `governance/spec_adapter.py:76-88` |
| Schema candidate | `git show 76730911` (`feat/range002-schema-batch`), `schema.py:598-609` |
| G10 in the Plan | `RANGE-002_Implementation_Plan_v0.5.md:649`, `:665`, s5.1A |
| Follow-ups and backlog | `RANGE-002_OD_Followups_v0.1.md` (this stage); `RANGE-002_P1_P2_Implementation_Backlog_v0.1.md` and `RANGE-002_Schema_Change_Batch_Proposal_v0.1.md` (merged, #746) |

## C-STAT. ILLUSTRATIVE STATISTICS RULE AND REPRODUCIBILITY LIMITATIONS

**This package states no pass-rate, power or probability figure of its own**: every statement of the form "x% of ... pass" or "nearly guarantees REJECT / STOP" is absent, and none may be added without its synthetic assumptions. Related documents quote such figures; this section records how they must be read.

**The data-feasibility report's chain figures** (about 2% and about 11% that a true 0.15 R edge passes P3a, P3b and P4) are valid only as illustrative arithmetic under these synthetic assumptions: per-trade SD 1.3 R; day-clustering design effect 1.2; exit-candidate correlation 0.8 (the P3a critical value 2.0 corresponds to about 0.9); trade counts 300 / 150 / 300 (about 2%) or 600 / 300 / 600 (about 11%); P3a, P3b and P4 treated as independent windows so the stage probabilities multiply; P3b and P4 true effect shrunk to 0.7 of the P3a value (an arbitrary choice); P3b one-sided alpha 0.05; P4 G4 alone at alpha 0.025; baseline -0.03 R; true edge 0.15 R. They are not measurements, not predictions about RANGE-002, not validator-calibrated, and support no statement about how likely a real edge is to produce STOP or REJECT.

**Reproducibility limitations (listed, not hidden):**

1. The script that produced those figures, `docs/implementation/evidence/range_002/range002_synthetic_power_illustration.py`, is published with the data feasibility report (`docs/implementation/evidence/range_002/RANGE-002_Data_Feasibility_and_Validation_Design_Report_v0.1.md`), both merged in #747; the citation resolves on `main`. Its provenance is documented separately in that report (section 6.8: the committed file is a copy of a scratch script; the post-edit script SHA-256 begins `19b4ccae`, as relayed). The output was **reproduced on one environment by Agent E** (output digest beginning `4c322991` and ending `2757`, as relayed; the full digests are in that report and were not re-checked by the preparer here); the preparer had also run it once earlier (chain values 0.024 and 0.113 at a true edge of 0.15 R). Remaining limits: reproduction on a single environment only, no independent statistical review by the validator, and the figures stay illustrative under their synthetic assumptions, not predictions about RANGE-002.
2. Missing evidence (no script or artifact exists): the validator's D06 calibration (size and power of the day-clustered bootstrap, block-length sensitivity, Monte Carlo precision); the A1 methodology review's selection-bias and pipeline-size study; the synthetic check of the G10 correlation method; the D17 trade-count feasibility analysis; any synthetic fixtures for the D19 `select_exit` tie cases.
3. The bootstrap-dependent steps in the illustrative script use a fixed seed (`20261010`); the chain figures are closed-form (normal approximation), so they would be unchanged by the seed but also inherit the normal approximation and the independence assumption.
4. Any figure in this package's sources that lacks a stated assumption set is to be treated as unsupported until its assumptions are stated.

## D. INVARIANTS

Recommendation: **NO-GO**. Formally approved decisions: **0**. All signatures, names, dates and SHA-256 fields are BLANK. The merged / proposed / owner-directed-unsigned distinction is kept per row. No value was invented: numbers quoted are those already present in code, schema, Plan or Sheets, each labelled with its status. No enrollment, freeze, data access, signing or code change occurred.
