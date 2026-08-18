"""Daily EC2 fleet audit — no instance runs without a recorded reason.

Owner ruling 2026-08-16: EC2/EBS must not become permanent evidence custody, and no
instance should keep running (billing) without an explicit, reviewable justification.
This monitor enforces that prospectively:

  - every RUNNING instance must appear in AUTHORIZED_RUNNING below;
  - a time-boxed authorization past its `authorized_until` is a violation even if listed;
  - an EBS volume in `available` state (attached to nothing) is a violation — orphaned
    volumes are exactly the "permanent infrastructure bill" the ruling forbids.

Deployed as Lambda `workbench-fleet-audit` (daily via EventBridge, 13:05 UTC, five
minutes after the MR-002 custody monitor so alert emails arrive together). On FAIL it
publishes to the standard alarms topic and always writes a dated receipt to S3.

This is a DETECTION control only. It stops nothing and authorizes nothing. Adding an
entry to AUTHORIZED_RUNNING is a deliberate, reviewed act — the entry IS the recorded
reason, so a bare instance id with no reason is refused at import time.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"

# Instance id -> {name, reason, authorized_until (ISO-8601 UTC or None = standing)}.
# A standing entry means "this is production"; everything else must carry an expiry.
AUTHORIZED_RUNNING = {
    "i-084f47fe4e69192e9": {
        "name": "workbench-paper",
        "reason": "Live paper-trading application host (ADR 0032 cutover); the production runtime.",
        "authorized_until": None,
    },
    "i-0db7a37488c8017cc": {
        "name": "globalcomplyai-lab-gateway",
        "reason": "Separate GlobalComplyAI lab project (not Trading Workbench); owner-acknowledged 2026-08-16.",
        "authorized_until": None,
    },
    # ADR-0043 WSS (i-0fff7076ad461aa9a) removed 2026-08-18: the authorization lapsed
    # unexercised at 21:41:00Z, the post-lapse census confirmed no substrate or trading
    # authority was ever exercised, and the CloudFormation stack was deleted at 22:41Z.
    # The evidence volume vol-0710769fb6981102d is retained by DeletionPolicy and is a
    # separate owner decision.
}

for _iid, _entry in AUTHORIZED_RUNNING.items():
    if not _entry.get("reason", "").strip():
        raise RuntimeError(f"AUTHORIZED_RUNNING entry {_iid} has no recorded reason")

TOPIC_ARN = os.environ.get(
    "FLEET_AUDIT_TOPIC_ARN", "arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
)
RECEIPT_BUCKET = os.environ.get(
    "FLEET_AUDIT_RECEIPT_BUCKET", "workbench-backups-219024422756"
)
RECEIPT_PREFIX = os.environ.get("FLEET_AUDIT_RECEIPT_PREFIX", "fleet-audit/receipts")


def _check(findings, name, ok, detail):
    findings.append(
        {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}
    )
    return ok


def _name_tag(instance):
    for tag in instance.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return "<unnamed>"


def run_checks(ec2, now):
    """Return (verdict, findings). Reports; never mutates anything."""
    findings = []

    try:
        reservations = ec2.describe_instances()["Reservations"]
    except ClientError as exc:
        _check(
            findings, "describe_instances", False, f"describe_instances failed: {exc}"
        )
        return "FAIL", findings

    running = {
        inst["InstanceId"]: inst
        for res in reservations
        for inst in res["Instances"]
        if inst["State"]["Name"] in ("running", "pending")
    }

    unauthorized = sorted(set(running) - set(AUTHORIZED_RUNNING))
    _check(
        findings,
        "no_unauthorized_running",
        not unauthorized,
        "every running instance has a recorded reason"
        if not unauthorized
        else "RUNNING WITHOUT RECORDED REASON: "
        + "; ".join(f"{iid} ({_name_tag(running[iid])})" for iid in unauthorized),
    )

    expired = [
        (iid, entry)
        for iid, entry in AUTHORIZED_RUNNING.items()
        if iid in running
        and entry["authorized_until"] is not None
        and now >= datetime.fromisoformat(entry["authorized_until"])
    ]
    _check(
        findings,
        "no_expired_authorization",
        not expired,
        "no time-boxed authorization has lapsed while its instance runs"
        if not expired
        else "AUTHORIZATION EXPIRED, INSTANCE STILL RUNNING: "
        + "; ".join(
            f"{iid} ({e['name']}) expired {e['authorized_until']}" for iid, e in expired
        ),
    )

    stale = sorted(
        set(AUTHORIZED_RUNNING)
        - {i for r in reservations for j in r["Instances"] for i in [j["InstanceId"]]}
    )
    _check(
        findings,
        "allowlist_entries_exist",
        not stale,
        "every allowlist entry matches a real instance"
        if not stale
        else f"allowlist names instances that no longer exist (prune them): {stale}",
    )

    try:
        volumes = ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )["Volumes"]
    except ClientError as exc:
        volumes = None
        _check(findings, "describe_volumes", False, f"describe_volumes failed: {exc}")
    if volumes is not None:
        _check(
            findings,
            "no_orphaned_ebs_volumes",
            not volumes,
            "no unattached EBS volumes"
            if not volumes
            else "ORPHANED (unattached) EBS VOLUMES: "
            + "; ".join(f"{v['VolumeId']} ({v['Size']} GiB)" for v in volumes),
        )

    verdict = "PASS" if all(f["status"] == "PASS" for f in findings) else "FAIL"
    return verdict, findings


def build_receipt(verdict, findings, now):
    receipt = {
        "record_type": "WorkbenchFleetAuditReceipt",
        "version": "1.0",
        "verified_at": now.isoformat(),
        "verdict": verdict,
        "region": REGION,
        "checks": findings,
        "authorized_running": AUTHORIZED_RUNNING,
        "scope": "fleet detection ONLY. This receipt authorizes nothing; adding an "
        "AUTHORIZED_RUNNING entry is the deliberate act, not this report.",
    }
    body = json.dumps(receipt, sort_keys=True)
    receipt["body_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    return receipt


def lambda_handler(event=None, context=None):  # noqa: ARG001 - AWS signature
    now = datetime.now(timezone.utc)
    ec2 = boto3.client("ec2", region_name=REGION)
    verdict, findings = run_checks(ec2, now)
    receipt = build_receipt(verdict, findings, now)

    key = f"{RECEIPT_PREFIX}/{now:%Y/%m}/fleet-{now:%Y%m%dT%H%M%SZ}-{verdict}.json"
    try:
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=RECEIPT_BUCKET,
            Key=key,
            Body=(json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
            ContentType="application/json",
        )
    except ClientError as exc:
        receipt["receipt_write_error"] = str(exc)

    if verdict != "PASS":
        failed = [f for f in findings if f["status"] == "FAIL"]
        lines = "\n".join(f"  - {f['check']}: {f['detail']}" for f in failed)
        boto3.client("sns", region_name=REGION).publish(
            TopicArn=TOPIC_ARN,
            Subject="WORKBENCH FLEET AUDIT FAILED - unjustified EC2/EBS",
            Message=(
                "WORKBENCH EC2 FLEET AUDIT FAILED\n\n"
                f"When: {now.isoformat()}\n\n"
                f"Failed checks:\n{lines}\n\n"
                "Ruling 2026-08-16: no instance runs without a recorded reason, and EC2/EBS "
                "is never permanent evidence custody. Either stop/terminate the resource, or "
                "add a reviewed AUTHORIZED_RUNNING entry (with expiry unless production) to "
                "scripts/fleet_audit/ec2_fleet_audit.py and redeploy the Lambda.\n\n"
                f"Receipt: s3://{RECEIPT_BUCKET}/{key}\n"
            ),
        )

    print(json.dumps({"verdict": verdict, "receipt": key}))
    return receipt


if __name__ == "__main__":
    result = lambda_handler()
    print(json.dumps(result, indent=2, sort_keys=True))
