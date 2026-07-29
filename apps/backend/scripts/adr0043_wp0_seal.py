#!/usr/bin/env python3
"""ADR-0043 WP0 — build or verify an evidence seal (read-only; never submits orders).

Usage (on the paper box or against a copied tree)::

    python scripts/adr0043_wp0_seal.py build \\
        --out-dir /opt/workbench/data/ops/adr0043_wp0_seals/20260729T160000Z \\
        --root /opt/workbench/app/DEPLOYED_BUILD_INFO.json \\
        --root /opt/workbench/data/ops \\
        --host-id ec2-paper \\
        --operator jay@globalcomplyai.com

    python scripts/adr0043_wp0_seal.py verify --seal-dir <that-out-dir>

Excludes credential/password material from content hashing by default (path noted
in ``exclusions``). Does not touch ``risk_loss_control_state``, canary locks, or
broker APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

CONTROLLING_DESIGN_ID = "ADR0043-PH0-CTRL-001 v1.1"
SCHEMA_VERSION = 1

# Basename patterns never content-hashed (secrets / live credentials).
_DEFAULT_EXCLUDE_BASENAME = re.compile(
    r"(?i)(password|credential|passwd|secret|\.pem$|\.key$|totp_)"
)

# Large / continuously mutating live state — exclude with reason unless --include-db.
_DEFAULT_EXCLUDE_SUFFIXES = (
    ".sqlite",
    ".sqlite-wal",
    ".sqlite-shm",
    ".duckdb",
    ".parquet",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            out.append(Path(dirpath) / name)
    return sorted(out)


def _should_exclude(path: Path, *, include_db: bool) -> str | None:
    if _DEFAULT_EXCLUDE_BASENAME.search(path.name):
        return "credential_or_secret_basename"
    if not include_db and path.suffix.lower() in {".sqlite", ".duckdb", ".parquet"}:
        return "mutable_or_bulk_data_excluded_by_default"
    if not include_db and any(str(path).endswith(sfx) for sfx in _DEFAULT_EXCLUDE_SUFFIXES):
        return "mutable_or_bulk_data_excluded_by_default"
    return None


def build_seal(
    *,
    roots: list[Path],
    out_dir: Path,
    host_id: str,
    operator: str,
    include_db: bool,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    exclusions: list[dict[str, str]] = []
    inventory: list[dict[str, str]] = []

    for root in roots:
        root = root.resolve()
        role = "file" if root.is_file() else "directory"
        inventory.append({"path": str(root), "role": role, "exists": str(root.exists())})
        if not root.exists():
            exclusions.append({"path": str(root), "reason": "missing_at_seal_time"})
            continue
        for path in _iter_files(root):
            rel_key = str(path.resolve())
            why = _should_exclude(path, include_db=include_db)
            if why:
                exclusions.append({"path": rel_key, "reason": why})
                continue
            try:
                manifest[rel_key] = _sha256_file(path)
            except OSError as exc:
                exclusions.append({"path": rel_key, "reason": f"unreadable:{exc}"})

    manifest_body = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(manifest_body, encoding="utf-8")
    manifest_sha = "sha256:" + hashlib.sha256(manifest_body.encode("utf-8")).hexdigest()

    deployed = Path("/opt/workbench/app/DEPLOYED_BUILD_INFO.json")
    deployed_sha = None
    if deployed.is_file():
        deployed_sha = _sha256_file(deployed)

    record = {
        "schema_version": SCHEMA_VERSION,
        "package": "WP0",
        "controlling_design_id": CONTROLLING_DESIGN_ID,
        "sealed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operator": operator,
        "host_id": host_id,
        "deployed_build_info_sha256": deployed_sha,
        "manifest_sha256": manifest_sha,
        "manifest_entries": len(manifest),
        "exclusions": exclusions,
        "inventory": inventory,
        "notes": (
            "WP0 evidence seal. Credential basenames and bulk DB/parquet excluded from "
            "content hashes by default. Read-only; no broker or loss-control mutation."
        ),
    }
    record_path = out_dir / "seal_record.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def verify_seal(seal_dir: Path) -> int:
    record_path = seal_dir / "seal_record.json"
    manifest_path = seal_dir / "manifest.json"
    if not record_path.is_file() or not manifest_path.is_file():
        print("FAIL: seal_record.json or manifest.json missing", file=sys.stderr)
        return 2
    record = json.loads(record_path.read_text(encoding="utf-8"))
    body = manifest_path.read_text(encoding="utf-8")
    actual = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
    expected = record.get("manifest_sha256")
    if actual != expected:
        print(f"FAIL: manifest_sha256 mismatch expected={expected} actual={actual}", file=sys.stderr)
        return 1
    manifest = json.loads(body)
    mismatches = 0
    for path_s, digest in manifest.items():
        path = Path(path_s)
        if not path.is_file():
            print(f"FAIL: missing {path_s}", file=sys.stderr)
            mismatches += 1
            continue
        got = _sha256_file(path)
        if got != digest:
            print(f"FAIL: digest mismatch {path_s}", file=sys.stderr)
            mismatches += 1
    if mismatches:
        print(f"FAIL: {mismatches} file(s) failed verification", file=sys.stderr)
        return 1
    print(
        f"PASS: seal {seal_dir} ok entries={len(manifest)} "
        f"design={record.get('controlling_design_id')}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build a new WP0 seal (read-only hashing)")
    b.add_argument("--out-dir", type=Path, required=True)
    b.add_argument("--root", type=Path, action="append", required=True, dest="roots")
    b.add_argument("--host-id", default=os.environ.get("WORKBENCH_HOST_ID", "unknown"))
    b.add_argument("--operator", default=os.environ.get("USER", "unknown"))
    b.add_argument(
        "--include-db",
        action="store_true",
        help="Include sqlite/duckdb/parquet in content hashes (usually avoid)",
    )

    v = sub.add_parser("verify", help="Re-verify an existing seal (fail closed)")
    v.add_argument("--seal-dir", type=Path, required=True)

    args = p.parse_args(argv)
    if args.cmd == "build":
        record = build_seal(
            roots=list(args.roots),
            out_dir=args.out_dir,
            host_id=args.host_id,
            operator=args.operator,
            include_db=bool(args.include_db),
        )
        print(json.dumps(record, indent=2))
        return 0
    return verify_seal(args.seal_dir)


if __name__ == "__main__":
    raise SystemExit(main())
