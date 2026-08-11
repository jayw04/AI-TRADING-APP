"""WP-D — the custodian sealing export: partition objects for the sealed store.

Authorized by the owner on 2026-08-10
(``docs/review/mr002/MR002_PrerequisiteProduction_Authorization_v1.0.json``,
WP-D) and sequenced by ``MR002_ExecutionSequencing_Direction_v1.0.json`` (D-S2).

Turns the single frozen DuckDB snapshot into per-partition objects, because an
IAM DENY cannot be enforced against a date range inside one file. The OOS DENY
that P8 requires only becomes real once OOS rows live in objects a policy can
name.

===============================================================================
WHY VERIFICATION HAPPENS BEFORE UPLOAD, NOT AFTER
===============================================================================

The obvious way to check an upload is to download it and compare. Here that
would be self-defeating: a ``GetObject`` against the validation prefix, issued
by the custodian's admin principal before the authorization event, is precisely
the event P7 must evidence as ZERO. Verifying by read-back would manufacture the
violation it was trying to rule out -- and it would be permanent, because
CloudTrail is append-only.

So integrity is established in two halves that never require a read:

  1. **Locally, before upload.** Every written object is read back FROM DISK and
     its canonical content hash recomputed and compared against the P6
     commitment. A Parquet encoding that silently altered a value -- a float
     narrowed, a NULL collapsed to empty, a timestamp shifted by a zone -- fails
     here, on the laptop, before anything leaves it.
  2. **On upload, by S3 itself.** Objects are written with a precomputed
     SHA-256 that S3 validates server-side against the bytes it received. A
     corrupted transfer is rejected by the service; no read-back is needed to
     learn that.

The pairing matters. (1) proves the object still means what the corpus meant.
(2) proves the bytes that arrived are the bytes that were verified.

===============================================================================
FAIL-CLOSED
===============================================================================

Any round-trip mismatch, any row-count disagreement, any table whose content
hash is absent from the P6 commitment raises. Nothing partially exported is
left behind for a later step to pick up and trust.

===============================================================================
SCOPE
===============================================================================

Reads the registered snapshot READ-ONLY and writes local files. Makes no
network call, creates no AWS resource, releases no credential, and does not
touch ``validation_authorization``. Uploading is a separate, later step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sealed_partition_commitment import (  # noqa: E402
    OBSERVATION_TABLES,
    REFERENCE_TABLES,
    SNAPSHOT,
    SNAPSHOT_SHA256,
    CommitmentRefused,
    canonical_row,
    open_snapshot,
    sha256_file,
    table_columns,
    window_predicate,
    write_record,
)

REFUSAL = "INTEGRITY_STOP:SEALED_STORE_EXPORT"

PARTITIONS = ("development", "validation", "oos")
REFERENCE_PREFIX = "reference"

_BATCH = 20000


class ExportRefused(Exception):
    """A precondition or a round-trip check failed. Never downgraded to a warning."""


def _object_key(partition: str, table: str) -> str:
    return f"{partition}/{table}.parquet"


def _hash_relation(con, sql: str) -> tuple:
    """Stream a result set through SHA-256. Values never leave this function."""
    digest = hashlib.sha256()
    rows = 0
    cursor = con.execute(sql)
    while True:
        batch = cursor.fetchmany(_BATCH)
        if not batch:
            break
        for row in batch:
            digest.update(canonical_row(row))
            rows += 1
    return rows, digest.hexdigest()


def _projection(con, table: str) -> str:
    return ", ".join(f'"{c["name"]}"' for c in table_columns(con, table))


def export_partition_object(con, table: str, predicate: str | None, destination: Path) -> dict:
    """Write one partition object and prove it round-trips to the same canonical content."""
    projection = _projection(con, table)
    where = f" WHERE {predicate}" if predicate else ""
    source_sql = f"SELECT {projection} FROM {table}{where} ORDER BY ALL"

    destination.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(destination).replace("'", "''")
    con.execute(f"COPY ({source_sql}) TO '{escaped}' (FORMAT PARQUET)")

    source_rows, source_hash = _hash_relation(con, source_sql)
    read_back = f"SELECT {projection} FROM read_parquet('{escaped}') ORDER BY ALL"
    object_rows, object_hash = _hash_relation(con, read_back)

    if object_rows != source_rows:
        raise ExportRefused(
            f"{REFUSAL}:row_count_drift:{table}:corpus={source_rows}:object={object_rows}"
        )
    if object_hash != source_hash:
        raise ExportRefused(
            f"{REFUSAL}:content_drift_through_parquet:{table}:"
            f"corpus={source_hash}:object={object_hash}"
        )
    return {
        "row_count": source_rows,
        "content_sha256": source_hash,
        "object_sha256": sha256_file(str(destination)),
        "object_bytes": destination.stat().st_size,
        "round_trip_verified": True,
    }


def _expected_hashes(p6: dict) -> dict:
    """Per-(partition, table) content hashes as committed by P6."""
    expected = {}
    for partition, key in (
        ("development", "development_partition"),
        ("validation", "validation_partition"),
        ("oos", "oos_partition"),
    ):
        for table, entry in p6[key]["tables"].items():
            expected[(partition, table)] = entry["content_sha256"]
    for table, entry in p6["reference_tables"]["tables"].items():
        expected[(REFERENCE_PREFIX, table)] = entry["content_sha256"]
    return expected


def export_store(con, out_dir: Path, p6: dict) -> dict:
    """Export every partition object and verify each against the P6 commitment."""
    expected = _expected_hashes(p6)
    objects = {}

    for partition in PARTITIONS:
        for table in sorted(OBSERVATION_TABLES):
            key = _object_key(partition, table)
            entry = export_partition_object(
                con, table, window_predicate(table, partition), out_dir / key
            )
            want = expected.get((partition, table))
            if want is None:
                raise ExportRefused(f"{REFUSAL}:uncommitted_object:{key}")
            if entry["content_sha256"] != want:
                raise ExportRefused(
                    f"{REFUSAL}:commitment_mismatch:{key}:"
                    f"p6={want}:object={entry['content_sha256']}"
                )
            entry["matches_p6_commitment"] = True
            objects[key] = entry

    for table in REFERENCE_TABLES:
        key = _object_key(REFERENCE_PREFIX, table)
        entry = export_partition_object(con, table, None, out_dir / key)
        want = expected.get((REFERENCE_PREFIX, table))
        if entry["content_sha256"] != want:
            raise ExportRefused(
                f"{REFUSAL}:commitment_mismatch:{key}:"
                f"p6={want}:object={entry['content_sha256']}"
            )
        entry["matches_p6_commitment"] = True
        objects[key] = entry

    missing = set(expected) - {
        (k.split("/")[0], k.split("/")[1].removesuffix(".parquet")) for k in objects
    }
    if missing:
        raise ExportRefused(f"{REFUSAL}:committed_but_not_exported:{sorted(missing)}")

    return objects


def build_manifest(objects: dict, p6: dict, *, custodian: str, authority: str,
                   produced_at: str) -> dict:
    prefixes = {}
    for key, entry in objects.items():
        prefixes.setdefault(key.split("/")[0], {"objects": 0, "rows": 0, "bytes": 0})
        prefixes[key.split("/")[0]]["objects"] += 1
        prefixes[key.split("/")[0]]["rows"] += entry["row_count"]
        prefixes[key.split("/")[0]]["bytes"] += entry["object_bytes"]

    manifest = {
        "record_type": "MR002_SealedStoreExportManifest",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/sealed_store_export.py",
        "producer_sha256": sha256_file(__file__),
        "snapshot": SNAPSHOT,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "bound_p6_commitment_identity_sha256": p6["commitment_identity_sha256"],
        "every_object_matches_p6": True,
        "every_object_round_trip_verified": True,
        "verification_method": (
            "Each object is re-read FROM DISK and its canonical content hash recomputed "
            "and compared against P6. Verification deliberately never reads an uploaded "
            "object: a GetObject on the validation prefix before authorization is the "
            "exact event P7 must evidence as zero."
        ),
        "sealed_prefixes": ["validation", "oos"],
        "open_prefixes": ["development", "reference"],
        "prefix_summary": prefixes,
        "objects": dict(sorted(objects.items())),
        "boundary": (
            "Local export only. No object uploaded, no credential released, no partition "
            "opened for research use. validation_authorization remains false."
        ),
    }
    payload = json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_identity_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    manifest["manifest_identity_sha256"] = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-D sealed-store export")
    parser.add_argument("--snapshot", default=SNAPSHOT)
    parser.add_argument("--snapshot-sha256", default=SNAPSHOT_SHA256)
    parser.add_argument("--p6", required=True, help="path to the P6 content commitment")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--custodian", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--emit-manifest", required=True)
    args = parser.parse_args(argv)

    p6 = json.loads(Path(args.p6).read_text(encoding="utf-8"))
    if p6.get("record_type") != "ValidationPartitionContentCommitment":
        print(json.dumps({"status": "REFUSED", "reason": f"{REFUSAL}:p6_wrong_record_type"}))
        return 2

    try:
        with open_snapshot(args.snapshot, args.snapshot_sha256) as con:
            objects = export_store(con, Path(args.out_dir), p6)
    except (ExportRefused, CommitmentRefused) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2

    manifest = build_manifest(
        objects, p6, custodian=args.custodian, authority=args.authority,
        produced_at=args.produced_at,
    )
    write_record(manifest, args.emit_manifest)
    print(json.dumps({
        "status": "EXPORTED",
        "objects": len(objects),
        "total_bytes": sum(o["object_bytes"] for o in objects.values()),
        "manifest": args.emit_manifest,
        "manifest_identity_sha256": manifest["manifest_identity_sha256"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
