#!/usr/bin/env python3
"""Publish MR-002 Gate N3 bulk execution evidence to governed S3 and emit package manifests.

Owner custody instruction for N3, reusing the pattern N1 and N2 proved
(MR002_N1_AdjudicationAddendum_v1.0 §5): large raw execution output goes to
versioned S3 recorded by bucket / key / VersionId / SHA-256 / bytes with read-back confirmation;
governing summaries stay in Git. `.mr002out/` remains "scratch — never evidence" and is not a
governance store, which is exactly why these files must be lifted out of it.

FAIL-CLOSED. Every object is read back BY ITS PINNED VersionId and its SHA-256 re-verified against
the local digest before the manifest is written. A mismatch aborts without emitting a manifest — an
unverified pin is worse than no pin, because it looks authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get("WORKBENCH_ARTIFACTS_BUCKET", "workbench-backups-219024422756")
REGION = os.environ.get("AWS_REGION", "us-east-1")
SOURCE_COMMIT = os.environ.get("MR002_N3_SOURCE_COMMIT", "")

PACKAGES = {
    "mr002-n3-execution-evidence": {
        "dir": REPO / ".mr002out" / "n3",
        "notes": ("MR-002 Gate N3 evidence (FULL DEVELOPMENT BEHAVIOURAL / ECONOMIC EQUIVALENCE), "
                  "produced in mr002-research:v1.4 under the registered FROZEN_THREAD_ENV with "
                  "--network=none. Rule sealed BEFORE execution as "
                  "MR002_N3_ProspectiveRegistration_v1.0, identity "
                  "b6b8aaca6fee92292f16d12243fdeace4a909234d12d4215c1c966b2cbb46328. Contains the "
                  "session-level and trade-level v1-vs-v2 differential for configs A, B and C over "
                  "the governed development window 2013-01-02..2019-10-02 (1,700 sessions per "
                  "config, 3,895 Stage-3 invocations, 7,588 closed trades), plus the governing "
                  "report. Frozen pair QUADPROG_SQRT + PIQP_P2; no solver selection occurred. "
                  "Result: N3_PASS on all three configs by TIER-1 BYTE IDENTITY, so the registered "
                  "numerical reconciliation bound was never invoked."),
    },
}


def sha256_file(p: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="actually upload (default: dry run)")
    args = ap.parse_args()

    if args.execute and not SOURCE_COMMIT:
        raise SystemExit("ABORT: MR002_N3_SOURCE_COMMIT is unset. A package that does not bind "
                         "its execution commit is not custody, it is just an upload.")

    import boto3

    s3 = boto3.client("s3", region_name=REGION)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written: list[str] = []

    for artifact_id, spec in PACKAGES.items():
        d: Path = spec["dir"]
        if not d.is_dir():
            print(f"SKIP {artifact_id}: {d} absent")
            continue
        # Telemetry (wall-clock) is deliberately NOT evidence: it is the only nondeterministic
        # output, and admitting it would make the governed package irreproducible for no gain.
        files = sorted(p for p in d.iterdir() if p.is_file()
                       and p.name != "README.txt" and "TELEMETRY" not in p.name)
        members = []
        print(f"\n=== {artifact_id} ({len(files)} files) ===")

        for p in files:
            digest, nbytes = sha256_file(p)
            key = f"artifacts/governed/{artifact_id}/1.0/{p.name}"
            if not args.execute:
                print(f"  DRY  {p.name:28s} {nbytes:>10,} B  sha={digest[:16]}")
                continue

            with p.open("rb") as fh:
                put = s3.put_object(Bucket=BUCKET, Key=key, Body=fh,
                                    ChecksumAlgorithm="SHA256",
                                    ServerSideEncryption="AES256")
            vid = put.get("VersionId")
            if not vid:
                raise SystemExit(f"ABORT: no VersionId returned for {key} — bucket not versioned")

            # fail-closed read-back BY THE PINNED VERSION
            got = s3.get_object(Bucket=BUCKET, Key=key, VersionId=vid)
            back = hashlib.sha256()
            nb = 0
            for chunk in got["Body"].iter_chunks(1 << 20):
                back.update(chunk)
                nb += len(chunk)
            if back.hexdigest() != digest or nb != nbytes:
                raise SystemExit(
                    f"ABORT: read-back MISMATCH for {key}@{vid}: "
                    f"{back.hexdigest()} != {digest} ({nb} vs {nbytes} bytes)")

            members.append({
                "name": p.name, "object_key": key, "s3_version_id": vid,
                "sha256": digest, "byte_length": nbytes,
                "readback_verified_by_version_id": True,
            })
            print(f"  OK   {p.name:28s} {nbytes:>10,} B  vid={vid}  readback VERIFIED")

        if not args.execute:
            continue

        pkg_digest = hashlib.sha256(
            json.dumps(members, sort_keys=True).encode("ascii")).hexdigest()
        manifest = {
            "schema_version": "1.0",
            "artifact_id": artifact_id,
            "schema_or_format_version": "1.0",
            "bucket": BUCKET,
            "object_key": f"artifacts/governed/{artifact_id}/1.0/",
            "s3_version_id": "PACKAGE",
            "sha256": pkg_digest,
            "byte_length": sum(m["byte_length"] for m in members),
            "created_at": now,
            "producing_job_or_run": f"mr002-n3-equivalence@{SOURCE_COMMIT[:12]}",
            "owner": "Engineering / Architecture",
            "retention_class": "governed",
            "sensitivity": "internal",
            "content_type": "application/json",
            "notes": spec["notes"],
            "package_members": members,
            "source_commit": SOURCE_COMMIT,
            "runtime_image": "mr002-research:v1.4",
            "frozen_thread_env": {
                "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
            },
            "package_sha256_basis": "sha256 of the canonical JSON of package_members",
        }
        out = REPO / "manifests" / "s3" / "objects" / f"{artifact_id}.v1.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                       newline="\n")
        written.append(str(out.relative_to(REPO)).replace("\\", "/"))
        print(f"  -> manifest {out.relative_to(REPO)}  package_sha256={pkg_digest[:16]}")

    if args.execute and written:
        idx_path = REPO / "manifests" / "s3" / "index.json"
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        have = {m["artifact_id"] for m in idx["manifests"]}
        for artifact_id in PACKAGES:
            mp = f"manifests/s3/objects/{artifact_id}.v1.json"
            if artifact_id not in have and (REPO / mp).exists():
                idx["manifests"].append({"artifact_id": artifact_id,
                                         "manifest_path": mp, "status": "active"})
        idx["manifests"].sort(key=lambda m: m["artifact_id"])
        idx_path.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("\nregistered in manifests/s3/index.json")
        print("manifests written:", *written, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
