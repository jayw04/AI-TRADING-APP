"""THE canonical tree-aggregate identity for MR-002 Validation-2 deployment.

This file SHIPS INSIDE THE DEPLOYMENT ARCHIVE. That is the whole point: the candidate aggregate
computed locally and the live aggregate computed on the host after cutover must come from the
IDENTICAL implementation, or their equality proves nothing. An aggregate described in prose and
re-implemented twice is two algorithms wearing one name.

ALGORITHM (fixed here, deliberately boring):

    select   every file under  <root>/apps/backend/app/research/mr002/**
             and every *.py under <root>/apps/backend/scripts/
    exclude  __pycache__/ and *.pyc  (generated; present on a live tree, absent in an archive,
             and their inclusion would make live != candidate for no real reason)
    line     "<sha256 of file bytes>  <path relative to root, forward slashes>\\n"
    sort     by that relative path, byte order
    aggregate = sha256(concatenation of all lines)

The PATH is inside the hashed line on purpose: a hash-only list is blind to a file moving, being
renamed, or being duplicated, and a deployment identity that cannot see a moved file is not a
deployment identity.

⚠ HISTORICAL NOTE, recorded so nobody later "reconciles" two incomparable numbers. The prior
rollback aggregate ff0308be99dd82087b03ef3b48006f4a7c4b87ca37bd951a8be42794c03f4bbc was computed
on the host under an implementation that is not preserved anywhere in this repository. It was NOT
reproducible locally: seven plausible formula variants over two candidate file sets, at the
recorded checkpoint 34eeee00, all failed to reproduce it. So that value is retained ONLY as a
historical marker of the pre-deployment tree. It is NOT comparable to values from this file, and
the rollback aggregate must be RE-DERIVED on the host with this script before cutover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

MR002 = os.path.join("apps", "backend", "app", "research", "mr002")
SCRIPTS = os.path.join("apps", "backend", "scripts")


def selected_files(root: str) -> list[str]:
    out: list[str] = []
    base = os.path.join(root, MR002)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            if fn.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    sdir = os.path.join(root, SCRIPTS)
    if os.path.isdir(sdir):
        for fn in sorted(os.listdir(sdir)):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(sdir, fn), root))
    return sorted(p.replace(os.sep, "/") for p in out)


def aggregate(root: str) -> dict:
    files = selected_files(root)
    lines, per_file = [], {}
    for rel in files:
        with open(os.path.join(root, rel.replace("/", os.sep)), "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        per_file[rel] = h
        lines.append(f"{h}  {rel}\n")
    agg = hashlib.sha256("".join(lines).encode("ascii")).hexdigest()
    return {"aggregate_sha256": agg, "file_count": len(files), "per_file_sha256": per_file}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="tree root that CONTAINS apps/backend/")
    ap.add_argument("--emit", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    res = aggregate(args.root)
    if args.emit:
        with open(args.emit, "wb") as fh:
            fh.write((json.dumps(res, sort_keys=True, indent=1) + "\n").encode("ascii"))
    if not args.quiet:
        print(f"root       {args.root}")
        print(f"files      {res['file_count']}")
    print(res["aggregate_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
