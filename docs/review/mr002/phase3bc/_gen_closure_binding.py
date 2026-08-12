"""Bind the Phase 3B executing closure to GIT BLOB bytes, never working-tree bytes.

The working tree is not a stable execution identity. This repository has ``core.autocrlf=true``, so
a file checked out on Windows carries CRLF while its blob carries LF. It showed up concretely:
``app/research/__init__.py`` measured 410 bytes on disk against 403 in the blob, because it is the
only closure file that has ever been checked out here. The other forty were authored in this session
and are still LF on disk, so they happened to agree. After a fresh clone on Windows, ALL of them
would diverge.

The container receives blob bytes, so blob bytes are what actually execute. A binding taken from a
Windows working tree would therefore be a binding on something that never runs - the same
"identified is not what runs" failure as v1, one layer down.

So the closure LIST is taken from the code (path membership is EOL-independent) and every DIGEST is
taken from ``git show <commit>:<path>``. The generator refuses if the two disagree about membership,
and reports - without failing - which files differ between blob and worktree, because that
divergence is a property of the checkout rather than of the binding.

Zero-data instrument: reads git objects. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_BACKEND = os.path.join(_REPO, "apps", "backend")

PREFIX = "apps/backend"


class ClosureBindingRefused(Exception):
    """The closure cannot be bound to blob bytes. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", "-C", _REPO, *args], capture_output=True)
    if proc.returncode != 0:
        raise ClosureBindingRefused(f"git {' '.join(args)}: {proc.stderr.decode()[:200]}")
    return proc.stdout


def _blob(commit: str, rel: str) -> bytes:
    return _git("show", f"{commit}:{PREFIX}/{rel}")


def closure_paths() -> list[str]:
    """Path membership only - EOL cannot change which files are in the closure."""
    sys.path.insert(0, _BACKEND)
    from app.research.mr002.phase3b import roster as R

    return sorted(R.enumerate_closure())


def build(commit: str) -> dict:
    remote = _git("rev-parse", "origin/research/mr002-preregistration").decode().strip()
    if remote != commit:
        raise ClosureBindingRefused(
            f"remote head {remote[:12]} is not {commit[:12]}; a binding must name pushed bytes"
        )

    paths = closure_paths()
    if not paths:
        raise ClosureBindingRefused("closure is empty")

    bound, divergent = {}, []
    for rel in paths:
        blob = _blob(commit, rel)
        bound[rel] = hashlib.sha256(blob).hexdigest()
        disk = os.path.join(_BACKEND, rel)
        if os.path.isfile(disk):
            with open(disk, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != bound[rel]:
                    divergent.append(rel)

    tracked = {
        p[len(PREFIX) + 1 :]
        for p in _git("ls-tree", "-r", "--name-only", commit, "--", f"{PREFIX}/app").decode().split()
    }
    untracked = sorted(set(paths) - tracked)
    if untracked:
        raise ClosureBindingRefused(
            f"closure names files not tracked at {commit[:7]}: {untracked}. An untracked file "
            "cannot be delivered to the container by identity."
        )

    return {
        "record_type": "MR002_Phase3B_ExecutingClosureBinding",
        "version": "1.0",
        "artifact_kind": "EXECUTION_IDENTITY",
        "commit": commit,
        "path_prefix": PREFIX,
        "digest_source": "git blob bytes via `git show <commit>:<path>`",
        "why_blob_not_worktree": (
            "core.autocrlf=true means a checked-out file carries CRLF while its blob carries LF. "
            "app/research/__init__.py measured 410 bytes on disk against 403 in the blob - it is "
            "the only closure file ever checked out here. After a fresh clone on Windows all of "
            "them would diverge. The container receives blob bytes, so blob bytes are what execute; "
            "binding the worktree would bind something that never runs."
        ),
        "membership_source": (
            "roster.enumerate_closure() - path membership only, which no EOL convention can change"
        ),
        "file_count": len(bound),
        "files": bound,
        "checkout_divergence": {
            "count": len(divergent),
            "files": divergent,
            "meaning": (
                "these differ between blob and this working tree. That is a property of the "
                "checkout, not of the binding, and is reported rather than treated as an error."
            ),
        },
        "boundary": "Zero-data. No AWS call, no sealed object, no credential. Opening UNSPENT.",
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _gen_closure_binding.py <commit-sha>")
    record = build(sys.argv[1])
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_ExecutingClosureBinding_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"record identity  {record['record_identity_sha256']}")
    print(f"commit           {record['commit'][:12]} (remote head verified)")
    print(f"bound files      {record['file_count']} (blob bytes)")
    print(f"checkout diverge {record['checkout_divergence']['count']} "
          f"{record['checkout_divergence']['files']}")


if __name__ == "__main__":
    main()
