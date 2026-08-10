# MR-002 Development Plan v1.3 — Review Memo v1.0

**Program:** MR-002 / SPQ-1 · **Reviews:** `MR002_Development_Plan_Next_Phases_v1.3.md` (APPROVED, 2026-08-09)
**Date:** 2026-08-09 · **Type:** review record only — proposes no work, opens no data, authorizes nothing
**Governing rule honored:** v1.3 two-review-max cycle is CLOSED. This memo does **not** open a revision
cycle. It submits **candidate execution-exposed inconsistencies** for owner adjudication under the plan's
own reopening clause, and records execution notes that explicitly do **not** justify reopening.

---

## Verdict

The v1.3 APPROVED status stands. The plan's structure — remaining-work-only scope, the §2.1 bounded
"get to validation" ruling, the P-numbered prerequisite ledger with P12 correctly isolated as an owner
event rather than producible work, and the actor/authorization boundary in §5 — is sound and should not
be touched. Three candidate inconsistencies are submitted below. Only EI-1 clearly meets the
"execution-exposed" bar; EI-2 is probable pending one owner classification; EI-3 is minor and may be
declined without prejudice.

---

## Candidate execution-exposed inconsistencies (owner adjudication requested)

### EI-1 — Step 2 gate references the recovery-media custodian record, not the operational custodian

**Severity: GENUINE — meets the reopening bar as written.**

| | |
|---|---|
| Conflict | §5 Step 2 gate: *"A real accountable individual is named in the §7 custodian record."* The §7 custodian record is the WP-A **A5** artifact — the **recovery-media** custodian. WP-A itself warns, in bold: *"A5 does not satisfy Step 2."* |
| Exposure | An executor (human, automation, or agent) following the Step-2 gate text literally will credit Step 2 — unblocking WP-C/WP-D and all custodian-produced prerequisites P6–P9, P11 — the moment the media custodian is named. This is precisely the mis-credit the two-role table exists to prevent, and it fires at the WP-C start boundary. |
| Proposed one-line correction | Step 2 gate → *"A real accountable individual is named in an **operational-custodian appointment record**; if the owner appoints one individual to both roles, the dual appointment is recorded in both the §7 record and the operational-custodian record."* |
| Not proposed | No change to the two-role design itself, which is correct. |

### EI-2 — WP-B (Requirement-7 resolver) has no downstream consumer and no acceptance condition

**Severity: PROBABLE — depends on one owner classification.**

| | |
|---|---|
| Gap | Dependency matrix: nothing depends on WP-B. WP-E depends on "frozen runtime + bound image" without naming the resolver; WP-F depends on "P6–P11 all complete." Grant-readiness conditions C1–C10 verify P3–P11, lineage, drift, and CAS state, but never that the Requirement-7 resolver exists and fails closed. |
| Exposure path 1 | WP-E can produce P10's container-image digest binding via ad-hoc resolution while the fail-closed resolver is unbuilt; P10 then reads as satisfied with custody Requirement 7 still owed. |
| Exposure path 2 | The WP-F verifier can return PASS with Requirement 7 unsatisfied, because C1's "every blocking prerequisite" is not mechanically enumerable — the verifier cannot apply a broad reading; it can only check what C1–C10 list. |
| Owner classification requested | Is custody Requirement 7 **blocking for the D3 grant**? (Custody requirements 1–6 satisfied and 7 carved into its own authorized WP suggests yes.) |
| If blocking, proposed correction | Add dependency edges WP-E ← WP-B and WP-F ← WP-B; add to C-conditions: *"the Requirement-7 fail-closed resolver is built, is the sole resolution path used by P10 and the run environment, and demonstrates FAIL-CLOSED on digest miss/mismatch."* |
| If not blocking | No plan change; record the classification so the WP-F builder does not have to infer it. |

### EI-3 — §0 "everything CLOSED" table contains an open item

**Severity: MINOR — may be declined without prejudice.**

The §0 header instructs *"Everything in this table is CLOSED. Do not re-plan, re-derive, or re-run it,"*
while the final row (external recovery archive) states *"placement still owed — see WP-A."* The
cross-reference prevents actual mis-execution, so this may fall below the bar; but if the file is
reopened for EI-1, the free fix is to move the archive row out of §0 or add the exception to the header.

---

## Execution notes — explicitly NOT reopening candidates

These are handled by doing the work, not by editing the plan. Recording them here prevents them from
resurfacing later as revision pressure.

1. **A6 staging-path disclosure.** `C:\LLM-RAG-APP\mr002_recovery_staging\` in a distributed governance
   document sits uneasily beside A5's "no serials, no physical locations" discipline and identifies the
   staging machine. Resolution is executing A6 (delete or explicitly accept), after which the path is
   historical. No plan edit.
2. **Self-attestation is acceptable here, and it is worth saying why.** At this program's scale the
   operational custodian will plausibly be the owner, making P7's "partition never opened" a
   self-attestation. This is acceptable **because** P7/P8/P11 were designed to make the attestation
   mechanically verifiable — hash-chained access history, CloudTrail S3 data events enabled before any
   access, and a pre-execution policy snapshot — rather than trust-based. The evidence design already
   substitutes mechanism for personnel independence; no additional governance layer is needed, and adding
   one would violate §2.1.
3. **Validation-phase verdict criteria live in the prereg, not this plan.** §4.2 reproduces the primary
   OOS Sharpe gate; the Phase 3C `ValidationVerdict` criteria are in
   `MR002_ValidationOOS_Preregistration_v1.0.4`. Correct under the reproduce-never-rederive rule — noted
   only so the 3C executor looks in the right place rather than reading §4.2's OOS gate as the
   validation gate.
4. **Housekeeping recommendation endorsed as-is.** The §3 Housekeeping reasoning — that a record closed
   by deletion leaves no audit trail it was ever adjudicated — is correct, and the recommended one-line
   `CLOSED AS SUPERSEDED` owner closure artifact is the right disposition. Nothing to add.

---

## Disposition requested

| Item | Requested owner action |
|---|---|
| EI-1 | ACCEPT as execution-exposed; apply the one-line Step-2 gate correction |
| EI-2 | Classify Requirement 7 (blocking / not blocking for D3); apply or decline accordingly |
| EI-3 | ACCEPT alongside EI-1, or DECLINE WITHOUT PREJUDICE |
| Execution notes 1–4 | RECORD ONLY — no plan revision |

If EI-1 (± EI-2/EI-3) is accepted, the resulting edit is a **correction under the reopening clause**,
not a new review cycle: single commit, changed lines only, version bump to v1.3.1, no re-review of
unchanged content.
