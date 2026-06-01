"""Verify the audit_log hash chain (P5 §8.1).

Walks every audit_log row in id order and checks two things per row:

  1. ``row_hash`` matches the recomputed canonical hash of the row's content
     (detects content tampering — a field edited after insert).
  2. ``prev_hash`` matches the previous row in the SAME user's chain
     (detects insertion, deletion, or reordering within a user's chain).

The chain links in commit order, which equals id order for the
one-row-per-transaction write pattern the codebase uses.

Run against a live DB or a backup:

    .\\.venv\\Scripts\\python.exe scripts\\verify_audit_integrity.py [db_path]

Exit codes:
  0 — all chains intact.
  1 — at least one row failed (details on stderr).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Make ``app`` importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability.audit_hash import compute_row_hash  # noqa: E402


def verify(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, user_id, actor_type, actor_id, action, target_type, "
        "target_id, payload_json, ts, row_hash, prev_hash "
        "FROM audit_log ORDER BY id"
    )

    per_user_last: dict[object, str | None] = {}
    errors = 0
    total = 0
    for row in cur:
        total += 1
        expected_prev = per_user_last.get(row["user_id"])

        if (row["prev_hash"] or None) != (expected_prev or None):
            print(
                f"ERROR row {row['id']}: prev_hash mismatch. "
                f"stored={row['prev_hash']!r} expected={expected_prev!r}",
                file=sys.stderr,
            )
            errors += 1

        expected_hash = compute_row_hash(
            user_id=row["user_id"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            payload_json=row["payload_json"],
            ts=row["ts"],
            prev_hash=row["prev_hash"],
        )
        if row["row_hash"] != expected_hash:
            print(
                f"ERROR row {row['id']}: row_hash mismatch. "
                f"stored={row['row_hash']} computed={expected_hash}",
                file=sys.stderr,
            )
            errors += 1

        per_user_last[row["user_id"]] = row["row_hash"]

    conn.close()
    print(f"Verified {total} rows; {errors} errors.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "data/workbench.sqlite"
    sys.exit(verify(db))
