# Runbooks

Runbooks capture **repeatable operational procedures** — *what an operator does* to diagnose, recover
from, or prevent a recurring operational issue, with the exact commands. They **complement** the other
documentation categories rather than overlap them:

- **Runbooks** (here) — *what operators do* (operational knowledge / procedures).
- **ADRs** (`docs/adr/`) — *why* an architectural decision was made (architecture, not operations).
- **Research reports** (`docs/review/`, `docs/implementation/evidence/`) — *evidence* for a capability.
- **Whitepaper** — vision / platform architecture / commercialization.

Keep these distinct: a runbook should not turn into an architecture doc (that's an ADR), and an ADR
should not turn into an operational guide. Each runbook is intentionally short.

> Runbooks are grouped by category below so navigation stays simple as they grow
> (**Development · Operations · Research · Production**). Add a category heading when the first
> runbook in it appears.

### Development
| Topic | When to use |
|---|---|
| [local-dev.md](local-dev.md) | Running backend / MCP / frontend standalone (no Docker) for fast iteration or debugger attach. |
| [database.md](database.md) | Resetting the SQLite DB, inspecting tables, regenerating an Alembic migration. |

### Operations
| Topic | When to use |
|---|---|
| [high-cpu-diagnosis.md](high-cpu-diagnosis.md) | Backend container pinned at ~100% CPU (one core) / asyncio event-loop spin — how to profile it with py-spy via a `SYS_PTRACE` sidecar, plus the 2026-06-27 alpaca `_run_forever` busy-wait incident + fix. |
| [symbol-mapping-gaps.md](symbol-mapping-gaps.md) | Triaging tickers that exist in Alpaca's universe but not in our local `symbols` table (placeholder; populated from P1). |

_(Many more topic runbooks live in this directory — `recovery.md`, `risk-gates.md`, `on-call.md`,
`live-mode.md`, `deployment.md`, etc. — and should be folded into these categories over time.)_

If you find yourself doing something more than twice that isn't covered here, add a runbook for it.
