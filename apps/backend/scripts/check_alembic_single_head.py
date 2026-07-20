"""Fail CI if the Alembic migration graph does not have exactly one head.

A second head means two migrations share a ``down_revision`` (a merge conflict that slipped
through, or two branches each adding a migration). ``alembic upgrade head`` then fails on a real
deploy with "multiple heads". Catching it on the PR — every PR, not just merges — is far cheaper
than catching it in a deploy.

Also validates that every revision's ``down_revision`` resolves (no dangling parent), so the chain
is walkable from the single head back to base. Pure metadata check: no database required.

Run from ``apps/backend``:  python scripts/check_alembic_single_head.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    heads = list(script.get_heads())
    if len(heads) != 1:
        print(
            f"ERROR: expected exactly one Alembic head, found {len(heads)}: {heads}",
            file=sys.stderr,
        )
        print(
            "Two heads means two migrations share a down_revision. Resolve with a merge "
            "migration or by re-chaining one onto the other.",
            file=sys.stderr,
        )
        return 1

    # Walk the whole graph so a dangling down_revision surfaces as an error, not a silent gap.
    revisions = list(script.walk_revisions())
    known = {r.revision for r in revisions}
    dangling: list[str] = []
    for r in revisions:
        downs = r.down_revision
        if downs is None:
            continue
        parents = (downs,) if isinstance(downs, str) else tuple(downs)
        for p in parents:
            if p not in known:
                dangling.append(f"{r.revision} -> missing parent {p}")
    if dangling:
        print("ERROR: dangling down_revision(s):", file=sys.stderr)
        for d in dangling:
            print(f"  - {d}", file=sys.stderr)
        return 1

    print(f"Alembic single-head OK: head={heads[0]} ({len(revisions)} revisions, chain intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
