"""Compute the build-time `code_digest` that `CONTAINER_ATTESTED` will check the runtime against.

⚠ Reads the deployed code from GIT BLOBS, never from the working tree. `build-deploy-archive.sh` ships
`git archive <sha>`, which carries the blob bytes; a Windows checkout with `core.autocrlf=true`
materializes CRLF, so hashing the working tree would stamp a digest no Linux runtime can reproduce.
This is the same reason the measurement-freeze generator reads blobs.

⚠⚠ The canonicalization is IMPORTED from `app.validation.deployment_identity`, never transcribed. A
producer with its own copy of the framing is a second implementation that can drift from the one the
runtime enforces, and a stamp produced by a drifted producer pins a value nothing can ever match.

## Scope parity is the whole point

The runtime derives over `/app/app/**` — the Dockerfile does `WORKDIR /app` then `COPY app ./app`, so
the container's `/app/app` IS `apps/backend/app`. This script therefore digests exactly
`apps/backend/app/**` at the deployed commit, with paths made relative to that prefix so both sides
produce identical relative keys (`validation/deployment_identity.py`, not `app/validation/...`).

Change the scope on one side and the deployment stops verifying — which fails closed, but wastes a
deploy. The two roots and the suffix/exclusion rules must be changed together or not at all.

    python scripts/compute_deploy_code_digest.py --ref <deployed-sha>
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/backend, for `app.validation`

from app.validation.deployment_identity import (  # noqa: E402
    CODE_DIGEST_EXCLUDED_DIRS,
    CODE_DIGEST_SUFFIXES,
    code_identity,
)

#: The path inside the repository whose contents become `/app/app` in the runtime image.
DEPLOYED_APP_PREFIX = "apps/backend/app"


class ProducerError(RuntimeError):
    """The build-time digest could not be computed. Fails closed rather than stamping a guess."""


def _git(*args: str, repo: Path) -> str:
    result = subprocess.run(("git", *args), cwd=repo, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProducerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def code_entries_from_git(ref: str, repo: Path, *, prefix: str = DEPLOYED_APP_PREFIX
                          ) -> list[tuple[str, str]]:
    """Collect `(relative_posix_path, sha256_of_blob)` under `prefix` at `ref`.

    ⚠ The sha256 is of the blob CONTENT, computed here — not git's own object id, which is a SHA-1 over
    a different framing entirely and would not match what the runtime computes over the same bytes.
    """
    listing = _git("ls-tree", "-r", "-z", "--format=%(objectname) %(path)", ref, "--", prefix,
                   repo=repo)
    entries: list[tuple[str, str]] = []
    for record in listing.split("\0"):
        record = record.strip()
        if not record:
            continue
        object_name, _, path = record.partition(" ")
        relative = Path(path).as_posix()
        if not relative.startswith(f"{prefix}/"):
            continue
        relative = relative[len(prefix) + 1:]
        parts = Path(relative).parts
        if any(part in CODE_DIGEST_EXCLUDED_DIRS for part in parts):
            continue
        if CODE_DIGEST_SUFFIXES and Path(relative).suffix not in CODE_DIGEST_SUFFIXES:
            continue
        blob = subprocess.run(("git", "cat-file", "blob", object_name), cwd=repo, capture_output=True)
        if blob.returncode != 0:
            raise ProducerError(f"git cat-file blob {object_name} failed for {relative}")
        entries.append((relative, hashlib.sha256(blob.stdout).hexdigest()))
    if not entries:
        raise ProducerError(
            f"no files matching {CODE_DIGEST_SUFFIXES} under {prefix} at {ref}; refusing to stamp a "
            f"digest derived from an empty tree")
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--ref", required=True, help="the commit whose archive is being deployed")
    parser.add_argument("--prefix", default=DEPLOYED_APP_PREFIX)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    try:
        entries = code_entries_from_git(args.ref, repo, prefix=args.prefix)
        print(code_identity(entries))
    except (ProducerError, Exception) as exc:  # noqa: BLE001 - fail closed, never stamp a guess
        print(f"code_digest computation FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
