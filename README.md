# Trading Workbench

Local-first trading workbench (Alpaca + TradingView + Claude Code).

## Status

**Phase P0 — Scaffolding.** No trading logic yet. Goal: `docker compose up` brings up backend (healthy), MCP server (responding), and frontend (renders empty shell). See [`docs/TradingWorkbench_P0_Checklist_v0.1.md`](docs/TradingWorkbench_P0_Checklist_v0.1.md).

## Quickstart (target — not all groups complete yet)

```bash
git clone https://github.com/globalcomplyai/trading-workbench.git
cd trading-workbench
cp .env.example .env       # then edit .env with your local values
./scripts/dev.sh           # brings up all services via docker compose
# open http://localhost:5173
```

Until Docker Compose lands (Group 7), run the backend standalone:

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate            # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_dev_data.py
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

Verify: `curl http://127.0.0.1:8000/healthz` → `{"status":"ok","db":"ok"}`.

## Architecture

See [`docs/TradingWorkbench_DesignDocument_v0.1.md`](docs/TradingWorkbench_DesignDocument_v0.1.md) §4.

Three services:

- **`apps/backend/`** — FastAPI + SQLAlchemy 2.x + Alembic. REST + WebSocket gateway. Owns the SQLite DB.
- **`apps/mcp-server/`** — Anthropic MCP server exposing tools that call back into the backend over HTTP with a shared-secret header.
- **`apps/frontend/`** — React + Vite + TypeScript + Tailwind. Talks to backend over REST + WS.

## Folder map

```
apps/backend/         FastAPI service (DB, REST, WS)
apps/mcp-server/      MCP server (Claude Code agent tools)
apps/frontend/        React/Vite UI
docs/                 Design doc, P0 checklist, runbooks, ADRs
scripts/              Top-level operator scripts (dev.sh, etc.)
data/                 SQLite DB lives here (gitignored)
.github/workflows/    CI pipelines
```

## Conventions

| Item | Choice |
|---|---|
| Python | 3.12.x target. 3.13 also works (this machine has 3.13). |
| Node | 20 LTS |
| Python package manager | pip + venv |
| Node package manager | pnpm |
| Default branch | `main` |
| Branching | PRs required for merge; CI must pass |
| License | Internal/private. No `LICENSE` file in MVP. |
| Issue tracker | GitHub Issues |

## Environment

`.env` is required at the repo root. Copy `.env.example` and edit. Never commit `.env`.

## Repo

- GitHub: `globalcomplyai/trading-workbench` (private)
- Default branch: `main` with branch protection (PR + CI required)

## Links

- [Design Doc v0.1](docs/TradingWorkbench_DesignDocument_v0.1.md)
- [P0 Checklist v0.1](docs/TradingWorkbench_P0_Checklist_v0.1.md)
