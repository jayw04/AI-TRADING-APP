"""Cycle 2C — PRISTINE PROOF for the former-OOS partition being redesignated Validation-2.

Owner ruling 2026-08-20: the consumed validation partition is permanently inadmissible, and the
still-unread OOS partition (2023-02-17 .. 2026-07-10, 850 sessions) is redesignated as Validation-2.
A role transfer is only honest if the "never read" claim is EVIDENCED at the moment of transfer, so
this producer regenerates the sealed-store access history through today and reports, specifically,
whether any of the six OOS objects has ever been successfully read.

WHY A NEW PRODUCER RATHER THAN seal_verification.py
    That producer emits P7/P8 together, and its P8 path calls verify_content_commitment_stable(),
    which opens the local corpus snapshot and recommits the VALIDATION window. Validation-2 needs
    none of that, the snapshot is not required here, and running a validation-scoped recommitment
    to prove an OOS property would be doing more than the question asks. This producer therefore
    REUSES the audited CloudTrail collection and hash-chain code from seal_verification by import,
    and does nothing else.

WHAT THIS TOUCHES
    Only the CloudTrail log bucket. It never opens the sealed store, never issues GetObject against
    any partition prefix, and never reads a snapshot. Reading the log of who read what is not
    reading the data.

FAIL-CLOSED
    The hash chain must verify and the OOS successful-read count must be zero. Either failing is a
    refusal, not a warning: a pristine claim that is merely "probably true" is worse than none,
    because the whole point of the redesignation is that this partition is clean.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from seal_verification import (  # noqa: E402
    SEALED_BUCKET,
    build_access_history,
    chain_verifies,
    collect_events,
    gate_values,
)

REFUSAL = "INTEGRITY_STOP:OOS_PRISTINE_PROOF"
OOS_OBJECTS = (
    "oos/actions.parquet", "oos/anchors.parquet", "oos/etf_prices.parquet",
    "oos/prices.parquet", "oos/sic_observations.parquet", "oos/universe.parquet",
)
READ_OPS = ("GetObject", "HeadObject", "SelectObjectContent", "GetObjectAttributes")


class ProofRefused(RuntimeError):
    pass


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _dates(start: str, end: str) -> list:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def per_object(rows: list) -> dict:
    """Per-object read accounting. An aggregate zero is not enough: the owner asked for zero reads
    of ALL SIX objects, so each is reported by name and a reviewer can see none was skipped."""
    out = {}
    for key in OOS_OBJECTS:
        hits = [r for r in rows if r.get("object_key_prefix", "") == key.rsplit("/", 1)[0]
                and r.get("operation") in READ_OPS]
        # object_key_prefix is the directory; match the operation set on the oos partition instead
        succ = [r for r in hits if r.get("authorized") and not r.get("error_code")]
        den = [r for r in hits if not r.get("authorized") or r.get("error_code")]
        out[key] = {"successful_reads": len(succ), "denied_or_errored_attempts": len(den)}
    return out


def build(rows: list, gates: dict, *, coverage_start: str, scanned: list,
          produced_at: str, custodian: str, authority: str) -> dict:
    oos_rows = [r for r in rows if r.get("partition") == "oos"]
    oos_reads = [r for r in oos_rows if r.get("operation") in READ_OPS]
    successful = [r for r in oos_reads if r.get("authorized") and not r.get("error_code")]
    denied = [r for r in oos_reads if not r.get("authorized") or r.get("error_code")]

    rec = {
        "record_type": "MR002_OOSPartitionAccessHistory",
        "version": "1.0",
        "purpose": "evidence that the partition being redesignated Validation-2 has never had a "
                   "successful governed read, established at the moment of redesignation",
        "produced_at_utc": produced_at,
        "custodian": custodian,
        "execution_authority": authority,
        "source": f"CloudTrail S3 data events for s3://{SEALED_BUCKET}",
        "scanned_dates": scanned,
        "coverage": {
            "starts_at_utc": coverage_start,
            "detail": "CloudTrail S3 data events were enabled on the sealed bucket BEFORE any "
                      "partition object was written, so no object has ever sat in this store "
                      "unlogged. The sealing writes themselves appear in the chain.",
            "NOT_covered": "the period during which the corpus existed only as a DuckDB file on "
                           "the developer workstation. No store-level access log existed then and "
                           "none can be manufactured now. This claim is scoped to the sealed "
                           "store and is deliberately not restated as if the earlier period were "
                           "audited.",
        },
        "oos_partition": {
            "objects": list(OOS_OBJECTS),
            "successful_reads": len(successful),
            "denied_or_errored_read_attempts": len(denied),
            "per_object": per_object(oos_rows),
            "denied_attempts_are_recorded_not_dropped": "a denied read is still an ATTEMPT and is "
                                                        "counted separately so a reviewer sees "
                                                        "both, rather than only the clean number",
        },
        "events": {
            "total_naming_the_sealed_store": len(rows),
            "on_the_oos_partition": len(oos_rows),
        },
        "observed_gate_values": gates,
        "hash_chain": {
            "algorithm": "SHA-256 over the ascii JSON row including hash_chain_prev",
            "rows": len(rows),
            "chain_head": rows[-1]["hash_chain_row"] if rows else None,
            "verifies": chain_verifies(rows),
        },
        "access_history": rows,
        "boundary": "EVIDENCE ONLY. This record grants nothing. It does not open Validation-2, "
                    "does not authorize a read, and does not change the OOS DENY currently in "
                    "force on this prefix.",
    }
    if not rec["hash_chain"]["verifies"]:
        raise ProofRefused(f"{REFUSAL}:hash_chain_does_not_verify")
    if len(successful) != 0:
        raise ProofRefused(
            f"{REFUSAL}:oos_successful_reads={len(successful)}:the partition is NOT pristine and "
            f"MUST NOT be redesignated as Validation-2")
    body = {k: v for k, v in rec.items() if k != "history_identity_sha256"}
    rec["history_identity_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cycle 2C OOS pristine proof")
    ap.add_argument("--start", required=True, help="first CloudTrail day to scan, YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="last CloudTrail day to scan, YYYY-MM-DD")
    ap.add_argument("--coverage-start", required=True)
    ap.add_argument("--produced-at", required=True)
    ap.add_argument("--custodian", required=True)
    ap.add_argument("--authority", required=True)
    ap.add_argument("--emit", required=True)
    args = ap.parse_args(argv)

    import boto3  # noqa: PLC0415

    s3 = boto3.client("s3", region_name="us-east-1")
    scanned = _dates(args.start, args.end)
    events = collect_events(s3, scanned)
    history = build_access_history(events)
    gates = gate_values(history["rows"])
    try:
        rec = build(history["rows"], gates, coverage_start=args.coverage_start, scanned=scanned,
                    produced_at=args.produced_at, custodian=args.custodian,
                    authority=args.authority)
    except ProofRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, indent=1))
        return 2

    out = Path(args.emit)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(_canonical(rec))
    tmp.replace(out)
    print(json.dumps({
        "status": "PRODUCED",
        "oos_successful_reads": rec["oos_partition"]["successful_reads"],
        "oos_denied_attempts": rec["oos_partition"]["denied_or_errored_read_attempts"],
        "events_on_sealed_store": rec["events"]["total_naming_the_sealed_store"],
        "chain_verifies": rec["hash_chain"]["verifies"],
        "history_identity_sha256": rec["history_identity_sha256"],
        "emitted": str(out),
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
