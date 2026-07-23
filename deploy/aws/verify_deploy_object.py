"""ADR-0043 validation-box deploy object verifier — checksum + size + provenance marker.

The evidence review approved an EXACT S3 object version and checksum. The deploy mechanism must
enforce those identities itself, not rely on an operator pre-check. This helper is the enforcement
point the hardened provisioner calls before it extracts anything:

  * ``verify_download`` — the downloaded byte count and SHA-256 equal the approved values, BEFORE
    the tarball is opened. A wrong VersionId or a truncated/tampered body is caught here.
  * ``verify_marker`` — the extracted ``DEPLOYED_BUILD_INFO.json`` names the approved deployed commit
    and ADR-0043 implementation baseline, and asserts ``adr0043_governed_paths_match == true``.

Both return a list of human-readable violations (empty == OK) so the tests can drive every failure
mode without a real S3 object, and so the provisioner fails CLOSED on any single mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_of(path: Path, _chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_download(path: Path, expected_sha256: str, expected_bytes: int) -> list[str]:
    """The downloaded object is exactly the approved artifact — checked BEFORE extraction."""
    v: list[str] = []
    if not path.exists():
        return [f"downloaded object not found at {path}"]
    actual_bytes = path.stat().st_size
    if actual_bytes != int(expected_bytes):
        v.append(f"byte size {actual_bytes} != approved {expected_bytes}")
    actual_sha = sha256_of(path)
    if actual_sha.lower() != str(expected_sha256).lower():
        v.append(f"sha256 {actual_sha} != approved {expected_sha256}")
    return v


def verify_marker(
    marker_path: Path,
    expected_deployed_commit: str,
    expected_impl_commit: str,
) -> list[str]:
    """The staged tree's provenance marker names the approved commits and asserts governed-path
    byte-match. Missing / malformed / mismatched marker is a refusal."""
    v: list[str] = []
    if not marker_path.exists():
        return [f"DEPLOYED_BUILD_INFO.json missing in staging ({marker_path})"]
    try:
        m = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"DEPLOYED_BUILD_INFO.json is not valid JSON: {exc}"]

    dep = str(m.get("deployed_repository_commit", ""))
    impl = str(m.get("adr0043_implementation_commit", ""))
    match = m.get("adr0043_governed_paths_match")
    if dep != expected_deployed_commit:
        v.append(f"deployed_repository_commit {dep or '<missing>'} != approved {expected_deployed_commit}")
    if impl != expected_impl_commit:
        v.append(f"adr0043_implementation_commit {impl or '<missing>'} != approved {expected_impl_commit}")
    if match is not True:
        v.append(f"adr0043_governed_paths_match is {match!r}, expected true")
    return v


def _fail(violations: list[str], what: str) -> int:
    if violations:
        print(f"REFUSE ({what}):", file=sys.stderr)
        for x in violations:
            print(f"  - {x}", file=sys.stderr)
        return 1
    print(f"OK: {what}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ADR-0043 deploy object verifier")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="verify a downloaded object's size + sha256")
    d.add_argument("--path", required=True)
    d.add_argument("--sha256", required=True)
    d.add_argument("--bytes", required=True, type=int)

    mk = sub.add_parser("marker", help="verify a staged DEPLOYED_BUILD_INFO.json")
    mk.add_argument("--marker", required=True)
    mk.add_argument("--deployed-commit", required=True)
    mk.add_argument("--impl-commit", required=True)

    args = ap.parse_args(argv)
    if args.cmd == "download":
        return _fail(
            verify_download(Path(args.path), args.sha256, args.bytes),
            "downloaded object identity",
        )
    return _fail(
        verify_marker(Path(args.marker), args.deployed_commit, args.impl_commit),
        "staged provenance marker",
    )


if __name__ == "__main__":
    raise SystemExit(main())
