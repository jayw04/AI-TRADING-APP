"""Reproduce the v3.2 execution closure identity and code archive from Git blob bytes.

Requirement 2 of the v3.3 rebind qualification is that the bound code archive REPRODUCES from Git.
This is that reproduction, runnable by anyone with the repository:

    python docs/review/mr002/phase3bc/_gen_v32_rebind_archive.py [--out code_v33.tar.gz]

It reads nothing from the working tree. Every archive member is `git show <checkpoint>:<path>`, so a
dirty checkout cannot change the result. It prints the closure identity and archive sha256 and exits
non-zero if either fails to match what the supplement binds.

Expected, for checkpoint b7c7369aaeb6812201e047a0ecb1b3e7c6fcc6b8:
    code_identity  d25296205b5fc3a79f9f3037486a124f6e5392591192f6ce7bd2d3491304c49e
    archive        ba6b58706b83cba3d6725a2a088b4052d0e56a4de7488eed4551cfd9e5f8057e
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

CHECKPOINT = "b7c7369aaeb6812201e047a0ecb1b3e7c6fcc6b8"
EXPECT_CODE_IDENTITY = "d25296205b5fc3a79f9f3037486a124f6e5392591192f6ce7bd2d3491304c49e"
EXPECT_ARCHIVE = "ba6b58706b83cba3d6725a2a088b4052d0e56a4de7488eed4551cfd9e5f8057e"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
# The accepted v3.1 closure defines the member set; v3.3 rebinds the same set at a new checkpoint.
V31_OBSERVATION = os.path.join(HERE, "MR002_Phase3B_LiveMaterializationObservation_v1.1.json")
PREFIX = "apps/backend"


def canonical(obj: dict) -> bytes:
    """The v3.1 closure-identity encoding. Verified to reproduce f35e8209... before reuse."""
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob(rel: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{CHECKPOINT}:{PREFIX}/{rel}"],
        cwd=REPO, capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"missing blob at {CHECKPOINT}: {rel}\n{proc.stderr.decode(errors='replace')}")
    return proc.stdout


def build_archive(members: list[str]) -> bytes:
    """Deterministic: sorted members, mtime=0, mode 0644, uid/gid 0, gzip mtime 0."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for rel in members:
            data = blob(rel)
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            tf.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(raw.getvalue())
    return out.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the archive here (optional; the hash is printed regardless)")
    args = ap.parse_args()

    with open(V31_OBSERVATION, encoding="utf-8") as fh:
        v31 = json.load(fh)["closure_files"]
    members = sorted(v31)

    closure = {rel: hashlib.sha256(blob(rel)).hexdigest() for rel in members}
    code_identity = hashlib.sha256(canonical(dict(sorted(closure.items())))).hexdigest()

    archive = build_archive(members)
    archive_sha = hashlib.sha256(archive).hexdigest()
    again = hashlib.sha256(build_archive(members)).hexdigest()

    changed = sorted(r for r in members if v31[r] != closure[r])

    print(f"checkpoint      : {CHECKPOINT}")
    print(f"members         : {len(members)}")
    print(f"changed vs v3.1 : {len(changed)} {changed}")
    print(f"code_identity   : {code_identity}")
    print(f"archive sha256  : {archive_sha} ({len(archive)} bytes)")
    print(f"deterministic   : {again == archive_sha}")

    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(archive)
        print(f"wrote           : {args.out}")

    ok = True
    if code_identity != EXPECT_CODE_IDENTITY:
        print(f"MISMATCH code_identity: expected {EXPECT_CODE_IDENTITY}", file=sys.stderr)
        ok = False
    if archive_sha != EXPECT_ARCHIVE:
        print(f"MISMATCH archive: expected {EXPECT_ARCHIVE}", file=sys.stderr)
        ok = False
    if again != archive_sha:
        print("MISMATCH archive is not deterministic", file=sys.stderr)
        ok = False
    print("REPRODUCES      :", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
