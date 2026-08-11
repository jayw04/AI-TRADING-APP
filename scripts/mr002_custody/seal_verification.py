"""WP-C — P7 and P8: the sealed-partition access history and seal verification.

Authorized by ``MR002_PrerequisiteProduction_Authorization_v1.0.json`` (WP-C)
and sequenced by ``MR002_ExecutionSequencing_Direction_v1.0.json`` (D-S2).

  * **P7** ``ValidationPartitionAccessHistory`` -- hash-chained access history
    evidencing ``validation_access_events_before_authorization = 0`` AND
    ``oos_access_events_before_validation = 0``.
  * **P8** ``ValidationSealVerificationReport`` -- content commitment stable, no
    access before authorization, OpenedObjectLedger reconciles against the
    SealedStoreAccessLog, OOS DENY in force.

===============================================================================
WHAT P7 CAN AND CANNOT HONESTLY CLAIM
===============================================================================

P7 is built from CloudTrail S3 data events. Those events exist only from the
moment data events were enabled on the sealed bucket, which is also the moment
before the first partition object was written. So the log genuinely covers the
sealed partitions from before they existed -- there is no window in which an
object sat in this store unlogged.

What P7 does NOT cover, and says so in the record rather than leaving a reader
to assume otherwise: the period during which the corpus existed only as a
DuckDB file on the developer laptop. No store-level access log existed then,
and none can be manufactured now. The zero-access claim is scoped to the sealed
store, and the earlier period rests on a different and weaker basis -- the
procedural seal recorded in the preregistration. Stating the boundary is the
point; a P7 that implied continuous coverage since 2026-07-12 would be false.

===============================================================================
READS ARE COUNTED, NOT ASSUMED
===============================================================================

An event is classified by CloudTrail's own ``readOnly`` flag and its
``eventName``, not by whether it succeeded. A DENIED read is still a read
ATTEMPT and is recorded as such, with ``authorized: false``. The gate counts
successful reads, and the record carries attempts separately so a reviewer can
see both. Silently dropping denied attempts would hide exactly the evidence a
seal audit exists to surface.

===============================================================================
SCOPE
===============================================================================

Reads the CloudTrail LOG bucket, which carries no data events of its own, so
producing this record creates no sealed-partition event. Opens no partition
object, releases no credential, and does not touch
``validation_authorization``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sealed_partition_commitment import (  # noqa: E402
    SNAPSHOT,
    SNAPSHOT_SHA256,
    commit_window,
    open_snapshot,
    sha256_file,
    write_record,
)

REFUSAL = "INTEGRITY_STOP:SEAL_VERIFICATION"

SEALED_BUCKET = "workbench-mr002-sealed-219024422756"
LOG_BUCKET = "workbench-cloudtrail-219024422756"
ACCOUNT = "219024422756"

SEALED_PREFIXES = ("validation", "oos")
ZERO = "0" * 64


class VerificationRefused(Exception):
    """A seal condition does not hold. Never downgraded to a warning."""


# ---------------------------------------------------------------------------
# CloudTrail collection
# ---------------------------------------------------------------------------


def log_prefixes(dates) -> list:
    return [
        f"AWSLogs/{ACCOUNT}/CloudTrail/us-east-1/{d[:4]}/{d[5:7]}/{d[8:10]}/" for d in dates
    ]


def collect_events(s3, dates) -> list:
    """Every CloudTrail record naming the sealed bucket, across the given days."""
    events = []
    for prefix in log_prefixes(dates):
        token = None
        while True:
            kwargs = {"Bucket": LOG_BUCKET, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = s3.list_objects_v2(**kwargs)
            for item in page.get("Contents", []):
                body = s3.get_object(Bucket=LOG_BUCKET, Key=item["Key"])["Body"].read()
                payload = json.loads(gzip.decompress(body).decode("utf-8"))
                for record in payload.get("Records", []):
                    if _names_sealed_bucket(record):
                        events.append(record)
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
    return events


def _names_sealed_bucket(record: dict) -> bool:
    params = record.get("requestParameters") or {}
    if params.get("bucketName") == SEALED_BUCKET:
        return True
    for resource in record.get("resources") or []:
        arn = resource.get("ARN") or ""
        if SEALED_BUCKET in arn:
            return True
    return False


def _object_key(record: dict) -> str:
    params = record.get("requestParameters") or {}
    key = params.get("key")
    if key:
        return key
    for resource in record.get("resources") or []:
        arn = resource.get("ARN") or ""
        if f":::{SEALED_BUCKET}/" in arn:
            return arn.split(f":::{SEALED_BUCKET}/", 1)[1]
    return ""


def _partition(key: str) -> str:
    return key.split("/")[0] if "/" in key else "(bucket-level)"


def _principal(record: dict) -> str:
    identity = record.get("userIdentity") or {}
    return identity.get("arn") or identity.get("principalId") or "(unknown)"


# ---------------------------------------------------------------------------
# P7 — hash-chained access history
# ---------------------------------------------------------------------------


def build_access_history(events: list) -> dict:
    rows = []
    chain = ZERO
    for record in sorted(events, key=lambda r: (r.get("eventTime", ""), r.get("eventID", ""))):
        key = _object_key(record)
        row = {
            "partition": _partition(key),
            "event_time_utc": record.get("eventTime"),
            "principal": _principal(record),
            "operation": record.get("eventName"),
            "object_key_prefix": key.rsplit("/", 1)[0] if "/" in key else key,
            "read_only": bool(record.get("readOnly")),
            "authorized": record.get("errorCode") is None,
            "error_code": record.get("errorCode"),
            "authorization_event_ref": None,
            "event_id": record.get("eventID"),
            "hash_chain_prev": chain,
        }
        row["hash_chain_row"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=True).encode("ascii")
        ).hexdigest()
        chain = row["hash_chain_row"]
        rows.append(row)
    return {"rows": rows, "chain_head": chain}


def chain_verifies(rows: list) -> bool:
    prev = ZERO
    for row in rows:
        if row["hash_chain_prev"] != prev:
            return False
        body = {k: v for k, v in row.items() if k != "hash_chain_row"}
        if hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=True).encode("ascii")
        ).hexdigest() != row["hash_chain_row"]:
            return False
        prev = row["hash_chain_row"]
    return True


def gate_values(rows: list) -> dict:
    def reads(partition, *, successful):
        return [
            r for r in rows
            if r["partition"] == partition and r["read_only"]
            and (r["authorized"] if successful else not r["authorized"])
        ]

    return {
        "validation_access_events_before_authorization": len(
            reads("validation", successful=True)
        ),
        "oos_access_events_before_validation": len(reads("oos", successful=True)),
        "validation_read_attempts_denied": len(reads("validation", successful=False)),
        "oos_read_attempts_denied": len(reads("oos", successful=False)),
        "sealing_writes": len(
            [r for r in rows if r["partition"] in SEALED_PREFIXES and not r["read_only"]]
        ),
        "total_events_on_sealed_store": len(rows),
    }


def build_p7(history: dict, gates: dict, *, coverage_start: str, custodian: str,
             authority: str, produced_at: str, upload_manifest: dict) -> dict:
    if gates["validation_access_events_before_authorization"] != 0:
        raise VerificationRefused(
            f"{REFUSAL}:validation_read_before_authorization:"
            f"{gates['validation_access_events_before_authorization']}"
        )
    if gates["oos_access_events_before_validation"] != 0:
        raise VerificationRefused(
            f"{REFUSAL}:oos_read_before_validation:"
            f"{gates['oos_access_events_before_validation']}"
        )
    if not chain_verifies(history["rows"]):
        raise VerificationRefused(f"{REFUSAL}:hash_chain_broken")

    record = {
        "record_type": "ValidationPartitionAccessHistory",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "prerequisite_id": "P7",
        "prerequisite_title": "ValidationPartitionAccessHistory (runtime instance)",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/seal_verification.py",
        "producer_sha256": sha256_file(__file__),
        "source": (
            f"CloudTrail S3 data events for s3://{SEALED_BUCKET}, delivered to "
            f"s3://{LOG_BUCKET}"
        ),
        "required_gate_values": {
            "validation_access_events_before_authorization": 0,
            "oos_access_events_before_validation": 0,
        },
        "observed_gate_values": gates,
        "gates_met": True,
        "hash_chain": {
            "rows": len(history["rows"]),
            "chain_head": history["chain_head"],
            "verifies": True,
            "algorithm": "SHA-256 over the ascii JSON row including hash_chain_prev",
        },
        "coverage": {
            "starts_at_utc": coverage_start,
            "covers_partition_from_before_it_existed": True,
            "detail": (
                "CloudTrail S3 data events were enabled on the sealed bucket before any "
                "partition object was written, so no object has ever sat in this store "
                "unlogged. The sealing writes themselves appear in the chain below."
            ),
            "NOT_covered": (
                "The period during which the corpus existed only as a DuckDB file on the "
                "developer workstation. No store-level access log existed then and none "
                "can be manufactured now. The zero-access claim above is scoped to the "
                "sealed store; the earlier period rests on the procedural seal recorded "
                "in prereg v1.0.4 (sealed_data_read = false), which is a weaker basis and "
                "is deliberately not restated here as if it were audited."
            ),
        },
        "denied_attempts_are_recorded_not_dropped": (
            "A denied read is still a read ATTEMPT and appears in the chain with "
            "authorized=false. The gate counts successful reads; attempts are reported "
            "separately so a reviewer sees both."
        ),
        "bound_upload_manifest_identity_sha256": upload_manifest["manifest_identity_sha256"],
        "access_history": history["rows"],
        "boundary": (
            "Evidence only. validation_authorization remains false; OOS remains under DENY."
        ),
    }
    record["history_identity_sha256"] = _identity(record)
    return record


# ---------------------------------------------------------------------------
# P8 — seal verification report
# ---------------------------------------------------------------------------


def verify_content_commitment_stable(p6: dict) -> dict:
    """Recompute the validation partition commitment and compare against P6."""
    with open_snapshot(SNAPSHOT, SNAPSHOT_SHA256) as con:
        recomputed = commit_window(con, "validation")
    committed = p6["validation_partition"]["partition_content_sha256"]
    stable = recomputed["partition_content_sha256"] == committed
    if not stable:
        raise VerificationRefused(
            f"{REFUSAL}:content_commitment_drifted:"
            f"p6={committed}:recomputed={recomputed['partition_content_sha256']}"
        )
    return {
        "committed_sha256": committed,
        "recomputed_sha256": recomputed["partition_content_sha256"],
        "stable": True,
        "row_count": recomputed["total_rows"],
        "method": "independent recomputation from the registered snapshot, read-only",
    }


def build_p8(*, p6: dict, p7: dict, p11: dict, commitment: dict, custodian: str,
             authority: str, produced_at: str) -> dict:
    oos_denied = (
        p11["access_decisions"]["dedicated_reader"]["oos"] == "explicitDeny"
        and p11["access_decisions"]["ordinary_development_principal"]["oos"] == "explicitDeny"
    )
    if not oos_denied:
        raise VerificationRefused(f"{REFUSAL}:oos_deny_not_in_force")

    opened = p7["observed_gate_values"]["validation_access_events_before_authorization"]
    store_reads = opened + p7["observed_gate_values"]["oos_access_events_before_validation"]

    record = {
        "record_type": "ValidationSealVerificationReport",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "prerequisite_id": "P8",
        "prerequisite_title": "ValidationSealVerificationReport (runtime instance)",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/seal_verification.py",
        "producer_sha256": sha256_file(__file__),
        "conditions": {
            "content_commitment_stable": commitment,
            "no_access_before_authorization": {
                "validation_access_events_before_authorization": opened,
                "oos_access_events_before_validation": (
                    p7["observed_gate_values"]["oos_access_events_before_validation"]
                ),
                "met": True,
                "source": "P7 hash-chained access history",
            },
            "opened_object_ledger_reconciles": {
                "opened_object_ledger_entries": 0,
                "sealed_store_read_events": store_reads,
                "reconciles": True,
                "note": (
                    "No authorized run has occurred, so the OpenedObjectLedger is empty by "
                    "construction. The reconciliation is therefore trivial (0 == 0) and is "
                    "reported as such rather than dressed up as a substantive check. It "
                    "becomes substantive only for the authorized Phase 3C run."
                ),
            },
            "oos_deny_in_force": {
                "dedicated_reader": p11["access_decisions"]["dedicated_reader"]["oos"],
                "ordinary_development_principal": (
                    p11["access_decisions"]["ordinary_development_principal"]["oos"]
                ),
                "met": True,
                "source": "P11 policy simulation, not an attempted read",
            },
        },
        "all_conditions_met": True,
        "bound_identities": {
            "p6_commitment_identity_sha256": p6["commitment_identity_sha256"],
            "p7_history_identity_sha256": p7["history_identity_sha256"],
            "p11_snapshot_identity_sha256": p11["snapshot_identity_sha256"],
        },
        "boundary": (
            "Verification only. This report satisfies a prerequisite; it does not "
            "authorize a run. validation_authorization remains false; OOS remains under "
            "DENY; the single validation opening remains unconsumed."
        ),
    }
    record["report_identity_sha256"] = _identity(record)
    return record


def _identity(record: dict) -> str:
    body = {k: v for k, v in record.items() if not k.endswith("_identity_sha256")}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-C P7/P8 seal verification")
    parser.add_argument("--dates", required=True, help="comma-separated YYYY-MM-DD to scan")
    parser.add_argument("--coverage-start", required=True)
    parser.add_argument("--p6", required=True)
    parser.add_argument("--p11", required=True)
    parser.add_argument("--upload-manifest", required=True)
    parser.add_argument("--custodian", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--emit-p7", required=True)
    parser.add_argument("--emit-p8", required=True)
    args = parser.parse_args(argv)

    import boto3  # noqa: PLC0415

    p6 = json.loads(Path(args.p6).read_text(encoding="utf-8"))
    p11 = json.loads(Path(args.p11).read_text(encoding="utf-8"))
    upload_manifest = json.loads(Path(args.upload_manifest).read_text(encoding="utf-8"))

    s3 = boto3.client("s3", region_name="us-east-1")
    events = collect_events(s3, args.dates.split(","))
    history = build_access_history(events)
    gates = gate_values(history["rows"])

    try:
        p7 = build_p7(
            history, gates, coverage_start=args.coverage_start, custodian=args.custodian,
            authority=args.authority, produced_at=args.produced_at,
            upload_manifest=upload_manifest,
        )
        commitment = verify_content_commitment_stable(p6)
        p8 = build_p8(
            p6=p6, p7=p7, p11=p11, commitment=commitment, custodian=args.custodian,
            authority=args.authority, produced_at=args.produced_at,
        )
    except VerificationRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2

    write_record(p7, args.emit_p7)
    write_record(p8, args.emit_p8)
    print(json.dumps({
        "status": "PRODUCED",
        "observed_gate_values": gates,
        "P7_history_identity_sha256": p7["history_identity_sha256"],
        "P8_report_identity_sha256": p8["report_identity_sha256"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
