"""MR-002 Cycle 2C — AMENDMENT B v1.2. Trust/assumption mechanism ONLY.

Owner ruling 2026-08-20: B v1.1 is substantively correct but mixes two AWS patterns. Issue v1.2
correcting ONLY the trust semantics; do not alter the permissions or the evidence-flow topology.

⛔ WHAT CHANGES: the trust policy of the evidence-publisher role, plus the introduction of the
publisher-host BASE role that assumes it.
⛔ WHAT DOES NOT CHANGE: every Allow, every Deny, the staging handoff, the sealed-store denial, the
reader/publisher mutual assume denials, and the standing of the run-host latch. v1.1's permission
set is carried forward BYTE-FOR-BYTE in intent.

THE DEFECT
    v1.1 gave the publisher role `Principal: {"Service": "ec2.amazonaws.com"}` -- the DIRECT
    instance-profile pattern, where the EC2 service assumes the role and delivers credentials via
    IMDS and the application never calls sts:AssumeRole. But v1.1 also registered the proof as
    `publish-host -> AssumeRole evidence-publisher = allowed` and
    `evaluator-host -> AssumeRole evidence-publisher = fail`. Those are STS proofs against a
    non-STS trust. The policy and the proof described different mechanisms, so the proof could
    not have meant what it claimed.

⭐ THE CORRECT FORM ALREADY EXISTS IN THIS DEPLOYMENT
    Both patterns are live today and the distinction is exactly the owner's:
      mr002-validation-reader   TWO-STAGE. Principal = account root, Condition
                                aws:PrincipalArn = mr002-phase3c-run-host. The run-host base role
                                (which itself has ec2.amazonaws.com trust) calls sts:AssumeRole
                                into the reader.
      mr002-evaluator-publisher DIRECT. Principal = ec2.amazonaws.com, credentials via instance
                                profile, no AssumeRole call.
    v1.1 borrowed the ECR publisher's TRUST form and the reader's PROOF form. v1.2 adopts the
    READER's form throughout, because the registered proof is an AssumeRole proof and because
    mirroring an already-validated deployed control is better than inventing a third shape.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
SUPERSEDES_V11 = "a2e6795e50f91c7781dd727fb0b3242497f83673d872346dad632706010c9917"
SUPERSEDES_V10 = "a259b0dc2a1aa1e51de24ffdf06ee7b9f21cec618128d1ed5d77e12b8185d758"
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
ACCT = "219024422756"
ROOT = f"arn:aws:iam::{ACCT}:root"
BASE = f"arn:aws:iam::{ACCT}:role/mr002-validation2-publish-host-role"
PUBLISHER = f"arn:aws:iam::{ACCT}:role/mr002-validation2-evidence-publisher"
READER = f"arn:aws:iam::{ACCT}:role/mr002-validation-reader"
RUNHOST = f"arn:aws:iam::{ACCT}:role/mr002-phase3c-run-host"


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_AmendmentB_TrustCorrection",
    "version": "1.2",
    "date": "2026-08-20",
    "status": "DRAFT PROPOSAL - NOT APPLIED",
    "scope": "TRUST / ASSUMPTION MECHANISM ONLY. Permissions and evidence-flow topology are "
             "carried forward from v1.1 unchanged.",
    "supersedes": {
        "v1.1": {"identity_sha256": SUPERSEDES_V11, "preserved_unmodified": True},
        "v1.0": {"identity_sha256": SUPERSEDES_V10, "preserved_unmodified": True},
        "why": "each is the INPUT to the next. Editing either to look correct would destroy the "
               "before/after audit structure.",
    },
    "authorizes": "NOTHING. Applying this requires the owner's separate go-ahead.",
    "bound_registration": REGISTRATION,

    "defect_being_corrected": {
        "what_v1_1_said": {
            "trust": "Principal {\"Service\": \"ec2.amazonaws.com\"} constrained to an instance "
                     "profile - the DIRECT pattern, credentials via IMDS, no AssumeRole call",
            "proof": "publish-host -> AssumeRole evidence-publisher = allowed; evaluator-host -> "
                     "AssumeRole evidence-publisher = fail - STS proofs",
        },
        "why_it_is_wrong": "an STS AssumeRole proof against a non-STS trust. Under the direct "
                           "pattern the application on the publisher host never calls AssumeRole "
                           "into that role at all, so the registered proof could not have meant "
                           "what it claimed - and the evaluator-host FAIL would have been "
                           "trivially true for the wrong reason.",
        "found_by": "owner review. Recorded plainly.",
        "severity": "mechanical, not architectural. The separation v1.1 describes is right; the "
                    "mechanism named for enforcing it was not.",
    },

    "chosen_architecture": {
        "shape": "TWO-STAGE, mirroring the deployed mr002-validation-reader",
        "chain": [
            "mr002-validation2-publish-host  (EC2 instance, distinct from the evaluator host)",
            "  -> instance profile ->  mr002-validation2-publish-host-role  (BASE role, trusts "
            "ec2.amazonaws.com)",
            "  -> sts:AssumeRole   ->  mr002-validation2-evidence-publisher",
            "  -> governed evidence only",
        ],
        "why_this_one": "the registered proof is an AssumeRole proof, so the trust must be an "
                        "AssumeRole trust. It also mirrors an ALREADY-VALIDATED deployed control "
                        "rather than inventing a third shape.",
        "symmetry_with_the_reader": {
            "reader": "run-host base role (ec2 trust) -> AssumeRole -> mr002-validation-reader, "
                      "whose trust is Principal=account-root + Condition aws:PrincipalArn="
                      "mr002-phase3c-run-host",
            "publisher": "publish-host base role (ec2 trust) -> AssumeRole -> evidence-publisher, "
                         "whose trust is Principal=account-root + Condition aws:PrincipalArn="
                         "mr002-validation2-publish-host-role",
            "note": "identical form on both branches, so a reviewer reads one pattern, not two.",
        },
        "⛔ do_not_change_the_reader_trust_form": "aws:PrincipalArn IS the role ARN there and the "
                                                 "form is correct. It is copied, not corrected.",
    },

    "trust_policies": {
        "mr002-validation2-publish-host-role (BASE)": {
            "trust": {"Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"},
            "attached_to": "instance profile mr002-validation2-publish-host, on a host DISTINCT "
                           "from the evaluator",
            "allow": [{"Sid": "AssumeTheEvidencePublisherOnly", "Action": "sts:AssumeRole",
                       "Resource": PUBLISHER}],
            "deny": [
                {"Sid": "DenyAssumingTheValidationReaderRole", "Action": "sts:AssumeRole",
                 "Resource": READER},
                {"Sid": "DenyAllAccessToTheSealedStore", "Action": "s3:*",
                 "Resource": ["arn:aws:s3:::workbench-mr002-sealed-219024422756",
                              "arn:aws:s3:::workbench-mr002-sealed-219024422756/*"]},
            ],
            "note": "the base role carries NO data capability of its own. Its only power is to "
                    "assume the publisher.",
        },
        "mr002-validation2-evidence-publisher": {
            "trust": {"Principal": {"AWS": ROOT}, "Action": "sts:AssumeRole",
                      "Condition": {"StringEquals": {"aws:PrincipalArn": BASE}}},
            "⚠ what_this_replaces": "v1.1's Principal {\"Service\": \"ec2.amazonaws.com\"}",
            "why_the_condition_is_load_bearing": "Principal=account-root alone would let ANY "
                                                 "principal in the account assume it. The "
                                                 "aws:PrincipalArn condition is the entire "
                                                 "control, exactly as it is for the reader.",
            "run_host_is_absent_from_the_allow": True,
            "permissions": "UNCHANGED from v1.1 - see permissions_carried_forward below",
        },
    },

    "permissions_carried_forward_unchanged_from_v1_1": {
        "evidence_publisher_allow": ["GetObject on the evidence staging prefix (read the handoff)",
                                     "PutObject on the governed Validation-2 evidence prefix",
                                     "GetObject/GetObjectVersion on its OWN publications, for the "
                                     "VersionId + SHA-256 read-back flow"],
        "evidence_publisher_deny": ["s3:* on the ENTIRE sealed store, so a future new-OOS prefix "
                                    "cannot be forgotten",
                                    "sts:AssumeRole on mr002-validation-reader",
                                    "delete/lifecycle/bucket-policy mutations",
                                    "iam:* self-widening"],
        "evaluator_side": ["PutObject-only to the evidence staging prefix",
                           "DenyAssumingTheEvidencePublisherRole",
                           "existing DenyAllAccessToTheSealedStore unchanged"],
        "handoff": "evaluator PutObject-only -> staging -> publisher GetObject-only. Raw content, "
                   "sealed-store credentials and reader session credentials never cross.",
        "run_host_latch": "DenyAssumingTheValidationReaderRole on the run host is UNCHANGED and is "
                          "LOAD-BEARING CONFIGURATION, not technical debt. It is the opening "
                          "latch: the standing state is unable to assume the reader, and the "
                          "owner opening grant causes a governed latch mutation that temporarily "
                          "changes that effective capability. ⛔ A future security cleanup must "
                          "NOT remove it as dead configuration.",
    },

    "live_proof_now_well_defined": {
        "why_it_is_meaningful_only_after_this_correction": "under v1.1's trust these AssumeRole "
                                                           "calls were not the mechanism in use, "
                                                           "so neither a pass nor a fail would "
                                                           "have evidenced the separation.",
        "required_results": {
            "publish-host base role -> AssumeRole evidence-publisher": "SUCCESS (real STS call)",
            "evaluator run-host -> AssumeRole evidence-publisher": "DENIED (real STS call, must "
                                                                   "FAIL)",
            "publish-host base role -> AssumeRole validation-reader": "DENIED",
            "evidence-publisher -> AssumeRole validation-reader": "DENIED",
            "evidence-publisher -> GetObject sealed oos/*": "explicitDeny",
            "evidence-publisher -> GetObject sealed validation/*": "explicitDeny",
            "evidence-publisher -> PutObject governed evidence prefix": "allowed",
            "validation-reader -> PutObject governed evidence prefix": "implicit or explicit deny",
        },
        "⚠ trust_cannot_be_simulated": "simulate-principal-policy NEVER evaluates a trust policy. "
                                       "The first three rows above MUST be real sts:AssumeRole "
                                       "attempts. A passing simulation is not evidence for them.",
        "propagation": "bind the OBSERVED EFFECTIVE POLICY, never elapsed time. Poll until the "
                       "intended matrix is observed, recording transitional decisions too.",
    },

    "does_this_amendment_open_validation_2": {
        "answer": "NO",
        "proof": "no permission is added or widened by v1.2 - only the trust mechanism is "
                 "corrected. The publisher remains denied s3:* on the entire sealed store and "
                 "denied assuming the reader, and the run-host latch is untouched.",
    },
    "boundary": {"validation_2_opening": "NOT AUTHORIZED", "validation_2_bytes_read": 0,
                 "amendments_applied": 1, "applied": ["C"]},
}


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_AmendmentB_TrustCorrection_v1.2.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 AMENDMENT B v1.2 - TRUST CORRECTION (NOT APPLIED)")
    print(f"  identity        {ident}")
    print(f"  supersedes v1.1 {SUPERSEDES_V11}")
    print("  scope           trust/assumption mechanism ONLY; permissions unchanged")
    print(f"  applied         {REC['boundary']['applied']}")
    print(f"  wrote           {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
