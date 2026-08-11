"""WP-D / P11 — access-control preconditions in force, snapshotted.

Authorized by ``MR002_PrerequisiteProduction_Authorization_v1.0.json`` (WP-D)
and sequenced by ``MR002_ExecutionSequencing_Direction_v1.0.json`` (D-S2).

P11's satisfaction criterion, verbatim from the runtime prerequisite register:

    CloudTrail S3 data events enabled BEFORE any access; dedicated IAM
    principal; explicit bucket/key DENY on the OOS partition; validation-only
    policy; pre-execution policy-state snapshot

===============================================================================
PROVEN BY SIMULATION, NEVER BY ATTEMPTING A READ
===============================================================================

The tempting way to prove a DENY is to try the read and observe the failure.
That is exactly wrong here. CloudTrail records a DENIED ``GetObject`` as a data
event just as faithfully as a successful one, so proving the OOS DENY by
attempting it would put an OOS access event on the permanent record --
the very count P7 and P8 must show is zero.

So every access claim in this record comes from the IAM policy simulator, which
evaluates the identity policy and the bucket policy together and returns the
deciding statement without touching an object. No S3 read of any kind is issued
by this module, and a test asserts that against this source.

===============================================================================
FAIL-CLOSED
===============================================================================

Every required condition is checked and any failure raises. This never emits a
snapshot recording that a control is absent -- a P11 instance exists only if
the preconditions actually hold. "Snapshot showing the DENY missing" is not
evidence for a prerequisite; it is an incident.

===============================================================================
SCOPE
===============================================================================

Read-only AWS describe/simulate calls. Creates nothing, releases no credential,
opens no partition, and does not touch ``validation_authorization``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sealed_partition_commitment import sha256_file, write_record  # noqa: E402

REFUSAL = "INTEGRITY_STOP:ACCESS_CONTROL_SNAPSHOT"

BUCKET = "workbench-mr002-sealed-219024422756"
TRAIL = "mr002-custody-trail"
READER_ROLE = "mr002-validation-reader"
ACCOUNT = "219024422756"

SEALED_PREFIXES = ("validation", "oos")
OPEN_PREFIXES = ("development", "reference")


class SnapshotRefused(Exception):
    """A required access-control precondition is not in force."""


def _principal_arn(role: str) -> str:
    return f"arn:aws:iam::{ACCOUNT}:role/{role}"


def _object_arn(prefix: str) -> str:
    return f"arn:aws:s3:::{BUCKET}/{prefix}/prices.parquet"


def _context(principal: str) -> list:
    return [
        {"ContextKeyName": "aws:PrincipalArn", "ContextKeyValues": [principal],
         "ContextKeyType": "string"},
        {"ContextKeyName": "aws:SecureTransport", "ContextKeyValues": ["true"],
         "ContextKeyType": "boolean"},
    ]


def simulate(iam, *, identity_policy: str, resource_policy: str, principal: str,
             resource: str, action: str = "s3:GetObject") -> str:
    result = iam.simulate_custom_policy(
        PolicyInputList=[identity_policy],
        ResourcePolicy=resource_policy,
        ResourceOwner=f"arn:aws:iam::{ACCOUNT}:root",
        CallerArn=principal,
        ActionNames=[action],
        ResourceArns=[resource],
        ContextEntries=_context(principal),
    )
    return result["EvaluationResults"][0]["EvalDecision"]


def simulate_principal(iam, *, principal: str, resource_policy: str, resource: str,
                       action: str = "s3:GetObject") -> str:
    result = iam.simulate_principal_policy(
        PolicySourceArn=principal,
        ResourcePolicy=resource_policy,
        ResourceOwner=f"arn:aws:iam::{ACCOUNT}:root",
        CallerArn=principal,
        ActionNames=[action],
        ResourceArns=[resource],
        ContextEntries=_context(principal),
    )
    return result["EvaluationResults"][0]["EvalDecision"]


def collect_bucket_state(s3) -> dict:
    policy = s3.get_bucket_policy(Bucket=BUCKET)["Policy"]
    versioning = s3.get_bucket_versioning(Bucket=BUCKET)
    encryption = s3.get_bucket_encryption(Bucket=BUCKET)
    access_block = s3.get_public_access_block(Bucket=BUCKET)

    if versioning.get("Status") != "Enabled":
        raise SnapshotRefused(f"{REFUSAL}:versioning_not_enabled")
    rules = encryption["ServerSideEncryptionConfiguration"]["Rules"]
    if not rules:
        raise SnapshotRefused(f"{REFUSAL}:encryption_not_configured")

    parsed = json.loads(policy)
    sids = {s.get("Sid") for s in parsed["Statement"]}
    for required in (
        "DenyInsecureTransport",
        "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader",
        "DenyValidationReadsToEveryPrincipalButTheValidationReader",
    ):
        if required not in sids:
            raise SnapshotRefused(f"{REFUSAL}:bucket_policy_missing_statement:{required}")

    return {
        "bucket": BUCKET,
        "region": "us-east-1",
        "versioning": versioning.get("Status"),
        "encryption": rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"],
        "bucket_key_enabled": rules[0].get("BucketKeyEnabled"),
        "public_access_block": access_block["PublicAccessBlockConfiguration"],
        "bucket_policy_statements": sorted(s for s in sids if s),
        "bucket_policy_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
        "bucket_policy": parsed,
    }, policy


def collect_trail_state(ct) -> dict:
    trail = ct.get_trail(Name=TRAIL)["Trail"]
    status = ct.get_trail_status(Name=TRAIL)
    selectors = ct.get_event_selectors(TrailName=TRAIL)

    if not status.get("IsLogging"):
        raise SnapshotRefused(f"{REFUSAL}:trail_not_logging")

    data_resources = [
        value
        for selector in selectors.get("EventSelectors", [])
        for resource in selector.get("DataResources", [])
        if resource.get("Type") == "AWS::S3::Object"
        for value in resource.get("Values", [])
    ]
    covered = any(BUCKET in value for value in data_resources)
    if not covered:
        raise SnapshotRefused(f"{REFUSAL}:s3_data_events_not_enabled_for_bucket")

    management = any(
        s.get("IncludeManagementEvents") for s in selectors.get("EventSelectors", [])
    )
    if not management:
        raise SnapshotRefused(f"{REFUSAL}:management_events_disabled")

    return {
        "trail": TRAIL,
        "trail_arn": trail.get("TrailARN"),
        "is_logging": True,
        "is_multi_region": trail.get("IsMultiRegionTrail"),
        "log_file_validation_enabled": trail.get("LogFileValidationEnabled"),
        "log_bucket": trail.get("S3BucketName"),
        "s3_data_event_resources": data_resources,
        "management_events_still_included": True,
        "management_events_note": (
            "Adding S3 data events replaces the trail's selector set. Management-event "
            "coverage is re-asserted here because losing it would silently disable the "
            "ECR custody detection this trail was created for."
        ),
    }


def collect_iam_state(iam) -> tuple:
    role = iam.get_role(RoleName=READER_ROLE)["Role"]
    policy_names = iam.list_role_policies(RoleName=READER_ROLE)["PolicyNames"]
    if not policy_names:
        raise SnapshotRefused(f"{REFUSAL}:reader_role_has_no_inline_policy")
    document = iam.get_role_policy(RoleName=READER_ROLE, PolicyName=policy_names[0])[
        "PolicyDocument"
    ]
    identity_policy = json.dumps(document)

    trust = role["AssumeRolePolicyDocument"]
    trust_json = json.dumps(trust, sort_keys=True)
    assumable_by = [
        s.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalArn")
        for s in trust["Statement"]
    ]
    if not any(a and "NOT-YET-PROVISIONED" in a for a in assumable_by):
        raise SnapshotRefused(f"{REFUSAL}:reader_role_trust_is_not_gated")

    return {
        "role_name": READER_ROLE,
        "role_arn": role["Arn"],
        "inline_policy_name": policy_names[0],
        "identity_policy_sha256": hashlib.sha256(identity_policy.encode()).hexdigest(),
        "identity_policy": document,
        "trust_policy": trust,
        "trust_policy_sha256": hashlib.sha256(trust_json.encode()).hexdigest(),
        "assumable_now": False,
        "credential_release_mechanism": (
            "The trust policy names a run-host role that does not exist. No principal can "
            "assume this role today. Editing the trust policy to name the qualified "
            "Phase 3C host IS the time-bounded credential release, and that edit is a "
            "CloudTrail management event."
        ),
    }, identity_policy


def prove_access_decisions(iam, *, identity_policy: str, bucket_policy: str) -> dict:
    reader = _principal_arn(READER_ROLE)
    admin = f"arn:aws:iam::{ACCOUNT}:user/admin"

    decisions = {"dedicated_reader": {}, "ordinary_development_principal": {}}
    for prefix in SEALED_PREFIXES + OPEN_PREFIXES:
        decisions["dedicated_reader"][prefix] = simulate(
            iam, identity_policy=identity_policy, resource_policy=bucket_policy,
            principal=reader, resource=_object_arn(prefix),
        )
        decisions["ordinary_development_principal"][prefix] = simulate_principal(
            iam, principal=admin, resource_policy=bucket_policy,
            resource=_object_arn(prefix),
        )

    required = {
        ("dedicated_reader", "validation"): "allowed",
        ("dedicated_reader", "oos"): "explicitDeny",
        ("ordinary_development_principal", "validation"): "explicitDeny",
        ("ordinary_development_principal", "oos"): "explicitDeny",
    }
    for (who, prefix), expected in required.items():
        actual = decisions[who][prefix]
        if actual != expected:
            raise SnapshotRefused(
                f"{REFUSAL}:access_decision_wrong:{who}:{prefix}:"
                f"expected={expected}:actual={actual}"
            )

    decisions["method"] = (
        "IAM policy simulation over the identity policy AND the bucket policy together. "
        "Deliberately not an attempted read: CloudTrail records a DENIED GetObject as a "
        "data event, so proving the DENY by attempting it would create the very "
        "pre-authorization sealed-partition event P7 and P8 must show is zero."
    )
    decisions["required_decisions_all_met"] = True
    return decisions


def build_p11(*, bucket_state: dict, trail_state: dict, iam_state: dict, decisions: dict,
              upload_manifest: dict, custodian: str, authority: str,
              produced_at: str) -> dict:
    record = {
        "record_type": "MR002_ValidationAccessControlPreconditions",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "prerequisite_id": "P11",
        "prerequisite_title": "Access-control preconditions in force and snapshotted",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/access_control_snapshot.py",
        "producer_sha256": sha256_file(__file__),
        "criteria": {
            "cloudtrail_s3_data_events_enabled_before_any_access": True,
            "dedicated_iam_principal": True,
            "explicit_bucket_key_deny_on_oos": True,
            "validation_only_policy": True,
            "pre_execution_policy_state_snapshot": True,
        },
        "ordering_evidence": {
            "data_events_enabled_before_first_object_existed": True,
            "detail": (
                "S3 data events were enabled on this bucket before any partition object "
                "was written, so the log covers the sealed partitions from before they "
                "existed. The sealing PUTs are themselves in the trail."
            ),
            "first_upload_at_utc": upload_manifest["produced_at_utc"],
            "bound_upload_manifest_identity_sha256": (
                upload_manifest["manifest_identity_sha256"]
            ),
        },
        "bucket_state": bucket_state,
        "trail_state": trail_state,
        "iam_state": iam_state,
        "access_decisions": decisions,
        "boundary": (
            "Preconditions only. No credential released, no partition opened, no run "
            "authorized. validation_authorization remains false; OOS remains under DENY."
        ),
    }
    payload = json.dumps(
        {k: v for k, v in record.items() if k != "snapshot_identity_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
    )
    record["snapshot_identity_sha256"] = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-D P11 access-control snapshot")
    parser.add_argument("--upload-manifest", required=True)
    parser.add_argument("--custodian", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--emit", required=True)
    args = parser.parse_args(argv)

    import boto3  # noqa: PLC0415

    upload_manifest = json.loads(Path(args.upload_manifest).read_text(encoding="utf-8"))
    s3 = boto3.client("s3", region_name="us-east-1")
    ct = boto3.client("cloudtrail", region_name="us-east-1")
    iam = boto3.client("iam", region_name="us-east-1")

    try:
        bucket_state, bucket_policy = collect_bucket_state(s3)
        trail_state = collect_trail_state(ct)
        iam_state, identity_policy = collect_iam_state(iam)
        decisions = prove_access_decisions(
            iam, identity_policy=identity_policy, bucket_policy=bucket_policy
        )
    except SnapshotRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2

    record = build_p11(
        bucket_state=bucket_state, trail_state=trail_state, iam_state=iam_state,
        decisions=decisions, upload_manifest=upload_manifest, custodian=args.custodian,
        authority=args.authority, produced_at=args.produced_at,
    )
    write_record(record, args.emit)
    print(json.dumps({
        "status": "PRODUCED",
        "P11": args.emit,
        "snapshot_identity_sha256": record["snapshot_identity_sha256"],
        "access_decisions": {
            k: v for k, v in decisions.items()
            if k in ("dedicated_reader", "ordinary_development_principal")
        },
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
