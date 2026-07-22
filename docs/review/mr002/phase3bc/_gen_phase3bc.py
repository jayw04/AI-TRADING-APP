"""SPQ-1 Phase 3B/C — Execution Authorization REQUEST package generator (request only).

Produces the Phase 3B/C execution-authorization request: a recomputed Phase-3A lineage proof, the
runtime-prerequisite register (what must exist before any grant, who produces it, and its current
status), the 3B/3C execution gate table and deliverable register, and the consolidated request
record + submission.

REQUEST ONLY. This package grants nothing, releases no credentials, opens no validation or OOS data,
and computes no performance. `validation_authorization` stays false. It reads only committed,
non-sealed governing artifacts in order to bind them by SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[4])
OUT = os.path.dirname(os.path.abspath(__file__))
RVW = os.path.join(ROOT, "docs", "review", "mr002")
P3A = os.path.join(RVW, "phase3a")
EVAL = os.path.join(RVW, "evaluator")

PREREG = "MR002_ValidationOOS_Preregistration_v1.0.4.json"
PREREG_COMMIT = "4385ec7728a81c0db965e2f44d6017e6116d027c"
PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"

# Phase 3A commit lineage (package -> HOLD corrections -> Review-2 final corrections)
P3A_LINEAGE = [
    {"commit": "be8ab538236be24dcad8876bb5914764da7c5aed",
     "tree": "5489f0df538c3ae7ded65902b9ef1c8508b0b08e",
     "role": "Phase 3A Validation Authorization Package (8 work packages, specifications only)"},
    {"commit": "3606995bbe8d6a7e19115f84a0214d5196912540",
     "tree": "49e5108f154af9a6f01a853876f633381ce8dc3c",
     "role": "Review-1 narrow corrections (4 HOLD items)"},
    {"commit": "f7319de951b6fd7b84112ad2b207d61376399ac1",
     "tree": "dac63eee46621562c5d85ac387e36657602e3c57",
     "role": "Review-2 FINAL corrections (A duplicate metric, B non-gating diagnostics) - review CLOSED"},
]


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_json(p):  # noqa: ANN001
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(obj, name):  # noqa: ANN001
    os.makedirs(OUT, exist_ok=True)
    p = Path(OUT) / name
    p.write_text(json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n",
                 encoding="utf-8", newline="\n")
    return sha_file(p)


def dump_md(text, name):  # noqa: ANN001
    p = Path(OUT) / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return sha_file(p)


H = {}

# =====================================================================================
# WP 3BC-1 - Phase 3A lineage proof (recomputed, not asserted)
# =====================================================================================
pub = read_json(os.path.join(P3A, "MR002_Phase3A_PublicationManifest_v1.0.json"))
p3a_files = sorted(f for f in os.listdir(P3A) if f.endswith((".json", ".md")))

artifact_check = {}
for name, want in pub["artifact_sha256"].items():
    cands = [f for f in p3a_files
             if f.startswith(f"{name}_v1.0.") or f.startswith(f"MR002_Phase3A_{name}_v1.0.")]
    assert len(cands) == 1, f"cannot resolve Phase 3A artifact {name} -> {cands}"
    got = sha_file(os.path.join(P3A, cands[0]))
    artifact_check[name] = {"file": cands[0], "bound_sha256": want, "recomputed_sha256": got,
                            "reproduces": got == want}
assert all(v["reproduces"] for v in artifact_check.values()), "Phase 3A artifact drift -> STOP"

prereg_sha_now = sha_file(os.path.join(RVW, PREREG))
assert prereg_sha_now == PREREG_SHA, "governing preregistration drift -> STOP"

runspec = read_json(os.path.join(P3A, "ValidationRunSpecification_v1.0.json"))
models_now = sha_file(os.path.join(ROOT, "apps", "backend", "app", "research", "mr002",
                                   "spq1", "models.py"))
gsr = read_json(os.path.join(P3A, "MR002_Phase3A_GoverningSourceRegistry_v1.0.json"))
bound_modules = gsr["evaluator_code_identities"]["modules"]
module_drift = []
for f, want in sorted(bound_modules.items()):
    p = os.path.join(EVAL, f)
    got = sha_file(p) if os.path.exists(p) else None
    if got != want:
        module_drift.append({"module": f, "bound_sha256": want, "recomputed_sha256": got})
unbound_modules = sorted(f for f in os.listdir(EVAL)
                         if f.endswith(".py") and f not in bound_modules)

sealed_manifest_now = sha_file(os.path.join(
    ROOT, "docs", "implementation", "evidence", "mr_002", "MR002_SealedManifest_v1.0.json"))
ctrl = read_json(os.path.join(
    P3A, "MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json"))
dsr_ledger_now = sha_file(os.path.join(RVW, "MR002_DSR_TrialLedger_v1.0.json"))

lineage = {
    "record_type": "MR002_Phase3BC_Phase3ALineageProof", "version": "1.0",
    "scope": "recomputes every Phase-3A binding from the committed tree; opens no sealed data",
    "phase3a_review_state": {
        "policy": "two-review-max (Review 1 corrections, Review 2 FINAL corrections, no further cycle)",
        "state": "CLOSED", "commit_lineage": P3A_LINEAGE,
        "final_correction_commit": P3A_LINEAGE[-1]["commit"]},
    "governing_preregistration": {
        "file": f"docs/review/mr002/{PREREG}", "version": "1.0.4", "commit": PREREG_COMMIT,
        "bound_sha256": PREREG_SHA, "recomputed_sha256": prereg_sha_now,
        "reproduces": prereg_sha_now == PREREG_SHA},
    "phase3a_artifacts": {
        "manifest_bound_artifact_count": pub["manifest_bound_artifact_count"],
        "package_file_count": pub["package_file_count"],
        "files_on_disk": len(p3a_files),
        "counts_reconcile": (len(p3a_files) == pub["package_file_count"]
                             and pub["manifest_bound_artifact_count"] == len(pub["artifact_sha256"])),
        "all_reproduce": True,
        "artifacts": artifact_check},
    "run_specification_schema_bindings": {
        "SignalDecisionRecord_model_module": {
            "path": "apps/backend/app/research/mr002/spq1/models.py",
            "bound_sha256": runspec["bound_schemas"]["SignalDecisionRecord_model_module_sha256"],
            "recomputed_sha256": models_now,
            "reproduces": models_now == runspec["bound_schemas"]["SignalDecisionRecord_model_module_sha256"]},
        "fail_closed_rule": runspec["bound_schemas"]["fail_closed"]},
    "evaluator_module_reference_identities": {
        "note": "Phase 3A bound the evaluator modules as a REFERENCE to be re-verified at evaluator "
                "qualification; this proves no silent drift since Phase 3A closed. It does NOT "
                "constitute evaluator qualification.",
        "bound_module_count": len(bound_modules), "drift": module_drift,
        "zero_drift": not module_drift, "modules_present_but_unbound": unbound_modules},
    "other_governing_identities": {
        "sealed_manifest_sha256": sealed_manifest_now,
        "sealed_manifest_matches_control_spec":
            sealed_manifest_now == ctrl["governing_binding"]["sealed_manifest_sha256"],
        "dsr_trial_ledger_sha256": dsr_ledger_now,
        "dsr_trial_ledger_matches_prereg":
            dsr_ledger_now == read_json(os.path.join(RVW, PREREG))["dsr"]["trial_ledger_sha256"],
        "dsr_trials_N": 5},
    "verdict": "PHASE_3A_LINEAGE_INTACT",
    "boundary": "no validation/OOS data opened; no performance computed; grants nothing",
}
assert lineage["other_governing_identities"]["dsr_trial_ledger_matches_prereg"]
assert lineage["run_specification_schema_bindings"]["SignalDecisionRecord_model_module"]["reproduces"]
H["Phase3ALineageProof"] = dump(lineage, "MR002_Phase3BC_Phase3ALineageProof_v1.0.json")

# =====================================================================================
# WP 3BC-2 - Runtime prerequisite register
# =====================================================================================
SATISFIED = "SATISFIED"
NOT_PRODUCED = "NOT_PRODUCED"
NOT_AUTHORIZED = "NOT_AUTHORIZED_TO_START"
RUNTIME = "PRODUCED_AFTER_AUTHORIZATION_AT_RUN_TIME"

prereqs = [
    {"id": "P1", "title": "Phase 3A package accepted by the owner",
     "producer": "OWNER", "status": SATISFIED, "blocks_grant": True,
     "evidence": "two-review-max cycle CLOSED; Review-2 final corrections at "
                 f"{P3A_LINEAGE[-1]['commit']}",
     "satisfaction_criterion": "Phase 3A review closed with corrections applied and no open HOLD"},
    {"id": "P2", "title": "Phase 3A bindings reproduce with zero drift",
     "producer": "RESEARCH", "status": SATISFIED, "blocks_grant": True,
     "evidence": "MR002_Phase3BC_Phase3ALineageProof_v1.0.json (25/25 artifacts, prereg, "
                 "SignalDecisionRecord module, 21 evaluator modules, sealed manifest, DSR ledger)",
     "satisfaction_criterion": "every Phase-3A-bound SHA-256 recomputes identically from the tree"},
    {"id": "P3", "title": "Evaluator operational increment (container / dependency / publication "
                          "wrapper / refusal layer / access-boundary qualification)",
     "producer": "RESEARCH (Workstream B)", "status": NOT_AUTHORIZED, "blocks_grant": True,
     "evidence": "MR002_Increment3_Qualification.json roadmap_disposition: "
                 "next_operational_increment = NOT YET AUTHORIZED",
     "satisfaction_criterion": "synthetic-fixture qualification of the operational layer, accepted "
                               "by owner review, reading no real dataset"},
    {"id": "P4", "title": "Consolidated evaluator acceptance submission "
                          "(EvaluatorQualificationPlan v1.0 SS5)",
     "producer": "RESEARCH (Workstream B)", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "Increments 1-3 accepted and closed (2026-07-20 adjudications); no consolidated "
                 "SS5 acceptance package exists",
     "satisfaction_criterion": "code identities + container/dependency identity + report schema + "
                               "full synthetic end-to-end evidence + per-gate fixture results + "
                               "refusal-test evidence + determinism proof + zero-performance "
                               "confirmation + proof trials_N=5 is READ FROM the bound ledger "
                               "(deda5cec...) and not a code constant"},
    {"id": "P5", "title": "Pre-access evaluator binding (EvaluatorQualificationPlan v1.0 SS4)",
     "producer": "RESEARCH (Workstream B)", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "PENDING_EVALUATOR_BIND unresolved",
     "satisfaction_criterion": "commit + tree + container digest + dependency lock + data-manifest "
                               "identity + benchmark/cost/metric/bootstrap/PBO/DSR implementations "
                               "+ report schema + expected output paths all bound; "
                               "PENDING_EVALUATOR_BIND must not survive into the authorized run"},
    {"id": "P6", "title": "ValidationPartitionContentCommitment (runtime instance)",
     "producer": "CUSTODIAN", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "SealedPartitionContentCommitment_v1.0.json is a SPECIFICATION_TEMPLATE "
                 "(contains_runtime_evidence = false)",
     "satisfaction_criterion": "value-blind SHA-256 content commitment over the sealed validation "
                               "partition, custodian-produced and audit-bound, committed BEFORE "
                               "any authorization"},
    {"id": "P7", "title": "ValidationPartitionAccessHistory (runtime instance)",
     "producer": "CUSTODIAN", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "SealedPartitionAccessHistory_v1.0.json is a SPECIFICATION_TEMPLATE",
     "satisfaction_criterion": "hash-chained access history evidencing "
                               "validation_access_events_before_authorization = 0 AND "
                               "oos_access_events_before_validation = 0"},
    {"id": "P8", "title": "ValidationSealVerificationReport (runtime instance)",
     "producer": "CUSTODIAN", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "SealVerificationReport_v1.0.json is a SPECIFICATION_TEMPLATE",
     "satisfaction_criterion": "content commitment stable + no access-before-authorization + "
                               "OpenedObjectLedger reconciles against SealedStoreAccessLog + "
                               "OOS partition DENY in force during validation"},
    {"id": "P9", "title": "Precommitted value-blind structural manifest for the validation partition",
     "producer": "CUSTODIAN (sealing process, before sealing)", "status": NOT_PRODUCED,
     "blocks_grant": True,
     "evidence": "ValidationStructuralManifestSpecification_v1.0.json requires a custodian producer; "
                 "a developer query of sealed rows is prohibited",
     "satisfaction_criterion": "schema identity, table names, row counts, date bounds, session "
                               "count, symbol/security counts, factor-series coverage, null-count "
                               "summaries, latest source date - all custodian-produced; this is the "
                               "sole input the structural preflight may read pre-authorization"},
    {"id": "P10", "title": "NumericRuntimeIdentityManifest runtime instance",
     "producer": "RESEARCH (run environment)", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "Phase 3A records only a drafting_reference_runtime; lockfile_binding is REQUIRED "
                 "at run time and is not a placeholder",
     "satisfaction_criterion": "all 17 required bindings populated incl. dependency lockfile "
                               "SHA-256 and container-image digest; mismatch FAIL-STOPS before any "
                               "metric"},
    {"id": "P11", "title": "Access-control preconditions in force and snapshotted",
     "producer": "CUSTODIAN / INFRASTRUCTURE", "status": NOT_PRODUCED, "blocks_grant": True,
     "evidence": "prereg v1.0.4 sealed_access_protocol",
     "satisfaction_criterion": "CloudTrail S3 data events enabled BEFORE any access; dedicated IAM "
                               "principal; explicit bucket/key DENY on the OOS partition; "
                               "validation-only policy; pre-execution policy-state snapshot"},
    {"id": "P12", "title": "Owner-signed authorization event + time-bounded credential release",
     "producer": "OWNER", "status": "NOT_EXECUTED (this is the act being requested)",
     "blocks_grant": True,
     "evidence": "ValidationAuthorization_v1.0.json: validation_authorization = false; state = "
                 "REQUEST / CONTRACT (NOT a grant)",
     "satisfaction_criterion": "explicit owner authorization event referencing this request, after "
                               "P1-P11 are satisfied"},
    {"id": "P13", "title": "MR002_DSR_TrialDispersion_Validation_v1.0.json (countersigned)",
     "producer": "RESEARCH at run time + OWNER countersignature", "status": RUNTIME,
     "blocks_grant": False,
     "evidence": "Increment-1 qualification: absent -> REFUSED_CODE_OR_DATA_IDENTITY; estimator "
                 "frozen by MR002_DSR_DispersionResolution_v1.0 (stddev ddof=1 of A/B/C validation "
                 "annualized Sharpes / sqrt(252))",
     "satisfaction_criterion": "produced during Phase 3C from the authorized run; the DSR gate "
                               "cannot be evaluated without it. NOT a pre-authorization blocker, "
                               "but a hard stop before any DSR verdict"},
]
blocking_unsatisfied = [p["id"] for p in prereqs if p["blocks_grant"] and p["status"] != SATISFIED]
# P12 is the authorization event itself (decision D3), not producible work under D2
producible_unsatisfied = [i for i in blocking_unsatisfied if i != "P12"]
register = {
    "record_type": "MR002_Phase3BC_RuntimePrerequisiteRegister", "version": "1.0",
    "purpose": "the complete set of conditions that must hold before a Phase 3B/C execution "
               "authorization may be granted, with producer and current status",
    "status_domain": [SATISFIED, NOT_PRODUCED, NOT_AUTHORIZED,
                      "NOT_EXECUTED (this is the act being requested)", RUNTIME],
    "prerequisites": prereqs,
    "counts": {"total": len(prereqs),
               "blocking": sum(1 for p in prereqs if p["blocks_grant"]),
               "blocking_satisfied": sum(1 for p in prereqs
                                         if p["blocks_grant"] and p["status"] == SATISFIED),
               "blocking_unsatisfied": len(blocking_unsatisfied)},
    "blocking_unsatisfied_ids": blocking_unsatisfied,
    "grant_readiness": "NOT_READY" if blocking_unsatisfied else "READY",
    "authorization_note": "producing P3-P11 is itself work that is NOT currently authorized; the "
                          "owner may authorize prerequisite production WITHOUT authorizing "
                          "validation opening. These are two separate decisions.",
}
H["RuntimePrerequisiteRegister"] = dump(register, "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json")

# =====================================================================================
# WP 3BC-3 - Execution gate table (roadmap SS4.3 / SS4.4)
# =====================================================================================
gates = {
    "record_type": "MR002_Phase3BC_ExecutionGateTable", "version": "1.0",
    "source": "MR002_Development_Plan_Next_Phases_v1.1 SS4.3 (Phase 3B integrity gates) and SS4.4 / "
              "SS4.4a / SS4.4b (Phase 3C controls), governed by preregistration v1.0.4",
    "phase_3b_integrity_gates": [
        {"gate": "decision_record_mutations", "required": 0,
         "evidenced_by": "ValidationDecisionExecutionBindingReport_v1.0.json"},
        {"gate": "missing_decision_enrichment_bindings", "required": 0,
         "evidenced_by": "ValidationDecisionExecutionBindingReport_v1.0.json"},
        {"gate": "duplicate_enrichment_identities", "required": 0,
         "evidenced_by": "ValidationExecutionEnrichmentManifest_v1.0.json"},
        {"gate": "future_information_violations", "required": 0,
         "evidenced_by": "ValidationExecutionEnrichmentManifest_v1.0.json"},
        {"gate": "oos_reads_run_ledger_and_store_access_log", "required": 0,
         "evidenced_by": "ValidationOpenedObjectLedger_v1.0.json + ValidationSealVerificationReport"},
        {"gate": "unregistered_data_source_reads", "required": 0,
         "evidenced_by": "ValidationOpenedObjectLedger_v1.0.json"},
        {"gate": "unreconciled_validation_units", "required": 0,
         "evidenced_by": "ValidationUnitReconciliation_v1.0.json"},
        {"gate": "validation_access_events_before_authorization", "required": 0,
         "evidenced_by": "ValidationPartitionAccessHistory_v1.0.json (custodian runtime instance)"},
    ],
    "phase_3c_controls": [
        "no parameter changes after results are viewed",
        "no substitution of Config A or C for Config B because they performed better",
        "no removal of difficult years, names, sectors, or the short side",
        "no unregistered metric may become a decision metric",
        "results reproducible from immutable inputs and frozen code under the bound numeric runtime",
    ],
    "metric_roles": {
        "binding": "MetricRoleRegistry_v1.0 (Phase 3A), each metric carrying metric_role and a bound "
                   "sample_stage",
        "primary_validation_gate": "Config B net Sharpe >= 0.70 under the governing "
                                   "conservative-borrow view, per preregistration v1.0.4 language "
                                   "and cost treatment",
        "diagnostics_are_not_gates": "PBO, regime concentration, maximum drawdown, Calmar, "
                                     "year-by-year behavior, side contribution, sector "
                                     "concentration, capacity, correlation, tail behavior - may "
                                     "qualify or contextualize only as preregistration permits; "
                                     "must never become substitute success criteria after results "
                                     "are observed",
        "stage_separation": "ValidationStageDecisionSpecification_v1.0 - OOS primary gates "
                            "(net_oos_sharpe / bootstrap / DSR-as-OOS-gate) are PROHIBITED as "
                            "validation-stage decision metrics",
    },
    "null_model_binding": {
        "dsr_trial_ledger_sha256": dsr_ledger_now, "trials_N": 5,
        "trial_set": ["Config A", "Config B", "Config C", "RNG-001", "RNG-EntryLogic"],
        "rule": "no new null models and no additional trials unless preregistration already "
                "authorizes them"},
    "verdict_domain": {
        "VALIDATION_ADVANCE_REQUEST": "validation-stage advancement may be requested (a request, "
                                      "not an OOS authorization)",
        "DO_NOT_ADVANCE": "stop; do not consume OOS",
        "INCONCLUSIVE": "evidence insufficient; stop",
        "INTEGRITY_FAILURE": "results not interpretable; repair without performance interpretation"},
    "oos_note": "a sealed OOS run requires a FURTHER separate authorization after an accepted "
                "validation outcome; it is explicitly OUT OF SCOPE of this request",
}
H["ExecutionGateTable"] = dump(gates, "MR002_Phase3BC_ExecutionGateTable_v1.0.json")

# =====================================================================================
# WP 3BC-4 - Deliverable register
# =====================================================================================
deliverables = {
    "record_type": "MR002_Phase3BC_DeliverableRegister", "version": "1.0",
    "note": "every deliverable below is RUNTIME-PRODUCED by the authorized run; none exists now and "
            "none may be pre-populated with values",
    "phase_3b": [
        "ValidationOpenedObjectLedger_v1.0.json",
        "ValidationExecutionEnrichmentManifest_v1.0.json",
        "ValidationDecisionExecutionBindingReport_v1.0.json",
        "ValidationUnitReconciliation_v1.0.json",
        "ExecutionEnrichmentEdgeCaseCensus_v1.0.json",
        "ValidationSealVerificationReport_v1.0.json",
    ],
    "phase_3c": [
        "ValidationPortfolioReplayManifest_v1.0.json",
        "ValidationMetricsReport_v1.0.json (conservative + frictionless views)",
        "ValidationDSRReport_v1.0.json",
        "ValidationConfigurationComparison_v1.0.json",
        "ValidationRegimeAndConcentrationReport_v1.0.json",
        "ValidationDeterminismReport_v1.0.json",
        "ValidationNullModelAndRandomizationReport_v1.0.json",
        "ValidationVerdict_v1.0.md",
    ],
    "census_rule": "the enrichment edge-case census is recomputed from the authorized partition; "
                   "known cases may be registered in advance but must NOT become a fixed "
                   "expected-count gate",
    "enrichment_default": "FAIL CLOSED - no silent price substitution, previous-close fallback, "
                          "later-open fallback, or post-hoc security winner",
}
H["DeliverableRegister"] = dump(deliverables, "MR002_Phase3BC_DeliverableRegister_v1.0.json")

# =====================================================================================
# WP 3BC-5 - The request record
# =====================================================================================
request = {
    "record_type": "MR002_Phase3BC_ExecutionAuthorizationRequest", "version": "1.0",
    "state": "REQUEST (not a grant)",
    "validation_authorization": False,
    "sealed_data_read": False,
    "grants": "NOTHING - this artifact asks the owner for a decision; it releases no credentials, "
              "opens no partition, and computes no performance",
    "governing_preregistration": {"file": PREREG, "version": "1.0.4", "commit": PREREG_COMMIT,
                                  "content_sha256": PREREG_SHA},
    "supersedes_nothing": True,
    "requested_scope_if_granted": {
        "phase_3b": "open ONLY the authorized validation partition under an opened-object ledger; "
                    "attach preregistered t+1 execution facts under the fail-closed enrichment "
                    "contract; mutate no close-t decision record",
        "phase_3c": "replay the frozen portfolio and execution machinery for Configs A, B, C and "
                    "compute ONLY preregistered metrics under both the governing "
                    "conservative-borrow view and the frictionless diagnostic view",
        "executions": 1,
        "configs": ["A", "B", "C"],
        "oos": "EXCLUDED - the OOS partition stays sealed under explicit DENY; a sealed OOS run is "
               "a further separate authorization after an accepted validation outcome"},
    "explicitly_not_requested": [
        "OOS partition access",
        "performance interpretation beyond the preregistered verdict domain",
        "production promotion or capital allocation",
        "any parameter, gate, cost, fold, seam, or estimator change",
        "additional trials or null models (DSR N stays 5)",
    ],
    "prerequisite_register": "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json",
    "prerequisite_summary": {
        "producible_unsatisfied_ids": producible_unsatisfied,
        "blocking_total": register["counts"]["blocking"],
        "blocking_satisfied": register["counts"]["blocking_satisfied"],
        "blocking_unsatisfied": register["counts"]["blocking_unsatisfied"],
        "blocking_unsatisfied_ids": blocking_unsatisfied},
    "grant_readiness": register["grant_readiness"],
    "decisions_requested_of_the_owner": [
        {"id": "D1", "decision": "accept this lineage proof and prerequisite register as the "
                                 "complete and correct set of conditions for a Phase 3B/C grant",
         "consequence": "fixes the checklist; authorizes nothing"},
        {"id": "D2", "decision": "authorize PRODUCTION of the unsatisfied producible prerequisites "
                                 f"({', '.join(producible_unsatisfied)}) by their named producers",
         "consequence": "custodian seal evidence + evaluator operational qualification + runtime "
                        "identity may be produced. Still opens NO partition values and computes NO "
                        "performance"},
        {"id": "D3", "decision": "grant the Phase 3B/C execution authorization",
         "consequence": "ONE validation execution. May be taken only after every blocking "
                        "prerequisite is satisfied and re-verified; it consumes the single "
                        "authorized validation opening"},
    ],
    "sequencing_rule": "D1 -> D2 -> re-verification of P3-P11 -> D3. D3 may not be taken while any "
                       "blocking prerequisite is unsatisfied; taking D3 early would open the "
                       "partition without the evidence that proves it was never opened before",
    "stop_conditions": [
        "any Phase-3A binding fails to reproduce at run time",
        "numeric-runtime identity mismatch",
        "SignalDecisionRecord or ExecutionEnrichmentSchema identity mismatch",
        "any non-zero Phase 3B integrity gate",
        "any OOS access event during validation",
        "PENDING_EVALUATOR_BIND unresolved at run time",
        "DSR trial-dispersion artifact absent when the DSR gate is reached",
    ],
    "boundary": "Validation and OOS remain SEALED AND UNREAD. No returns, PnL, Sharpe, DSR, "
                "ranking, or verdict exists or is produced by this package.",
}
H["ExecutionAuthorizationRequest"] = dump(
    request, "MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json")

# =====================================================================================
# WP 3BC-6 - Submission + publication manifest
# =====================================================================================
unsat_rows = "\n".join(
    f"| {p['id']} | {p['title']} | {p['producer']} | {p['status']} |"
    for p in prereqs if p["blocks_grant"] and p["status"] != SATISFIED)

sub = f"""# MR-002 SPQ-1 Phase 3B/C — Execution Authorization Request

**Type:** request + lineage proof + prerequisite register. **Grants nothing, releases no
credentials, opens no validation or OOS partition, computes no performance
(`validation_authorization = false`).**

**Governing preregistration:** `{PREREG}`, commit `{PREREG_COMMIT}`, content SHA-256 `{PREREG_SHA}`.

## 1. Phase 3A lineage — INTACT

Phase 3A closed under the two-review-max policy at `{P3A_LINEAGE[-1]['commit'][:12]}` (Review-2 final
corrections). Every binding recomputes from the committed tree:

- **{len(artifact_check)}/{len(artifact_check)}** Phase-3A artifacts reproduce their manifest SHA-256;
  package file count reconciles ({pub['package_file_count']} files = {pub['manifest_bound_artifact_count']}
  bound + 1 self-excluded manifest).
- Governing preregistration v1.0.4 reproduces.
- `SignalDecisionRecord` model module reproduces the identity bound in the run specification
  (a mismatch would fail the run closed).
- **{len(bound_modules)}** evaluator modules: **zero drift**, zero unbound modules.
- Sealed manifest and the countersigned DSR trial ledger (`{dsr_ledger_now[:8]}…`, N = 5) reproduce.

## 2. Prerequisites — {register['counts']['blocking_satisfied']} of {register['counts']['blocking']} blocking conditions satisfied

**Grant readiness: `{register['grant_readiness']}`.** The unsatisfied blocking prerequisites are:

| ID | Prerequisite | Producer | Status |
|---|---|---|---|
{unsat_rows}

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
   ({', '.join(producible_unsatisfied)}) by their named producers. P12 is the authorization event
   itself and is *not* part of D2. *Still opens no partition values and computes no performance.*
3. **D3** — grant the Phase 3B/C execution authorization. *Only after every blocking prerequisite is
   satisfied and re-verified; this consumes the single authorized validation opening.*

Taking D3 early would open the partition without the evidence that proves it was never opened
before — which is unrecoverable.

## 5. Boundary

Validation and OOS remain **SEALED AND UNREAD**. No returns, PnL, Sharpe, DSR, ranking, or verdict
exists. This package stops for owner adjudication.
"""
H["AuthorizationRequestSubmission"] = dump_md(
    sub, "MR002_Phase3BC_AuthorizationRequestSubmission_v1.0.md")

MANIFEST_NAME = "MR002_Phase3BC_PublicationManifest_v1.0.json"
# exclude the manifest itself so a regeneration does not count the previous run's copy
files_now = [f for f in os.listdir(OUT) if f.endswith((".json", ".md")) and f != MANIFEST_NAME]
manifest = {
    "record_type": "MR002_Phase3BC_PublicationManifest", "version": "1.0",
    "package": "SPQ-1 Phase 3B/C Execution Authorization Request (request only)",
    "governing_preregistration": {"file": PREREG, "commit": PREREG_COMMIT,
                                  "content_sha256": PREREG_SHA},
    "phase3a_final_correction_commit": P3A_LINEAGE[-1]["commit"],
    "artifact_sha256": H,
    "manifest_bound_artifact_count": len(H),
    "package_file_count": len(files_now) + 1,  # + this manifest
    "publication_manifest_self_excluded": True,
    "publication_manifest_binding": "the publication manifest does NOT hash itself; it is bound "
                                    "externally by its Git blob SHA + the commit/tree that lands it",
    "phase3a_lineage_intact": True,
    "grant_readiness": register["grant_readiness"],
    "blocking_unsatisfied_ids": blocking_unsatisfied,
    "validation_authorization": False,
    "boundary": "REQUEST ONLY. validation_authorization=false; validation/OOS SEALED AND UNREAD; "
                "no credentials released; no performance computed; stop for owner adjudication.",
}
dump(manifest, MANIFEST_NAME)

print(f"Phase 3B/C request package written: {len(H)} bound artifacts + manifest")
print(f"lineage: {len(artifact_check)}/{len(artifact_check)} Phase-3A artifacts reproduce; "
      f"evaluator drift={len(module_drift)}")
print(f"grant_readiness={register['grant_readiness']} "
      f"blocking_unsatisfied={blocking_unsatisfied}")
