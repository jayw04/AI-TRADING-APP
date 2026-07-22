# MR-002 SPQ-1 Phase 3B/C — Execution Authorization Request

**Type:** request + lineage proof + prerequisite register. **Grants nothing, releases no
credentials, opens no validation or OOS partition, computes no performance
(`validation_authorization = false`).**

**Governing preregistration:** `MR002_ValidationOOS_Preregistration_v1.0.4.json`, commit `4385ec7728a81c0db965e2f44d6017e6116d027c`, content SHA-256 `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c`.

## 1. Phase 3A lineage — INTACT

Phase 3A closed under the two-review-max policy at `f7319de951b6` (Review-2 final
corrections). Every binding recomputes from the committed tree:

- **25/25** Phase-3A artifacts reproduce their manifest SHA-256;
  package file count reconciles (26 files = 25
  bound + 1 self-excluded manifest).
- Governing preregistration v1.0.4 reproduces.
- `SignalDecisionRecord` model module reproduces the identity bound in the run specification
  (a mismatch would fail the run closed).
- **21** evaluator modules: **zero drift**, zero unbound modules.
- Sealed manifest and the countersigned DSR trial ledger (`deda5cec…`, N = 5) reproduce.

## 2. Prerequisites — 2 of 12 blocking conditions satisfied

**Grant readiness: `NOT_READY`.** The unsatisfied blocking prerequisites are:

| ID | Prerequisite | Producer | Status |
|---|---|---|---|
| P3 | Evaluator operational increment (container / dependency / publication wrapper / refusal layer / access-boundary qualification) | RESEARCH (Workstream B) | NOT_AUTHORIZED_TO_START |
| P4 | Consolidated evaluator acceptance submission (EvaluatorQualificationPlan v1.0 SS5) | RESEARCH (Workstream B) | NOT_PRODUCED |
| P5 | Pre-access evaluator binding (EvaluatorQualificationPlan v1.0 SS4) | RESEARCH (Workstream B) | NOT_PRODUCED |
| P6 | ValidationPartitionContentCommitment (runtime instance) | CUSTODIAN | NOT_PRODUCED |
| P7 | ValidationPartitionAccessHistory (runtime instance) | CUSTODIAN | NOT_PRODUCED |
| P8 | ValidationSealVerificationReport (runtime instance) | CUSTODIAN | NOT_PRODUCED |
| P9 | Precommitted value-blind structural manifest for the validation partition | CUSTODIAN (sealing process, before sealing) | NOT_PRODUCED |
| P10 | NumericRuntimeIdentityManifest runtime instance | RESEARCH (run environment) | NOT_PRODUCED |
| P11 | Access-control preconditions in force and snapshotted | CUSTODIAN / INFRASTRUCTURE | NOT_PRODUCED |
| P12 | Owner-signed authorization event + time-bounded credential release | OWNER | NOT_EXECUTED (this is the act being requested) |

The Phase 3A seal artifacts are `SPECIFICATION_TEMPLATE`s: their zero-access values are *required
runtime gate values*, not evidence. Nothing currently proves the validation partition has never been
opened, because the custodian evidence that would prove it does not exist yet.

P13 (DSR trial-dispersion artifact) is deliberately **not** a pre-authorization blocker — it is
produced during Phase 3C from the authorized run — but the DSR gate cannot be evaluated without it.

## 3. What is being requested

One validation execution: Phase 3B (open the validation partition, attach preregistered `t+1`
execution facts under the fail-closed enrichment contract) and Phase 3C (replay Configs A/B/C,
compute only preregistered metrics). Primary gate: **Config B net Sharpe ≥ 0.70** under the governing
conservative-borrow view. Diagnostics may not become substitute success criteria.

**OOS is excluded.** The OOS partition stays sealed under explicit DENY and requires a further,
separate authorization after an accepted validation outcome.

## 4. Decisions requested — three, in order

1. **D1** — accept the lineage proof and the prerequisite register as complete and correct.
   *Authorizes nothing.*
2. **D2** — authorize *production* of the unsatisfied prerequisites
   (P3, P4, P5, P6, P7, P8, P9, P10, P11) by their named producers. P12 is the authorization event
   itself and is *not* part of D2. *Still opens no partition values and computes no performance.*
3. **D3** — grant the Phase 3B/C execution authorization. *Only after every blocking prerequisite is
   satisfied and re-verified; this consumes the single authorized validation opening.*

Taking D3 early would open the partition without the evidence that proves it was never opened
before — which is unrecoverable.

## 5. Boundary

Validation and OOS remain **SEALED AND UNREAD**. No returns, PnL, Sharpe, DSR, ranking, or verdict
exists. This package stops for owner adjudication.
