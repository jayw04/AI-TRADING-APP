"""WP-D — upload the exported partition objects into the sealed store.

Authorized by ``MR002_PrerequisiteProduction_Authorization_v1.0.json`` (WP-D)
and sequenced by ``MR002_ExecutionSequencing_Direction_v1.0.json`` (D-S2).

===============================================================================
WRITE-ONLY BY CONSTRUCTION
===============================================================================

This module can only PUT. It never issues ``get_object``, ``head_object`` or
``download_file``, and a test asserts that by reading this source. The reason is
P7: a read against the validation prefix before the authorization event is the
exact thing P7 must evidence as zero, and CloudTrail is append-only, so doing it
once would be permanently on the record.

Integrity therefore comes from the service rather than from a read-back. Every
object is uploaded with the SHA-256 that the export already verified against the
P6 commitment. S3 recomputes that digest on the bytes it actually received and
rejects the write if it disagrees. A truncated or corrupted transfer fails at
the API, and the failure is loud.

The returned ``ChecksumSHA256`` is compared again locally, so a service response
that did not echo the expected digest also refuses.

===============================================================================
UPLOAD ORDER
===============================================================================

CloudTrail S3 data events were enabled on this bucket BEFORE these objects
existed. The sealing writes are therefore themselves captured, which is what
lets P7 claim coverage from before the partition existed rather than from some
point after it was already sitting there.

===============================================================================
SCOPE
===============================================================================

Writes objects and records their version identities. Creates no IAM principal,
releases no credential, reads no partition, and does not touch
``validation_authorization``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sealed_partition_commitment import sha256_file, write_record  # noqa: E402

REFUSAL = "INTEGRITY_STOP:SEALED_STORE_UPLOAD"

BUCKET = "workbench-mr002-sealed-219024422756"


class UploadRefused(Exception):
    """A digest disagreed or a precondition failed. Never retried past the mismatch."""


def _b64_sha256(hex_digest: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")


def upload_object(client, bucket: str, key: str, path: Path, expected_sha256: str) -> dict:
    """PUT one object with a server-validated SHA-256. No read is ever issued."""
    actual = sha256_file(str(path))
    if actual != expected_sha256:
        raise UploadRefused(
            f"{REFUSAL}:local_digest_drift:{key}:manifest={expected_sha256}:disk={actual}"
        )
    expected_b64 = _b64_sha256(expected_sha256)
    response = client.put_object(
        Bucket=bucket,
        Key=key,
        Body=path.read_bytes(),
        ChecksumAlgorithm="SHA256",
        ChecksumSHA256=expected_b64,
        ServerSideEncryption="AES256",
    )
    returned = response.get("ChecksumSHA256")
    if returned != expected_b64:
        raise UploadRefused(
            f"{REFUSAL}:service_checksum_mismatch:{key}:expected={expected_b64}:got={returned}"
        )
    version = response.get("VersionId")
    if not version:
        raise UploadRefused(f"{REFUSAL}:no_version_id:{key}")
    return {
        "key": key,
        "version_id": version,
        "sha256": expected_sha256,
        "checksum_sha256_b64": returned,
        "bytes": path.stat().st_size,
        "server_validated": True,
    }


def upload_store(client, export_manifest: dict, store_dir: Path, bucket: str) -> dict:
    uploaded = {}
    for key, entry in sorted(export_manifest["objects"].items()):
        uploaded[key] = upload_object(
            client, bucket, key, store_dir / key, entry["object_sha256"]
        )
    return uploaded


def build_manifest(uploaded: dict, export_manifest: dict, *, bucket: str, custodian: str,
                   authority: str, produced_at: str) -> dict:
    manifest = {
        "record_type": "MR002_SealedStoreUploadManifest",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/sealed_store_upload.py",
        "producer_sha256": sha256_file(__file__),
        "bucket": bucket,
        "region": "us-east-1",
        "bound_export_manifest_identity_sha256": export_manifest["manifest_identity_sha256"],
        "bound_p6_commitment_identity_sha256": (
            export_manifest["bound_p6_commitment_identity_sha256"]
        ),
        "object_count": len(uploaded),
        "total_bytes": sum(o["bytes"] for o in uploaded.values()),
        "every_object_server_validated": all(o["server_validated"] for o in uploaded.values()),
        "integrity_method": (
            "Each object was uploaded with the SHA-256 already verified against P6; S3 "
            "recomputed it server-side on the received bytes. No object was read back: a "
            "GetObject on the validation prefix before authorization is the event P7 must "
            "evidence as zero."
        ),
        "cloudtrail_data_events_enabled_before_upload": True,
        "sealed_prefixes": ["validation", "oos"],
        "objects": dict(sorted(uploaded.items())),
        "boundary": (
            "Objects written and pinned by version. No credential released, no partition "
            "opened. validation_authorization remains false; OOS remains under DENY."
        ),
    }
    payload = json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_identity_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    manifest["manifest_identity_sha256"] = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-D sealed-store upload")
    parser.add_argument("--export-manifest", required=True)
    parser.add_argument("--store-dir", required=True)
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--custodian", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--emit-manifest", required=True)
    args = parser.parse_args(argv)

    import boto3  # noqa: PLC0415 — kept local so the module imports without the AWS SDK

    export_manifest = json.loads(Path(args.export_manifest).read_text(encoding="utf-8"))
    if export_manifest.get("record_type") != "MR002_SealedStoreExportManifest":
        print(json.dumps({"status": "REFUSED", "reason": f"{REFUSAL}:wrong_export_record"}))
        return 2
    if not export_manifest.get("every_object_matches_p6"):
        print(json.dumps({"status": "REFUSED", "reason": f"{REFUSAL}:export_not_verified"}))
        return 2

    client = boto3.client("s3", region_name="us-east-1")
    try:
        uploaded = upload_store(client, export_manifest, Path(args.store_dir), args.bucket)
    except UploadRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2

    manifest = build_manifest(
        uploaded, export_manifest, bucket=args.bucket, custodian=args.custodian,
        authority=args.authority, produced_at=args.produced_at,
    )
    write_record(manifest, args.emit_manifest)
    print(json.dumps({
        "status": "UPLOADED",
        "objects": len(uploaded),
        "total_bytes": manifest["total_bytes"],
        "manifest_identity_sha256": manifest["manifest_identity_sha256"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
