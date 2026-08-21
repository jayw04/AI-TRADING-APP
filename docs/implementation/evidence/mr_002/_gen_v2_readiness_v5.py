"""Validation-2 readiness qualification v5.0 — carries the ELEVENTH GATE.

Supersedes v4.0, which reported READY and was, on its own terms, correct: every gate it registered
did pass. The 2026-08-21 opening still failed pre-read, because the gate set had no member that
evaluated the RESOURCE-side authorization decision. v5.0 adds that gate rather than restating the
old set more loudly.

This record does NOT authorize an opening.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_ReadinessQualification",
    "version": "5.0",
    "date": "2026-08-21",
    "supersedes": "MR002_Validation2_ReadinessQualification_v4.0 "
                  "(6f0e7b3e698c867c1b2697e564be17d9f827b77c9a0207415ea58e941ec62203), preserved "
                  "unmodified — it reported READY and every gate it registered did pass. It was "
                  "not wrong about its gates; it was incomplete in its gate SET.",
    "what_changed": "an ELEVENTH gate, the resource-side counterpart to Amendment A, plus the "
                    "sealed-store resource-policy repair it verifies. Everything else is "
                    "re-verified under the bound runtime, not carried forward.",
    "occasioned_by": "MR002_Validation2_OpeningPreReadFailure_v1.0 / "
                     "d1303229a26b80ac5b02255e0c81211d02a296cff9151464635b71ac071f5059",
}

REC["binds"] = {
    "readiness_v4_0_superseded":
        "6f0e7b3e698c867c1b2697e564be17d9f827b77c9a0207415ea58e941ec62203",
    "pre_read_failure": "d1303229a26b80ac5b02255e0c81211d02a296cff9151464635b71ac071f5059",
    "resource_policy_amendment_R":
        "MR002_Validation2_SealedStoreResourcePolicyAmendment_v1.0",
    "sealed_store_bucket_policy_BEFORE":
        "b529bb26c5d542b255adf8c94349609180bd4599108debbd8fac693567437baf",
    "sealed_store_bucket_policy_AFTER":
        "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5",
    "amendment_A_v1_2_identity_side_unchanged":
        "d7b5cf2be0d4523967ff63d121341572c3b111ac5085e04f9c4a7a2b4e25eedd",
    "governed_reader": "arn:aws:iam::219024422756:role/mr002-validation-reader",
    "dependency_amendment": "12877b32704da2bf4e13cd60599b194789a28d7da4ff9b97584b140ec0f3f86d",
    "bundle_content_identity":
        "26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1",
    "execution_package": "e22c4d4f9e1007340d7c30385af0ee6a95c0c0be8a1a8cd8b4a4e8140c832d23",
    "deployment_artifact": "aab2e7a56acf8dcc15e12e5345110c92e0ab43f04cbafe2e5380c359738e4b93",
    "deployed_live_aggregate":
        "6841756f8026932370531fde49de5dfccda1c2cee964174f1eec1901e3660ae9",
    "execution_closure": "3c32bda64dd1cd6efe306bcf7e69e56a78c53b3bd58076d7735ddbe2d516df3b",
    "launcher": "12b1a0c4899d79a54322664ec82b2c9193b32212891eb59e61caf15f4ad9ce3a",
    "production_registry": "bbd330b7a41e338353ebd061707b5f633937e0cc82cdd97b794e72021657ae2e",
    "image_config_digest":
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
    "host": "i-00c1034f7026db45e",
    "source_commit": "740a1420ad55c2c2cb74c681fd49b1da2f3c11b2",
    "head_authorization_probe_instrument":
        "448804f139da29a58587a39a335c4c6df5b2d6a404d797f466631bc0433c1bd3",
    "resource_policy_gate_script": "apps/backend/scripts/mr002_v2_resource_policy_gate.py",
}

REC["bound_runtime_invocation"] = {
    "source_tree_mount": "-v /opt/mr002/phase3c_src:/work:ro",
    "dependency_mount": "-v /opt/mr002/deps_v12:/opt/mr002/deps:ro",
    "pythonpath": "/work/apps/backend:/opt/mr002/deps",
    "frozen_thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                          "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                          "OPENBLAS_CORETYPE": "HASWELL"},
    "docker_flags_passed_inline": True,
    "host_filesystem_mutated": False,
}

# ── gates 1-10, re-run in full today under the bound runtime ─────────────────────────────────
REC["gates_1_to_10"] = {
    "verdict": "PASS — 14/14",
    "evidence": "MR002_Validation2_PreOpeningCheck_2026-08-21.json",
    "evidence_sha256": "0b035f179173d0feb8430be2cd237f80b02767b1415564f96e2b38323a0a9b81",
    "re_run_after_the_failed_opening": True,
    "reproducibility": "the qualification was executed twice today — 11:57Z before the opening "
                       "and 14:09Z after it, across a full host stop/start — and produced a "
                       "BYTE-IDENTICAL result document both times. That is evidence the "
                       "qualification is deterministic AND that the deployed state is unchanged, "
                       "which is stronger than either claim alone.",
    "items": {
        "deployed live aggregate": "PASS — 6841756f..., 277 files, recomputed by the aggregate "
                                   "script that ships inside the archive",
        "execution closure": "PASS — 25/25 members hash-match the deployed tree, identity "
                             "re-derives to 3c32bda6..., 0 CRLF members",
        "launcher": "PASS — 12b1a0c4...",
        "production registry": "PASS — bbd330b7..., registry_role VALIDATION2_PRODUCTION",
        "mounted bundle content identity": "PASS — 26e23049..., 2954 files, computed INSIDE the "
                                           "container at /opt/mr002/deps",
        "image config digest": "PASS — sha256:770553ae...",
        "aws import chain from the mount": "PASS — boto3/botocore 1.43.70, dateutil "
                                           "2.9.0.post0, six 1.17.0",
        "governed modules": "PASS — 11/11, every one resolved under the mounted tree",
        "numerical stack still from the IMAGE": "PASS — numpy 2.2.6, scipy 1.18.0, quadprog, "
                                                "piqp 0.6.3, duckdb 1.1.3; pyarrow from the "
                                                "mount at 54d0e4db..., 758 files",
        "Stage-3 frozen routing": "PASS — PRIMARY_SOLVER_ID QUADPROG_SQRT, FALLBACK_SOLVER_ID "
                                  "PIQP_P2, zero QUADPROG_RAW references in the cascade",
        "frozen thread environment in force": "PASS",
        "window constants and frozen folds": "PASS",
        "OOS boundary interlock fires": "PASS — IntegrityFailure on a session past the window end",
    },
}

# ── THE ELEVENTH GATE ────────────────────────────────────────────────────────────────────────
REC["gate_11"] = {
    "name": "resource_policy_admits_only_the_governed_validation2_reader_to_the_registered_"
            "validation2_population",
    "why_it_is_separate_from_gate_10": "gate 10 covers launcher and manifest coverage. This is a "
            "DISTINCT boundary: a complete, sealed, byte-verified IDENTITY-side amendment says "
            "nothing whatever about the RESOURCE side, because an explicit Deny in a resource "
            "policy defeats any identity Allow. Folding it into gate 10 would hide exactly the "
            "surface that failed.",
    "why_hashing_was_never_going_to_find_it": "the bucket policy that refused the opening was "
            "BYTE-IDENTICAL to its tracked copy. Hashing proves a document has not drifted; it "
            "cannot prove the document says the right thing. The gate therefore EVALUATES "
            "combined bucket+identity authorization semantics.",
    "static_half": {
        "verdict": "PASS",
        "checks": 13,
        "authorization_matrix": "28/28",
        "evidence": "MR002_Validation2_ResourcePolicyGate_2026-08-21.json",
        "binds": {
            "live_bucket_policy_identity":
                "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5",
            "governed_reader_arn": "arn:aws:iam::219024422756:role/mr002-validation-reader",
            "oos_resource_scope":
                "arn:aws:s3:::workbench-mr002-sealed-219024422756/oos/*",
            "placeholder_absent": "no 'NOT-YET-PROVISIONED' fragment anywhere in the document",
            "current_role_sid":
                "DenyValidation2ReadsToEveryPrincipalButGovernedValidationReader",
            "stale_sid_gone": "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader",
            "identity_side_unchanged": "Amendment A v1.2, d7b5cf2b...",
        },
        "mutation_control": "the evaluator was run against the ARCHIVED PRE-AMENDMENT document "
                            "and returned DENY for the governed reader. A checker that cannot "
                            "fail is worthless, and this program has already shipped three such "
                            "checks; this one is proven to discriminate against the exact "
                            "document that caused the failure.",
        "evaluator_refuses_what_it_cannot_model": "every unmodelled policy construct raises "
                                                  "rather than being treated as inert.",
        "discrimination_matrix_covers": [
            "the governed reader at each registered key and VersionId -> ALLOW",
            "the governed reader at a WRONG VersionId -> DENY",
            "the governed reader, UNVERSIONED read of a registered key -> DENY",
            "the governed reader on an unregistered seventh oos/ key -> DENY",
            "the governed reader writing or deleting -> DENY",
            "the governed reader on the CONSUMED validation/ partition -> DENY",
            "the run-host role reading oos/ directly -> DENY",
            "an administrator MODELLED AS ALLOW-* reading oos/ -> DENY, so the denial must come "
            "from the resource policy alone",
            "any read over insecure transport -> DENY",
            "the governed reader on the open reference/ partition -> ALLOW",
        ],
    },
    "live_half": {
        "verdict": "NOT YET RUN",
        "instrument": "apps/backend/scripts/mr002_v2_head_authorization_probe.py",
        "instrument_sha256":
            "448804f139da29a58587a39a335c4c6df5b2d6a404d797f466631bc0433c1bd3",
        "staged_on_host": "/opt/mr002/stage/v2open/mr002_v2_head_authorization_probe.py, "
                          "sha256 verified equal to the Git blob",
        "structural_test": "PASS — 7/7 body-returning operations raise ContentReadAttempted, no "
                           "unlisted operation is exposed at all, zero content-returning call "
                           "sites exist in the file, and its six-object population is EXACTLY "
                           "the tracked production registry (key, VersionId, sha256, bytes). "
                           "Verified both on the workstation and inside the bound runtime.",
        "why_it_cannot_run_now": "the governed reader is assumable only with the latch OPEN, so "
                                 "the live authorization decision is unobservable from a closed "
                                 "state. This is the residual v4.0 registered and the opening "
                                 "realised; it is now isolated in one named gate instead of "
                                 "being spread across a prose limitation.",
        "sufficiency": "a pinned-version HeadObject and a pinned-version GetObject authorize "
                       "under the SAME action, s3:GetObjectVersion, against the same resource "
                       "with the same s3:VersionId condition key. The probe receives the EXACT "
                       "decision the content read would receive, and transfers no body. It is a "
                       "sufficient proof, not a correlated proxy.",
        "not_consumption": "the program has always counted HeadObject as an ATTEMPT and never as "
                           "exposure — the seven denied HeadObject events in the access history "
                           "were counted exactly that way. Consumption is the first successful "
                           "VALIDATION CONTENT read.",
        "required_outcome_before_any_content_read": [
            "all six exact registered oos/* keys",
            "the exact registered VersionId on each",
            "six successful metadata-only probes",
            "zero GetObject / GetObjectVersion content calls",
            "zero read_verified journal rows",
            "zero body bytes",
        ],
        "on_any_failure": "restore the latch 7->8 immediately, seal a PRE-READ failure, leave "
                          "Validation-2 UNCONSUMED, do not launch the evaluation.",
        "metadata_corroboration_that_is_NOT_a_content_check": "the probe compares the echoed "
            "VersionId and ContentLength against the registry. That is corroboration available "
            "without content; it is NOT the sha256 commitment and is never reported as one. The "
            "six content hashes remain unverified until the governed read.",
    },
    "verdict": "PARTIAL — static half PASSES, live half unrunnable from a closed latch",
    "is_true": False,
    "why_not_true": "this gate is TRUE only when the static half passes AND the six live "
                    "metadata-only probes have succeeded. Reporting TRUE on the static half "
                    "alone would reproduce precisely the failure it exists to prevent: a "
                    "faithful hash of a policy that is faithfully wrong.",
}

REC["amendment_R_application"] = {
    "authority": "owner ruling 2026-08-21 — AUTHORIZED TO SEAL AND APPLY, narrow",
    "sealed_before_application": True,
    "identity_before": "b529bb26c5d542b255adf8c94349609180bd4599108debbd8fac693567437baf",
    "identity_after": "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5",
    "deployed_equals_sealed": True,
    "statements_before": 4,
    "statements_after": 4,
    "changed": ["the oos/ statement Sid", "its Condition principal"],
    "unchanged": ["Version", "Id", "DenyInsecureTransport",
                  "DenyValidationReadsToEveryPrincipalButTheValidationReader",
                  "DenyPermanentDeletionOfSealedObjectVersions",
                  "the amended statement's Effect, Principal, Action and Resource"],
    "admitted_principal_broadened": False,
    "latch_throughout": "8 / CLOSED",
    "successful_validation2_content_reads_after": 0,
    "tracked_copy_synced": "scripts/mr002_custody/aws/sealed-store-bucket-policy.json now equals "
                           "the live document",
    "a_defect_caught_in_my_own_amendment_before_applying_it": {
        "what": "the first draft wrote the governance invariant into the policy's top-level Id. "
                "The live policy ALREADY had one ('MR002SealedStorePolicy'), so the draft would "
                "have REPLACED an existing element rather than added one — and the diff omitted "
                "it, because the diff only reported Id when the old document had none.",
        "why_it_matters": "that is the same shape as the defect being repaired: a quiet change "
                          "to a governance surface, invisible in the artifact meant to expose "
                          "changes.",
        "fix": "the Id is left untouched; the invariant is carried by the Sid and stated in full "
               "in the amendment record; and the diff now ENUMERATES every top-level element and "
               "REFUSES if any of them changed.",
    },
    "not_done": "no blanket validation/* deny. Owner ruling: Validation-1 is permanently "
                "inadmissible to EVALUATION, which is not the same as its bytes being unreadable "
                "by every custody, forensic or administrative principal forever. A narrower "
                "evaluator-path guard with enumerated custody principals is a separate "
                "strengthening, not part of this repair.",
}

REC["boundary"] = {
    "latch": "8 / CLOSED, canonical 44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba"
             "999fab48",
    "validation_2_population": "UNCONSUMED",
    "successful_validation2_content_reads": 0,
    "opening_consumed": False,
    "validation_2_opening": "NOT AUTHORIZED",
    "prior_opening_authorization": "EXHAUSTED — not carried forward",
    "host": "stopped",
}

REC["verdict"] = {
    "gates_1_to_10": "PASS",
    "gate_11": "PARTIAL — static PASS, live probe pending an authorized latch cycle",
    "readiness": "READY FOR AN OPENING RULING, WITH ONE GATE THAT CANNOT CLOSE FROM A CLOSED "
                 "STATE",
    "scope_of_that_phrase": "everything provable without releasing the latch is proven. Gate 11's "
                            "live half is unobservable until an opening is authorized, and is "
                            "designed to be the FIRST act of that opening — before any content "
                            "read and on the safe side of the consumption boundary. It is stated "
                            "as an open gate, not quietly folded into a PASS.",
    "if_the_next_opening_is_authorized": [
        "release the latch 8 -> 7",
        "prove OPEN behaviourally",
        "run the six metadata-only HEAD probes FIRST",
        "only on 6/6 success, launch the indivisible content-read sequence",
        "on any probe failure, restore 7 -> 8, seal a PRE-READ failure, do not launch",
    ],
    "economics": "unknown by construction. No performance statistic has ever been read.",
}

REC["authorizes"] = ("NOTHING. A fresh opening requires its own owner ruling. This record reports "
                     "that readiness now covers the surface that failed on 2026-08-21.")

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ReadinessQualification_v5.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_Validation2_ReadinessQualification_v5.0")
    print("  identity      %s" % ident)
    print("  gates 1-10    %s" % REC["verdict"]["gates_1_to_10"])
    print("  gate 11       %s" % REC["verdict"]["gate_11"])
    print("  readiness     %s" % REC["verdict"]["readiness"])
    print("  latch         8 / CLOSED     validation-2: UNCONSUMED")
