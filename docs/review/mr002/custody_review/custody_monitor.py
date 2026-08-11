"""MR-002 custody-integrity monitor (scheduled detection control).

⚠ THIS IS NOT AN EXECUTION AUTHORIZATION GATE.

This monitor DETECTS loss or drift of the P5-bound evaluator image. It does NOT
satisfy custody Requirement 7, and it must never be consumed by require_binding()
or any pre-read path as a cached substitute for live resolution.

    Property            | This monitor            | Requirement 7 resolver
    --------------------|-------------------------|------------------------------
    Purpose             | Detect loss or drift    | Block execution
    Timing              | Scheduled               | Immediately before window read
    Failure effect      | Alert + incident        | Fail closed; no read
    Registry down       | Report custody failure  | Prevent execution
    Satisfies Req 7     | NO                      | Yes, once accepted

A PASSING RUN OF THIS MONITOR AUTHORIZES NOTHING. It does not advance any
prerequisite, does not change validation_authorization, and grants no access to
validation, OOS, or sealed values. This monitor never reads sealed data.

What it verifies, per the adjudicated custody model:
  1. the bound OCI index retrieves by digest and hashes BYTE-EXACT
  2. the index media type is an OCI image index
  3. the linux/amd64 platform manifest is present at its bound digest
  4. the image configuration is at its bound digest
  5. the BuildKit attestation descriptor is accounted for
  6. the SINGLE-ARTIFACT REPOSITORY INVARIANT holds — no foreign objects
  7. tag immutability is still enforced
  8. no lifecycle policy exists (a lifecycle policy could expire the bound image)
"""
import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
REPOSITORY = "mr002-evaluator-p5"
TAG = "runtime-index-v1"

# Bound identities, RETARGETED 2026-08-11 to the runtime image index alongside
# the WP-B rebind. The INDEX is the governing object; the platform manifest and
# configuration are subordinate identities and are NOT substitutes for it. A
# monitor still watching the predecessor would have reported healthy custody of
# an image no run can execute.
INDEX = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
AMD64 = "sha256:4d1945a64c114c078db2be1938c40f64faa24191d12c7355174b3ddbeef7969b"
CONFIG = "sha256:226643c46e0d0043fb43147c214a6d71cd28acb847e66a093dcd882ea78d0cf6"

# The governed index carries exactly one platform entry and NO attestation
# child. The predecessor's descriptor count of 2 was one image plus a buildx
# attestation, never two platforms, so "expect an attestation" is not a
# property to carry forward.
ATTEST = None

# Historical artifacts that MUST remain present. They are superseded, not
# disposable: the predecessor index is the SS4/P5 evidence, and its children are
# reachable beneath it. Their disappearance is a custody failure even though no
# run resolves them.
HISTORICAL_INDEX = "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"
HISTORICAL_AMD64 = "sha256:a4e3ac54151b0bd27dd527b4df13da47058dbb8596be8ec9a77f44b863191a3d"
HISTORICAL_ATTEST = "sha256:b81cd073e34445ec31f2bffff0bb1345c6ccc31940c20a29fb7d9987915ae7cc"
PRESERVED_HISTORICAL = {HISTORICAL_INDEX, HISTORICAL_AMD64, HISTORICAL_ATTEST}

INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"

# The repository is no longer single-artifact: it holds the governed pair AND
# the preserved predecessor set. Both absence and foreign additions are drift.
EXPECTED_INVENTORY = {INDEX, AMD64} | PRESERVED_HISTORICAL

TOPIC_ARN = os.environ.get(
    "CUSTODY_TOPIC_ARN", "arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
)
RECEIPT_BUCKET = os.environ.get("CUSTODY_RECEIPT_BUCKET", "workbench-backups-219024422756")
RECEIPT_PREFIX = os.environ.get("CUSTODY_RECEIPT_PREFIX", "mr002/custody/receipts")


def _check(findings, name, ok, detail):
    findings.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    return ok


def run_checks(ecr):
    """Return (verdict, findings). Never raises on a custody failure — it reports."""
    findings = []

    # --- repository-level controls -------------------------------------------
    try:
        repo = ecr.describe_repositories(repositoryNames=[REPOSITORY])["repositories"][0]
        _check(findings, "tag_immutability", repo.get("imageTagMutability") == "IMMUTABLE",
               f"imageTagMutability={repo.get('imageTagMutability')}")
    except ClientError as exc:
        _check(findings, "repository_present", False, f"describe_repositories failed: {exc}")
        return "FAIL", findings

    try:
        ecr.get_lifecycle_policy(repositoryName=REPOSITORY)
        _check(findings, "no_lifecycle_policy", False,
               "a lifecycle policy EXISTS and could expire the bound image")
    except ClientError as exc:
        absent = exc.response["Error"]["Code"] == "LifecyclePolicyNotFoundException"
        _check(findings, "no_lifecycle_policy", absent,
               "absent" if absent else f"unexpected error: {exc}")

    # --- single-artifact repository invariant ---------------------------------
    try:
        inventory, paginator = set(), ecr.get_paginator("describe_images")
        tags_on_index = []
        for page in paginator.paginate(repositoryName=REPOSITORY):
            for det in page["imageDetails"]:
                inventory.add(det["imageDigest"])
                if det["imageDigest"] == INDEX:
                    tags_on_index = det.get("imageTags") or []
        foreign = inventory - EXPECTED_INVENTORY
        missing = EXPECTED_INVENTORY - inventory
        _check(findings, "repository_inventory_invariant", not foreign and not missing,
               f"foreign={sorted(foreign)} missing={sorted(missing)}")
        _check(findings, "historical_artifacts_preserved",
               PRESERVED_HISTORICAL <= inventory,
               f"missing_historical={sorted(PRESERVED_HISTORICAL - inventory)}")
        _check(findings, "governing_tag", tags_on_index == [TAG],
               f"tags on index={tags_on_index}")
    except ClientError as exc:
        _check(findings, "single_artifact_invariant", False, f"describe_images failed: {exc}")

    # --- the governing object, verified byte-exact -----------------------------
    try:
        raw = ecr.batch_get_image(
            repositoryName=REPOSITORY, imageIds=[{"imageDigest": INDEX}]
        )["images"][0]["imageManifest"]
        actual = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
        _check(findings, "index_byte_exact", actual == INDEX, f"retrieved={actual}")

        index = json.loads(raw)
        _check(findings, "index_media_type", index.get("mediaType") == INDEX_MEDIA_TYPE,
               f"mediaType={index.get('mediaType')}")

        members = {m["digest"]: m for m in index.get("manifests", [])}
        amd = members.get(AMD64, {})
        plat = amd.get("platform", {})
        _check(findings, "amd64_manifest_bound", bool(amd),
               f"linux/amd64 manifest {AMD64[:19]}... {'present' if amd else 'ABSENT'}")
        _check(findings, "amd64_platform",
               (plat.get("os"), plat.get("architecture")) == ("linux", "amd64"),
               f"platform={plat.get('os')}/{plat.get('architecture')}")
        attestations = [
            d for d, m in members.items()
            if (m.get("annotations") or {}).get("vnd.docker.reference.type")
            == "attestation-manifest"
            or (m.get("platform") or {}).get("architecture") == "unknown"
        ]
        _check(findings, "no_attestation_child", not attestations,
               f"attestation/provenance descriptors={sorted(attestations)}")
        _check(findings, "no_extra_descriptors", set(members) == {AMD64},
               f"descriptors={sorted(members)}")
    except (ClientError, IndexError, KeyError, ValueError) as exc:
        _check(findings, "index_retrieval", False, f"index retrieval failed: {exc}")

    # --- subordinate identity: image configuration -----------------------------
    try:
        raw = ecr.batch_get_image(
            repositoryName=REPOSITORY, imageIds=[{"imageDigest": AMD64}]
        )["images"][0]["imageManifest"]
        cfg = json.loads(raw).get("config", {}).get("digest")
        _check(findings, "config_digest", cfg == CONFIG, f"config={cfg}")
    except (ClientError, IndexError, KeyError, ValueError) as exc:
        _check(findings, "config_digest", False, f"platform manifest retrieval failed: {exc}")

    verdict = "PASS" if all(f["status"] == "PASS" for f in findings) else "FAIL"
    return verdict, findings


def build_receipt(verdict, findings, now):
    return {
        "record_type": "MR002_CustodyIntegrityReceipt",
        "version": "1.0",
        "verified_at": now.isoformat(),
        "verdict": verdict,
        "registry": f"219024422756.dkr.ecr.{REGION}.amazonaws.com/{REPOSITORY}",
        "governing_index_digest": INDEX,
        "checks": findings,
        "not_an_execution_gate": True,
        "satisfies_requirement_7": False,
        "scope": "custody detection ONLY. This receipt authorizes nothing, advances no "
                 "prerequisite, and must NOT be consumed by require_binding() or any "
                 "pre-read path as a substitute for live resolution.",
        "reads_sealed_data": False,
    }


def lambda_handler(event=None, context=None):  # noqa: ARG001 - AWS signature
    now = datetime.now(timezone.utc)
    ecr = boto3.client("ecr", region_name=REGION)
    verdict, findings = run_checks(ecr)
    receipt = build_receipt(verdict, findings, now)

    key = f"{RECEIPT_PREFIX}/{now:%Y/%m}/custody-{now:%Y%m%dT%H%M%SZ}-{verdict}.json"
    try:
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=RECEIPT_BUCKET, Key=key,
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
            Subject="MR-002 CUSTODY FAILURE - bound evaluator image",
            Message=(
                "MR-002 CUSTODY INTEGRITY CHECK FAILED\n\n"
                f"When: {now.isoformat()}\n"
                f"Repository: {REPOSITORY}\n"
                f"Governing index: {INDEX}\n\n"
                f"Failed checks:\n{lines}\n\n"
                "Do NOT rebuild the image and do NOT substitute a later build. The binding is "
                "instance identity, not bit-for-bit reproducibility; a rebuild is NOT equivalent "
                "and requires a superseding qualification.\n\n"
                "This is a DETECTION alert. It is not an execution gate and does not satisfy "
                "custody Requirement 7.\n"
                f"Receipt: s3://{RECEIPT_BUCKET}/{key}\n"
            ),
        )

    print(json.dumps({"verdict": verdict, "receipt": key}))
    return receipt


if __name__ == "__main__":
    print(json.dumps(lambda_handler(), sort_keys=True, indent=2))
