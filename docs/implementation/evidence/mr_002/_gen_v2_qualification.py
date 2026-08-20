"""MR-002 Cycle 2C — VALIDATION-2 DRY-RUN QUALIFICATION record.

Adjudicates the dry run against MR002_Validation2_ProspectiveRegistration_v1.0 §dry_run_requirement
and emits the Cycle-2C disposition, which is a READINESS statement and never an execution
authorization.

⛔ Validation-2 was not opened. Zero withheld economic bytes were read.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
E = "docs/implementation/evidence/mr_002/"
S = "apps/backend/scripts/"


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob(path: str):
    r = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None


def main() -> int:
    with open(os.path.join(REPO, ".mr002out", "v2", "dryrun.json"), encoding="utf-8") as fh:
        D = json.load(fh)
    reg = os.path.join(_HERE, "MR002_Validation2_ProspectiveRegistration_v1.0.json")
    with open(reg, encoding="utf-8") as fh:
        REG = json.load(fh)

    nc = D["negative_controls"]
    proven = {
        "state_machine_reaches_every_terminal_path": D["every_terminal_path_exercised"],
        "integrity_failure_suppresses_excellent_economics":
            nc["INTEGRITY_FAILURE"]["economic_verdict_suppressed"],
        "integrity_failure_not_mislabelled_as_reject":
            nc["INTEGRITY_FAILURE"]["not_mislabelled_as_reject"],
        "registered_numerical_termination_is_not_a_defect":
            nc["REGISTERED_TERMINATION_IS_NOT_A_DEFECT"]["conformant"],
        "zero_stage3_invocations_aborts_as_invalid_harness":
            nc[ "INVALID_TEST_HARNESS"]["guard_raised"],
        "wrong_solver_pair_caught_even_with_a_full_census":
            nc["INVALID_TEST_HARNESS_wrong_pair"]["caught"],
        "pre_read_abort_leaves_the_opening_unconsumed":
            nc["PRE_READ_ABORT_NOT_CONSUMED"]["must_be_not_consumed"],
        "one_exposure_consumes_the_opening":
            nc["CONSUMPTION_BOUNDARY"]["one_exposure_consumes"],
        "ledger_is_durable_on_disk":
            nc["CONSUMPTION_BOUNDARY"]["ledger_durable_on_disk"],
        "routing_guard_passes_against_REAL_routing":
            bool(D.get("surrogate_run", {}).get("guard_passed_on_real_routing")),
    }

    outstanding = [
        {"item": "live reader/publisher role-assumption separation test",
         "required_by": "registration §dry_run_requirement — 'reader can read ONLY the authorized "
                        "object set', 'publisher CANNOT read the sealed store', 'reader CANNOT "
                        "write governing evidence', 'publisher CANNOT alter raw input'",
         "status": "NOT PERFORMED",
         "why_it_matters": "these four are capability claims about DEPLOYED IAM roles. The dry run "
                           "verified only that this process never constructs a sealed-store client, "
                           "which is a property of the harness, not a proof about the roles.",
         "remediation": "assume mr002-validation-reader and the publisher role in turn and record "
                        "the allowed/denied matrix as evidence"},
        {"item": "Validation-2 structural preflight",
         "required_by": "registration §execution_freeze — structural preflight is a fail-closed "
                        "precondition; §fold_geometry — the 850/775/155 geometry must be VERIFIED "
                        "against the actual window",
         "status": "NOT PRODUCED",
         "why_it_matters": "the fold geometry is DERIVED arithmetic. It has not been confirmed "
                           "against the oos window's own session list, and a silently short fold "
                           "would move the 3-of-5 verdict.",
         "remediation": "produce a value-blind structural manifest for the 2023-02-17..2026-07-10 "
                        "window with the custodian producer, exactly as P9 was produced for "
                        "Validation-1"},
        {"item": "economic evaluator re-qualification against the Validation-2 window",
         "required_by": "registration §execution_freeze — evaluator source identity",
         "status": "NOT PERFORMED",
         "why_it_matters": "the mr002_valoos_* evaluator was qualified for Validation-1. Its "
                           "identities are bound in ValidationInputIdentityManifest_v1.0, but it "
                           "has not been exercised end-to-end under the Validation-2 population "
                           "definition.",
         "remediation": "run the full evaluator against the development surrogate under the "
                        "Validation-2 opening protocol, not only the Stage-3 seam"},
        {"item": "version-controlled research-plane isolation check",
         "required_by": "registration §execution_freeze.isolation_dependency",
         "status": "BLOCKED — both ADR-0051 invariant scripts are UNTRACKED and exist at no commit",
         "why_it_matters": "a fail-closed control that cannot be hash-bound is not a control",
         "remediation": "commit and hash-bind the two scripts, or establish that the Validation-2 "
                        "harness depends on neither and record that vacuous satisfaction "
                        "explicitly"},
    ]

    rec = {
        "record_type": "MR002_VALIDATION2_DRYRUN_QUALIFICATION",
        "version": "1.0",
        "cycle": "2C",
        "date": "2026-08-20",
        "authority": {"registration": "MR002_Validation2_ProspectiveRegistration_v1.0",
                      "identity_sha256": REG["record_identity_sha256"],
                      "registration_status": REG["record_status"]},
        "validation_2_opened": False,
        "validation_2_economic_bytes_read": 0,
        "sealed_store_touched_by_the_dry_run": False,
        "surrogate": D.get("surrogate_run", {}).get("surrogate"),

        "what_the_dry_run_PROVES": proven,
        "terminal_path_coverage": D["terminal_path_coverage"],
        "negative_controls": nc,
        "surrogate_run": D.get("surrogate_run"),

        "what_remains_OUTSTANDING": outstanding,

        "disposition": "VALIDATION2_NOT_READY",
        "disposition_rationale": (
            "The decision machinery is proven: every terminal path fires, an integrity failure "
            "suppresses even excellent economics, a registered numerical termination does NOT "
            "break conformance, the N3-derived guard aborts on zero invocations AND on a full "
            "census produced by the wrong solver pair, a pre-read abort leaves the opening "
            "unconsumed, and the ledger is durable on disk. That is the core of what Cycle 2C was "
            "for, and it holds. But FOUR of the proofs the registration itself demands have not "
            "been produced, and one of them is BLOCKED on an untracked script. Declaring READY "
            "with the reader/publisher capability separation untested and the fold geometry "
            "unverified against the actual window would be exactly the overstatement that "
            "consumed the first opening. The honest status is NOT_READY with a short, concrete "
            "remediation list."
        ),
        "⛔ this_record_authorizes": "NOTHING. It does not open Validation-2 and is not execution "
                                    "authorization.",
        "boundary": {
            "validation_2_opening": "NOT AUTHORIZED",
            "new_oos": "PROHIBITED — architecture approved, opening not granted",
            "validation_1": "CONSUMED — permanently inadmissible",
            "stage_3_pair": "FROZEN — QUADPROG_SQRT + PIQP_P2",
            "consumed_original_opening": "unchanged",
        },
        "bound_sources": {p: blob(p) for p in (S + "mr002_v2_harness.py",
                                               "scripts/mr002_custody/oos_pristine_proof.py",
                                               E + "_gen_v2_registration.py")},
    }
    ident = hashlib.sha256(_canonical(rec)).hexdigest()
    rec["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_DryRunQualification_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(rec))
    os.replace(tmp, out)

    print("MR-002 CYCLE 2C — VALIDATION-2 DRY-RUN QUALIFICATION")
    print(f"  identity     {ident}")
    print(f"  disposition  {rec['disposition']}")
    print(f"  proven       {sum(1 for v in proven.values() if v)}/{len(proven)}")
    print(f"  outstanding  {len(outstanding)}")
    for o in outstanding:
        print(f"     - {o['item']}: {o['status']}")
    print(f"  wrote        {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
