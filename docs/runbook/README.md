# Runbooks

Operational how-tos for the Trading Workbench. Each runbook is intentionally short — what to do when, with the exact commands.

| Topic | When to use |
|---|---|
| [local-dev.md](local-dev.md) | Running backend / MCP / frontend standalone (no Docker) for fast iteration or debugger attach. |
| [database.md](database.md) | Resetting the SQLite DB, inspecting tables, regenerating an Alembic migration. |
| [symbol-mapping-gaps.md](symbol-mapping-gaps.md) | Triaging tickers that exist in Alpaca's universe but not in our local `symbols` table (placeholder; populated from P1). |
| [high-cpu-diagnosis.md](high-cpu-diagnosis.md) | Backend container pinned at ~100% CPU (one core) / asyncio event-loop spin — how to profile it with py-spy via a `SYS_PTRACE` sidecar, plus the 2026-06-27 alpaca `_run_forever` busy-wait incident + fix. |

If you find yourself doing something more than twice that isn't covered here, add a runbook for it.
