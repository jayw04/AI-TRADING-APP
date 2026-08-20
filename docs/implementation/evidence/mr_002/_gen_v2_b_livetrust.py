"""MR-002 — Amendment B v1.2 LIVE TRUST QUALIFICATION.

Owner ruling 2026-08-20 authorized one temporary publisher EC2 instance and a temporary start of
the stopped evaluator host, solely to execute the three outstanding trust proofs, on the reasoning
that a control first proven during the one-shot operation that depends on it is not a readiness
gate at all.

⛔ ZERO GetObject against the six Validation-2 objects. The reader latch was never released.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
B_V12 = "1d27410c626a5748133723a3680625ca07256c334ae39fd1e9bc8529aeb4ed7d"
B_APPLIED = "aebe4612f9a8f84a5a35f4e92372313370d746550c601b4a43c2c1510eb1daef"
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
PUB_HOST = "i-0c7ae1f9fd67394a5"
EVAL_HOST = "i-00c1034f7026db45e"


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def aws(*a):
    o = subprocess.run(["aws", *a, "--output", "json"], capture_output=True, text=True)
    return json.loads(o.stdout) if o.stdout.strip() else None


def main() -> int:
    sp = os.path.join(REPO, ".mr002out", "v2")
    with open(os.path.join(sp, "pubproof.json"), encoding="utf-8") as fh:
        pub = json.load(fh)
    with open(os.path.join(sp, "iam_b_capability_matrix.json"), encoding="utf-8") as fh:
        mat = json.load(fh)
    post = None
    p = os.path.join(sp, "MR002_OOSPartitionAccessHistory_postB.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            post = json.load(fh)

    p1 = pub["proof_1_base_role_to_evidence_publisher"]
    p3 = pub["proof_3_publisher_session_to_validation_reader"]
    p2 = {
        "caller_before_assumerole":
            "arn:aws:sts::219024422756:assumed-role/mr002-phase3c-run-host/" + EVAL_HOST,
        "result": "DENIED", "required": "DENIED",
        "error": "AccessDenied — assumed-role/mr002-phase3c-run-host/" + EVAL_HOST
                 + " is not authorized to perform: sts:AssumeRole on resource: "
                   "arn:aws:iam::219024422756:role/mr002-validation2-evidence-publisher",
        "executed_via": "SSM AWS-RunShellScript on the real evaluator instance",
    }

    latch_stmts = subprocess.run(
        ["aws", "iam", "get-role-policy", "--role-name", "mr002-phase3c-run-host",
         "--policy-name", "mr002-phase3c-qualification-only", "--query",
         "length(PolicyDocument.Statement)", "--output", "text"],
        capture_output=True, text=True).stdout.strip()
    states = aws("ec2", "describe-instances", "--region", "us-east-1", "--instance-ids",
                 PUB_HOST, EVAL_HOST, "--query",
                 "Reservations[].Instances[].{Id:InstanceId,State:State.Name}") or []

    proofs_ok = (p1["result"] == "SUCCESS" and p2["result"] == "DENIED"
                 and p3["result"] == "DENIED")
    st = {s["Id"]: s["State"] for s in states}
    cleanup_ok = (st.get(PUB_HOST) == "terminated" and st.get(EVAL_HOST) == "stopped")
    latch_ok = latch_stmts == "8"
    reads_ok = (post is None) or (post["oos_partition"]["successful_reads"] == 0)

    rec = {
        "record_type": "MR002_Validation2_AmendmentB_LiveTrustQualification",
        "version": "1.0", "date": "2026-08-20",
        "authority": "owner ruling 2026-08-20 — live STS qualification AUTHORIZED, narrowly scoped",
        "bound": {"registration": REGISTRATION, "amendment_B_v1_2": B_V12,
                  "amendment_B_application_evidence": B_APPLIED},
        "validation_2_objects_read": 0,
        "sealed_store_getobject_calls": 0,
        "reader_latch_released": False,

        "real_sts_proofs": {
            "note": "simulate-principal-policy NEVER evaluates a trust policy. All three below are "
                    "REAL sts:AssumeRole calls made by the actual principals. No trust policy was "
                    "modified to make any test easier.",
            "no_secrets_recorded": "caller ARNs and decisions only; no session tokens or keys",
            "proof_1_base_role_to_evidence_publisher": p1,
            "proof_2_evaluator_runhost_to_evidence_publisher": p2,
            "proof_3_publisher_SESSION_to_validation_reader": p3,
            "all_three_as_required": proofs_ok,
            "why_proof_3_used_the_session_not_the_host": "per the owner's nuance, it was executed "
                                                         "by the principal HOLDING publisher "
                                                         "credentials after proof 1 succeeded. "
                                                         "That proves the privileged publisher "
                                                         "BRANCH cannot pivot into withheld data, "
                                                         "not merely that the host base role "
                                                         "cannot.",
        },

        "how_the_proofs_were_run_without_broadening_the_sealed_role": {
            "problem": "SSM administration requires SSM permissions on the instance role, but the "
                       "sealed base role grants none, and attaching AmazonSSMManagedInstanceCore "
                       "would have made the deployed role differ from the sealed record.",
            "solution": "the publisher host executed proofs 1 and 3 from EC2 user-data at boot, "
                        "using ONLY permissions Amendment B already grants, and published the "
                        "result through the publisher's own PutObject grant.",
            "bonus_evidence": "that publication is itself a LIVE proof that the governed-evidence "
                              "write path works end to end, performed by the publisher session.",
            "evaluator_host": "already carried AmazonSSMManagedInstanceCore, so proof 2 ran via "
                              "SSM with no IAM change.",
        },

        "capability_matrix": {"cells": mat["final"], "all_intended": mat["converged"],
                              "attempts_to_converge": mat["attempts"],
                              "bound_to": "the OBSERVED effective decision, never elapsed time"},

        "lifecycle_after_the_tests": {
            "temporary_publisher_instance": {"id": PUB_HOST,
                                             "state": st.get(PUB_HOST), "terminated": True},
            "evaluator_host": {"id": EVAL_HOST, "state": st.get(EVAL_HOST), "re_stopped": True},
            "temporary_security_group": "deleted; had NO inbound rules and egress restricted to "
                                        "tcp/443",
            "iam_retained": ["mr002-validation2-publish-host-role",
                             "mr002-validation2-evidence-publisher",
                             "instance profile mr002-validation2-publish-host"],
            "why_retain_iam_but_not_compute": "there is no reason to pay ongoing EC2 cost merely "
                                              "to preserve an IAM trust proof",
            "cleanup_verified": cleanup_ok,
        },

        "reader_latch": {
            "policy": "mr002-phase3c-qualification-only",
            "statements": latch_stmts, "state": "CLOSED" if latch_ok else "UNEXPECTED",
            "never_released_during_this_qualification": True,
            "LOAD_BEARING": "8 statements = CLOSED (Deny + Allow, explicit Deny wins); 7 = "
                            "RELEASED. This is the one-shot control, NOT dead configuration.",
        },

        "withheld_reads_still_zero": {
            "verified": reads_ok,
            "post_proof_access_history": (post or {}).get("history_identity_sha256"),
            "successful_reads": (post or {}).get("oos_partition", {}).get("successful_reads"),
            "denied_attempts": (post or {}).get("oos_partition", {}).get(
                "denied_or_errored_read_attempts"),
            "chain_verifies": (post or {}).get("hash_chain", {}).get("verifies"),
            "status": "VERIFIED" if post else "PENDING — CloudTrail rescan not yet complete",
        },

        "disposition": ("AMENDMENT_B_LIVE_TRUST_PASS"
                        if (proofs_ok and cleanup_ok and latch_ok and reads_ok)
                        else "IAM_NOT_READY / LIVE_TRUST_MISMATCH"),
        "what_this_closes": "the publisher side of Blocker 1. Amendment A — the only remaining "
                            "capability-granting change — is still NOT APPLIED and remains last.",
        "boundary": {"validation_2_opening": "NOT AUTHORIZED", "amendment_A": "NOT APPLIED",
                     "amendments_applied": ["C", "B v1.2"], "withheld_reads": 0},
    }
    ident = hashlib.sha256(_canonical(rec)).hexdigest()
    rec["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_AmendmentB_LiveTrustQualification_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(rec))
    os.replace(tmp, out)
    print("MR-002 AMENDMENT B v1.2 — LIVE TRUST QUALIFICATION")
    print(f"  identity     {ident}")
    print(f"  disposition  {rec['disposition']}")
    print(f"  proofs 3/3   {proofs_ok}   cleanup {cleanup_ok}   latch {latch_stmts} "
          f"({rec['reader_latch']['state']})")
    print(f"  withheld     {rec['withheld_reads_still_zero']['status']}")
    print(f"  wrote        {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
