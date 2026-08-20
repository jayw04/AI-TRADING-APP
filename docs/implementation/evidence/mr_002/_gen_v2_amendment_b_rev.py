"""MR-002 Cycle 2C — AMENDMENT B, REVISED (v1.1). Supersedes Amendment B of the v1.0 package.

Owner ruling 2026-08-20: B is NOT YET APPROVED; the trust topology must be corrected before any
IAM change is applied. The v1.0 draft asserted two things that cannot both hold — that the new
publisher is "assumable by the Validation-2 run host via instance profile" AND that it "must NOT be
assumable by the same principal that assumes the reader". The run host IS the principal that
assumes the reader, so one compromised or erroneous run-host session could obtain both capabilities
sequentially. That was a real defect in my draft, not a wording problem.

⛔ The v1.0 record is preserved UNMODIFIED as the superseded input to this revision. Editing it to
look correct would destroy the before/after audit structure, the same reason N1's pre-ruling
verdict was committed unchanged.

THE REQUIRED INVARIANT (owner's graph)
                     ┌─> validation-reader ────> sealed Validation-2 input
    run/evaluator ───┤
                     └─X─> evidence-publisher

    publisher principal ──> evidence-publisher ──> governed evidence
                        └─X─> validation-reader

    No single ordinary execution principal may walk both branches.

⭐ THE TOPOLOGY ALREADY EXISTS AND IS NOT INVENTED HERE.
The deployed mr002-phase3c-run-host policy already carries DenyAssumingTheValidationReaderRole and
DenyAllAccessToTheSealedStore, and already hands off to a publisher through a write-only staging
prefix (StagePublishArtifactWriteOnly -> s3:PutObject on mr002/publish-staging/*), which the ECR
publisher reads with ReadTheStagedPublishArtifactOnly. That is precisely the separation the owner
asked for, already proven in the image-publish path. This revision MIRRORS it for evidence rather
than designing a second mechanism.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
SUPERSEDES = "a259b0dc2a1aa1e51de24ffdf06ee7b9f21cec618128d1ed5d77e12b8185d758"
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
IAM_EVIDENCE = "55a81cba8a136ceda2efe96c82fb25dbd8c0f06d5e3b175a65d9af8e4292975f"
SEALED = "workbench-mr002-sealed-219024422756"
BACKUPS = "workbench-backups-219024422756"
STAGING = f"arn:aws:s3:::{BACKUPS}/mr002/validation2-evidence-staging/*"
GOVERNED = (f"arn:aws:s3:::{BACKUPS}/artifacts/governed/"
            "mr002-validation2-execution-evidence/1.0/*")
READER = "arn:aws:iam::219024422756:role/mr002-validation-reader"
PUBLISHER = "arn:aws:iam::219024422756:role/mr002-validation2-evidence-publisher"


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_AmendmentB_Revised",
    "version": "1.1",
    "date": "2026-08-20",
    "status": "DRAFT PROPOSAL - NOT APPLIED",
    "supersedes": {"record": "MR002_Validation2_ProspectiveAmendmentDrafts_v1.0 -> amendment_B",
                   "identity_sha256": SUPERSEDES,
                   "preserved_unmodified": True,
                   "why": "it is the INPUT to this revision. Editing it to look correct would "
                          "destroy the before/after audit structure."},
    "defect_being_corrected": {
        "what_the_v1_0_draft_said": ["the publisher is assumable by the Validation-2 run host via "
                                     "instance profile",
                                     "it must NOT be assumable by the same principal that assumes "
                                     "the reader"],
        "why_those_cannot_both_hold": "mr002-phase3c-run-host IS the principal that assumes "
                                      "mr002-validation-reader. Granting it the publisher too "
                                      "means one compromised or erroneous run-host session can "
                                      "obtain both capabilities sequentially.",
        "severity": "the bucket policies would still stop the publisher READING raw data, which is "
                    "worth having, but that is not the reader/publisher PRINCIPAL separation the "
                    "registration claims. The claim would have been stronger than the control.",
        "found_by": "owner review, not by me. Recorded plainly.",
    },
    "authorizes": "NOTHING. Applying this requires a separate owner ruling.",
    "bound": {"registration": REGISTRATION, "pre_amendment_iam_evidence": IAM_EVIDENCE},

    "principal_separation": {
        "evaluator_branch": {
            "principal": "mr002-phase3c-run-host (instance profile on the EVALUATOR host)",
            "may_assume": ["mr002-validation-reader"],
            "must_be_denied_assuming": [PUBLISHER],
            "sealed_store": "Deny s3:* (already deployed as DenyAllAccessToTheSealedStore) - the "
                            "run host reaches sealed input ONLY through the reader",
            "evidence_capability": "s3:PutObject on the staging prefix ONLY. Write-only: it cannot "
                                   "read back, list, or publish.",
        },
        "publisher_branch": {
            "principal": "a NEW, SEPARATE instance profile mr002-validation2-publish-host, on a "
                         "host distinct from the evaluator",
            "may_assume": [PUBLISHER],
            "must_be_denied_assuming": [READER],
            "sealed_store": "Deny s3:* on the whole sealed store, all prefixes",
            "must_not_be": "the same instance profile, the same instance, or any principal that "
                           "can reach the reader. If the two branches share a principal the "
                           "separation is cosmetic.",
        },
        "handoff": {
            "mechanism": "a write-only staging prefix, mirroring the deployed image-publish path",
            "staging_prefix": STAGING,
            "evaluator": "s3:PutObject only",
            "publisher": "s3:GetObject only",
            "what_crosses": "the evaluator's COMPLETED evidence package",
            "what_never_crosses": "raw Validation-2 content, sealed-store credentials, and reader "
                                  "session credentials",
        },
    },

    "new_role_mr002_validation2_evidence_publisher": {
        "trust_policy": {
            "principal": {"Service": "ec2.amazonaws.com"},
            "constrained_to": "the mr002-validation2-publish-host instance profile via an "
                              "aws:SourceArn / instance-profile condition, so the EVALUATOR host "
                              "cannot assume it even though both are EC2",
            "why_the_condition_is_load_bearing": "a bare ec2.amazonaws.com trust would let ANY "
                                                 "instance in the account assume this role, "
                                                 "including the evaluator host. That would "
                                                 "silently re-create the exact defect this "
                                                 "revision exists to fix.",
        },
        "allow": [
            {"Sid": "ReadTheStagedEvidencePackageOnly", "Action": ["s3:GetObject"],
             "Resource": STAGING},
            {"Sid": "PublishGovernedValidation2Evidence", "Action": ["s3:PutObject"],
             "Resource": GOVERNED},
            {"Sid": "ReadBackOwnPublicationForVerification",
             "Action": ["s3:GetObject", "s3:GetObjectVersion"], "Resource": GOVERNED,
             "note": "supports the proven VersionId + SHA-256 read-back flow WITHOUT any "
                     "raw-input access"},
        ],
        "deny": [
            {"Sid": "DenyAllAccessToTheSealedStore", "Action": "s3:*",
             "Resource": [f"arn:aws:s3:::{SEALED}", f"arn:aws:s3:::{SEALED}/*"],
             "note": "covers Validation-1, Validation-2 and any future new-OOS prefix in one "
                     "statement, so a later prefix cannot be forgotten"},
            {"Sid": "DenyAssumingTheValidationReaderRole", "Action": "sts:AssumeRole",
             "Resource": READER},
            {"Sid": "DenyDestroyingPublishedEvidence",
             "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutBucketPolicy",
                        "s3:PutBucketVersioning", "s3:PutBucketLifecycleConfiguration"],
             "Resource": "*"},
            {"Sid": "DenyEditingTheCredentialReleaseControl",
             "Action": ["iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:AttachRolePolicy",
                        "iam:CreateRole", "iam:DeleteRolePolicy"], "Resource": "*",
             "note": "mirrors the deployed run-host statement - a principal must not be able to "
                     "widen its own or another role's grant"},
        ],
        "create_not_overwrite": "S3 has no native append. 'Create, never destroy' is enforced by "
                                "bucket versioning plus DenyDestroyingPublishedEvidence: an "
                                "overwrite creates a NEW version and cannot destroy the pinned "
                                "one, which is what the custody model actually relies on.",
    },

    "companion_change_to_the_evaluator_side": {
        "target": "mr002-phase3c-run-host inline policy",
        "add_deny": [{"Sid": "DenyAssumingTheEvidencePublisherRole", "Effect": "Deny",
                      "Action": "sts:AssumeRole", "Resource": PUBLISHER}],
        "add_staging_write": [{"Sid": "StageValidation2EvidenceWriteOnly", "Effect": "Allow",
                               "Action": "s3:PutObject", "Resource": STAGING}],
        "unchanged": ["DenyAssumingTheValidationReaderRole - this is the OPENING LATCH and is "
                      "released only under an owner opening grant, then re-applied",
                      "DenyAllAccessToTheSealedStore",
                      "DenyEditingTheCredentialReleaseControl"],
        "CAUTION": "the existing DenyAssumingTheValidationReaderRole on the run host is NOT a "
                   "mistake to clean up. It is the latch. Do not remove it as part of this "
                   "amendment.",
    },

    "verification_that_the_invariant_holds": {
        "method": "iam simulate-principal-policy on sts:AssumeRole for BOTH directions, plus the "
                  "sealed-store matrix, after propagation is observed",
        "required_results": {
            "run-host -> AssumeRole validation-reader": "explicitDeny in the LATCHED state",
            "run-host -> AssumeRole evidence-publisher": "explicitDeny ALWAYS",
            "publish-host -> AssumeRole validation-reader": "explicitDeny ALWAYS",
            "publish-host -> AssumeRole evidence-publisher": "allowed",
            "evidence-publisher -> GetObject sealed oos/*": "explicitDeny",
            "evidence-publisher -> GetObject sealed validation/*": "explicitDeny",
            "evidence-publisher -> PutObject governed evidence": "allowed",
            "validation-reader -> PutObject governed evidence": "implicitDeny or explicitDeny",
        },
        "trust_is_not_covered_by_simulation": "simulate-principal-policy never evaluates a trust "
                                              "policy. The instance-profile condition on the "
                                              "publisher trust MUST be proven by a real AssumeRole "
                                              "attempt from the EVALUATOR host, which must FAIL. A "
                                              "passing simulation is not evidence for that cell.",
    },

    "does_this_amendment_open_validation_2": {
        "answer": "NO",
        "proof": "the publisher is denied s3:* on the entire sealed store and denied assuming the "
                 "reader. It cannot reach raw holdout content by any path. Provisioning it issues "
                 "no read, and the opening latch on the evaluator branch is untouched.",
    },
    "boundary": {"validation_2_opening": "NOT AUTHORIZED", "validation_2_bytes_read": 0,
                 "amendments_applied": 0},
}


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_AmendmentB_Revised_v1.1.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 AMENDMENT B - REVISED v1.1 (NOT APPLIED)")
    print(f"  identity    {ident}")
    print(f"  supersedes  {SUPERSEDES}")
    print(f"  applied     {REC['boundary']['amendments_applied']}")
    print(f"  wrote       {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
