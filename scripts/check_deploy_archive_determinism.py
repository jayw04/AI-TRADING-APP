#!/usr/bin/env python3
"""CI invariant: the deploy archive must reproduce the Git blob bytes, deterministically.

The paper box has no ``.git``. Code arrives as a ``git archive`` tarball extracted into
``/opt/workbench/app``, so the bytes that actually run are whatever ``git archive``
emitted on whichever machine built it. ``git archive`` applies end-of-line conversion,
which means the answer depends on the *builder's* ``core.autocrlf`` setting unless the
repository pins it per path.

On 2026-08-21 that dependency bit: a redeploy built on a ``core.autocrlf=true``
workstation shipped ``app/research/disc_mdq/ledger.py`` with 670 CR bytes. Nothing broke
-- Python reads CRLF fine, and the governed-artifact loader LF-normalizes before comparing
pins -- but the claim "the deployed bytes are the reviewed bytes" quietly stopped being
true. Measured at the time: **2,078 of 2,239 archived files (93%) differed from their Git
blob**.

This check turns the fix from documentation into enforcement. It asserts two properties:

  DETERMINISM (all files, no exceptions)
      The archive is byte-identical whether it is built with ``core.autocrlf=true`` or
      ``core.autocrlf=false``. A builder's local configuration cannot change what ships.

  IDENTITY (all files except an explicit, documented allowlist)
      Every archived file equals its Git blob exactly. Not "equal after normalization" --
      equal.

The allowlist exists so that an intentional exception is visible in code review rather
than hidden in a silently-skipped path. It currently holds Windows-only launchers, which
are pinned CRLF on purpose and never execute on the Linux box.

Failure means someone added a file type with no EOL pin. The fix is a one-line entry in
``.gitattributes`` -- and note the ordering rule documented there: generic rules must stay
*above* the ``-text`` protections, because the last matching rule wins.

Usage:
    python scripts/check_deploy_archive_determinism.py [<ref>]     # default: HEAD
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from collections import Counter

#: Paths permitted to differ from their Git blob in the archive. Each entry must carry a
#: reason. Determinism is still enforced for these -- only byte-identity is waived.
IDENTITY_ALLOWLIST_SUFFIXES: dict[str, str] = {
    ".bat": (
        "Windows-only launcher, pinned `text eol=crlf`; never executed on the Linux box, "
        "and cmd.exe is historically fragile with LF-only batch files."
    ),
}

MAX_REPORTED = 25


def _git(args: list[str], *, binary: bool = False):
    out = subprocess.run(["git", *args], capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def _archive(ref: str, autocrlf: str) -> dict[str, bytes]:
    """Build the deploy archive with an explicit core.autocrlf and return {path: bytes}."""
    raw = subprocess.run(
        ["git", "-c", f"core.autocrlf={autocrlf}", "archive", ref],
        capture_output=True,
        check=True,
    ).stdout
    tf = tarfile.open(fileobj=io.BytesIO(raw))
    files: dict[str, bytes] = {}
    for member in tf.getmembers():
        if member.isfile():
            fh = tf.extractfile(member)
            if fh is not None:
                files[member.name] = fh.read()
    return files


def _blobs(ref: str) -> dict[str, str]:
    out = _git(["ls-tree", "-r", ref])
    mapping: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "blob":
            mapping[path] = sha
    return mapping


def _read_blobs(shas: list[str]) -> list[bytes]:
    """Read many blobs in one `git cat-file --batch` process."""
    if not shas:
        return []
    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    payload, _ = proc.communicate(("\n".join(shas) + "\n").encode())
    contents: list[bytes] = []
    pos = 0
    for _ in shas:
        nl = payload.index(b"\n", pos)
        header = payload[pos:nl].decode().split()
        size = int(header[2])
        start = nl + 1
        contents.append(payload[start : start + size])
        pos = start + size + 1  # trailing newline after the payload
    return contents


def _allowlist_reason(path: str) -> str | None:
    for suffix, reason in IDENTITY_ALLOWLIST_SUFFIXES.items():
        if path.endswith(suffix):
            return reason
    return None


def _ext(path: str) -> str:
    tail = path.rsplit("/", 1)[-1]
    return "." + tail.rsplit(".", 1)[-1] if "." in tail else "(no extension)"


def main(argv: list[str]) -> int:
    ref = argv[1] if len(argv) > 1 else "HEAD"

    print(f"Deploy-archive determinism check @ {ref}")

    archive_true = _archive(ref, "true")
    archive_false = _archive(ref, "false")

    # --- property 1: determinism -------------------------------------------
    nondeterministic = sorted(
        p
        for p in set(archive_true) | set(archive_false)
        if archive_true.get(p) != archive_false.get(p)
    )

    # --- property 2: identity against the Git blobs ------------------------
    blobs = _blobs(ref)
    paths = sorted(p for p in archive_true if p in blobs)
    contents = _read_blobs([blobs[p] for p in paths])

    mismatched: list[str] = []
    waived: list[str] = []
    for path, blob in zip(paths, contents, strict=True):
        if archive_true[path] == blob:
            continue
        if _allowlist_reason(path):
            waived.append(path)
        else:
            mismatched.append(path)

    print(f"  archived files compared : {len(paths)}")
    print(f"  identical to Git blob   : {len(paths) - len(mismatched) - len(waived)}")
    print(f"  waived by allowlist     : {len(waived)}")
    print(f"  NOT deterministic       : {len(nondeterministic)}")
    print(f"  NOT identical to blob   : {len(mismatched)}")

    unarchived = sorted(set(blobs) - set(archive_true))
    if unarchived:
        print(f"  (not in archive, e.g. export-ignore: {len(unarchived)})")

    ok = True

    if nondeterministic:
        ok = False
        print()
        print("FAIL: the archive depends on the builder's core.autocrlf setting.")
        print(
            "      These files differ between an autocrlf=true and an autocrlf=false build:"
        )
        for path in nondeterministic[:MAX_REPORTED]:
            print(f"        {path}")
        if len(nondeterministic) > MAX_REPORTED:
            print(f"        ... and {len(nondeterministic) - MAX_REPORTED} more")

    if mismatched:
        ok = False
        by_ext = Counter(_ext(p) for p in mismatched)
        print()
        print(
            "FAIL: archived bytes differ from the Git blob for files with no EOL pin."
        )
        print("      The deployed source would not be the reviewed source.")
        print(
            "      By extension: "
            + ", ".join(f"{e}={n}" for e, n in by_ext.most_common())
        )
        for path in mismatched[:MAX_REPORTED]:
            print(f"        {path}")
        if len(mismatched) > MAX_REPORTED:
            print(f"        ... and {len(mismatched) - MAX_REPORTED} more")
        print()
        print(
            "      FIX: add the extension to .gitattributes as `text eol=lf`, ABOVE the"
        )
        print(
            "           `-text` protections -- the last matching rule wins, so a generic"
        )
        print(
            "           rule appended at the end would override a digest-pinned `-text`"
        )
        print("           entry and rewrite bytes that are pinned by hash.")

    if waived:
        print()
        print("Allowlisted (deterministic, intentionally not blob-identical):")
        for path in waived[:MAX_REPORTED]:
            print(f"        {path}  --  {_allowlist_reason(path)}")

    print()
    if ok:
        print(
            "PASS: deploy archive is deterministic and byte-identical to the Git blobs."
        )
        return 0
    print("FAILED: deploy-archive determinism invariant.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
