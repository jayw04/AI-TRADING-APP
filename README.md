# Trading Workbench

The Trading Workbench is a local-first trading application for active equity traders. It pairs a trader-facing web UI (charts via TradingView, order management, positions, journal, strategy console) with a **Claude Code–powered agent layer** that helps author, monitor, and (optionally) execute systematic strategies. Broker integration is **Alpaca** — paper trading first, with a gated path to live.

> ⚠️ **Status: Pre-MVP.** Not for production trading. Paper trading only by default; live trading requires explicit, audited opt-in.

## Status

**Phase P3 — Agent MVP (B1+B2) closing.** P0 (scaffolding), P1 (manual
trading MVP — paper orders, risk engine, positions, charts), P2
(systematic strategies + backtesting), and P4 (polish: TV webhooks,
async backtests, hot-reload, opportunities page, WS bar dispatch) all
shipped. P3 Sessions 1–5 merged: agent schema + pricing, read-only
MCP tool expansion, agent runtime, REST + WS surface, frontend chat
panel. This PR closes Session 6 (tests, runbooks, exit gate).

The agent operates strictly under
[ADR 0006](docs/adr/0006-llm-not-in-order-path.md) — LLM calls are
allowed only in the user-initiated chat and scheduled-advisory paths.
The order routing path never imports the Anthropic SDK; a CI invariant
(`apps/backend/scripts/check_no_llm_in_order_path.sh`) enforces it.

See [`tasks/todo.md`](tasks/todo.md) for the single-source-of-truth state
index (shipped PRs per phase, next-up session, active blockers).

## Quickstart (Docker — recommended)

```bash
git clone https://github.com/jayw04/AI-TRADING-APP.git
cd AI-TRADING-APP
./scripts/dev.sh                       # creates .env from .env.example, builds, brings up all 3 services
# open http://localhost:5173
```

The script:
1. Creates `.env` from `.env.example` if it doesn't exist (edit it with real Alpaca creds when you reach P1).
2. Builds the backend, MCP server, and frontend images.
3. Starts the stack via `docker compose up`. All three services bind to `127.0.0.1` only (local-first).

On boot, the backend container self-bootstraps: runs `alembic upgrade head` then `seed_dev_data.py` (both idempotent), then serves FastAPI on `:8000`. SQLite lives in `./data/` on the host (persists across `docker compose down`).

Verify:
- `curl http://127.0.0.1:8000/healthz` → `{"status":"ok","db":"ok"}`
- `curl -H "X-Workbench-Auth: change-me-shared-secret" http://127.0.0.1:8000/api/v1/internal/ping` → `{"pong":true}`
- Open `http://localhost:5173` — Dashboard shows the stub account JSON; bottom status bar shows a live `system.heartbeat` ts updating every 5s.

Stop:
```bash
./scripts/dev.sh down
```

### Running a strategy (P2)

The Strategies page is where systematic strategies live.

1. Visit `http://localhost:5173/strategies`.
2. Click "+ New strategy". The defaults register the reference RSI
   mean-reversion strategy on AAPL.
3. Click the strategy name → Backtests tab → "Run backtest". The backtest
   runs asynchronously; the modal polls the job until done.
4. Review metrics + equity curve + trades.
5. Back to the strategy header → "Start (paper)". Status transitions
   IDLE → PAPER.
6. The Signals tab streams live signals via WebSocket; the Orders tab
   shows strategy-attributed orders.
7. Click Stop when done. Any open position is left for you to close
   manually from the Positions page.

> The reference strategy at
> `apps/backend/strategies_user/examples/rsi_meanreversion.py` is a
> **reference implementation, not a trading recommendation**. To write
> your own, see
> [`docs/runbook/strategy-authoring.md`](docs/runbook/strategy-authoring.md).
> Backtesting mechanics are in
> [`docs/runbook/backtesting.md`](docs/runbook/backtesting.md).

### Talking to the agent (P3)

The Agent page is a Claude-powered chat for the workbench. It can read
account state, positions, strategies, signals, quotes, bars, and
indicators via the read-only MCP tool catalog. **It never executes
trades** — see
[ADR 0006](docs/adr/0006-llm-not-in-order-path.md) and
[`docs/runbook/agent.md`](docs/runbook/agent.md) for the architectural
boundary and operational details.

1. Set `ANTHROPIC_API_KEY` in `.env` (empty disables the agent). Get a
   key at [console.anthropic.com](https://console.anthropic.com/).
2. Optional: tune `AGENT_DEFAULT_MODEL` (default
   `claude-haiku-4-5-20251001`) and `AGENT_DAILY_BUDGET_USD` (default
   `2.00`).
3. Visit `http://localhost:5173/agent`.
4. Click "+ B2 chat" for an interactive session or "+ B1 read" for a
   read-only one.
5. Ask about your positions, strategies, signals, or market data. In
   B2, the agent emits structured suggestion cards for actionable
   recommendations — you execute them manually via the rest of the UI.

The agent has a per-user daily cost cap (default `$2.00`). When the
running total would push past the cap, the session transitions to
CAPPED (read-only) — start a new session to continue. See
[`docs/runbook/agent.md`](docs/runbook/agent.md) for the cap mechanics,
session-audit SQL, troubleshooting, and the list of deferred work.

The MCP catalog the agent draws from is documented in
[`docs/runbook/mcp-tools.md`](docs/runbook/mcp-tools.md) (13 read-only
tools: account, positions, orders, fills, strategies, signals,
backtests, quotes, bars, indicators, system status). The same catalog
is reachable from Claude Desktop / Claude Code via SSE — connection
instructions are in that runbook.

## Quickstart (standalone, no Docker)

For backend-only iteration:

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\Activate.ps1            # PowerShell
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_dev_data.py
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

Frontend:
```bash
cd apps/frontend
pnpm install
pnpm dev          # http://localhost:5173
```

MCP server:
```bash
cd apps/mcp-server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
workbench-mcp     # SSE on 127.0.0.1:8765
```

## Architecture

See [Design Doc §4.1](docs/design/TradingWorkbench_DesignDocument_v0.1.md#41-conceptual-diagram-described) for the conceptual diagram. ADRs in [`docs/adr/`](docs/adr/) capture the load-bearing decisions.

A FastAPI backend hosts the order router, risk engine, strategy engine, and an event-driven WebSocket gateway. A separate MCP server, talking to the backend over HTTP with a shared secret, exposes a curated set of tools to Claude Code (read-only + propose-order for advisory sessions; full action surface inside the strict bounds of an "Agent Strategy" for autonomous trading). A React + TypeScript frontend renders the trader-facing UI. All three services run locally via Docker Compose, bound to `127.0.0.1`. SQLite for MVP; PostgreSQL-ready via SQLAlchemy + Alembic.

Three services:

- **`apps/backend/`** — FastAPI + SQLAlchemy 2.x + Alembic. REST + WebSocket gateway. Owns the SQLite DB.
- **`apps/mcp-server/`** — Anthropic MCP server exposing tools that call back into the backend over HTTP with a shared-secret header.
- **`apps/frontend/`** — React + Vite + TypeScript + Tailwind. Talks to backend over REST + WS.

## Repository layout

```
apps/
  backend/         FastAPI service: orders, strategies, risk, market data, audit
  mcp-server/      Claude Code MCP server (separate process)
  frontend/        React + Vite + Tailwind UI
docs/
  design/          Design docs
  implementation/  Implementation plans, P0 checklist, session docs
  runbook/         Operational how-tos
  adr/             Architecture Decision Records
scripts/           Dev helpers (./scripts/dev.sh, seeds, etc.)
data/              SQLite DB lives here (gitignored)
.github/workflows/ CI pipelines
```

## Conventions

| Topic | Choice |
|---|---|
| Python | 3.12.x target (3.13 also works — this machine has 3.13) |
| Node | 20 LTS |
| Python pkg mgr | pip + venv |
| Node pkg mgr | pnpm |
| Default branch | `main` (PR-required, CI-checks-required) |
| Code style — Python | `ruff` (lint + format) |
| Code style — TS | ESLint + Prettier defaults |
| Type checking | `mypy` (backend), `tsc --noEmit` (frontend) |
| Tests | `pytest` (backend), `vitest` (frontend) |
| Commit style | Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`) |
| Issue tracker | GitHub Issues |

## Environment

`.env` is required at the repo root. Copy `.env.example` and edit. Never commit `.env`.

`ANTHROPIC_API_KEY` is for **server-side** Anthropic calls the backend makes for the P3 agent chat panel (B1 read-only + B2 interactive Q&A). Future phases extend its use: P5.5 §2 (scheduled morning brief), P6 (strategy review / parameter tuning proposals / drift detection), P7 (NL → Python strategy authoring). It is **not** used by Claude Code in your IDE — Claude Code authenticates itself.

The set of modules permitted to import the Anthropic SDK is an explicit allowlist enforced by `apps/backend/scripts/check_no_llm_in_order_path.sh` per ADR 0006. The order routing path is permanently off-limits.

## Repo

- GitHub: [`jayw04/AI-TRADING-APP`](https://github.com/jayw04/AI-TRADING-APP) (private)
- Default branch: `main` with branch protection (PR + CI required — planned, set up after Group 8 CI)
- Original planning docs reference `globalcomplyai/trading-workbench`; the repo lives under `jayw04` for now and may transfer to an org later.

## License

Internal / proprietary. Owned by **DigiTech Edge** (IP-holding) and licensed to **GlobalComplyAI** for operation. Not for redistribution. No `LICENSE` file in MVP — keeping the repo unlicensed defaults to "all rights reserved" under copyright.

## Links

- [Design Doc v0.1](docs/design/TradingWorkbench_DesignDocument_v0.1.md)
- [P0 Checklist v0.1](docs/implementation/TradingWorkbench_P0_Checklist_v0.1.md)
- [P0 Session 1 v0.1](docs/implementation/TradingWorkbench_P0_Session1_v0.1.md)
- [Runbooks](docs/runbook/) — operational how-tos
- [ADRs](docs/adr/) — architecture decision records
