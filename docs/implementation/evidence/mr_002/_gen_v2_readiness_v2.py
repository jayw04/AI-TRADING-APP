"""MR-002 — VALIDATION-2 READINESS QUALIFICATION v2.0 (corrected, NINE gates).

Supersedes v1.0 (daa1f7ca...) FOR OPENING PURPOSES only. v1.0 is preserved unmodified: it was
valid for what it tested, and is NOT rewritten to pretend the ninth gate existed.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
M = "apps/backend/app/research/mr002/"
CRIT = [M + "phase3c/__init__.py", M + "phase3c/folds.py", M + "phase3c/replay.py",
        M + "phase3c/gates.py", M + "phase3c/materialize.py", M + "phase3c/exits.py",
        M + "phase3c/adopted.py", M + "phase3c/durable_evidence.py",
        M + "phase3c/credential_readiness.py", M + "phase3b/readers.py",
        M + "joint_portfolio.py", M + "stage3_route.py", M + "stage3_cascade.py",
        M + "n1/method.py", M + "n1/seam.py", M + "runner.py", M + "dataset.py",
        M + "execution.py", "apps/backend/scripts/mr002_development_run.py",
        "apps/backend/scripts/mr002_coverage_signed_gap.py"]


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob(p: str) -> str:
    r = subprocess.run(["git", "-C", REPO, "show", "HEAD:" + p], capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest()


HOSTQUAL = {
    "run_inside": "the exact container the opening will use: mr002-research:v1.4, "
                  "-v /opt/mr002/phase3c_src:/work:ro, PYTHONPATH=/work/apps/backend, "
                  "FROZEN_THREAD_ENV, --network=none, deps bundle mounted",
    "import_resolution": {
        "all_modules_resolve_under_work_mount": True,
        "module_files": {
            "phase3c": "/work/apps/backend/app/research/mr002/phase3c/__init__.py",
            "folds": "/work/apps/backend/app/research/mr002/phase3c/folds.py",
            "replay": "/work/apps/backend/app/research/mr002/phase3c/replay.py",
            "gates": "/work/apps/backend/app/research/mr002/phase3c/gates.py",
            "joint_portfolio": "/work/apps/backend/app/research/mr002/joint_portfolio.py"},
        "why_this_is_THE_gate": "matching files at /opt/mr002/phase3c_src prove nothing if the "
                                "runner imports a different copy. This asserts the LOADED "
                                "modules' __file__."},
    "effective_constants_from_loaded_objects": {
        "VALIDATION_WINDOW_START": "2023-02-17", "VALIDATION_WINDOW_END": "2026-07-10",
        "SCORING_ELIGIBLE_FIRST": "2023-05-30", "SCORING_ELIGIBLE_LAST": "2026-07-01",
        "OUT_OF_BOUNDS_AFTER": "2026-07-10", "VALIDATION_WINDOW_SESSIONS": 850,
        "ELIGIBLE_SESSIONS": 775, "all_match": True},
    "folds": [[1, "2023-05-30", "2024-01-09", 155], [2, "2024-01-10", "2024-08-21", 155],
              [3, "2024-08-22", "2025-04-04", 155], [4, "2025-04-07", "2025-11-14", 155],
              [5, "2025-11-17", "2026-07-01", 155]],
    "folds_match": True, "validation_1_folds_retained_as_history": True,
    "fatal_interlock": {"fired": True, "probe_session": "2026-07-11",
                        "detail": "OOS_BOUNDARY_VIOLATION: session 2026-07-11 is beyond the "
                                  "Validation-2 window end 2026-07-10"},
    "runtime": {
        "image_config_digest_observed":
            "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
        "matches_bound": True,
        "typed_identity_note": "the qualification machine's OCI/index identity is "
                               "sha256:aa930021c072... for the SAME image. Two values, two "
                               "identity TYPES, not drift. A bare image_id must never be a gate.",
        "deps_bundle_mounted": True,
        "libs": {"duckdb": "1.1.3", "piqp": "0.6.3", "numpy": "2.2.6", "quadprog": "present"}},
    "frozen_solver_pair": {"A": "QUADPROG_SQRT", "B": "PIQP_P2",
                           "disposition_vocabulary_present": True},
    "non_withheld_conformance": {"suite": "phase3c, executed from the DEPLOYED tree in the "
                                          "opening container", "exit_code": 0, "failures": 0},
}

DEPLOY = {
    "package": "MR002_Validation2_ExecutionPackage_v1.0 (6c2484f8) SUPERSEDED by correction "
               "ed2ffcf4 - v1.0's bound archive hash was defective",
    "correction_record": "ed2ffcf458314e19d102e7261ddf78691c9fd5725337f68e6af51d4bb42c57d6",
    "archive_deployed": "19d5e4b208c533768f3184fd64ae3076ff94bfd1a15e36c3eb4b52e348c500ce",
    "archive_not_regenerated": "the authorized frozen bytes were re-hashed and staged; the "
                               "archive was NOT rebuilt from the commit",
    "source_commit": "6aca0d80225b6aa650eb9b90712d7f88b55c21e8",
    "candidate_gates": {"archive_sha": "PASS", "safe_paths": "PASS",
                        "critical_hashes": "20/20", "crlf_files": "0/20",
                        "py_file_count": 1064, "ownership_mode": "root:root:664"},
    "crlf_gate_is_secondary": "the hashes remain authoritative; no-CRLF cannot rescue a hash "
                              "mismatch",
    "cutover": {
        "pattern": "staged extraction, full verification, then same-filesystem atomic rename",
        "candidate_aggregate":
            "047abe0f6f103158172aaa84a1b882ebdc4ccb85378aa5f730fca23f538a1ac9",
        "post_cutover_live_aggregate":
            "047abe0f6f103158172aaa84a1b882ebdc4ccb85378aa5f730fca23f538a1ac9",
        "rename_changed_no_bytes": True,
        "rollback_tree": "/opt/mr002/phase3c_src_pre_amendmentC",
        "rollback_aggregate":
            "ff0308be99dd82087b03ef3b48006f4a7c4b87ca37bd951a8be42794c03f4bbc"},
}

CRLF_DET = {
    "question": "does any still-operative MR-002 gate, registration, manifest, certification or "
                "integrity assertion REQUIRE one of the known defective CRLF identities?",
    "answer": "NO",
    "enforced_constants_in_adopted_py": {
        "ADOPTED_RUNNER_SHA256": "57d0fcac... = the LF Git blob",
        "MECHANICS_BLOCK_SHA256": "2ab94236... = LF basis"},
    "the_one_CRLF_value_present": "MECHANICS_BLOCK_SHA256_FROZEN_CRLF_BASIS = 02d9ea75...",
    "is_it_enforced": "NO. The source documents it as retained verbatim and NOT enforced, and its "
                      "only reference outside its definition is a reporting dict - it is never "
                      "compared. The code explains why it cannot be enforced: a 26-line block "
                      "loses exactly 26 carriage returns under LF, so no LF checkout could "
                      "reproduce it.",
    "operational_proof": "the phase3c suite passed from the DEPLOYED LF tree, which exercises "
                         "adopted.verify_binding(); both enforced hashes therefore verify against "
                         "LF bytes.",
    "consequence": "historical CRLF identities are recorded as SUPERSEDED/CORRECTED provenance. "
                   "NOT an opening blocker.",
    "follow_up_debt": "Source Identity Provenance Sweep - Windows checkout / archive line-ending "
                      "contamination. Future source identities must derive from Git objects or "
                      "another explicitly byte-canonical source, never an ambient Windows "
                      "checkout. Build control must use "
                      "git -c core.autocrlf=false -c core.eol=lf archive. Tracked separately.",
}


GATES = {
    "deployed_matrix_fully_green": True,
    "deployed_policy_equals_sealed_document": True,
    "latch_closed_8_statements": True,
    "reader_trust_unchanged": True,
    "zero_successful_validation2_reads": True,
    "no_live_read_used_during_qualification": True,
    "every_required_identity_present": True,
    "all_bound_sources_committed": True,
    "execution_host_source_identity_matches_registered_execution_package": True,
}


def main() -> int:
    rec = {
        "record_type": "MR002_Validation2_ReadinessQualification", "version": "2.0",
        "date": "2026-08-20",
        "disposition": ("VALIDATION2_READY_FOR_OWNER_OPENING_GRANT" if all(GATES.values())
                        else "VALIDATION2_NOT_READY"),
        "supersedes_for_opening_purposes": {
            "record": "MR002_Validation2_ReadinessQualification_v1.0",
            "identity": "daa1f7ca7abb24509a2a1623a1ae3f6652f47197b7fc83106897efe73852f28f",
            "status": "READY under an EIGHT-gate model, later found INCOMPLETE by pre-opening "
                      "verification",
            "preserved_unmodified": True,
            "not_rewritten": "the old record is NOT edited to pretend the ninth gate existed"},
        "lineage": [
            "daa1f7ca... READY under the eight-gate model; the deployed-source question was "
            "never asked",
            "c2f4d8b2... opening NEVER BEGUN; the missing deployed-source gate discovered at step 1",
            "ed2ffcf4... deployment preparation FAILED at candidate verification (CRLF archive); "
            "cutover not performed; corrected package sealed",
            "THIS RECORD  corrected NINE-gate qualification with the execution-host gate bound"],
        "readiness_gates": GATES,
        "the_new_ninth_gate": {
            "name": "execution_host_source_identity_matches_registered_execution_package",
            "binds": "host + destination path + 20 execution-critical source hashes + IMPORT "
                     "RESOLUTION + runtime/image typed identities + frozen solver identities",
            "why": "the eight-gate model verified Amendment C was applied IN THE REPOSITORY and "
                   "never asked whether the EXECUTION HOST carried it. Applied was checked at the "
                   "wrong place. This gate closes exactly that class of defect.",
            "stronger_than_four_hashes": True},
        "execution_host_qualification": HOSTQUAL,
        "deployment": DEPLOY,
        "crlf_identity_determination": CRLF_DET,
        "execution_critical_source_identities": {p: blob(p) for p in CRIT},
        "iam_state_reverified_now": {
            "deployed_A_v1_2_equals_sealed": True, "latch_statements": 8,
            "reader_trust_condition": "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
            "evaluator_host_state": "stopped"},
        "withheld_reads": {
            "successful": 0, "denied_attempts": 7, "chain_verifies": True,
            "access_history":
                "20dc9f69fc1d71514d718ce8894c5bfe16694d02863ce1a033641ca1e490b7a9"},
        "evidence_chain": {
            "prospective_registration":
                "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57",
            "partition_identity":
                "3b3910d00395d90189b94fd0f9901811b1813905f17219010b336c567cfa1296",
            "structural_preflight":
                "3810e071761a5100fe8cda6754488ebac5230f74b1b5e0f812ec53764d94436a",
            "amendment_C_commit": "1498039b7ca825a555dd562513ca74a8d5145034",
            "amendment_B_v1_2": "1d27410c626a5748133723a3680625ca07256c334ae39fd1e9bc8529aeb4ed7d",
            "amendment_B_live_trust":
                "6b8a73a6633a9e709409caf9ce339c777cd49b98f5b300fd30d7acf4b130c8bc",
            "amendment_A_v1_2": "3ce28be1cf6c422a2f0acc9d7fe5388f0fea9c62ad91c57c30459da32d6d4735",
            "execution_package": "6c2484f892b753f622f4151071e524001140980d5e48f0b7c99dbdde7d3c85d7",
            "package_correction": "ed2ffcf458314e19d102e7261ddf78691c9fd5725337f68e6af51d4bb42c57d6",
            "N1": "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81",
            "N2": "27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471",
            "N3": "5a14028024a1f78ca60ebeb174b5ecd7b8a3e1f5027f8768ec93b6f2a8195ec4"},
        "disclosed_limitations_carried_forward": [
            "Validation-2 is machine-pristine but HISTORICALLY ELAPSED",
            "fold RESULTS are not computable on the development surrogate",
            "the dividend corporate-action leg is reconciled but VACUOUS on development",
            "the six objects BYTES remain bound INDIRECTLY via write-time server-validated "
            "SHA-256; direct verification is only possible at the opening itself"],
        "what_this_record_does_NOT_authorize": [
            "releasing the 8 -> 7 latch", "assuming the reader",
            "reading one Validation-2 byte", "executing phase3c against Validation-2",
            "inspecting any resulting economics"],
        "boundary": {"validation_2_opening": "NOT AUTHORIZED", "latch": "8 / CLOSED",
                     "withheld_reads": 0,
                     "prior_opening_authorization": "SUSPENDED - a fresh ruling is required"},
    }
    ident = hashlib.sha256(_canonical(rec)).hexdigest()
    rec["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ReadinessQualification_v2.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(rec))
    os.replace(tmp, out)
    print("CORRECTED READINESS QUALIFICATION v2.0")
    print(f"  identity   {ident}")
    print(f"  disposition {rec['disposition']}")
    print(f"  gates      {sum(GATES.values())}/{len(GATES)}")
    for k, v in GATES.items():
        print(f"    {'OK ' if v else 'X  '} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
