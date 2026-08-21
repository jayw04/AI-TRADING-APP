"""MR-002 — custody transfer of the CONSUMED Validation-2 materialization.

Owner ruling 2026-08-21: preserve it as evidence, move it into custody the evaluator and research
planes cannot reach, verify independently, then delete the host copy. Do not destroy it outright;
it is the only evidence of what was actually materialized before the integrity stop.

Executed with the latch 8/CLOSED throughout. The database was never opened, queried or inspected —
it was handled purely as a byte artifact.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


SHA = "3786c9c0af53046df6e70d9586a675b949cf135a68744f71fe74cf9ab64903f4"

REC: dict = {
    "record_type": "MR002_ConsumedValidation2_MaterializationCustodyTransfer",
    "version": "1.0",
    "date": "2026-08-21",
    "authority": "owner ruling 2026-08-21 — archive to inaccessible evidence custody, then "
                 "delete the host copy after verified custody",
    "classification": "CONSUMED_VALIDATION2_MATERIALIZATION — EVIDENCE ONLY — NOT AN AUTHORIZED "
                      "RESEARCH CORPUS",
    "label_is_secondary": "the classification string is documentation. The control is the "
                          "resource-side Deny recorded below, proven behaviourally.",
    "binds_terminal_record":
        "9c08bfc5cb18d683beeb347243fb657cc24d37d925ad06d5409b76979d5fa53b",
}

REC["artifact"] = {
    "what": "the DuckDB the governed run materialized from the six consumed Validation-2 objects "
            "and four reference objects, immediately before the Stage-3 integrity stop",
    "source_host": "i-00c1034f7026db45e",
    "source_path": "/opt/mr002/stage/v2open/cycle2/validation2.duckdb",
    "bytes": 13905920,
    "sha256": SHA,
    "created_utc": "2026-08-21T14:26:22Z",
    "never_opened": "handled as a byte artifact only. It was hashed and copied; it was never "
                    "opened, queried or inspected, and no open file handle existed at the time "
                    "of hashing.",
}

REC["transfer"] = {
    "step_1_hash_on_host": {"sha256": SHA, "bytes": 13905920},
    "step_2_write_via_the_hosts_only_sanctioned_s3_path": {
        "path": "s3://workbench-backups-219024422756/mr002/publish-staging/validation2/"
                "2026-08-21-cycle2/validation2.duckdb",
        "version_id": "EIcTYFA3wFbQl9tBhziHuhKdUCkzHwCQ",
        "s3_computed_checksum_sha256_base64": "N4bJwK9TBG325w2VhqZ1uUnPE1podE9x/nTPmrZJA/Q=",
        "s3_computed_checksum_sha256_hex": SHA,
        "independent_agreement": "S3 computed the digest itself at write time and it equals the "
                                 "host's. Two independent computations, not one repeated.",
        "why_this_path": "the evaluator host's IAM policy permits s3:PutObject on this prefix and "
                         "nothing else on this bucket. No host policy was changed.",
    },
    "step_3_promote_to_dedicated_custody": {
        "path": "s3://workbench-backups-219024422756/mr002/consumed-validation2-custody/"
                "2026-08-21/validation2_materialization.duckdb",
        "version_id": "FTElW.C8g8RnluoK7jCKEcu5d1o3tyM6",
        "method": "server-side copy pinned to the staging VersionId, so the bytes never transited "
                  "a workstation on the way in",
        "checksum_sha256_hex": SHA,
        "object_metadata": {
            "custody": "CONSUMED_VALIDATION2_MATERIALIZATION",
            "classification": "EVIDENCE_ONLY_NOT_AN_AUTHORIZED_RESEARCH_CORPUS",
            "source": "i-00c1034f7026db45e:/opt/mr002/stage/v2open/cycle2/validation2.duckdb",
            "terminal_record":
                "9c08bfc5cb18d683beeb347243fb657cc24d37d925ad06d5409b76979d5fa53b",
        },
    },
    "step_4_read_back_by_the_custody_principal": {
        "principal": "arn:aws:iam::219024422756:user/admin",
        "principal_is_not": "the evaluator host role, the governed reader, any publisher role, or "
                            "a research-plane role",
        "bytes_read": 13905920,
        "sha256_recomputed": SHA,
        "byte_for_byte_equality": True,
        "local_copy": "the verification copy was deleted immediately after hashing. It was never "
                      "opened by DuckDB and no consumed-population bytes remain on the "
                      "workstation.",
    },
    "step_5_staging_copy_removed": {
        "why": "the staging prefix is OUTSIDE the custody prefix and is writable by the evaluator "
               "host. Leaving the consumed materialization there would have defeated the point of "
               "the transfer.",
        "deleted_version_id": "EIcTYFA3wFbQl9tBhziHuhKdUCkzHwCQ",
        "verified_absent": "no versions and no delete markers remain under that key",
    },
    "step_6_host_copy_deleted": {
        "sha256_reconfirmed_immediately_before_deletion": SHA,
        "path_absent_after": "/opt/mr002/stage/v2open/cycle2/validation2.duckdb",
        "verified": True,
        "order": "deletion happened ONLY after custody was independently verified, never before",
    },
}

REC["access_control"] = {
    "record": "MR002_ConsumedValidation2_CustodyDenial_v1.0",
    "bucket_policy_existed_before": False,
    "sealed_identity": "d44230f45ed3d94af5bacfdd9f35529c0999186aa0661e7fb59dc3014aed0176",
    "deployed_equals_sealed": True,
    "allow_statements": 0,
    "grants_nothing": "the policy contains only Deny. It grants no access and removes none from "
                      "any other prefix — absent an explicit Deny, evaluation falls through to "
                      "identity policies exactly as before.",
    "denied_principals": [
        "mr002-phase3c-run-host", "mr002-validation-reader", "mr002-evaluator-publisher",
        "mr002-validation2-evidence-publisher", "mr002-validation2-publish-host-role",
        "workbench-paper-InstanceRole-4P2Tvq7FaG1E", "workbench-forward-validation-session",
        "workbench-forward-validation-witness",
    ],
    "retained_by_design": {
        "user/admin": "the custody verification principal",
        "MR002CustodyMonitorRole": "custody monitoring",
        "WorkbenchFleetAuditRole": "audit",
    },
    "honest_scope": "custody, audit and administrative principals RETAIN access by design. An "
                    "unconditional Deny would block exactly the evidence verification this "
                    "archive exists to support — the same reasoning that made a blanket "
                    "validation/* deny the wrong answer. This is a scoped control, not a claim "
                    "that nobody can read the object.",
    "why_resource_side_rather_than_identity_absence": "the evaluator host role grants no read on "
        "this bucket, so before this change it had no route by OMISSION. Omission is not a "
        "control; it holds only until someone attaches a policy. The morning's pre-read failure "
        "was the mirror image — a complete, correct identity-side amendment defeated by the "
        "resource side nobody had re-pointed.",
    "behavioural_proof": {
        "principal": "arn:aws:sts::219024422756:assumed-role/mr002-phase3c-run-host/"
                     "i-00c1034f7026db45e",
        "get_object_at_the_pinned_version": "AccessDenied on s3:GetObjectVersion",
        "head_object": "403 Forbidden",
        "bytes_written_locally": 0,
        "note": "proven from the evaluator host itself, not inferred from policy text. This is "
                "the check whose absence cost a latch cycle this morning.",
    },
}

REC["boundary_during_the_transfer"] = {
    "latch": "8 / CLOSED, canonical 44f5549a..., unchanged throughout and re-verified after",
    "database_opened_or_queried": False,
    "research_or_diagnostic_use": "NONE. The transfer touched bytes only.",
    "validation_2": "CONSUMED",
    "host": "stopped",
}

# ── a finding surfaced by the sweep, flagged and NOT acted on ────────────────────────────────
REC["finding_outside_this_authorization"] = {
    "what": "the sweep for other copies of consumed-holdout material found a materialized "
            "VALIDATION-1 database still on the evaluator host's EBS root.",
    "path": "/opt/mr002/work/validation.duckdb",
    "bytes": 14430208,
    "sha256": "c4cabab228e7824144036afde09f5c949d9dea6144eb0b24d41e1fcad0856c82",
    "created_utc": "2026-08-19T12:54:47Z",
    "why_it_matters": "Validation-1 is the CONSUMED, permanently inadmissible partition. This is "
                      "the same class of artifact as the one just archived — consumed-holdout "
                      "material on a disposable volume — and it is subject to none of the "
                      "controls just applied.",
    "action_taken": "NONE. Today's authorization covers the Validation-2 materialization "
                    "specifically. Archiving or destroying Validation-1 material is a separate "
                    "decision and is raised, not taken.",
    "handled_as": "bytes only — stat and sha256sum. It was not opened.",
}

REC["also_present_and_deliberately_retained"] = {
    "/opt/mr002/stage/v2open/run/validation2.duckdb": {
        "bytes": 12288,
        "sha256": "0dbc2c9e3be28c0770c3ab64461659bbfd177e17f22cfcf96925f216f2d6487d",
        "why_retained": "this is the failed FIRST attempt's database, created at 12:07:54Z before "
                        "the resource-policy refusal. It contains ZERO tables and no "
                        "Validation-2 bytes, and it is the artifact behind the PreReadFailure "
                        "record's claim that the materialized database held no tables. Deleting "
                        "it would remove evidence bound in a sealed record.",
    },
    "rehearsal databases under /opt/mr002/stage/reh_*": "built from fixture and development data, "
                                                        "never from holdout material. Not in "
                                                        "scope.",
}

REC["authorizes"] = ("NOTHING. It records a custody transfer. The archived database remains "
                     "EVIDENCE ONLY; querying it for research or diagnosis is prohibited, and no "
                     "opening, rerun or replay is authorized by this record.")

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE,
                       "MR002_ConsumedValidation2_MaterializationCustodyTransfer_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_ConsumedValidation2_MaterializationCustodyTransfer_v1.0")
    print("  identity          %s" % ident)
    print("  custody version   %s"
          % REC["transfer"]["step_3_promote_to_dedicated_custody"]["version_id"])
    print("  denial identity   %s" % REC["access_control"]["sealed_identity"])
    print("  host copy         DELETED, path verified absent")
    print("  latch             %s" % REC["boundary_during_the_transfer"]["latch"])
