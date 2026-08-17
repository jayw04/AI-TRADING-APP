"""SPQ-1 Phase 3B — v3.6 execution refusal event (2026-08-17): launch-harness dependency omission.

The released execution refused in ~2 seconds at the reader factory (`import boto3`) because the
launch invocation omitted the bound dependency-bundle mount (/opt/mr002/deps, DependencyBundle
v1.1 61bd7d98...). No STS call, no sealed access, ZERO objects opened - the opening is UNCONSUMED
by the runner's own record and affirmatively by windowed CloudTrail. Containment was restored
byte-identically within seconds of terminal state. No relaunch was performed without an owner
ruling, per the run stop conditions.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


record = {
    "record_type": "MR002_Phase3B_ExecutionRefusalEvent",
    "version": "v36-1.0",
    "artifact_kind": "EXECUTION_REFUSAL_EVENT",
    "produced_at": "2026-08-17T00:00:00Z",
    "executed_under": (
        "owner GRANT 2026-08-17 (ReplacementOpeningAuthorization v3.0, 7d037e75...), CI-green "
        "condition substituted by owner ruling '1' (equivalence certification accepted)."
    ),
    "release": {
        "latch_released_at": "statements 8 -> 7, removed exactly DenyAssumingTheValidationReaderRole",
        "pre_release_canonical_sha256": "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48",
        "post_release_simulation": {"host_to_reader": "allowed", "host_to_sealed_GetObject": "explicitDeny"},
        "pre_release_reconfirmation": (
            "four-way c4852231... re-proven in the bound image; config 1959dcd3...; archive "
            "024db8fa...; mapping {A:1.75, B:2.00, C:2.25}; contracts frozen; out_exec fresh; "
            "26,849 MiB disk / 7.9 GB RAM"
        ),
    },
    "refusal": {
        "ssm_command_id": "e32850f7-b4e3-4a8c-b308-e461cd5460e7",
        "started_utc": "2026-08-17T23:20:35Z",
        "ended_utc": "2026-08-17T23:20:37Z",
        "disposition": "REFUSED",
        "exit_code": 2,
        "state": "S8_READER_ASSUMED",
        "opening_consumed": False,
        "error": "ModuleNotFoundError: No module named 'boto3'",
        "evidence": "/opt/mr002/v36/out_exec/stdout.log (227 B, d37a520e...)",
        "why_S8_without_STS": (
            "_assume_reader() only advances the state machine; the S3 client is built lazily at "
            "the FIRST read. The factory failed at `import boto3` before any STS call, so "
            "S9_OPENING_CONSUMED was never reached and the guard opened zero objects."
        ),
    },
    "root_cause": {
        "classification": "LAUNCH_HARNESS_DEPENDENCY_OMISSION - not a package, identity, config or ceremony defect",
        "detail": (
            "the launch invocation mounted /opt/mr002/v36 and set PYTHONPATH to the closure only. "
            "The bound ExecutionDependencyBundle v1.1 (61bd7d98..., inventory 7c50b2ab..., 2,919 "
            "files) supplies boto3/botocore/jmespath/pyarrow/s3transfer/urllib3 at /opt/mr002/deps "
            "(read-only, top-level names DISJOINT from the image so no ordering can shadow). That "
            "mount and path entry were omitted."
        ),
        "why_the_dry_ceremony_could_not_catch_it": (
            "dry stops at S7 BEFORE reader construction and never decodes parquet, so neither "
            "boto3 nor pyarrow is imported on the dry path. Non-consumption and this blind spot "
            "are the same property. A clean dry run proves the gates, not the live import path."
        ),
    },
    "containment": {
        "latch_restored_at_terminal": True,
        "restored_canonical_sha256": "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48",
        "byte_identical_to_pre_release_capture": True,
        "simulate_after_restore": "explicitDeny",
        "cloudtrail_windowed_23_10_to_23_30_utc": (
            "AssumeRole events show ONLY the host's routine EC2 instance-role refresh; ZERO events "
            "name mr002-validation-reader. The reader was never assumed."
        ),
        "sealed_reads": 0,
        "oos_reads": 0,
        "host": "STOPPED after evidence collection",
    },
    "state": {
        "opening": "GRANTED and UNCONSUMED - the grant's single release was used by this refused launch; relaunch requires an owner ruling per the run stop conditions ('do not automatically authorize another')",
        "openings_spent_historical": 4,
        "research_verdict": "NONE",
        "v36_package": "UNCHANGED - staged, bound, ceremony-green",
    },
    "corrected_launch_delta_proposed_not_executed": {
        "add_mount": "-v /opt/mr002/deps:/opt/mr002/deps:ro",
        "pythonpath": "/work/apps/backend:/opt/mr002/deps (bundle disjointness makes ordering shadow-free per DependencyBundle v1.1)",
        "output_root": "preserve /opt/mr002/v36/out_exec as refusal evidence; a relaunch writes to a fresh root",
        "everything_else": "byte-identical invocation",
    },
    "grants": "NOTHING.",
}

body = _canonical(record)
record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
with open(os.path.join(_HERE, "MR002_Phase3B_ExecutionRefusalEvent_v36_v1.0.json"), "wb") as fh:
    fh.write(_canonical(record))
print("identity", record["record_identity_sha256"])
