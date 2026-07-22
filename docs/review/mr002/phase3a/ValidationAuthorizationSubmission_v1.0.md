# MR-002 SPQ-1 Phase 3A — Validation Authorization Submission

**Type:** specifications / manifests / schemas / diff-proofs only. **Opens no validation or OOS data; computes no performance; releases no credentials; grants no authorization (`validation_authorization = false`).**

**Governing preregistration:** `MR002_ValidationOOS_Preregistration_v1.0.4`, commit `4385ec7728a81c0db965e2f44d6017e6116d027c`, content SHA-256 `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c`.

## Work packages delivered

- **3A-1 Governing-source extraction** — `GoverningSourceRegistry` + `PregistrationDiffProof`: every roadmap-bound value reproduces from v1.0.4 (windows, folds, seams, primary gate net Sharpe >= 0.70, cost/exposure model, stationary Politis-Romano bootstrap L5+L10/10000/seed20260711, DSR N=5). Moving-block/L21/2000/seed42 confirmed absent.
- **3A-2 Degrees-of-freedom attestation** — every change from prereg v1.0.3 through Phase 2B closure + the v1.0.4 bootstrap correction classified INTEGRITY/EVIDENCE/GOVERNANCE_ONLY; `SIGNAL_OR_TRIAL_AFFECTING = 0`; DSR N remains 5.
- **3A-3 Sealed-partition control** — control spec + content-commitment + access-history + seal-verification (`OpenedObjectLedger` per-run AND `SealedStoreAccessLog` program-history; access-before-authorization = 0; metadata only, no partition values).
- **3A-4 Short implementation contract** — PRIMARY (preregistered net-with-borrow-cost) vs SECONDARY (conservative availability/locate/SSR) vs DIAGNOSTIC (frictionless); rules classified OBSERVED/RECONSTRUCTED/CONSERVATIVE_PROXY/UNOBSERVABLE; no manufactured locate data; primary gate unchanged.
- **3A-5 Enrichment contract** — immutable SignalDecisionRecord -> ExecutionEnrichedCandidateRecord schema, fail-closed edge-case spec, and a SEPARATE `EXECUTION_ENRICHMENT_*` code namespace.
- **3A-6 Metrics + OOS-consumption** — `MetricRoleRegistry` (primary/secondary/diagnostic/integrity, each with a bound `sample_stage`), `ValidationStageDecisionSpecification` (validation advancement rule SEPARATE from OOS gates; OOS-only metrics prohibited during validation; verdicts VALIDATION_ADVANCE_REQUEST / DO_NOT_ADVANCE / INCONCLUSIVE / INTEGRITY_FAILURE), metric spec, OOS-consumption protocol (stages O1-O5), null-model spec (binds the 5-trial ledger + dispersion rule; the dispersion artifact is produced at validation run time, not Phase 3A).
- **3A-7 Runtime + structural-preflight** — numeric-runtime identity manifest (versions, BLAS/LAPACK, thread vars, seeds, lockfile/container required at run time), structural-manifest spec (custodian, value-blind), and a preflight that operates only from precommitted metadata (`STRUCTURAL_PREFLIGHT`, never `PERFORMANCE_OBSERVATION`; direct sealed-row reads = 0).
- **3A-8 Consolidated authorization** — `ValidationAuthorization` (REQUEST/CONTRACT, not a grant) + `ValidationRunSpecification` + `ValidationInputIdentityManifest` + `ValidationCostExecutionSpecification` + this submission, all hash-bound in the publication manifest.

## Phase 3A HOLD corrections applied

1. `ValidationStageDecisionSpecification` added; `sample_stage` on every metric; OOS primary gates (net_oos_sharpe/bootstrap/DSR) prohibited during validation.
2. Run spec now binds `ExecutionEnrichmentSchema` (5b2480c1...) AND the governing SignalDecisionRecord schema (49c0e550...), fail-closed on either mismatch; runtime-critical artifacts bound directly.
3. Seal artifacts marked `artifact_kind=SPECIFICATION_TEMPLATE`, `contains_runtime_evidence=false`, `runtime_instance_required_before_authorization=true`; zero-access values are REQUIRED RUNTIME GATE VALUES (reserved runtime-evidence names for the validation/OOS instances).
4. Count reconciliation: **package_file_count = 26, manifest_bound_artifact_count = 25, publication_manifest_self_excluded = true**; the manifest is bound externally by its Git blob/commit/tree (in the correction commit).

## Boundary

Validation/OOS SEALED AND UNREAD. No returns, PnL, Sharpe, DSR, ranking, or verdict. Stops for review before any validation access.
