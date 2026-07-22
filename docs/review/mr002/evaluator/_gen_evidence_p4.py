"""MR-002 prerequisite P4 — EvaluatorQualificationPlan SS5 acceptance submission generator.

Two products:

  1. `MR002_P3_AcceptanceRecord_v1.0.json` — an INDEPENDENT re-verification of the P3 evidence. It
     recomputes every claim from the COMMITTED GIT OBJECTS rather than trusting the P3 submission's
     own assertions, and binds the eight items the adjudication requires.
  2. `MR002_EvaluatorAcceptanceSubmission_v1.0.json` — the consolidated SS5 return across
     Increments 1-4.

Boundary (D2 + the P3 adjudication): this does NOT begin P5 qualification, resolve the evaluator
binding, create P10, access validation/OOS values, compute performance, or modify the preregistered
acceptance standard. It does not mutate the CAS anchor and contains no grant-capable field. The
status transition it proposes takes effect on OWNER adjudication of P4, not on this file's existence.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

import mr002_valoos_access_boundary as AB
import mr002_valoos_code_identity as CI
import mr002_valoos_gates as G
import mr002_valoos_identity as GOV
import mr002_valoos_registry as REG
import mr002_valoos_runtime as RT

HERE = os.path.abspath(os.path.dirname(__file__))
RVW = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(RVW, "..", "..", ".."))
REL = "docs/review/mr002/evaluator"
P3BC = os.path.join(RVW, "phase3bc")
STATE_PATH = os.path.join(P3BC, "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")

P3_COMMITS = {"increment": "9ecae4ee3f6c5e41753fd7871a8e4526fe3abc3d",
              "finding": "c726ede3adeff2e1dd999b37353cda8b80675b9a"}
REQUEST_COMMIT = "ea437ce9355650ab907079fea10243db5599a1a7"
ADJUDICATION_COMMIT = "953bda934fbf8619cbcfed28ed09ec8e1a0bc75d"

P3_MODULES = ("mr002_valoos_runtime.py", "mr002_valoos_code_identity.py",
              "mr002_valoos_access_boundary.py", "mr002_valoos_publication.py")
P3_EVIDENCE = ("MR002_Increment4_Qualification.json", "MR002_Increment4_AccessBoundaryReport.json",
               "MR002_Increment4_TestLog.txt", "test_increment4.py", "_gen_evidence_p4.py")


def _git(*args) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout


def _git_bytes(*args) -> bytes:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True,
                          check=True).stdout


def sha_committed(commit: str, relpath: str) -> str:
    """SHA-256 of the file as COMMITTED — the authoritative identity, not the working copy."""
    return hashlib.sha256(_git_bytes("show", f"{commit}:{relpath}")).hexdigest()


def sha_worktree(name: str) -> str:
    with open(os.path.join(HERE, name), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def canonical_sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


def load(name: str) -> dict:
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


findings: list = []


def check(check_id: str, description: str, passed: bool, detail=None) -> bool:
    findings.append({"check": check_id, "description": description,
                     "result": "PASS" if passed else "FAIL", "detail": detail})
    return passed


# =====================================================================================
# V1-V3 — the P3 evidence exists as committed objects and its digests reproduce
# =====================================================================================
for label, commit in P3_COMMITS.items():
    check(f"V1.{label}", f"commit {commit[:7]} exists and is an ancestor of HEAD",
          _git("merge-base", "--is-ancestor", commit, "HEAD") == "")

tip = P3_COMMITS["finding"]
committed_modules = {m: sha_committed(tip, f"{REL}/{m}") for m in P3_MODULES}
worktree_modules = {m: sha_worktree(m) for m in P3_MODULES}
check("V2", "the four P3 modules' committed digests equal the working-tree digests",
      committed_modules == worktree_modules,
      {m: {"committed": committed_modules[m], "worktree": worktree_modules[m]}
       for m in P3_MODULES if committed_modules[m] != worktree_modules[m]} or None)

inc4 = load("MR002_Increment4_Qualification.json")
claimed = inc4["source_hashes"]
check("V3", "digests claimed by the P3 qualification record reproduce independently",
      all(claimed.get(m) == committed_modules[m] for m in P3_MODULES),
      {m: {"claimed": claimed.get(m), "recomputed": committed_modules[m]}
       for m in P3_MODULES if claimed.get(m) != committed_modules[m]} or None)

# =====================================================================================
# V4 — the zero-read denial chain, RE-DERIVED rather than read out of the P3 report
# =====================================================================================
state = AB.load_authorization_state(STATE_PATH)
registered = {AB.SYNTHETIC: {"synthetic/p4_fixture"},
              AB.VALIDATION: {"validation/registered_object_placeholder_identity"},
              AB.OOS: {"oos/registered_object_placeholder_identity"}}
boundary = AB.AccessBoundary(
    authorization_state=state, registered_objects=registered,
    expected_identities={"prerequisite_digest": state["bound_identities"]["prerequisite_digest"]},
    expected_rev=0)
denials = []
for partition, obj in ((AB.VALIDATION, "validation/registered_object_placeholder_identity"),
                       (AB.OOS, "oos/registered_object_placeholder_identity"),
                       (AB.VALIDATION, "validation/unregistered_identity"),
                       (AB.SYNTHETIC, "synthetic/unregistered_identity")):
    try:
        boundary.open_object(partition, obj)
        denials.append({"partition": partition, "refused": False})
    except AB.AccessBoundaryViolation as exc:
        denials.append({"partition": partition, "refused": True, "reason": str(exc).split(":")[3]})
rederived = boundary.boundary_report()
check("V4", "denial chain re-derives: 4 refusals, zero sealed reads, chain verifies",
      all(d["refused"] for d in denials) and rederived["counts"]["sealed_reads"] == 0
      and rederived["chain_verifies"] is True, rederived["counts"])

# stale-digest enforcement re-proved independently of the P3 test suite
stale = AB.AccessBoundary(authorization_state=dict(state, validation_authorization=True),
                          registered_objects=registered,
                          expected_identities={"prerequisite_digest": "STALE"}, expected_rev=0)
try:
    stale.open_object(AB.VALIDATION, "validation/registered_object_placeholder_identity")
    stale_blocks = False
except AB.AccessBoundaryViolation as exc:
    stale_blocks = "bound_identity_mismatch:prerequisite_digest" in str(exc)
check("V5", "a stale prerequisite digest blocks validation even when the flag reads true",
      stale_blocks)

# =====================================================================================
# V6-V7 — P10 and PENDING_EVALUATOR_BIND remain unsatisfied / unresolved
# =====================================================================================
completeness = RT.manifest_completeness(RT.capture_runtime())
check("V6", "the workstation runtime is still NOT a bound runtime instance (P10 unsatisfied)",
      completeness["is_runtime_instance"] is False, completeness["missing"])

evaluator_inventory = CI.module_digests(HERE)
self_check = CI.verify_code_identity(
    HERE, {"commit": "PENDING_EVALUATOR_BIND", "tree": "PENDING_EVALUATOR_BIND",
           "container_image_digest": "PENDING_EVALUATOR_BIND", "modules": evaluator_inventory})
unresolved = sorted(p["field"] for p in self_check["problems"]
                    if p["kind"] == "binding_field_unresolved")
check("V7", "commit/tree/container remain PENDING_EVALUATOR_BIND (P5 not begun)",
      unresolved == ["commit", "container_image_digest", "tree"], unresolved)

# =====================================================================================
# V8 — the sealed packages were not mutated
# =====================================================================================
untouched_since_adjudication = _git("diff", "--name-only", ADJUDICATION_COMMIT, "HEAD", "--",
                                    "docs/review/mr002/phase3a",
                                    "docs/review/mr002/phase3bc").strip()
check("V8", "Phase 3A and the adjudication packages are unmodified since the adjudication commit",
      untouched_since_adjudication == "", untouched_since_adjudication or None)

state_sha_now = hashlib.sha256(_git_bytes("show", "HEAD:docs/review/mr002/phase3bc/"
                                                  "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")
                               ).hexdigest()
state_sha_at_adjudication = sha_committed(
    ADJUDICATION_COMMIT,
    "docs/review/mr002/phase3bc/MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")
check("V9", "the CAS anchor is byte-identical to its adjudicated form",
      state_sha_now == state_sha_at_adjudication)
check("V10", "the CAS anchor still records validation_authorization=false at _rev 0",
      state["validation_authorization"] is False and state["_rev"] == 0)

# =====================================================================================
# V11 — the SS6 inventory finding, derived mechanically (never a hard-coded count)
# =====================================================================================
gsr = json.loads(_git_bytes("show", "HEAD:docs/review/mr002/phase3a/"
                                    "MR002_Phase3A_GoverningSourceRegistry_v1.0.json")
                 .decode("utf-8"))
phase3a_bound = gsr["evaluator_code_identities"]["modules"]

# Phase 3A bound EVERY .py in the directory (tests and generators included). The SS4 module rule
# excludes tests and generators. Comparing the two rules directly is not like-for-like, so both
# inventories are derived here and the drift check is made against Phase 3A's OWN rule.
all_py = {f: sha_worktree(f) for f in sorted(os.listdir(HERE)) if f.endswith(".py")}
drift = {m: {"bound": s, "now": all_py.get(m)}
         for m, s in phase3a_bound.items() if all_py.get(m) != s}
newly_present = sorted(set(all_py) - set(phase3a_bound))
phase3a_under_section4_rule = sorted(
    m for m in phase3a_bound if not m.startswith(("test_", "_gen_")))
check("V11", "no Phase-3A-bound evaluator file drifted (compared under Phase 3A's own rule)",
      not drift, drift or None)
check("V11b", "the SS4 inventory is derived mechanically and is NOT the 25 asserted in the P3 "
              "submission",
      len(evaluator_inventory) == len(phase3a_under_section4_rule) + len(P3_MODULES),
      {"section4_now": len(evaluator_inventory),
       "section4_at_phase3a": len(phase3a_under_section4_rule),
       "new_modules": len(P3_MODULES)})

# =====================================================================================
# V12-V14 — SS5 content: gates, refusals, determinism, N=5 provenance
# =====================================================================================
canonical = load("MR002_Increment1_CanonicalReport.json")
gate_results = {g["gate_id"]: g for g in canonical["gate_results"]}
missing_gates = sorted(set(REG.REQUIRED_GATES) - set(gate_results))
check("V12", "every required gate has a synthetic-fixture result in the canonical report",
      not missing_gates, missing_gates or None)
diagnostics = {d["diag_id"]: d for d in canonical["diagnostics"]}
missing_diags = sorted(set(REG.REQUIRED_DIAGNOSTICS) - set(diagnostics))
check("V13", "every required diagnostic is present and classified non-gating",
      not missing_diags and all(d["classification"] != G.GATE for d in diagnostics.values()),
      missing_diags or None)

gov = GOV.load_governing_identity(RVW)
n_from_ledger = gov["dsr_trials_N"]
tampered = json.loads(_git_bytes("show", "HEAD:docs/review/mr002/"
                                         "MR002_DSR_TrialLedger_v1.0.json").decode("utf-8"))
tampered["trials_N"] = 4
try:
    GOV._validate_semantics(
        json.loads(_git_bytes("show", "HEAD:docs/review/mr002/"
                                      "MR002_ValidationOOS_Preregistration_v1.0.4.json")
                   .decode("utf-8")),
        tampered,
        json.loads(_git_bytes("show", "HEAD:docs/review/mr002/MR002_DSR_Resolution_v1.0.json")
                   .decode("utf-8")),
        json.loads(_git_bytes("show", "HEAD:docs/review/mr002/"
                                      "MR002_ValidationOOS_CorrectionRecord_v1.0.4.json")
                   .decode("utf-8")),
        json.loads(_git_bytes("show", "HEAD:docs/review/mr002/"
                                      "MR002_DSR_DispersionResolution_v1.0.json").decode("utf-8")))
    n_refuses_tamper = False
except GOV.RefusedIdentity:
    n_refuses_tamper = True
check("V14", "trials_N=5 is read from the countersigned ledger and a tampered N fails closed",
      n_from_ledger == 5 and n_refuses_tamper)

all_pass = all(f["result"] == "PASS" for f in findings)

# =====================================================================================
# product 1 — the P3 acceptance record
# =====================================================================================
register = json.loads(_git_bytes(
    "show", "HEAD:docs/review/mr002/phase3bc/"
            "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json").decode("utf-8"))
current_statuses = {p["id"]: p["status"] for p in register["prerequisites"]}
current_digest = canonical_sha(current_statuses)
prospective_statuses = dict(current_statuses, P3="SATISFIED")
prospective_digest = canonical_sha(prospective_statuses)

acceptance = {
    "record_type": "MR002_P3_AcceptanceRecord", "version": "1.0",
    "prerequisite": "P3 (evaluator operational increment)",
    "produced_under": "owner adjudication 2026-07-22 (D2 AUTHORIZED WITH RESTRICTIONS) and the P3 "
                      "adjudication authorizing P4 only",
    "verification_method": "INDEPENDENT RE-DERIVATION from committed git objects and live "
                           "re-execution of the boundary; the P3 submission's own assertions were "
                           "not taken as evidence of themselves",
    "bound_commits": P3_COMMITS,
    "bound_evidence_digests": {
        **{m: committed_modules[m] for m in P3_MODULES},
        **{e: sha_worktree(e) for e in P3_EVIDENCE if os.path.exists(os.path.join(HERE, e))}},
    "operational_modules": {
        "mr002_valoos_runtime.py": "numeric-runtime identity; FAIL-STOP on mismatch; rejects "
                                   "placeholder completion",
        "mr002_valoos_code_identity.py": "pre-read code identity; REFUSED_CODE_OR_DATA_IDENTITY on "
                                         "drift/missing/unbound/mismatch/absent binding",
        "mr002_valoos_access_boundary.py": "single read path; validation gated, OOS unconditionally "
                                           "denied, hash-chained opened-object ledger",
        "mr002_valoos_publication.py": "exclusive-create publication, exit/disposition agreement, "
                                       "read-only locks and hashes"},
    "test_inventory": {
        "increment_4": inc4["tests"],
        "full_evaluator_suite": inc4["full_evaluator_suite"],
        "log": "MR002_Increment4_TestLog.txt"},
    "zero_read_denial_chain": {
        "re_derived": True, "attempts": denials,
        "validation_reads": rederived["counts"]["validation_reads"],
        "oos_reads": rederived["counts"]["oos_reads"],
        "sealed_reads": rederived["counts"]["sealed_reads"],
        "chain_verifies": rederived["chain_verifies"],
        "stale_digest_blocks_validation": stale_blocks},
    "explicit_exclusions_and_unresolved_fields": {
        "P10_runtime_instance": "UNSATISFIED - workstation observation is a reference only; "
                                f"missing {completeness['missing']}",
        "PENDING_EVALUATOR_BIND": f"UNRESOLVED - {unresolved} remain sentinels; P5's SS4 procedure",
        "not_performed": inc4["excluded_not_authorized"]},
    "phase3a_registry_finding": {
        "interpretation": "the Phase 3A evaluator registry is HISTORICAL for its sealed commit and "
                          "is NOT the future P5 qualification binding",
        "phase3a_rule": "Phase 3A bound EVERY .py file in the evaluator directory - tests and "
                        "generators INCLUDED",
        "phase3a_bound_file_count": len(phase3a_bound),
        "phase3a_bound_files_drifted": len(drift),
        "current_all_py_file_count": len(all_py),
        "newly_present_since_phase3a": newly_present,
        "section4_rule": "the SS4 module inventory EXCLUDES tests and generators "
                         "(CI.module_digests)",
        "section4_inventory_at_phase3a": len(phase3a_under_section4_rule),
        "section4_inventory_now": len(evaluator_inventory),
        "section4_inventory_derivation": "mechanically enumerated; NOT a hard-coded count",
        "CORRECTION_to_P3_submission_section6": {
            "p3_submission_asserted": "21 -> 25 modules under the SS4 rule",
            "defect": "the figure added the 4 new modules to Phase 3A's 21, but that 21 was "
                      "counted under a DIFFERENT rule (all .py, tests and generators included); "
                      "the two counts are not like-for-like",
            "mechanically_derived_truth": {
                "section4_modules_at_phase3a": len(phase3a_under_section4_rule),
                "section4_modules_now": len(evaluator_inventory),
                "all_py_files_at_phase3a": len(phase3a_bound),
                "all_py_files_now": len(all_py)},
            "unchanged_conclusions": "the SUBSTANCE of the SS6 finding stands: zero drift on every "
                                     "Phase-3A-bound file, new files present, the Phase 3A registry "
                                     "is historical, and P5 must enumerate the then-current "
                                     "inventory. Only the numeral was wrong",
            "status": "the P3 submission text is left UNMODIFIED (it was adjudicated); this record "
                      "is the corrigendum"},
        "C9_evaluation_rule": "D3 condition C9 must be evaluated against the accepted P5 binding "
                              "and the then-current-tree recomputation, never by comparing the "
                              "current tree to the historical Phase 3A registry"},
    "verification_findings": findings,
    "verification_all_pass": all_pass,
    "verdict": "ACCEPT_AS_COMPLIANT" if all_pass else "REJECT",
    "status_transition": {
        "from": "PRODUCED", "to": "SATISFIED",
        "effective": "ON OWNER ADJUDICATION OF P4 - not on the existence of this record",
        "applied_here": False},
    "cas_anchor_effect": {
        "anchor_modified": False,
        "grant_capable_field_present": False,
        "adjudicated_prerequisite_digest": current_digest,
        "prospective_prerequisite_digest_if_only_P3_transitions": prospective_digest,
        "note": "the prospective digest is illustrative of the mechanism, not a future constant: "
                "the D3 submission must recompute the digest from the THEN-current register "
                "version, which will also reflect P4-P11",
        "rule": "this record cannot make the stale anchor grant-capable; a status change only feeds "
                "a NEW prerequisite digest for a later, separately adjudicated submission"},
    "boundary": "No validation or OOS access, no credential release, no performance, no P5 "
                "qualification, no evaluator binding resolution, no P10, no acceptance-standard "
                "change. validation_authorization remains false.",
}
with open(os.path.join(HERE, "MR002_P3_AcceptanceRecord.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(acceptance, sort_keys=True, indent=2) + "\n")

# =====================================================================================
# product 2 — the SS5 consolidated evaluator acceptance submission
# =====================================================================================
inc1, inc2, inc3 = (load(f"MR002_Increment{i}_Qualification.json") for i in (1, 2, 3))
submission = {
    "record_type": "MR002_EvaluatorAcceptanceSubmission", "version": "1.0",
    "prerequisite": "P4 (EvaluatorQualificationPlan SS5 consolidated acceptance submission)",
    "scope": "consolidated Workstream-B return across Increments 1-4; evaluation of the P3 evidence; "
             "NO P5 binding, NO P10, NO validation/OOS access, NO performance",
    "section5_elements": {
        "evaluator_code_identities": {
            "modules": evaluator_inventory,
            "module_count": len(evaluator_inventory),
            "inventory_digest": canonical_sha(evaluator_inventory),
            "commit_tree_container": "PENDING_EVALUATOR_BIND - authoritative binding is P5 via the "
                                     "registered SS4 procedure; NOT resolved here"},
        "container_and_dependency_identity": {
            "dependency_lock": inc1["dependency_lock"],
            "dependency_lock_sha256": inc1["dependency_lock_sha256"],
            "container_image_digest": "ABSENT - produced by the runtime producer under P10",
            "numeric_runtime": "reference observation only; not a bound instance"},
        "report_schema": {
            "module": "mr002_valoos_report.py",
            "schema_version": canonical.get("schema_version"),
            "self_hash_verifies": inc1["report_self_hash_verifies"],
            "publication_wrapper": "mr002_valoos_publication.py (no-overwrite, exit/disposition "
                                   "agreement, read-only locks)"},
        "synthetic_end_to_end_evidence": {
            "increment_1_canonical_report_hash": inc1["canonical_report_output_hash"],
            "increment_2_ledger_report_hash": inc2["ledger_report_output_hash"],
            "increment_3_replay_report_hash": inc3["replay_report_output_hash"],
            "increment_4_access_boundary_report": sha_worktree(
                "MR002_Increment4_AccessBoundaryReport.json")},
        "gate_fixture_results": {
            "required_gate_count": len(REG.REQUIRED_GATES),
            "gates_with_synthetic_result": len([g for g in REG.REQUIRED_GATES if g in gate_results]),
            "missing": missing_gates,
            "results": {gid: {"status": gate_results[gid]["status"],
                              "threshold": gate_results[gid]["threshold"],
                              "sample": gate_results[gid]["sample"]}
                        for gid in sorted(REG.REQUIRED_GATES) if gid in gate_results}},
        "diagnostics_non_gating": {
            "required": sorted(REG.REQUIRED_DIAGNOSTICS),
            "present": sorted(diagnostics),
            "all_classified_non_gating": all(d["classification"] != G.GATE
                                             for d in diagnostics.values())},
        "refusal_test_evidence": {
            "governing_identity_chain": "Increment 1 semantic-tamper suite (ledger N, prereg N, "
                                        "dispersion cross-binding, id set, bool-as-int)",
            "code_identity": "Increment 4 T4-11..T4-17 (drift, missing, unbound, commit/tree/"
                             "container mismatch, absent binding)",
            "runtime_identity": "Increment 4 T4-05..T4-08 (placeholder, field drift, thread env)",
            "access_boundary": "Increment 4 T4-18..T4-29 (authorization false, OOS unconditional, "
                               "stale digest, rev mismatch, unregistered, malformed state)",
            "publication": "Increment 4 T4-31..T4-37 (occupied destination, exit disagreement, "
                           "missing identity, second publication)"},
        "determinism_proof": {
            "increment_1": inc1["determinism_proof"], "increment_3": inc3["determinism_proof"],
            "increment_4": inc4["determinism_proof"]},
        "zero_performance_confirmation": {
            "validation_data_read": False, "oos_data_read": False,
            "development_performance_computed": False, "synthetic_fixture_only": True,
            "sealed_reads": rederived["counts"]["sealed_reads"]},
        "trials_N_read_from_bound_identity": {
            "N": n_from_ledger,
            "source": "MR002_DSR_TrialLedger_v1.0.json (deda5cec...) via load_governing_identity",
            "no_code_constant_fallback": True,
            "tampered_N_fails_closed": n_refuses_tamper,
            "evidence": "V14 re-derived here; Increment-1 test_01/test_05 in the suite"}},
    "p3_evaluation": {
        "record": "MR002_P3_AcceptanceRecord.json",
        "verdict": acceptance["verdict"],
        "all_checks_pass": all_pass,
        "check_count": len(findings)},
    "outstanding_prerequisites_not_addressed_here": [
        "P5 SS4 pre-access evaluator binding (commit/tree/container)",
        "P6-P9 custodian seal and structural evidence", "P10 runtime instance",
        "P11 access-control preconditions", "P13 DSR trial dispersion (Phase 3C)"],
    "acceptance_standard_unchanged": {
        "asserted": True,
        "statement": "the EvaluatorQualificationPlan SS5 standard was not modified after examining "
                     "the P3 result; no gate, threshold, sample, or trial rule was touched"},
    "boundary": "Validation and OOS remain SEALED AND UNREAD; validation_authorization=false; the "
                "single validation opening remains unconsumed; OOS under DENY.",
}
with open(os.path.join(HERE, "MR002_EvaluatorAcceptanceSubmission.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(submission, sort_keys=True, indent=2) + "\n")

print(f"P4 SS5 acceptance submission written: {len(findings)} checks, "
      f"all_pass={all_pass}, verdict={acceptance['verdict']}")
print(f"  section4 inventory (mechanical) = {len(evaluator_inventory)} modules; "
      f"phase3a historical = {len(phase3a_bound)}; drift = {len(drift)}")
print(f"  gates with synthetic result = {len(REG.REQUIRED_GATES) - len(missing_gates)}"
      f"/{len(REG.REQUIRED_GATES)}; trials_N = {n_from_ledger}")
print(f"  adjudicated digest {current_digest[:16]}... -> prospective {prospective_digest[:16]}...")
for f in findings:
    if f["result"] != "PASS":
        print("  FAIL:", f["check"], f["description"], f["detail"])
