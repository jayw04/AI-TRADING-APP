"""Generate the governed measurement-freeze manifest and its ratified-increment inventory.

⚠ Reads the measured content from GIT BLOBS, not from the working tree. Git stores LF; a Windows
checkout with ``core.autocrlf=true`` materializes CRLF, so hashing the working tree would produce a
digest that no Linux deployment can ever match. Hashing the blobs produces exactly the bytes the
deployment archive carries — the same reason `git archive` must be run with ``core.autocrlf=false``.

The manifest lives OUTSIDE the tree it pins, so regenerating it does not change the digest it records.
That is the whole point of the amendment: an in-tree constant could never name the commit containing
it.

    python scripts/forward_validation/generate_measurement_freeze.py \
        --ref HEAD --supersedes 764883b5… --amendment docs/governance/<amendment>.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # apps/backend, for `app.validation`

# ⚠⚠ The canonicalization is IMPORTED, never transcribed. A generator with its own copy of the rules
# is a second implementation that can drift from the one the runtime enforces — and a manifest
# produced by a drifted generator would pin a digest no deployment can ever reproduce. This is the
# "not a separate one-off command" requirement, made structural.
from app.validation.measurement_freeze import (  # noqa: E402
    MEASURED_PATHS,
    TREE_IDENTITY_ALGORITHM,
    byte_manifest,
    tree_identity,
)

SCHEMA_VERSION = "1.0"
BACKEND_PREFIX = "apps/backend"


def _git(*args: str, repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def entries_from_git(ref: str, repo: Path) -> list[tuple[str, bytes]]:
    """The measured content at `ref` as `(runtime-relative path, raw blob bytes)`.

    Read from GIT BLOBS, not the working tree: git stores LF, and a Windows checkout with
    ``core.autocrlf=true`` materializes CRLF. The blobs are the COMMITTED bytes — the authoritative
    source from which both the content identity and the transport manifest are derived.
    """
    out: list[tuple[str, bytes]] = []
    for rel in MEASURED_PATHS:
        listing = _git("ls-tree", "-r", "--name-only", ref, f"{BACKEND_PREFIX}/{rel}",
                       repo=repo).splitlines()
        for path in sorted(p for p in listing if p.endswith(".py")):
            blob = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{ref}:{path}"],
                                  capture_output=True).stdout
            out.append((path[len(BACKEND_PREFIX) + 1:], blob))
    if not out:
        raise SystemExit(f"no measured content found at {ref}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default="HEAD", help="the ref whose measured content is ratified")
    ap.add_argument("--measurement-commit", required=True,
                    help="the last ratified measurement-code commit (ancestry anchor)")
    ap.add_argument("--supersedes", required=True)
    ap.add_argument("--amendment", required=True, help="path to the governance amendment")
    ap.add_argument("--out", default="manifests/forward/measurement_freeze.json")
    ap.add_argument("--inventory", default="manifests/forward/ratified_increments.json")
    ap.add_argument("--byte-manifest", default="manifests/forward/measurement_bytes.json")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    entries = entries_from_git(args.ref, repo)
    digest = tree_identity(entries)              # the IMPORTED implementation, under test
    bytes_map = byte_manifest(entries)           # the authoritative transport reference
    n = len(entries)

    # The ratified increments, generated rather than narrated — 28 commits is too many to hand-list
    # accurately, and a hand-list is exactly the sort of thing that quietly goes stale.
    log = _git("log", "--format=%H%x1f%ad%x1f%s", "--date=short",
               f"{args.supersedes}..{args.ref}", "--", f"{BACKEND_PREFIX}/app/validation", repo=repo)
    commits = [dict(zip(("commit", "date", "subject"), line.split("\x1f"), strict=True))
               for line in log.splitlines() if line.strip()]
    inventory = {"kind": "ratified_measurement_increments", "version": "1.0",
                 "from_commit": args.supersedes, "to_ref_commit": _git(
                     "rev-parse", args.ref, repo=repo).strip(),
                 "measured_paths": list(MEASURED_PATHS), "commit_count": len(commits),
                 "commits": commits}
    inv_bytes = json.dumps(inventory, indent=2, sort_keys=True).encode() + b"\n"
    inv_path = repo / args.inventory
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_bytes(inv_bytes)

    amendment = repo / args.amendment
    if not amendment.exists():
        raise SystemExit(f"amendment not found: {amendment}")

    manifest = {
        "manifest_schema_version": SCHEMA_VERSION,
        "measurement_commit": args.measurement_commit,
        "validation_tree_sha256": digest,
        "supersedes_measurement_commit": args.supersedes,
        "ratified_increment_inventory_sha256": hashlib.sha256(inv_bytes).hexdigest(),
        "amendment_sha256": hashlib.sha256(amendment.read_bytes()).hexdigest(),
        "measured_paths": list(MEASURED_PATHS),
        "validation_tree_identity_algorithm": TREE_IDENTITY_ALGORITHM,
    }
    bytes_bytes = json.dumps({"kind": "measurement_byte_manifest", "version": "1.0",
                              "measured_paths": list(MEASURED_PATHS), "files": bytes_map},
                             indent=2, sort_keys=True).encode() + b"\n"
    bytes_path = repo / args.byte_manifest
    bytes_path.write_bytes(bytes_bytes)
    manifest["byte_manifest_sha256"] = hashlib.sha256(bytes_bytes).hexdigest()

    out = repo / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")

    print(f"measured files            {n}")
    print(f"validation_tree_sha256    {digest}")
    print(f"ratified increments       {len(commits)}")
    print(f"inventory sha256          {manifest['ratified_increment_inventory_sha256']}")
    print(f"amendment sha256          {manifest['amendment_sha256']}")
    print(f"wrote {out}")
    print(f"byte manifest sha256      {manifest['byte_manifest_sha256']}")
    print(f"identity algorithm        {TREE_IDENTITY_ALGORITHM}")
    print(f"wrote {inv_path}")
    print(f"wrote {bytes_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
