"""MR-002 Cycle 2C — PROSPECTIVE AMENDMENT DRAFTS required before Validation-2 readiness.

Owner ruling 2026-08-20: draft the IAM amendments separately from the readiness qualification and
seal them BEFORE they are applied. ⛔ NOTHING HERE IS APPLIED. This record is a proposal.

Three amendments, not two. A and B are the IAM changes the owner specified. C was discovered while
scoping the evaluator re-qualification and is the same class of defect on the compute side: the
bound evaluator still implements the pre-redesignation architecture and would refuse the
Validation-2 window outright.

⛔ PROOF OBLIGATION CARRIED BY EVERY AMENDMENT
   No amendment may itself open Validation-2. Each is checked against that below, because a
   permission change that quietly grants a read IS an opening, whatever the record calls it.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
IAM_EVIDENCE = "55a81cba8a136ceda2efe96c82fb25dbd8c0f06d5e3b175a65d9af8e4292975f"
PREFLIGHT = "3810e071761a5100fe8cda6754488ebac5230f74b1b5e0f812ec53764d94436a"
PARTITION = "3b3910d00395d90189b94fd0f9901811b1813905f17219010b336c567cfa1296"
BUCKET = "workbench-mr002-sealed-219024422756"
EVID_BUCKET = "workbench-backups-219024422756"

V2 = [
    ("actions", "F6m6am6cBahBd95p41C1.aAVmYd8GuNG"),
    ("anchors", "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw"),
    ("etf_prices", "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj"),
    ("prices", "1ope9PR._oR303.EbZNGPVlIJRy.SZbA"),
    ("sic_observations", "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt"),
    ("universe", "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY"),
]


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_ProspectiveAmendmentDrafts",
    "version": "1.0",
    "date": "2026-08-20",
    "status": "DRAFT PROPOSAL — NOT APPLIED",
    "authorizes": "NOTHING. Applying any of these requires a separate owner ruling.",
    "bound": {"registration": REGISTRATION, "pre_amendment_iam_evidence": IAM_EVIDENCE,
              "structural_preflight": PREFLIGHT, "partition_identity": PARTITION},

    # ══ AMENDMENT A ═══════════════════════════════════════════════════════════════════════════
    "amendment_A_validation2_reader": {
        "target": "IAM role mr002-validation-reader, inline policy mr002-validation-only",
        "problem": "the deployed policy implements the PRE-redesignation architecture: it grants "
                   "GetObject on validation/* (now CONSUMED and permanently inadmissible) and "
                   "carries an explicit statement DenyOOSEntirelyIncludingListing denying s3:* on "
                   "oos/* (now the Validation-2 population). No deployed role can read "
                   "Validation-2.",
        "before": {
            "read validation/* (consumed)": "ALLOW",
            "read development/*, reference/*": "ALLOW",
            "read oos/* (= Validation-2)": "explicitDeny",
            "list validation/, development/, reference/": "ALLOW",
            "any write/delete in sealed custody": "explicitDeny",
            "write governing evidence": "implicitDeny",
        },
        "after_intended": {
            "read the SIX Validation-2 objects BY EXACT VersionId": "ALLOW",
            "read anything else under oos/": "explicitDeny",
            "read validation/* (consumed)": "explicitDeny  <- reversed; the partition is "
                                            "permanently inadmissible and must not be readable",
            "read development/*, reference/*": "ALLOW (unchanged)",
            "read the NEW OOS (post-seal accrual, wherever it lands)": "explicitDeny",
            "list": "minimum capability only",
            "any write/delete in sealed custody": "explicitDeny (unchanged)",
            "write governing evidence": "implicitDeny (unchanged — the reader never publishes)",
        },
        "exact_grant": {
            "action": ["s3:GetObjectVersion"],
            "why_not_GetObject_on_the_prefix": "the purpose is NOT 'the reader may read oos/'. It "
                                               "is 'the reader may consume exactly partition "
                                               f"{PARTITION[:16]}... when the one-shot opening is "
                                               "granted'. A wildcard on the historical prefix "
                                               "would grant more than the registered population "
                                               "merely because those six objects happen to live "
                                               "there.",
            "resources": [f"arn:aws:s3:::{BUCKET}/oos/{t}.parquet" for t, _ in V2],
            "version_pinning": {
                "mechanism": "Condition on s3:versionid per object",
                "version_ids": {t: v for t, v in V2},
                "⚠ caveat": "IAM cannot express 'this key AND this VersionId' as a single ARN. "
                            "The pin is a Condition block, and a policy statement per object is "
                            "the only form that binds each key to its own VersionId without "
                            "cross-permitting. Six statements, not one.",
            },
        },
        "explicit_denies_to_add": [
            f"Deny s3:* on arn:aws:s3:::{BUCKET}/validation/* — the consumed partition",
            f"Deny s3:GetObject on arn:aws:s3:::{BUCKET}/oos/* — so that anything under the "
            "prefix that is NOT one of the six version-pinned objects stays denied",
        ],
        "trust_model": "UNCHANGED. Assumable only by arn:aws:iam::219024422756:role/"
                       "mr002-phase3c-run-host via the aws:PrincipalArn condition. ⛔ Do NOT "
                       "change the trust form — the condition is correct as written.",
        "does_this_amendment_open_validation_2": {
            "answer": "NO",
            "proof": "the amendment changes CAPABILITY, not access. No GetObject is issued by "
                     "applying it. The role remains assumable only by the run-host, whose only "
                     "instance is stopped. And per the opening latch below, capability alone is "
                     "deliberately not sufficient to read.",
        },
    },

    # ══ THE OPENING LATCH ═════════════════════════════════════════════════════════════════════
    "opening_latch": {
        "owner_requirement": "mr002-validation-reader being structurally capable of reading the "
                             "six must NOT mean anyone can start reading whenever they assume it.",
        "existing_mechanism_found": {
            "what": "a governed IAM latch already exists and was exercised for the consumed "
                    "opening: an inline policy on the run-host path (mr002-phase3c-"
                    "qualification-only) whose statement count was mutated 7 -> 8 -> 7 -> 8 around "
                    "the opening window",
            "evidence": "MR002_Phase3C_ReconstructedExecutionCustodyEvidence_v1.0 records four "
                        "governed_latch_mutations on 2026-08-19 at 00:26:56, 00:27:08, 12:49:23 "
                        "and 12:56:40Z",
            "ruling_applied": "PRESERVE AND BIND IT. The owner said not to invent a redesign, and "
                              "one does not need inventing — the latch exists and is audited.",
        },
        "design": "the permanent reader policy grants capability; the LATCH grants permission to "
                  "exercise it, and is released only after the owner opening grant and re-applied "
                  "immediately afterwards. The permanent policy must never become the one-shot "
                  "authorization.",
        "⚠ measured_operational_hazard": {
            "fact": "a released deny latch takes a MEASURED ~286 seconds to reach STS",
            "consequence": "a released latch is NOT in force immediately. This already burned one "
                           "latch cycle on this program when a call was made at +5s.",
            "rule": "⛔ do NOT make 'wait 286 seconds' the proof. Poll the effective capability "
                    "until the intended matrix is OBSERVED, then proceed. Bind the observed "
                    "effective policy, never elapsed time.",
        },
    },
}

# ══ AMENDMENT B ═══════════════════════════════════════════════════════════════════════════════
REC["amendment_B_evidence_publisher"] = {
    "target": "a NEW IAM role, proposed name mr002-validation2-evidence-publisher",
    "problem": "no deployed role can write governing evidence. mr002-evaluator-publisher is an "
               "ECR IMAGE publisher (ecr:PutImage to mr002-evaluator-p5, plus GetObject on "
               "mr002/publish-staging/*). N1/N2/N3 evidence was published to S3 by the admin "
               "principal, so the reader/publisher capability separation the registration assumes "
               "is not deployed.",
    "owner_ruling_applied": "provision the new scoped role. Do NOT normalize admin-principal "
                            "publication into the Validation-2 design, and do NOT repurpose the "
                            "mr002-evaluator-publisher name — it is correctly described as what "
                            "it really is, an ECR image publisher, and keeps that meaning.",
    "before": {
        "any role that can write governing evidence": "NONE",
        "mr002-evaluator-publisher writes evidence": "implicitDeny",
        "actual N1/N2/N3 publication principal": "admin (unscoped)",
    },
    "after_intended": {
        "read Validation-1 / Validation-2 / new OOS raw stores": "explicitDeny (all three)",
        "modify or delete sealed inputs": "explicitDeny",
        "write to the Validation-2 evidence destination": "ALLOW",
        "overwrite arbitrary existing evidence": "DENY — create/append semantics only",
        "read back its own writes by VersionId for SHA-256 verification": "ALLOW",
        "raw-input access of any kind": "NONE",
    },
    "exact_grant": {
        "allow": [
            {"action": ["s3:PutObject"],
             "resource": f"arn:aws:s3:::{EVID_BUCKET}/artifacts/governed/"
                         "mr002-validation2-execution-evidence/1.0/*",
             "note": "write only into the designated Validation-2 evidence prefix"},
            {"action": ["s3:GetObject", "s3:GetObjectVersion"],
             "resource": f"arn:aws:s3:::{EVID_BUCKET}/artifacts/governed/"
                         "mr002-validation2-execution-evidence/1.0/*",
             "note": "supports the existing read-back / VersionId / SHA-256 verification flow "
                     "WITHOUT granting any raw-input access"},
        ],
        "deny": [
            {"action": "s3:*", "resource": [f"arn:aws:s3:::{BUCKET}/validation/*",
                                            f"arn:aws:s3:::{BUCKET}/oos/*"],
             "note": "the publisher must never see raw holdout content, consumed or otherwise"},
            {"action": ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutBucketPolicy",
                        "s3:PutBucketVersioning"],
             "resource": "*", "note": "no destruction of custody artifacts"},
            {"action": "sts:AssumeRole",
             "resource": "arn:aws:iam::219024422756:role/mr002-validation-reader",
             "note": "mirrors the existing DenyAssumingTheValidationReaderRole on the ECR "
                     "publisher — the separation must hold in both directions"},
        ],
        "append_only_note": "S3 has no native append. 'Create, never overwrite' is enforced by "
                            "bucket versioning plus the delete denies above: an overwrite creates "
                            "a new version and cannot destroy the pinned one, which is what the "
                            "custody model actually relies on.",
    },
    "trust_model": {
        "assumable_by": "the Validation-2 run host via instance profile, matching the existing "
                        "pattern",
        "⚠": "must NOT be assumable by the same principal that assumes the reader, or the "
             "separation is cosmetic",
    },
    "does_this_amendment_open_validation_2": {
        "answer": "NO",
        "proof": "the role is explicitly denied s3:* on both oos/* and validation/*. It cannot "
                 "read raw holdout content by construction, so provisioning it cannot expose a "
                 "withheld economic observation.",
    },
}

# ══ AMENDMENT C — discovered while scoping the evaluator re-qualification ═════════════════════
REC["amendment_C_evaluator_oos_boundary"] = {
    "discovered_during": "Blocker 3 scoping. Not an IAM issue — the same class of defect on the "
                         "COMPUTE side.",
    "target": "apps/backend/app/research/mr002/phase3c/__init__.py window constants, consumed by "
              "phase3c/replay.py:run_config_validation",
    "problem": {
        "constants": {"OOS_WINDOW_START": "2023-05-30", "OOS_WINDOW_END": "2026-07-01",
                      "comment_in_source": "'The sealed OOS window. Touching it is fatal, not "
                                           "advisory.'"},
        "behaviour": "run_config_validation raises IntegrityFailure(OOS_BOUNDARY_VIOLATION) for "
                     "any session >= OOS_WINDOW_START",
        "consequence": "Validation-2's SCORING-ELIGIBLE span is EXACTLY 2023-05-30 .. 2026-07-01. "
                       "The bound evaluator would replay the 69 formation sessions and then abort "
                       "at the first scoring-eligible session. It cannot score Validation-2 at "
                       "all.",
        "why_this_matters_beyond_the_bug": "the evaluator, like the IAM, still encodes the "
                                           "PRE-redesignation architecture. The role transfer was "
                                           "a governance act; it has not been propagated to "
                                           "either control surface.",
    },
    "⛔ the_wrong_fix": {
        "what": "run_config_validation already takes assert_oos_boundary: bool = True. Passing "
                "False would make Validation-2 run today.",
        "why_forbidden": "that is disabling a safety interlock to make a run succeed. The "
                         "interlock is not wrong — it is correctly enforcing a boundary that "
                         "governance has since MOVED. The fix is to move the boundary in a "
                         "registered amendment, not to switch off the check that enforces it.",
    },
    "after_intended": {
        "VALIDATION_WINDOW_START/END": "2023-02-17 / 2026-07-10 (the Validation-2 partition)",
        "SCORING_ELIGIBLE_FIRST/LAST": "2023-05-30 / 2026-07-01",
        "OOS_WINDOW_START": "the first eligible session STRICTLY AFTER the Cycle-2C seal, per the "
                            "registration's prospective new-OOS boundary",
        "the_interlock_itself": "UNCHANGED and still fatal. Only the date it guards moves.",
    },
    "corroboration_that_the_new_bounds_are_right": {
        "finding": "the CURRENT frozen constants 2023-05-30 / 2026-07-01 are exactly ordinals 70 "
                   "and 844 of the 850-session Validation-2 window, independently recomputed by "
                   f"the structural preflight {PREFLIGHT[:16]}...",
        "significance": "these constants were frozen long before Cycle 2C, from the OOS window's "
                        "own 69-formation / 6-realization arithmetic. That the preflight "
                        "reproduces them exactly is NON-CIRCULAR confirmation of the transferred "
                        "fold geometry.",
        "derived_fold_labels": [
            {"fold": 1, "first": "2023-05-30", "last": "2024-01-09", "sessions": 155},
            {"fold": 2, "first": "2024-01-10", "last": "2024-08-21", "sessions": 155},
            {"fold": 3, "first": "2024-08-22", "last": "2025-04-04", "sessions": 155},
            {"fold": 4, "first": "2025-04-07", "last": "2025-11-14", "sessions": 155},
            {"fold": 5, "first": "2025-11-17", "last": "2026-07-01", "sessions": 155},
        ],
        "how_these_labels_were_obtained": "value-blind, from the session calendar via the "
                                          "authorized custodian path. Zero GetObject against the "
                                          "six. Deriving them BEFORE the opening is stronger than "
                                          "emitting them at open time, because there is no "
                                          "opportunity to tune them after seeing results.",
    },
    "does_this_amendment_open_validation_2": {
        "answer": "NO",
        "proof": "it changes constants in source. It issues no read, and the IAM latch and the "
                 "reader policy still deny the six objects independently of it.",
    },
}

REC["propagation_verification_procedure"] = {
    "rule": "bind the OBSERVED EFFECTIVE POLICY, never elapsed time",
    "steps": [
        "1. apply the approved policies; record the IAM policy identities and version ids",
        "2. wait for propagation - do NOT treat any fixed duration as the proof",
        "3. repeat simulate-principal-policy until the INTENDED matrix is observed; record the "
        "polling series, including the transitional decisions, not only the final one",
        "4. perform the real AssumeRole from the authorized run-host path, proving ASSUMABILITY",
        "5. prove post-assumption capability with non-content tests or a sentinel; keep "
        "assumability and authorization-after-assumption as SEPARATE fields",
        "6. still perform ZERO GetObject against the six before the opening grant",
    ],
    "iam_pass_requires_both": "a role can be assumable but overprivileged, or perfectly scoped "
                              "but not assumable. Neither leg alone is an IAM PASS.",
    "sentinel_caution": "if a sentinel object is used, it must sit under the SAME resource policy "
                        "as the six, or it proves nothing about them. It must NOT be written into "
                        "the oos/ prefix, because that mutates the sealed store and would appear "
                        "in the access history as a write to the partition being certified.",
}

REC["combined_proof_no_amendment_opens_validation_2"] = {
    "A": "capability change only; no read issued; reader assumable only by the run-host, whose "
         "only instance is stopped; the opening latch remains applied",
    "B": "explicitly denied s3:* on oos/* and validation/*; cannot read raw holdout content by "
         "construction",
    "C": "source constants only; issues no read; IAM denies the six independently",
    "joint": "even with ALL THREE applied, reading the six still requires (a) the run-host "
             "instance started, (b) the reader assumed, and (c) the opening latch released by the "
             "owner. Three independent gates remain.",
}

REC["ordering_recommendation"] = {
    "sequence": ["C (source constants — no AWS surface touched)",
                 "B (new role — additive, denies raw access by construction)",
                 "A (reader policy — the only one that grants any read capability, applied last)"],
    "why": "apply the least-privileged-impact change first and the capability-granting one last, "
           "so that at every intermediate state the six remain unreadable by every principal.",
}

REC["what_this_record_does_NOT_do"] = [
    "apply any policy or source change",
    "open Validation-2",
    "authorize starting instance i-00c1034f7026db45e",
    "supersede the pre-amendment IAM evidence, which is preserved immutably",
]
REC["boundary"] = {"validation_2_opening": "NOT AUTHORIZED",
                   "validation_2_bytes_read": 0,
                   "amendments_applied": 0}


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ProspectiveAmendmentDrafts_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 CYCLE 2C — PROSPECTIVE AMENDMENT DRAFTS (NOT APPLIED)")
    print(f"  identity   {ident}")
    print(f"  status     {REC['status']}")
    print("  amendments A (reader policy), B (evidence publisher), C (evaluator OOS boundary)")
    print(f"  applied    {REC['boundary']['amendments_applied']}")
    print(f"  wrote      {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
