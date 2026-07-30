# Owner Adjudication — D-BOX CAMPAIGN-001 v1.2 Close-Out

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-V12-CLOSE-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | Close-out of CAMPAIGN-001 **v1.2** authorized executable packages only |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2 |
| Campaign label | **O3/O4-A/O4-B EXECUTION CAMPAIGN — O5 DEFERRED — NO D-WIRE ELIGIBILITY** |
| Ruling date (UTC) | 2026-07-30 |
| Effective date (UTC) | `2026-07-30T18:49:40Z` |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| Freeze body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Start ruling | ADR0043-PH0-D-BOX-START-002 (EFFECTIVE) |
| Start merge | `952848c4696f9b8750c91c82967cdec065c6a804` |
| Execution record | ADR0043-PH0-D-BOX-V12-RUN-001 |
| Evidence root | `docs/design/evidence/dbox_campaign_v1_2_run_001/` |
| O3 evidence merge | `b542d1c2228993b44bb3d3c8067ec9dc99d72d61` |
| O4-A evidence merge | `d85f4879e8188d4ea08543c57ff4a72bc5ed2f83` |
| O4-B evidence merge | `83813a68768330556f97bf290278411a10d7e95d` |
| Seal publish merge | `99a8537f78ad758eef5f23f803ce9eff098e83b6` |
| Publication path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_v1_2_Closeout_v1.0.md` |

---

## 1. Purpose

This ruling closes CAMPAIGN-001 v1.2 as **complete for its authorized scope** under
START-002: opening controls PASS, then **O3 → O4-A → O4-B** each adjudicated with a
governed disposition. Sealing, publication, and package execution did **not** create
D-WIRE eligibility.

---

## 2. Final package dispositions (accepted)

| Package | Final disposition |
|---------|-------------------|
| CORR-06 | **Inherited APPROVE** (Option 2A; not rerun under v1.2) |
| O1 | **Inherited APPROVE** (Option 2A; not rerun under v1.2) |
| O2 | **Inherited APPROVE** (Option 2A; not rerun under v1.2) |
| O3 | **INCONCLUSIVE — replay surfaces absent** |
| O4-A | **INCONCLUSIVE — decision-time quotes absent** |
| O4-B | **INCONCLUSIVE — day_change absent** |
| Combined O4 | **INCONCLUSIVE** |
| O5 | **INCONCLUSIVE**, `anchors: []` |
| D-WIRE | **BLOCKED** |

Basis (evidence limitations, not harness/hash failure):

| Package | Evidence limitation |
|---------|---------------------|
| O3 | 0/292 observations with complete quote/authority/checkpoint/loss/recovery surfaces |
| O4-A | 0/287 observations with usable two-sided decision-time quotes |
| O4-B | 286/286 observations missing `day_change` baseline for `UNREACHABLE_WITHIN_CAPS` |

Structural/hash/`ord:`/exclusion/no-mix controls for O3/O4-A/O4-B **passed** where
applicable and are retained under the evidence root.

---

## 3. Binding identities

| Binding | Value |
|---------|-------|
| START-002 merge | `952848c4696f9b8750c91c82967cdec065c6a804` |
| FREEZE-003 body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| O3 evidence merge | `b542d1c2228993b44bb3d3c8067ec9dc99d72d61` |
| O4-A evidence merge | `d85f4879e8188d4ea08543c57ff4a72bc5ed2f83` |
| O4-B evidence merge | `83813a68768330556f97bf290278411a10d7e95d` |
| Evidence root | `docs/design/evidence/dbox_campaign_v1_2_run_001/` |

Any close-out identity mismatch voids this ruling until corrected by a superseding owner
ruling.

---

## 4. Explicit close-out statements

1. **START-002’s executable set is exhausted** (O3, O4-A, O4-B each disposed).  
2. **No package may be rerun** under FREEZE-MANIFEST-003 / START-002.  
3. Missing fields are **evidence limitations**, **not** authorization to enrich, patch, or
   reconstruct sealed QUALIFIED archives.  
4. Any new corpus, reconstruction, source acquisition, or observation capture requires a
   **new** design, authorization, freeze, and start decision.  
5. **All HOLD conditions remain effective** (broker orders, new live fills, production
   imports, deployed-path observation, canary, ENFORCE, caps, July 24 limits-digest
   changes). Production stack `b0058bf` remains reference-only / unmodified.

---

## 5. D-WIRE

D-WIRE remains **fail-closed / BLOCKED**. O3/O4 INCONCLUSIVE plus O5 `anchors: []` do not
and cannot create D-WIRE eligibility under this campaign.

---

## 6. Recommended successor (not authorized by this close-out)

**Do not** open another immediate execution campaign. First draft a **narrowly scoped
evidence-gap design** covering prospective collection of:

1. O3 replay-surface capture  
2. O4-A two-sided decision-time quote capture  
3. O4-B governed `day_change` (or equivalent forensic baseline)  
4. O5 Tier-A anchor acquisition  

Until that prospective collection design is approved and produces **QUALIFIED** evidence
under a new freeze/start, D-WIRE remains fail-closed. This close-out does **not**
authorize that design, freeze, start, or any collection activity.

---

## 7. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** — CAMPAIGN-001 v1.2 closed for authorized scope |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | `2026-07-30T18:49:40Z` |

**CAMPAIGN-001 v1.2 CLOSED as complete for its authorized scope.**

*End of ADR0043-PH0-D-BOX-V12-CLOSE-001.*
