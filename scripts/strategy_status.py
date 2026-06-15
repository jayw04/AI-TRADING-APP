"""One-line status of a strategy, read straight from the DB (no auth).

Designed to run INSIDE the backend container so it shares the writer's process
space (WAL-consistent) and needs no login/TOTP:

    type scripts\\strategy_status.py | docker compose exec -T backend python -

Reads the `strategies` table read-only and prints whether the named strategy
(default `momentum-portfolio`, excluding paper-variant clones) is in a running
status. Exit 0 = active, 1 = not active / not found — so a caller can branch.
"""

import sqlite3
import sys

NAME = sys.argv[1] if len(sys.argv) > 1 else "momentum-portfolio"
DB = sys.argv[2] if len(sys.argv) > 2 else "/app/data/workbench.sqlite"
# StrategyStatus is stored as the member NAME (SQLEnum native_enum=False).
ACTIVE = {"PAPER", "LIVE", "PAPER_VARIANT"}

try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute(
        "SELECT id, status FROM strategies "
        "WHERE name = ? AND parent_strategy_id IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (NAME,),
    ).fetchone()
except Exception as exc:  # DB unreadable → report, don't crash the launcher
    print(f"{NAME}: STATUS UNKNOWN (db error: {exc})")
    raise SystemExit(2) from exc

if row and str(row[1]).upper() in ACTIVE:
    print(f"{NAME}: ACTIVE (status={row[1]}, id={row[0]})")
    raise SystemExit(0)
print(f"{NAME}: NOT ACTIVE ({'status=' + str(row[1]) + ', id=' + str(row[0]) if row else 'no strategy row - activate once'})")
raise SystemExit(1)
