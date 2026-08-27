"""Derive a running container's code identity from a `docker cp` tar stream, on the HOST.

    docker cp <container>:/app/app - | python scripts/derive_runtime_code_digest_from_tar.py

⚠⚠ THE POINT IS THAT NO CONTAINER USERLAND RUNS. `docker exec <container> sha256sum ...` would ask the
suspect to describe itself: a wrong or hostile image can carry a wrong tree *and* a matching
self-description, and the answer would look perfect. The Docker daemon streams the container's
filesystem out; the digest is computed here, by code the container cannot influence.

`docker cp` rather than `docker export` because the measured scope is `/app/app`, not the whole
container filesystem — exporting gigabytes to hash a few hundred kilobytes invites both timeouts and
scope drift.

⚠ The canonicalization is IMPORTED from `app.validation.deployment_identity`, never transcribed, so the
host attestation and the in-container derivation cannot disagree about framing.

## Fail closed, loudly

A tar stream is attacker-shaped input. Every one of these is a refusal, not a skip:

  * the archive contains no measured files at all (wrong path, wrong container, empty scope);
  * a duplicate path — two entries for one name means the digest depends on which one you kept;
  * absolute paths or `..` traversal;
  * a special file (device, fifo, socket) or a hardlink inside the measured scope;
  * a symlink whose name is in scope — executable indirection is refused, matching the tree collector.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
from pathlib import PurePosixPath

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.validation.deployment_identity import (  # noqa: E402
    CODE_DIGEST_EXCLUDED_DIRS,
    CODE_DIGEST_SUFFIXES,
    code_identity,
)


class RuntimeAttestationError(RuntimeError):
    """The running code could not be attested. Fails closed rather than reporting a partial digest."""


def _strip_root(name: str) -> str | None:
    """`docker cp <c>:/app/app -` roots every entry at `app/`. Return the path relative to that root."""
    path = PurePosixPath(name)
    if path.is_absolute():
        raise RuntimeAttestationError(f"absolute path in the archive: {name!r}")
    parts = path.parts
    if ".." in parts:
        raise RuntimeAttestationError(f"path traversal in the archive: {name!r}")
    if len(parts) <= 1:
        return None                      # the root directory entry itself
    return PurePosixPath(*parts[1:]).as_posix()


def entries_from_tar(stream) -> list[tuple[str, str]]:
    """Collect `(relative_posix_path, sha256)` for the measured files in a docker-cp tar stream."""
    seen: dict[str, str] = {}
    with tarfile.open(fileobj=stream, mode="r|*") as archive:
        for member in archive:
            relative = _strip_root(member.name)
            if relative is None:
                continue
            parts = PurePosixPath(relative).parts
            if any(part in CODE_DIGEST_EXCLUDED_DIRS for part in parts):
                continue
            in_scope = (not CODE_DIGEST_SUFFIXES
                        or PurePosixPath(relative).suffix in CODE_DIGEST_SUFFIXES)
            if member.issym() or member.islnk():
                if in_scope:
                    raise RuntimeAttestationError(
                        f"the measured code scope contains a link at {relative}; executable "
                        f"indirection inside the measured set is refused rather than skipped")
                continue
            if member.isdir():
                continue
            if not member.isfile():
                if in_scope:
                    raise RuntimeAttestationError(
                        f"the measured code scope contains a special file at {relative}")
                continue
            if not in_scope:
                continue
            if relative in seen:
                raise RuntimeAttestationError(
                    f"duplicate archive entry for {relative}; the identity would depend on which copy "
                    f"was kept")
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeAttestationError(f"unreadable archive entry for {relative}")
            seen[relative] = hashlib.sha256(handle.read()).hexdigest()

    if not seen:
        raise RuntimeAttestationError(
            "the archive contained no measured files; refusing to attest an empty scope (wrong "
            "container, wrong path, or an empty deployment are indistinguishable here)")
    return sorted(seen.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", default=None,
                        help="read the tar from a file instead of stdin (tests)")
    args = parser.parse_args(argv)
    try:
        if args.from_file:
            with open(args.from_file, "rb") as handle:
                entries = entries_from_tar(handle)
        else:
            entries = entries_from_tar(sys.stdin.buffer)
        print(code_identity(entries))
    except Exception as exc:  # noqa: BLE001 - fail closed; never print a partial identity
        print(f"runtime code attestation FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
