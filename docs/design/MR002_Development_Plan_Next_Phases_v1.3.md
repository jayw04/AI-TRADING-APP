# MR-002 / SPQ-1 Development Plan — v1.3.1 (remaining work only)

**Program:** MR-002 — Sector-Neutral Residual Reversion · **Workstream:** SPQ-1
**Date:** 2026-08-09 · **Status: APPROVED (owner, 2026-08-09).** Review-1 and review-2 editorial corrections applied; two-review-max cycle **CLOSED**.

**v1.3.1 — correction under the reopening clause, not a new review cycle.** Three
execution-exposed inconsistencies raised in `MR002_DevPlan_v1_3_ReviewMemo_v1_0.md` were accepted
by the owner and applied as changed lines only; unchanged content is not re-reviewed.

| Ref | Correction | Where |
|---|---|---|
| **EI-1** | Step 2's gate cited the §7 **recovery-media** custodian record, which WP-A explicitly states does not satisfy Step 2. Gate now cites an **operational-custodian appointment record**. | §5 Step 2 |
| **EI-2** | Custody **Requirement 7** classified **BLOCKING for the D3 grant** — the research-side closeout lists it under `image_custody_requirements_before_p10_or_readiness`. WP-B now has downstream consumers (WP-E, WP-F) and a grant-readiness condition. | §3.0, WP-B, WP-E, WP-F |
| **EI-3** | §0's "everything CLOSED" header contradicted the recovery-archive row, whose placement is still owed. Header now carries the exception. | §0 |
**Type:** planning and governance record only — opens no validation/OOS data and authorizes no performance computation
**Supersedes:** `MR002_Development_Plan_Next_Phases_v1.2.md` (all completed work removed)
**Companion:** `docs/review/mr002/MR002_Architecture_Review_v1.1.md` (platform integration; research-only until promotion)

> **Purpose of this revision.** v1.2 carried the full Phase 2B completion record and a Phase 3A
> task list that has since been executed in full. v1.3 keeps **only work that is not yet done**.
> Completed work is not restated — it is referenced by artifact path so the evidence stays
> findable without living in the plan.

---

## 0. What was removed, and where its evidence now lives

Everything in this table is **CLOSED**. Do not re-plan, re-derive, or re-run it — **with one stated
exception**: the final row (external recovery archive) is closed as to *production and
verification* only. Its physical **placement is still owed** and is live work under **WP-A**.

| Removed from the plan | Disposition | Evidence |
|---|---|---|
| Phase 2B — full development signal production (425,000 units), collision amendment, 2B-3 closeout | **CLOSED** | `docs/review/mr002/spq1/phase2b/**` · closeout `.../2b3/…ClosureCloseout_v1.0.json` |
| v1.2 §10 developer assignment, tasks 1–10 (locate/bind prereg, bind A/B/C, DoF attestation, A2 short model, A4 enrichment contract, A3 seal, A6 preflight, metric roles, OOS consumption rule, zero-access proof, commit + stop) | **ALL DELIVERED** | `docs/review/mr002/phase3a/` (27 artifacts) |
| Phase 3A amendments A1, A2, A3, A4, A6, §4.4a, §5.3a | **DELIVERED** as the Phase 3A package | same |
| Phase 3A review cycle (two-review-max) | **CLOSED**, corrections applied | commit `f7319de951b6fd7b84112ad2b207d61376399ac1` |
| Phase 3B/C execution-authorization request + lineage proof + prerequisite register | **SUBMITTED AND ADJUDICATED** | `docs/review/mr002/phase3bc/` |
| Owner adjudication of 2026-07-22 | **D1 ACCEPTED / D2 AUTHORIZED WITH RESTRICTIONS / D3 DENIED WITHOUT PREJUDICE** | `.../MR002_Phase3BC_AuthorizationAdjudication_v1.0.{md,json}` |
| P1 Phase 3A owner acceptance · P2 lineage reproduces with zero drift | **SATISFIED** | `.../MR002_Phase3BC_Phase3ALineageProof_v1.0.json` (25/25) |
| P3 evaluator operational increment · P4 SS5 consolidated acceptance · P5 SS4 pre-access binding (source + roster + container legs; `PENDING_EVALUATOR_BIND` **RESOLVED**) | **SATISFIED** | `docs/review/mr002/MR002_ResearchSidePrerequisiteCloseout_v1.0.json` |
| Evaluator image custody requirements **1–6** (durable ECR custody by immutable digest) | **SATISFIED** | `.../MR002_EvaluatorImageCustody_v1.0.json` |
| Custody detection package (CloudTrail data events, alerting, scheduled integrity monitor 11/11) | **IMPLEMENTED** | `scripts/mr002_custody/` · `.../MR002_CustodyDetection_Submission_v1.0.md` |
| External recovery **archive** — produced, digest-verified, restore-tested, offline verifier hardened and SDK-free | **PRODUCED AND VERIFIED** (placement still owed — see WP-A) | `.../MR002_ExternalRecoveryCopy_v1.0.json` · commits `6b8d92d`…`9a93fff` |

⚠ **Correcting a stale claim in v1.2.** v1.2 is dated 2026-07-24 and states "Phase 3A drafting
NOT YET AUTHORIZED / not drafted." That was already untrue when written: the Phase 3A package
landed at `be8ab53` on 2026-07-22 and the 3B/C adjudication at `953bda9` the same day. v1.2 was
drafted from a pre-3A baseline. v1.3 supersedes it on that point.

---

## 1. Where the program actually stands (2026-08-09)

| Item | State |
|---|---|
| Phase 2B | **CLOSED** |
| Phase 3A validation authorization package | **DELIVERED AND ACCEPTED** (P1) |
| Phase 3B/C authorization | **DENIED WITHOUT PREJUDICE** — resubmittable |
| Prerequisite production (P3–P11) | **AUTHORIZED WITH RESTRICTIONS** (D2), production-only |
| Pre-grant prerequisites **satisfied** | **P1, P2, P3, P4, P5** |
| Pre-grant prerequisites **outstanding** | **P6, P7, P8, P9, P10, P11 — 6** |
| Authorization event **outstanding** | **P12** — the owner grant itself at the D3 gate. **Not** a prerequisite the team can complete; it is the act being requested. |
| `validation_authorization` | **false**, `_rev 0` |
| Validation partition | **CLOSED**; single opening **UNCONSUMED** |
| OOS partition | **UNDER DENY** |
| Performance / ranking / portfolio / execution | **NOT AUTHORIZED** |
| Named operational custodian | **UNRESOLVED** — first-class blocker for WP-C/WP-D |
| Custody Requirement 7 (fail-closed resolver) | **SPECIFIED_NOT_IMPLEMENTED** — classified **BLOCKING for the D3 grant** at v1.3.1; gates P10 and grant readiness (WP-B) |
| SPQ-1 Phase 0 formal closure | **DISPOSITION DECISION OWED** (see §3, Housekeeping) |

⚠ **Do not read this as "seven prerequisites to complete."** Six (P6–P11) are producible work.
P12 is an owner authorization event that can only follow a D3 resubmission — the team cannot
complete it, and reaching it early does not accelerate it.

Authoritative anchor: `docs/review/mr002/phase3bc/MR002_Phase3BC_ValidationAuthorizationState_v1.0.json`.

---

## 2. Standing prohibitions (unchanged, binding on every item below)

- No opening, reading, querying, sampling, summarizing, or indirect inference of
  validation-partition values.
- No performance computation, returns, Sharpe, DSR verdict, ranking, or portfolio construction.
- No change to the preregistered evaluator, model identity, acceptance criteria, trial design, or
  structural bindings.
- Runtime evidence must be produced **prospectively**. Specification templates, retrospective
  attestations, inferred state, and placeholder completion **do not satisfy** a runtime-evidence
  prerequisite.
- Any prerequisite that cannot be completed truthfully without validation access **must remain
  unsatisfied**.
- No grafting into Momentum, Range Trader, or other live templates. Portfolio combination requires
  a separate preregistered study.
- Frozen MR-002 signal logic must not change after validation/OOS observation. **Config B** is the
  only candidate eligible for sealed OOS.

### 2.1 Scope rule (owner ruling, 2026-08-09)

**MR-002 is now a bounded "get to validation" workstream, not an open-ended development program.**

> Only work that moves MR-002 directly toward opening the validation partition is authorized. **No
> new strategy research, architecture expansion, refactoring, product integration, or additional
> governance layers before the validation verdict.**

Rationale: Phase 2B and 3A are closed, the evaluator is bound, the image is under custody, and the
validation data is untouched. The remaining work is controls and authorization plumbing. The next
economically useful information from MR-002 is **the validation result**, not another
specification. Further refinement of the strategy or its governance surface before the verdict has
diminishing value and competes with getting other strategies into meaningful paper testing.

---

## 3. Remaining work

Ordered by dependency. Nothing later may start before everything it depends on is satisfied.

### 3.0 Dependency matrix

| WP | Owner | Authorization | Depends on | Produces |
|---|---|---|---|---|
| **WP-A** | Owner (physical) | **Existing** — no new authorization needed | none | Independent offline recovery control |
| **WP-B** | Research | **New authorization required** | evaluator image digest fixed | Requirement-7 fail-closed resolver — **BLOCKING for the D3 grant**; consumed by WP-E and WP-F |
| **WP-C** | Custodian | **D2 already authorizes** | **named custodian** | P6, P7, P8, P9 |
| **WP-D** | Infrastructure / Custodian | **D2 already authorizes** | **named custodian**, IAM/CloudTrail setup | P11 |
| **WP-E** | Research (run environment) | **D2 authorizes P10; production instance still needs an explicit owner go** | frozen runtime + bound image · **WP-B** (the resolver is the only permitted resolution path for the image digest) | P10 |
| **WP-F** | Research (verifier) | **Separate future authorization — NOT_BUILT, not granted** | P6–P11 all complete · **WP-B** | Closed C1–C10 + C-R7 grant-readiness proof |
| **WP-G** | Owner / governance | **D3 adjudication** | WP-F PASS | Fresh CAS anchor → P12 → `validation_authorization: false → true` |

Housekeeping (Phase 0 disposition) and naming the custodian are owner acts that gate WP-C/WP-D;
they are not work packages.

### WP-A — Complete the external recovery control *(OWNER; physical action)*

**Blocking for:** custody credibility ahead of P10/grant-readiness. Archive is built and verified;
only placement remains. Procedure: `MR002_ExternalRecoveryCopy_Submission_v1.0.md` §5–§7.

| # | Action |
|---|---|
| A1 | Encrypt the archive at rest on the destination medium (owner-held key; **never** record key, passphrase, or recovery phrase in any governance artifact) |
| A2 | Write to genuinely independent removable media |
| A3 | Confirm the medium is normally disconnected |
| A4 | Run the §5 offline verification **from the medium** and record the verdict |
| A5 | Complete the custodian record (§7) — name a real accountable **recovery-media custodian**; no serials, no physical locations |
| A6 | Delete the staging copy at `C:\LLM-RAG-APP\mr002_recovery_staging\`, or explicitly accept it as a second online copy |

Verification command (air-gapped, no AWS SDK required):

```
python scripts/mr002_custody/export_recovery_copy.py --verify <medium>/mr002-evaluator-p5-recovery.tar \
    sha256:c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a
```

Until A1–A6 are complete: `INDEPENDENT_OFFLINE_RECOVERY_COPY` = **NOT YET CREATED**, and recovery
from ECR loss stays **UNSATISFIED**. The laptop Docker copy is **not** creditable.

⚠ **Two custodian roles, deliberately distinguished — A5 does not satisfy Step 2.**

| Role | Named in | Accountable for |
|---|---|---|
| **Recovery-media custodian** | WP-A **A5** (§7 custodian record) | The encrypted offline archive: physical medium, disconnection, scheduled offline re-verification |
| **Operational custodian** | Execution order **Step 2** | The sealed validation partition: producing P6–P9 and P11 as runtime evidence, and attesting the partition was never opened |

The owner **may** appoint one individual to both roles, and doing so is entirely reasonable at
this scale — but that must be an explicit appointment recorded in both places. Naming a
recovery-media custodian in A5 does **not** by itself resolve the operational custodian, which is
the role the 2026-07-22 detection adjudication recorded as unresolved and which gates WP-C/WP-D.

### WP-B — Fail-closed image resolver (custody Requirement 7) *(needs authorization; BLOCKING for D3)*

Status **SPECIFIED_NOT_IMPLEMENTED**. Required behavior: resolve the evaluator strictly by index
digest `sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9`; on any miss,
mismatch, or unavailability **FAIL CLOSED** — no fallback to a tag, to a local image, or to a
rebuild.

⚠ Building it is research-side prerequisite production, which the research-side closeout
**explicitly does not authorize**. Requires a separate owner authorization before work starts.

**Blocking status (settled at v1.3.1, EI-2).** Requirement 7 **blocks the D3 grant**. This is not
an inference: `MR002_ResearchSidePrerequisiteCloseout_v1.0.json` records all seven custody
requirements under the key `image_custody_requirements_before_p10_or_readiness`, and item 7 is
*"the binding resolver fails if the exact image digest is unavailable."* Requirements 1–6 are
SATISFIED against that same list; 7 is not. The closeout therefore already gates **P10 and grant
readiness** on it, and v1.3 failed to carry that edge forward.

Two failure paths this closes:

1. **WP-E** could bind P10's container-image digest by ad-hoc resolution while the resolver is
   unbuilt — P10 would read as satisfied with Requirement 7 still owed.
2. **WP-F** could return PASS with Requirement 7 unsatisfied, because C1's "every blocking
   prerequisite" is not mechanically enumerable; the verifier can only check what its conditions
   list.

### WP-C — Custodian-side prerequisites *(CUSTODIAN; authorized under D2)*

> ⛔ **Hard precondition: a named operational custodian.** It is still unresolved. P6–P9 and P11
> are custodian-produced by definition, so no part of WP-C or WP-D can start — or be credited —
> until the owner names a real accountable individual. This is a first-class blocker, not a
> paperwork detail.

All four must be **actual runtime instances**. The Phase 3A files of the same name are
specification templates and cannot serve as evidence.

| ID | Deliverable | Satisfaction criterion |
|---|---|---|
| **P6** | `ValidationPartitionContentCommitment` (runtime) | value-blind SHA-256 content commitment over the sealed validation partition, custodian-produced, audit-bound, committed **before** any authorization |
| **P7** | `ValidationPartitionAccessHistory` (runtime) | hash-chained access history evidencing `validation_access_events_before_authorization = 0` **and** `oos_access_events_before_validation = 0` |
| **P8** | `ValidationSealVerificationReport` (runtime) | content commitment stable · no access-before-authorization · OpenedObjectLedger reconciles against SealedStoreAccessLog · OOS DENY in force |
| **P9** | Precommitted value-blind structural manifest | schema identity, table names, row counts, date bounds, session/symbol/security counts, factor coverage, null summaries, latest source date — custodian-produced **before sealing**; the sole input the structural preflight may read pre-authorization |

### WP-D — Access-control preconditions in force and snapshotted *(CUSTODIAN / INFRASTRUCTURE)*

| ID | Deliverable |
|---|---|
| **P11** | CloudTrail S3 data events enabled **before** any access · dedicated IAM principal · explicit bucket/key **DENY** on the OOS partition · validation-only policy · pre-execution policy-state snapshot |

Carried forward from the detection package as still open and feeding this: custody role
**proposed, not applied**; Object-Lock immutable copy not started (needs a separate retention
decision); member-account migration + SCP not started; single-principal risk still disclosed.

### WP-E — Numeric runtime identity *(RESEARCH — run environment; D2 authorizes P10, but the production instance requires an explicit owner go)*

| ID | Deliverable |
|---|---|
| **P10** | `NumericRuntimeIdentityManifest` **runtime instance** — all 17 required bindings populated, including dependency-lockfile SHA-256 and container-image digest; mismatch **FAIL-STOPS before any metric** |

⚠ P5 implies **nothing** about P10. P5 established instance identity only — no numerical library,
BLAS/LAPACK, CPU-dispatch, threading, floating-point, seed, or determinism claim.

⛔ **Depends on WP-B (added at v1.3.1).** P10's container-image digest binding must be obtained
through the Requirement-7 fail-closed resolver, which is the **sole permitted resolution path**.
Binding the digest by any ad-hoc means — a tag, the local Docker daemon, a rebuild, or a
hand-copied value — does **not** satisfy P10, however identical the resulting string looks.

### WP-F — Closed grant-readiness verification run *(not yet authorized to build)*

One closed run must demonstrate **C1–C10 as adjudicated, plus C-R7 added by this plan**, against
the then-current tree.

**C1–C10 — verbatim from the 2026-07-22 owner adjudication. Do not edit these; they are the
owner's adjudicated conditions, not this plan's.**

| | Condition |
|---|---|
| C1 | every blocking prerequisite other than the authorization event itself is satisfied |
| C2 | P3–P11 are runtime-produced, identity-bound, and hash-bound |
| C3 | SS5 acceptance submission complete and accepted |
| C4 | SS4 pre-access evaluator binding resolved |
| C5 | structural manifest precommitted and reproduces exactly |
| C6 | numeric-runtime instance sealed and reproducible |
| C7 | access-control preconditions prove no prior validation opening occurred |
| C8 | Phase 3A lineage still reproduces from the then-current tree |
| C9 | zero evaluator drift, zero unbound evaluator code |
| C10 | `validation_authorization` remains false until the explicit D3 grant event is durably recorded |

**C-R7 — added by this plan at v1.3.1 (EI-2). Not part of the 2026-07-22 adjudication; it is a
condition this plan places on the future D3 submission.** Labeled separately so no reader
mistakes it for an owner-adjudicated condition.

| | Condition |
|---|---|
| **C-R7** | The Requirement-7 fail-closed resolver is **built**, is the **sole resolution path** used by P10 and the run environment, and **demonstrates FAIL-CLOSED** on digest miss, mismatch, and registry unavailability |

Rationale: C1 says "every blocking prerequisite," but a verifier cannot apply a broad reading — it
checks only what its conditions enumerate. Requirement 7 is blocking (see WP-B) and was not
enumerated, so without C-R7 the run could return PASS with it unsatisfied.

Verifier status: **NOT_BUILT**, and the research-side closeout lists "grant-readiness verifier" as
explicitly not authorized. It belongs to a **future D3 submission**, not to the prior adjudication.

### WP-G — D3 resubmission and the authorization event

| # | Step |
|---|---|
| G1 | Re-anchor the CAS: the adjudicated prerequisite digest `088d700b…` is **deliberately stale** now that P3/P4/P5 are satisfied (current-state digest `8d93b656…`). A new adjudicated D3 submission must supply a fresh anchor — it may **never** be silently satisfied against the old one. |
| G2 | Resubmit D3 with the WP-F run attached |
| G3 | **P12** — owner-signed authorization event + time-bounded credential release |
| G4 | Execute the compare-and-set `validation_authorization: false → true` at `_rev 0`, failing closed on any mismatch of stored state, `_rev`, prerequisite digest, evaluator/SignalDecisionRecord code identity, publication-manifest identity, or authorization-request identity |
| G5 | The grant event must be **durably recorded before** any credential release or partition access. A released credential without a recorded grant is an integrity failure. |

### Phase 3B — Validation opening and enrichment

Open the validation partition under seal controls. Produce `ExecutionEnrichedCandidateRecord`s
without mutating close-**t** facts. Enrichment edge-case census per the Phase 3A contract.
**OOS reads = 0.** `FUTURE_INFORMATION_DETECTED` on any t/t+1 seam violation.

### Phase 3C — Validation portfolio replay and metrics

Replay A/B/C under the conservative-availability and frictionless views. Produce **P13**
`MR002_DSR_TrialDispersion_Validation_v1.0.json` (countersigned) — the DSR gate cannot be
evaluated without it. Null-model report. `ValidationVerdict_v1.0.md`.

### Phase 3 decision gate

`VALIDATION_PASS` → prepare OOS authorization. `VALIDATION_INCONCLUSIVE` / `VALIDATION_FAIL` /
`INTEGRITY_FAILURE` → **stop**; no OOS consumption.

### Phase 4 — Single sealed OOS run (Config B only)

One run. Consumption rule enforced per the Phase 3A OOS Consumption Protocol.
`FinalResearchVerdict_v1.0.md`. Requires a further separate authorization after an accepted
validation outcome.

### Phases 5–8 — Product path *(only after a research pass)*

5. Product-viability assessment · 6. Standalone paper strategy (publication consumer +
OrderRouter) · 7. Optional multi-sleeve study · 8. Live-money readiness.
Architecture Review v1.1 governs: combine-don't-graft, no duplicate signal economics, ADRs for
shorting if needed.

### Housekeeping — SPQ-1 Phase 0 formal closure *(one-line owner disposition owed)*

The Phase 0 specification package is submitted; formal closure is **HELD** and no closure record
exists in `docs/review/mr002/spq1/`. It is non-blocking for 3B/C, and it will not be left as
"HELD" — an unresolved non-blocking record is pure accumulated cognitive cost on an already large
governance surface.

**Recommended disposition: `CLOSED AS SUPERSEDED — no additional substantive review required.`
Record a one-line owner closure referencing the accepted downstream phases.**

The substantive Phase 0 output was the owner rulings
(`docs/review/mr002/spq1/MR002_SPQ1_Phase0_OwnerRulings_v1.0.json`), and Phases 1, 2A, 2B and 3A
were each accepted on top of them — so no further review is warranted. But the closure should
still exist as an **artifact**, not as the absence of a note: write the one-line owner closure to
`docs/review/mr002/spq1/MR002_SPQ1_Phase0_Closure_v1.0.json` citing the downstream acceptances,
then replace this subsection with a pointer to it. A record that was closed by deletion leaves no
audit trail that it was ever adjudicated.

⚠ Enacting this is an owner adjudication, not a drafting act.

---

## 4. Frozen execution contract — reference only, no work required

> **Every item in this section is already closed and bound. No implementation, redesign, review,
> or owner decision is required here.** It is reproduced solely so that whoever executes Phase
> 3B/3C has the contract visible at the point of execution rather than scattered across the
> Phase 3A package. Reproduce it; never re-derive or reinterpret it.

### 4.1 Governing preregistration

| Item | Value |
|---|---|
| Governing prereg | `MR002_ValidationOOS_Preregistration_v1.0.4` |
| Governing commit | `4385ec7728a81c0db965e2f44d6017e6116d027c` |
| Content SHA-256 | `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c` |
| Correction class | **GOVERNANCE_ONLY** — `SIGNAL_OR_TRIAL_AFFECTING` must remain **0** |

### 4.2 Preregistered facts the run must honor

| Fact | Value |
|---|---|
| Validation window | 2020-01-13 → 2023-02-08 |
| OOS window | 2023-05-30 → 2026-07-01 |
| Walk-forward folds | 5 |
| **Primary Sharpe gate** | **net_oos_sharpe ≥ 0.70**, net **including** 50 bps/yr borrow financing (day-count 360) |
| Cost stresses | 20 bps/side and 300 bps/yr borrow (severe diagnostic: 30 bps/side + 1000 bps/yr) |
| **Bootstrap** | stationary (Politis–Romano, circular); expected block length **5 primary + 10 sensitivity**; **10,000** replications each; RNG NumPy PCG64; seed **20260711** |
| Bootstrap confidence | one-sided 95% lower bound |
| Confirmatory gate | expected-L=5 lower bound of mean daily net return **> 0** (L=10 is diagnostic only) |
| DSR multiplicity | N = 5 · ledger `deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b` |
| DSR trial set | A, B, C, RNG-001, RNG-EntryLogic |
| DSR annualization | sqrt(252) · benchmark Sharpe = 0.0 |
| Diagnostics (not gates) | PBO, regime concentration |
| Execution endpoint | −5/−6 endpoint = next-open exit (realization horizon 6) |
| Portfolio | dollar-neutral (`long_gross == short_gross`); `min_short = 100` |

### 4.3 DSR dispersion rule (compute only during authorized validation)

Dispersion = sample standard deviation (`ddof = 1`) of the validation-period annualized net
Sharpes of Configs A, B, C, divided by `sqrt(252)`. RNG-001 and RNG-EntryLogic count toward **N**
but are **excluded from dispersion**. Required artifact: **P13** (Phase 3C only).

### 4.4 Short-side metric roles — do not move the primary gate

| View | `metric_role` |
|---|---|
| Preregistered net model incl. 50 bps/yr borrow financing | `PRIMARY_GATE` |
| Conservative availability / locate / SSR model | `SECONDARY_GATE` / `ECONOMIC_OPERABILITY_GATE` |
| Zero-borrow frictionless short attribution | `DIAGNOSTIC_ONLY` |

### 4.5 Frozen upstream identities

| Artifact | Identity |
|---|---|
| Governing run specification | `RunSpecification_v1.1` · `fd19aef5230bac56bc82be1efb1be55ba3fe5d4f9daae33608f49ebbfd4554c3` |
| Frozen orchestration code | `bb029a96bb0c9e31600bd0b7ab068c31f70bbc7ac23afce0a3ffe0cb4412845b` |
| Collision rule module / ID | `d827cc422b93aef3e89eaac1b95956f520cc78c721e7f6bcb83e3ec7422b0c33` · `MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1` |
| Publication core | `f72902c5aa6db19204658c8487cda53a42a11cb391ec555ba46e0dd365508aff` |
| Canonical merge | `1d6defec7373a32bd213078fa656bd12069a4790a7c5b30fe2418b1ce7e526ef` |
| Development snapshot content | `1c6a5121467ea68a18a0e1b779e7aed10f39b606a2c769517a938b8f6f4a359a` |
| Evaluator binding (RESOLVED) | `c83df63989ab019f216f594ed115ad824f99c42065c31dad67483226088ae1b2` · source commit `d1e7ffc6ef280b69d6244cfbff3bb18c5d412f4b` · 21 modules |
| Evaluator image (OCI **index**) | `sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9` |
| Phase 3A final-correction commit | `f7319de951b6fd7b84112ad2b207d61376399ac1` |
| 3B/C adjudication reference commit | `ea437ce9355650ab907079fea10243db5599a1a7` |

---

## 5. Execution order

Follow these steps in order. Do not start a step before the previous one is complete — the
sequence exists to stop the program jumping ahead to grant readiness with a prerequisite
unsatisfied, which is exactly what D3 denied.

| Step | Action | Actor | Gate to the next step |
|---|---|---|---|
| **1** | **WP-A — finish the physical recovery control.** Owner handwork, not development; the archive is already built and verified. Placement, offline verification from the medium, and custodianship remain. | Owner | §5 verification run **from the medium** returns PASS and is recorded |
| **2** | **Name the operational custodian.** Unblocks all of WP-C and WP-D. Settle the Phase 0 disposition in the same pass. | Owner | A real accountable individual is named in an **operational-custodian appointment record**. If the owner appoints one individual to both roles, the dual appointment is recorded in **both** the §7 recovery-media record and the operational-custodian record. ⚠ Naming the §7 media custodian alone does **not** satisfy this gate. |
| **3** | **Authorize the minimum prerequisite-production block:** WP-B (Req. 7 resolver), WP-C (P6–P9), WP-D (P11), WP-E (P10). **Do not authorize WP-F yet.** | Owner | Written authorization referencing this plan |
| **4** | **Produce and verify P6–P11.** All runtime-produced, identity-bound, hash-bound. Anything not truthfully completable without validation access stays unsatisfied. | Custodian / Infra / Research | Every prerequisite except the authorization event itself is satisfied |
| **5** | **Authorize and build WP-F**, then execute the closed grant-readiness run against the then-current tree. **WP-B must be complete first** — C-R7 cannot pass without it. | Owner authorizes; Research builds | One closed run demonstrating **C1–C10 + C-R7** |
| **6** | **WP-G — D3 resubmission.** Fresh CAS anchor → D3 adjudication → P12 owner grant → durably record the grant → CAS `false → true` at `_rev 0`. | Owner / governance | Grant event durably recorded **before** any credential release |
| **7** | **Phase 3B, then Phase 3C.** Only now. | Research | Validation verdict |

**No execution work may begin outside the actor and authorization boundaries shown above.** Steps
1–3 require owner action; subsequent steps may begin only after their stated authorization gates
are satisfied. This binds whoever performs the work — developer, automation, AI agent, or another
operator. The boundary is the authorization, not the identity of the actor.

Until step 6 completes, the standing state holds: validation partition **closed**, single opening
**UNCONSUMED**, OOS **under DENY**, `validation_authorization` **false** at `_rev 0`.

---

## 6. Relationship to prior plan versions

| Document | Role after v1.3.1 |
|---|---|
| `MR002_Development_Plan_Next_Phases_v1.3.md` | **Current — v1.3.1.** Remaining work only. The file keeps its `v1_3` name; the version is carried in the header, so the approved-document path stays stable across corrections. |
| `MR002_DevPlan_v1_3_ReviewMemo_v1_0.md` | **Review record** — the three accepted execution-exposed inconsistencies (EI-1/2/3) and four record-only execution notes |
| `MR002_Development_Plan_Next_Phases_v1.2.md` | **Superseded** — completion record for Phase 2B; its §10 task list is fully executed; its Phase 3A authorization status was stale on publication |
| `MR002_Development_Plan_Next_Phases_v1.1.1.md` | Superseded (erratum merged) |
| `MR002_Development_Plan_Next_Phases_v1.1.md` | **Reference** for full Phase 3A–8 deliverable prose (A1–A6, §5.3a, §7.6) |
| `MR002_Development_Plan_Next_Phases_v1.0.md` | Historical |

---

## Final instruction

Phase 2B and Phase 3A are **closed**. **Six pre-grant prerequisites (P6–P11) remain, plus the owner
authorization event P12.** WP-A is the remaining owner physical-control action. **Complete only the
work required to reach D3 grant readiness; no additional strategy research or product development
is authorized before the validation decision.**

Each step stops for adjudication; no phase auto-authorizes the next.
