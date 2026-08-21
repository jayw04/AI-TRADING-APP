"""MR-002 — custody transfer of the CONSUMED Validation-1 materialization, and closure of the class.

Owner ruling 2026-08-21: give the newly discovered Validation-1 database the same treatment as
Validation-2 — archive as byte-only evidence into inaccessible custody, verify independently, then
remove the EBS copy. Do not destroy it.

Executed with the latch 8/CLOSED throughout. The database was never opened or queried.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


SHA = "c4cabab228e7824144036afde09f5c949d9dea6144eb0b24d41e1fcad0856c82"

REC: dict = {
    "record_type": "MR002_ConsumedValidation1_MaterializationCustodyTransfer",
    "version": "1.0",
    "date": "2026-08-21",
    "authority": "owner ruling 2026-08-21 — V1 byte-only custody archival AUTHORIZED; delete the "
                 "EBS copy after verified custody AUTHORIZED / REQUIRED; destruction without "
                 "custody NOT APPROVED",
    "classification": "CONSUMED_VALIDATION1_MATERIALIZATION — EVIDENCE ONLY — NOT AN AUTHORIZED "
                      "RESEARCH CORPUS",
    "peer_record": "MR002_ConsumedValidation2_MaterializationCustodyTransfer_v1.0 / 62dc0985...",
}

REC["artifact"] = {
    "source_host": "i-00c1034f7026db45e",
    "source_path": "/opt/mr002/work/validation.duckdb",
    "bytes": 14430208,
    "sha256": SHA,
    "materialized_utc": "2026-08-19T12:54:47Z",
    "identified_how": "NOT by its filename. Its mtime coincides with the CloudTrail validation/* "
                      "reads at 2026-08-19T12:54:46-47Z by session mr002-p3c-validation-v1 — the "
                      "six successful Validation-1 content reads of that run. Identification is "
                      "by access-log correlation.",
    "never_opened": "handled as a byte artifact only; hashed and copied, never opened or queried, "
                    "with no open file handle at hashing time",
}

REC["immutability_finding"] = {
    "observed": "the first deletion attempt failed with EPERM. The file carried the ext/xfs "
                "IMMUTABLE attribute (lsattr `----i----------------`), set during the 2026-08-19 "
                "run to protect the materialized holdout.",
    "handled": "the attribute was cleared with `chattr -i` as a recorded governance act, the hash "
               "was RE-COMPUTED in the resulting mutable window and required to equal the archived "
               "custody bytes before deletion proceeded, and the script was written to restore "
               "`chattr +i` and abort had the hash differed.",
    "why_the_re_hash_earns_its_place": "clearing immutability makes the file mutable for a window. "
                                       "The re-hash between clearing and deleting is the only "
                                       "thing that proves the bytes deleted are the bytes "
                                       "archived.",
    "asymmetry_worth_recording": "the Validation-1 cycle protected its materialization with "
                                 "chattr +i; the Validation-2 cycle did NOT — the V2 database "
                                 "deleted without resistance. Not actionable now, since V2 is "
                                 "consumed and archived, but the next method version should apply "
                                 "the protection consistently rather than by accident of which "
                                 "cycle happened to set it.",
}

REC["transfer"] = {
    "order": "the resource-side denial was EXTENDED FIRST, so the V1 custody object was covered "
             "from the moment it existed. There was never a window in which it sat in custody "
             "unprotected.",
    "step_1_hash_on_host": {"sha256": SHA, "bytes": 14430208},
    "step_2_write_via_the_hosts_only_sanctioned_path": {
        "path": "s3://workbench-backups-219024422756/mr002/publish-staging/validation1/"
                "2026-08-19/validation.duckdb",
        "version_id": "1C9kpExFv5u_qX.Yj0ZAmjdfjO6Yes.w",
        "s3_computed_checksum_sha256_hex": SHA,
        "independent_agreement": "S3 computed the digest itself at write time and it equals the "
                                 "host's — two independent computations, not one repeated",
        "transient_exposure_disclosed": "the staging prefix is host-writable and is NOT covered "
                                        "by the custody denial. The bytes sat there only between "
                                        "the write and the promotion, and the staging version was "
                                        "then deleted. This window is structural: the host's IAM "
                                        "policy permits PutObject to that prefix and nowhere "
                                        "else, and widening it would mean editing the latch "
                                        "document. It is disclosed rather than hidden.",
    },
    "step_3_promote_to_dedicated_custody": {
        "path": "s3://workbench-backups-219024422756/mr002/consumed-validation1-custody/"
                "2026-08-19/validation1_materialization.duckdb",
        "version_id": "6nQlnlYUimZC3WkLOBi6YI56Xv4Gs4IP",
        "method": "server-side copy pinned to the staging VersionId; the bytes never transited a "
                  "workstation inbound",
        "checksum_sha256_hex": SHA,
    },
    "step_4_read_back_by_the_custody_principal": {
        "principal": "arn:aws:iam::219024422756:user/admin",
        "principal_is_not": "the evaluator host role, the governed reader, any publisher role, or "
                            "a research-plane role",
        "bytes_read": 14430208,
        "sha256_recomputed": SHA,
        "byte_for_byte_equality": True,
        "local_copy": "deleted immediately after hashing; never opened by DuckDB",
    },
    "step_5_behavioural_denial_proof": {
        "principal": "arn:aws:sts::219024422756:assumed-role/mr002-phase3c-run-host/"
                     "i-00c1034f7026db45e",
        "get_object_at_the_pinned_version": "AccessDenied on s3:GetObjectVersion",
        "head_object": "403 Forbidden",
        "bytes_written_locally": 0,
        "v2_regression_check": "the V2 custody object remains 403 to the host as well — the "
                               "extension did not weaken the existing protection",
    },
    "step_6_staging_copy_removed": {"deleted_version_id": "1C9kpExFv5u_qX.Yj0ZAmjdfjO6Yes.w",
                                    "verified_absent": "no versions, no delete markers"},
    "step_7_host_copy_deleted": {
        "immutable_attribute_cleared_first": True,
        "sha256_reconfirmed_in_the_mutable_window": SHA,
        "path_absent_after": "/opt/mr002/work/validation.duckdb",
        "verified": True,
        "order": "deletion only after custody was independently verified, never before",
    },
}

REC["prefix_naming_decision"] = {
    "chosen": "mr002/consumed-validation1-custody/",
    "rejected": "mr002/consumed-holdout-custody/validation1/",
    "why": "the V2 object's location is now evidentiary identity and cannot move. A second naming "
           "scheme for a class of exactly two members would leave the generations under different "
           "conventions — the same split that has produced six role-transfer defects in this "
           "program. Symmetry with the immovable member beats tidiness that only half the class "
           "can adopt.",
    "date_component_convention": "the date is the MATERIALIZATION date, not the transfer date. "
                                 "For V2 those coincided (2026-08-21); for V1 they do not, so the "
                                 "convention is stated here rather than left to be inferred from "
                                 "a single example.",
}

REC["access_control"] = {
    "record": "MR002_ConsumedHoldoutCustodyDenial_v2.0",
    "identity_before": "d44230f45ed3d94af5bacfdd9f35529c0999186aa0661e7fb59dc3014aed0176",
    "sealed_identity_after": "4944eb59bc01cc56c1395349cc37843c9f69e43c7c2728efcc5a2e1e9a15f134",
    "sealed_before_application": True,
    "deployed_equals_sealed": True,
    "statement_count": 1,
    "allow_statements": 0,
    "sid_renamed": {
        "from": "DenyTheEvaluatorAndResearchPlanesTheConsumedValidation2Materialization",
        "to": "DenyTheEvaluatorAndResearchPlanesEveryConsumedHoldoutMaterialization",
        "why": "adding the V1 prefix to a statement whose Sid named Validation-2 would leave a "
               "statement asserting a narrower scope than it enforces. That is the "
               "FutureOOSReader defect, which this program has already paid for twice. The name "
               "now states the invariant.",
    },
    "invariant": "consumed holdout custody — irrespective of validation generation — is "
                 "inaccessible to the evaluator, reader, publisher, paper and forward-validation "
                 "planes.",
    "principals_actions_condition_unchanged": True,
    "retained_by_design": {"user/admin": "custody verification",
                           "MR002CustodyMonitorRole": "custody monitoring",
                           "WorkbenchFleetAuditRole": "audit"},
    "scope_regression_check": "unrelated prefixes are unaffected — the cycle-2 publish-staging "
                              "evidence objects remain listable and readable to the custody "
                              "principal.",
}

# ── the standing decommissioning rule, implemented and run ───────────────────────────────────
REC["decommissioning_sweep"] = {
    "standing_rule": "before terminating an MR-002 host, enumerate all local DuckDB / parquet / "
                     "materialization artifacts and classify each as development, fixture, "
                     "failed-pre-read evidence, or consumed-holdout evidence. No consumed-holdout "
                     "material may remain solely on EBS.",
    "implemented_as": "a classifier, not prose — the same principle as gate 11. It walks the host, "
                      "hashes every candidate as bytes, and classifies by evidence-linked "
                      "identity first and path rules second.",
    "refuses_to_guess": "UNKNOWN is a real verdict. Anything the classifier cannot place is "
                        "reported as NEEDS_RULING rather than folded into a benign bucket — a "
                        "classifier that cannot say 'I do not know' will silently misclassify the "
                        "one file that matters.",
    "before": {"total_artifacts": 44, "consumed_holdout_on_ebs": 1, "needs_ruling": 0},
    "after": {"total_artifacts": 43, "consumed_holdout_on_ebs": 0, "needs_ruling": 0,
              "summary": {"FAILED_PRE_READ_EVIDENCE": 1, "FIXTURE_OR_REHEARSAL": 15,
                          "PACKAGING": 15, "SOURCE_TREE": 12}},
    "result_sha256": "75d82934d0d563c3ddbbe233fa97fc25965a0f5401bfd9ab5525fa35d4495784",
    "closure": "the class is closed on this host: no consumed-holdout material remains solely on "
               "EBS, and nothing is unclassified.",
    "scope_note": "the sweep covered /opt/mr002, /root, /home, /var/tmp, /tmp, /mnt and /data, "
                  "and .duckdb/.parquet/.db/.sqlite/.arrow/.feather. It is a host sweep, not a "
                  "claim about any other machine.",
}

REC["retained_deliberately"] = {
    "/opt/mr002/stage/v2open/run/validation2.duckdb": {
        "bytes": 12288,
        "sha256": "0dbc2c9e3be28c0770c3ab64461659bbfd177e17f22cfcf96925f216f2d6487d",
        "classification": "FAILED_PRE_READ_EVIDENCE",
        "why": "zero tables, zero Validation-2 content, and it is the artifact behind the "
               "PreReadFailure record's claim. Owner-ruled RETAIN. It does not create the "
               "consumed-corpus reuse risk.",
    },
    "rehearsal databases": "FIXTURE_OR_REHEARSAL — built with --reader fixture --window "
                           "development, structurally incapable of reaching sealed data",
}

REC["boundary"] = {
    "latch": "8 / CLOSED, canonical 44f5549a..., unchanged throughout and re-verified after",
    "database_opened_or_queried": False,
    "validation_1": "CONSUMED — archived, EBS copy removed",
    "validation_2": "CONSUMED — archived, EBS copy removed",
    "host": "stopped",
}

REC["authorizes"] = ("NOTHING. Both archived databases are EVIDENCE ONLY. Querying either for "
                     "research or diagnosis is prohibited, and no opening, rerun or replay is "
                     "authorized by this record.")

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE,
                       "MR002_ConsumedValidation1_MaterializationCustodyTransfer_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_ConsumedValidation1_MaterializationCustodyTransfer_v1.0")
    print("  identity         %s" % ident)
    print("  custody version  %s"
          % REC["transfer"]["step_3_promote_to_dedicated_custody"]["version_id"])
    print("  denial identity  %s" % REC["access_control"]["sealed_identity_after"])
    print("  sweep after      consumed-holdout on EBS = %d, needs_ruling = %d"
          % (REC["decommissioning_sweep"]["after"]["consumed_holdout_on_ebs"],
             REC["decommissioning_sweep"]["after"]["needs_ruling"]))
    print("  latch            %s" % REC["boundary"]["latch"])
