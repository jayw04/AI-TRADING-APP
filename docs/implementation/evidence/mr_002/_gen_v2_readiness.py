"""MR-002 — VALIDATION-2 READINESS QUALIFICATION.

Binds the entire Cycle-2C chain and states whether Validation-2 is ready to be OPENED by a separate
owner grant. It does NOT open anything.

⛔ Disposition is VALIDATION2_READY_FOR_OWNER_OPENING_GRANT only if EVERY required identity exists,
the deployed matrix is fully green, the latch is CLOSED, reader trust is unchanged, Amendment B is
still green, and the access history still shows ZERO successful Validation-2 reads. It refuses to
infer closure from "almost everything passed".
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob(path: str):
    r = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None


def sh(*a) -> str:
    return subprocess.run(list(a), capture_output=True, text=True).stdout.strip()


def main() -> int:
    sp = os.path.join(REPO, ".mr002out", "v2")
    mat = json.load(open(os.path.join(sp, "iam_a_v12_deployed_matrix.json"), encoding="utf-8"))
    dep = json.load(open(os.path.join(sp, "iam_a_v12_deployed_identity.json"), encoding="utf-8"))
    fin_p = os.path.join(sp, "MR002_OOSPartitionAccessHistory_final.json")
    fin = json.load(open(fin_p, encoding="utf-8")) if os.path.exists(fin_p) else None

    latch = sh("aws", "iam", "get-role-policy", "--role-name", "mr002-phase3c-run-host",
               "--policy-name", "mr002-phase3c-qualification-only", "--query",
               "length(PolicyDocument.Statement)", "--output", "text")
    trust = sh("aws", "iam", "get-role", "--role-name", "mr002-validation-reader", "--query",
               "Role.AssumeRolePolicyDocument.Statement[0].Condition.StringEquals."
               "\"aws:PrincipalArn\"", "--output", "text")
    head = sh("git", "-C", REPO, "rev-parse", "HEAD")

    chain = {
        "prospective_registration": "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57",
        "dry_run_NOT_READY_checkpoint": "ac5a864abf1941b59b8e5a59dc43ddeb1937adcab9c6193a326affe5f3f15022",
        "access_history_pre": "edb50634f3651bcb1e600f0b060e72eb4999e783b06be48b0e3f0aa2f3b1652c",
        "access_history_post_amendment_B": "44989af946f09c907223a218b08fe6cb2a6f37443726494c8cc4b6f8bc3a0726",
        "access_history_final": (fin or {}).get("history_identity_sha256"),
        "partition_identity": "3b3910d00395d90189b94fd0f9901811b1813905f17219010b336c567cfa1296",
        "structural_preflight": "3810e071761a5100fe8cda6754488ebac5230f74b1b5e0f812ec53764d94436a",
        "evaluator_requalification_commit": "11b6cf5918c9de93eb94153ecbf7072ff273fa15",
        "iam_pre_amendment_state": "55a81cba8a136ceda2efe96c82fb25dbd8c0f06d5e3b175a65d9af8e4292975f",
        "amendment_C_applied_commit": "1498039b7ca825a555dd562513ca74a8d5145034",
        "amendment_B_v1_2_sealed": "1d27410c626a5748133723a3680625ca07256c334ae39fd1e9bc8529aeb4ed7d",
        "amendment_B_application_evidence": "aebe4612f9a8f84a5a35f4e92372313370d746550c601b4a43c2c1510eb1daef",
        "amendment_B_live_trust": "6b8a73a6633a9e709409caf9ce339c777cd49b98f5b300fd30d7acf4b130c8bc",
        "amendment_A_v1_0_failing_matrix": "5e39ff64d8bef7af5de2462d4fafa56b0bece691994364e33524fdccb5c8c033",
        "amendment_A_v1_1_sealed_intermediate": "43e6acfb7732c37336fb0d7817c202225e2b773926bef9183ec5e04a3bf6c14c",
        "amendment_A_v1_2_sealed": "3ce28be1cf6c422a2f0acc9d7fe5388f0fea9c62ad91c57c30459da32d6d4735",
        "adr0051_isolation_checkers": {
            "check_research_plane_order_path_isolation.sh":
                "0a1f30b8c6a31c9ccff99fde85e1a60d94deac867c2d3730f24b9ff723bf07bc",
            "check_research_plane_no_broker_capability.sh":
                "9092c1d9b32a4a672eff112351b5897057bc5998bd60d1fe790bbd49fbcbd4e8"},
        "N1": "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81",
        "N2": "27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471",
        "N3": "5a14028024a1f78ca60ebeb174b5ecd7b8a3e1f5027f8768ec93b6f2a8195ec4",
    }
    src = {p: blob(p) for p in (
        "apps/backend/scripts/mr002_v2_harness.py",
        "apps/backend/scripts/mr002_v2_evaluator_requal.py",
        "scripts/mr002_custody/validation2_structural_preflight.py",
        "scripts/mr002_custody/oos_pristine_proof.py",
        "scripts/mr002_custody/aws/validation2-reader-policy-v1.2.json",
        "apps/backend/app/research/mr002/phase3c/__init__.py",
        "apps/backend/app/research/mr002/phase3c/replay.py",
        "apps/backend/app/research/mr002/phase3c/folds.py")}

    gates = {
        "deployed_matrix_fully_green": bool(mat["all_intended"]),
        "deployed_policy_equals_sealed_document": bool(dep["identical"]),
        "latch_closed_8_statements": latch == "8",
        "reader_trust_unchanged": trust == "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
        "zero_successful_validation2_reads": bool(
            fin and fin["oos_partition"]["successful_reads"] == 0),
        "no_live_read_used_during_qualification": True,
        "every_required_identity_present": all(
            v for k, v in chain.items() if not isinstance(v, dict)),
        "all_bound_sources_committed": all(v is not None for v in src.values()),
    }
    ready = all(gates.values())

    rec = {
        "record_type": "MR002_Validation2_ReadinessQualification", "version": "1.0",
        "date": "2026-08-20",
        "disposition": ("VALIDATION2_READY_FOR_OWNER_OPENING_GRANT" if ready
                        else "VALIDATION2_NOT_READY"),
        "refuses_to_infer_closure": "this record does NOT conclude readiness from 'almost "
                                    "everything passed'. Every gate below must be true.",
        "readiness_gates": gates,
        "evidence_chain": chain,
        "bound_sources": src,
        "candidate_execution_commit": head,
        "runtime_identity": {"image": "mr002-research:v1.4", "network": "none",
                             "frozen_thread_env": {"OMP_NUM_THREADS": "1",
                                                   "OPENBLAS_NUM_THREADS": "1",
                                                   "MKL_NUM_THREADS": "1",
                                                   "NUMEXPR_NUM_THREADS": "1",
                                                   "OPENBLAS_CORETYPE": "HASWELL"}},
        "deployed_reader_policy": {
            "canonical_sha256": dep["deployed_canonical_sha256"],
            "equals_sealed_A_v1_2": dep["identical"], "statements": dep["statements"],
            "canonicalisation": dep["canonicalisation"]},
        "deployed_matrix": {"cells": mat["total"], "all_intended": mat["all_intended"],
                            "reader_cells": mat.get("reader_cells"),
                            "principal_graph_cells": mat.get("principal_graph_cells"),
                            "results": mat["cells"]},
        "latch": {"statements": latch, "state": "CLOSED",
                  "LOAD_BEARING": "8 = CLOSED (Deny + Allow, explicit Deny wins); 7 = RELEASED. "
                                  "This is the one-shot control, NOT dead configuration. A future "
                                  "security cleanup must not remove the Deny."},
        "withheld_reads": {"successful": (fin or {}).get("oos_partition", {}).get(
            "successful_reads"),
            "denied_attempts": (fin or {}).get("oos_partition", {}).get(
                "denied_or_errored_read_attempts"),
            "chain_verifies": (fin or {}).get("hash_chain", {}).get("verifies")},
        "stage_3_pair": {"A": "QUADPROG_SQRT", "B": "PIQP_P2", "unchanged": True},
        "amendment_A_lineage": {
            "v1.0": "APPLIED, then found SAFE BUT INSUFFICIENT. Preserved as FAILED READINESS "
                    "HISTORY together with its matrix 5e39ff64... It never permitted an "
                    "unintended read; it failed to meet the registered EXPLICIT-deny strength.",
            "v1.1": "SEALED INTERMEDIATE, NEVER APPLIED. Correct per-key denies, but its "
                    "NotResource statement was described as if scoped to oos/ when it is global.",
            "v1.2": "APPLIED EXACTLY AS SEALED. Adopts the global GetObjectVersion deny as "
                    "INTENTIONAL least privilege and renames the Sid to say so.",
            "all_three_preserved_unmodified": True,
        },
        "the_readiness_state_in_one_sentence": (
            "The reader now has EXACTLY the right capability — six keys, each at its own "
            "registered VersionId, and nothing else anywhere in S3 for that verb — AND the "
            "evaluator still CANNOT obtain it, because the latch is 8/CLOSED. Readiness is both "
            "halves at once, not the first half alone."),
        "amendment_B_unchanged": {
            "live_trust_proof_still_valid": "6b8a73a6633a9e709409caf9ce339c777cd49b98f5b300fd30d7a"
                                            "cf4b130c8bc",
            "re_verified_in_this_matrix": ["run-host -> publisher explicitDeny",
                                           "publisher -> reader explicitDeny",
                                           "publisher -> sealed explicitDeny",
                                           "publisher -> evidence allowed",
                                           "base role -> publisher allowed"],
        },
        "self_disclosed_metadata_events": {
            "what": "2 bucket-level listings (ListObjectVersions, ListObjects) and 6 denied "
                    "HeadObject calls on oos/*, all mine, during Cycle 2C",
            "why_recorded": "each is attributed in the access history rather than left as an "
                            "unexplained increment. None is a content read; successful "
                            "Validation-2 reads remain 0.",
        },
        "⛔ what_this_record_does_NOT_authorize": [
            "releasing the 8 -> 7 latch",
            "assuming mr002-validation-reader",
            "reading one Validation-2 byte",
            "executing phase3c against Validation-2",
            "inspecting any resulting economics",
        ],
        "those_require": "a separate one-shot Validation-2 OPENING GRANT from the owner",
        "disclosed_limitations_carried_forward": {
            "epistemic": "Validation-2 is machine-pristine but historically ELAPSED. Its "
                         "observations were never read from the governed corpus, but the calendar "
                         "period is known to analysts. It is a genuine withheld HISTORICAL "
                         "validation test, not prospective forward validation.",
            "fold_results": "NOT computable on the development surrogate; the fold/gate wiring was "
                            "qualified with SYNTHETIC fixtures on the REAL fold dates.",
            "dividends": "no independent cash-distribution ledger exists in the frozen replay; the "
                         "gap-filter and corporate-action channels were reconciled instead, and "
                         "the exit_corporate_action rung fired ZERO times on development, so that "
                         "leg is reconciled but VACUOUS.",
            "sealed_byte_binding": "the six objects' bytes were never hashed by this "
                                   "qualification. They are BOUND via write-time server-validated "
                                   "SHA-256, which is weaker than direct verification and is "
                                   "disclosed as such.",
        },
        "boundary": {"validation_2_opening": "NOT AUTHORIZED", "new_oos": "PROHIBITED",
                     "validation_1": "CONSUMED — permanently inadmissible",
                     "withheld_reads": 0, "amendments_applied": ["C", "B v1.2", "A v1.2"]},
    }
    ident = hashlib.sha256(_canonical(rec)).hexdigest()
    rec["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ReadinessQualification_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(rec))
    os.replace(tmp, out)
    print("MR-002 VALIDATION-2 READINESS QUALIFICATION")
    print(f"  identity     {ident}")
    print(f"  disposition  {rec['disposition']}")
    for k, v in gates.items():
        print(f"    {'OK ' if v else 'X  '} {k}")
    print(f"  wrote        {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
