"""ADR 0042 canary — build the provenance manifest from the REVIEWED COMMIT.

Run this on the HOST, against a clean checkout of the merged commit. It records the SHA-256 of
every harness file as git has it. The preflight then recomputes those hashes INSIDE the running
container and refuses to proceed unless they match.

That two-sided check is the point. A host-side hash alone proves only what is in the repository; it
says nothing about which bytes the deployed interpreter actually read. Hashing on both sides, and
requiring agreement, is what turns "we ran the reviewed code" from an assertion into evidence.

    python scripts/adr0042_make_manifest.py <commit_sha> <image_digest> > manifest.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HARNESS = [
    "scripts/adr0042_canary_lib.py",
    "scripts/adr0042_churn_to_breach.py",
    "scripts/adr0042_canary_run.py",
    "scripts/adr0042_concurrency_worker.py",
    "scripts/adr0042_preflight.py",
    "app/risk/decision_service.py",
    "app/risk/risk_effect.py",
    "app/risk/account_snapshot.py",
    "app/db/models/risk_capacity_state.py",
]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    commit, digest = sys.argv[1], sys.argv[2]

    root = Path(__file__).resolve().parents[1]          # apps/backend
    hashes: dict[str, str] = {}
    for rel in HARNESS:
        p = root / rel
        if not p.exists():
            print(f"missing: {rel}", file=sys.stderr)
            return 1
        # Hash the bytes as they will land in the image: normalise line endings, because a CRLF
        # checkout on the host would otherwise never match an LF file in the container, and the
        # provenance check would fail for a reason that has nothing to do with provenance.
        data = p.read_bytes().replace(b"\r\n", b"\n")
        hashes[rel] = hashlib.sha256(data).hexdigest()

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *[f"apps/backend/{r}" for r in HARNESS]],
        capture_output=True, text=True, cwd=root.parents[1], check=False,
    ).stdout.strip()

    print(json.dumps(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "commit_sha": commit,
            "image_digest": digest,
            "working_tree_clean": not dirty,
            "dirty_files": dirty.splitlines(),
            "source_sha256": hashes,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
