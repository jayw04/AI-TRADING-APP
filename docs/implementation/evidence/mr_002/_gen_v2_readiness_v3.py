"""Validation-2 readiness qualification v3.0 — after the deployed-tree cutover.

Supersedes ReadinessQualification v2.0 (nine gates, bound the library surface but neither the
launcher nor the manifest). This record adds the TENTH gate and reports it from a DEPLOYED,
EXECUTED tree rather than from a source closure.

⛔ IT DOES NOT DECLARE THE OPENING READY. The deployment qualified; a dependency-bundle defect
found during it did not. Both facts are in here, and the second one governs.
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
    "version": "3.0",
    "date": "2026-08-20",
    "supersedes": "MR002_Validation2_ReadinessQualification_v2.0 "
                  "(3e1e6e292a02a8b5102842c2fc99baa7d00e0218b0e87679fd959cd5167a3db4), "
                  "preserved unmodified",
    "what_changed": "the nine-gate record qualified a SOURCE surface. This one qualifies the "
                    "DEPLOYED tree, by running it.",
}

# ── the tenth gate ───────────────────────────────────────────────────────────────────────────
REC["tenth_gate"] = {
    "name": "launcher_and_manifest_bind_the_registered_validation2_population_and_current_authority",
    "value": True,
    "requires_BOTH": ["static identity verification of launcher and manifest",
                      "a SUCCESSFUL rehearsal of the ACTUAL launcher from the DEPLOYED tree"],
    "why_both": "hashing the launcher proves what it says; running it proves what it does. The "
                "second halt was precisely a case where the file was intact and its behaviour "
                "was wrong.",
    "static": {
        "launcher_sha256":
            "12b1a0c4899d79a54322664ec82b2c9193b32212891eb59e61caf15f4ad9ce3a",
        "validation2_object_registry_sha256":
            "bbd330b7a41e338353ebd061707b5f633937e0cc82cdd97b794e72021657ae2e",
        "validation2_rehearsal_registry_sha256":
            "4fedce0e094527cbf587e63613aeec7692724e4833a221fbdbda7581479fc11b",
        "closure_identities_on_the_live_tree": "25/25 matched, 0 missing, 0 mismatched",
        "governed_CRLF_on_the_live_tree": 0,
    },
    "executed_from_the_deployed_tree": {
        "positive_closed_latch_rehearsal": "PASS",
        "consuming_reads": 6, "reference_reads": 4, "unclassified_reads": 0,
        "opened_object_ledger_rows": 6,
        "version_ids": "ALL synthetic fixture://<table>/v1 — no production VersionId present",
        "journal_rows": 23, "journal_row_1": "run_opened, preceding every read",
        "terminal": "COMPLETED",
        "verdict": "REHEARSAL_NO_VERDICT",
        "authority_stamped": "MR002_Validation2_ProspectiveRegistration_v1.0 / 93ee4688",
        "s3_reader_invoked": False,
        "container_network": "none",
    },
}

# ── deployment bindings ──────────────────────────────────────────────────────────────────────
REC["binds"] = {
    "deployment_artifact":
        "aab2e7a56acf8dcc15e12e5345110c92e0ab43f04cbafe2e5380c359738e4b93",
    "archive_sha256":
        "c3d3a7e026f65dcf611826f3d9746cee6ba46cd0eb66d8bfa32563bce80cc4df",
    "archive_bytes": 8724480,
    "source_commit": "740a1420ad55c2c2cb74c681fd49b1da2f3c11b2",
    "execution_package":
        "e22c4d4f9e1007340d7c30385af0ee6a95c0c0be8a1a8cd8b4a4e8140c832d23",
    "execution_closure":
        "3c32bda64dd1cd6efe306bcf7e69e56a78c53b3bd58076d7735ddbe2d516df3b",
    "deployed_live_aggregate":
        "6841756f8026932370531fde49de5dfccda1c2cee964174f1eec1901e3660ae9",
    "host": "i-00c1034f7026db45e",
    "destination": "/opt/mr002/phase3c_src",
    "runtime_image": "mr002-research:v1.4",
    "image_config_digest_on_host":
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
    "container_mount": "/work read-only, so the tree resolves as /work/apps/backend",
}

REC["cutover"] = {
    "method": "staged: extract to candidate -> verify on host -> atomic same-filesystem rename",
    "same_filesystem_verified": "device id compared before renaming; a cross-device rename is a "
                                "copy, not an atomic swap, and would have been refused",
    "archive_sha_verified_on_host_before_extraction": True,
    "pre_cutover_live_aggregate":
        "21c6a4f2f25a5a82b4dad3045bf4a99242e3e79a3decc26dc1e39d537db5e474",
    "post_cutover_live_aggregate":
        "6841756f8026932370531fde49de5dfccda1c2cee964174f1eec1901e3660ae9",
    "candidate_aggregate_equals_post_cutover_live": True,
    "preserved_trees": {
        "/opt/mr002/phase3c_src_pre_amendmentC":
            "1477 files — the original pre-Amendment-C tree, NOT touched",
        "/opt/mr002/phase3c_src_pre_validation2_launcher_amendment":
            "1120 files — the nine-gate state that produced the SECOND HALT, preserved rather "
            "than discarded; its aggregate is "
            "21c6a4f2f25a5a82b4dad3045bf4a99242e3e79a3decc26dc1e39d537db5e474, identical to the "
            "pre-cutover live reading, which is what proves it is exactly what was live",
    },
    "disk_after": "26 GB free of 30 GB, 1% inodes used — preserving the intermediate tree cost "
                  "nothing that mattered",
    "transport": {
        "mechanism": "presigned S3 GET, time-limited, for the exact frozen archive",
        "why_not_IAM": "the run host has NO S3 read capability anywhere and its role must not "
                       "gain one. A presigned URL is authenticated as the SIGNER, so no host "
                       "policy changed, no credential was placed on the host, and nothing near "
                       "the latch was touched.",
        "verified": "the host recomputed the archive SHA-256 and refused to extract unless it "
                    "equalled c3d3a7e0... exactly",
    },
}

# ── the boundary ─────────────────────────────────────────────────────────────────────────────
REC["boundary_verified_AFTER_deployment"] = {
    "latch": "8 statements / CLOSED — statement 4 Deny sts:AssumeRole on the reader is present "
             "and beats statement 8 Allow",
    "successful_validation2_reads": 0,
    "how_reads_were_verified": "CloudTrail S3 DATA events for the sealed bucket were scanned "
                               "directly, not inferred: 59,074 records across the trail's "
                               "us-east-1 August logs, 108 events touching the sealed bucket, of "
                               "which 7 were reads against oos/* and ALL 7 failed AccessDenied. "
                               "Re-scanned after deployment: still 0 successful.",
    "⚠ context_not_to_be_misread": "36 SUCCESSFUL reads exist against validation/*. That is the "
                                   "CONSUMED Validation-1 partition and is expected history, not "
                                   "a Validation-2 exposure. Six successful AssumeRole calls on "
                                   "the reader role also exist, all 2026-08-12..08-19, i.e. the "
                                   "Validation-1 era; none since.",
    "amendment_A_v1_2_deployed_equals_sealed": True,
    "amendment_A_canonical_sha256":
        "d7b5cf2be0d4523967ff63d121341572c3b111ac5085e04f9c4a7a2b4e25eedd",
    "reader_trust_deployed_equals_sealed": True,
    "publisher_trust_deployed_equals_sealed": True,
    "population": "UNCONSUMED",
}

# ── the gates ────────────────────────────────────────────────────────────────────────────────
REC["post_cutover_gates"] = {
    "post_cutover_live_aggregate == candidate aggregate": "PASS",
    "25/25 closure identities on the live tree": "PASS",
    "exact launcher + both registries present at sealed identities": "PASS",
    "import resolution inside the exact opening container": "PASS — 11 governed modules; "
        "app.research.mr002.phase3c resolves under /work/apps/backend",
    "20/20 launcher static invariants": "PASS from the deployed tree",
    "10/10 negative cases fail closed pre-credential": "PASS from the deployed tree",
    "positive closed-latch rehearsal": "PASS from the deployed tree",
    "fold/gate synthetic rehearsal": "PASS from the deployed tree",
    "runtime/image identity unchanged": "PASS — config digest 770553ae...",
    "latch still 8/CLOSED": "PASS",
    "successful Validation-2 reads still 0": "PASS",
    "dependency bundle identity unchanged": "⛔ SEE THE BLOCKER BELOW. Unchanged, and "
                                            "NON-FUNCTIONAL.",
}

# ── THE BLOCKER ──────────────────────────────────────────────────────────────────────────────
REC["⛔ NEW_BLOCKER_dependency_bundle_cannot_import_boto3"] = {
    "found": "during post-cutover import qualification in the exact opening container.",
    "finding": "/opt/mr002/deps — the bundle the execution package names as the MANDATORY mount "
               "('MUST be mounted at /opt/mr002/deps') — CANNOT import boto3. It is missing "
               "dateutil (and six). botocore.compat does `from dateutil.tz import tzlocal` at "
               "import time, so `import boto3` raises ModuleNotFoundError.",
    "measured": {
        "/opt/mr002/deps": "ModuleNotFoundError: No module named 'dateutil'",
        "/opt/mr002/deps_v11_clean": "ModuleNotFoundError: No module named 'dateutil'",
        "/opt/mr002/deps_v12": "OK — boto3 1.43.70 / botocore 1.43.70 import cleanly",
    },
    "why_this_is_material": "the launcher does `import boto3` INSIDE the args.reader == 's3' "
                            "branch. With the documented mount the governed opening would raise "
                            "ModuleNotFoundError at that line.",
    "what_it_would_and_would_not_cost": {
        "opening_consumed": "NO — the failure occurs AFTER _assert_production_contract_before_"
                            "credentials and BEFORE acquire_reader_credentials, so no credential "
                            "is issued and no byte is read. The journal would carry a terminal "
                            "FAILED.",
        "latch_cycle_burned": "YES — the latch would have been released, the ~286s propagation "
                              "waited out, and the run would have died on a missing Python "
                              "package.",
        "why_that_is_unacceptable_here": "the governing principle for Cycle 2C is that the next "
                                         "validation opening must never again be consumed or "
                                         "wasted because INFRASTRUCTURE failed. This is exactly "
                                         "that failure mode, caught before the latch moved "
                                         "instead of after.",
    },
    "not_fixed_by_me": "I did not modify, replace or re-point any dependency bundle. Changing "
                       "the runtime mount changes a bound runtime identity, and that is an "
                       "owner ruling, not a repair I may make mid-qualification.",
    "recommendation": "re-point the documented mount to /opt/mr002/deps_v12, which is the only "
                      "bundle that imports boto3, and re-bind the dependency identity in the "
                      "execution package. NOTE that Validation-1's successful reads on "
                      "2026-08-19 postdate deps_v12's creation on 08-18, which is consistent "
                      "with deps_v12 having been the bundle actually used — the PACKAGE TEXT, "
                      "not the working configuration, is what is stale.",
    "open_question_for_the_owner": "whether the correct action is to re-point the mount, rebuild "
                                   "/opt/mr002/deps, or bind deps_v12 by content identity. All "
                                   "three change a bound runtime identity.",
}

REC["verdict"] = {
    "deployment": "COMPLETE AND QUALIFIED",
    "tenth_gate": "TRUE",
    "gates_1_through_9": "carried forward from ReadinessQualification v2.0, re-verified where "
                         "the deployed tree touches them",
    "⛔ OPENING_READINESS": "NOT READY",
    "single_reason": "the documented dependency bundle cannot import boto3, so the governed S3 "
                     "path would fail after a latch release. Every other gate passes.",
    "what_would_clear_it": "an owner ruling on the dependency bundle, then a re-run of the "
                           "import qualification against whatever bundle is bound.",
}
REC["authorizes"] = ("NOTHING. This is a readiness report. The opening requires a fresh owner "
                    "ruling, and on the evidence here it should not be granted until the "
                    "dependency-bundle blocker is resolved.")
REC["what_was_NOT_done"] = [
    "the latch was NOT released (still 8/CLOSED)",
    "no reader was assumed and no STS call was made",
    "no Validation-2 object was read at any version",
    "no dependency bundle was modified, replaced or re-pointed",
    "no preserved tree was overwritten or deleted",
    "no closure member was changed",
]
REC["boundary"] = {
    "latch": "8 / CLOSED", "withheld_reads": 0, "opening_consumed": False,
    "validation_2_population": "UNCONSUMED",
    "validation_2_opening": "NOT AUTHORIZED",
    "host": "i-00c1034f7026db45e — deployed, then stopped",
}
REC["record_status"] = "SEALED"


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ReadinessQualification_v3.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 VALIDATION-2 READINESS QUALIFICATION v3.0")
    print(f"  identity        {ident}")
    print(f"  tenth gate      {REC['tenth_gate']['value']}")
    print(f"  deployment      {REC['verdict']['deployment']}")
    print(f"  live aggregate  {REC['binds']['deployed_live_aggregate']}")
    print(f"  latch           {REC['boundary']['latch']}")
    print(f"  v2 reads        {REC['boundary_verified_AFTER_deployment']['successful_validation2_reads']}")
    print(f"  OPENING         {REC['verdict']['⛔ OPENING_READINESS']}")
    print(f"  reason          {REC['verdict']['single_reason'][:88]}")
    print(f"  wrote           {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
