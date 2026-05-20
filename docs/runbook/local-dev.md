# Local development (no Docker)

Use `./scripts/dev.sh` for the normal path. Drop to standalone when you want to attach a debugger, profile, or iterate fast on one service.

> All commands assume you're at the repo root unless noted. Windows PowerShell paths shown — adjust slashes for bash/zsh.

## Prereqs

- Python **3.12** (3.13 also works on Windows; 3.11 is the documented fallback).
- Node **20 LTS**.
- pnpm **10.x** (pin: `corepack enable && corepack prepare pnpm@10.33.4 --activate`).
- Docker Desktop only required for `./scripts/dev.sh`.

## Backend (FastAPI + SQLAlchemy + Alembic)

```powershell
cd apps\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# First run only: migrate + seed
alembic upgrade head
python scripts\seed_dev_data.py

uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

Sanity:
- `curl http://127.0.0.1:8000/healthz` → `{"status":"ok","db":"ok"}`
- `curl http://127.0.0.1:8000/api/v1/account` → stub account JSON
- `curl -H "X-Workbench-Auth: change-me-shared-secret" http://127.0.0.1:8000/api/v1/internal/ping` → `{"pong":true}`

Tests: `pytest -q` (7 tests should pass).

## MCP server

```powershell
cd apps\mcp-server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

workbench-mcp                 # serves SSE on 127.0.0.1:8765
```

The MCP server expects the backend to be reachable at `MCP_BACKEND_URL` (default `http://127.0.0.1:8000`). Start the backend first.

Tests: `pytest -q` (4 tests).

## Frontend (Vite + React)

```powershell
cd apps\frontend
pnpm install
pnpm dev                       # serves http://localhost:5173
```

Other useful scripts:
- `pnpm test` — Vitest run
- `pnpm test:watch` — Vitest watch mode
- `pnpm exec tsc --noEmit` — type check only
- `pnpm lint` — ESLint
- `pnpm build` — production build into `dist/`

The frontend reads `VITE_API_BASE` (default `http://127.0.0.1:8000`) and `VITE_WS_BASE` (default `ws://127.0.0.1:8000`) from `.env` at build time. Open DevTools → Application → Local Storage if those don't seem to apply: a hard reload (Shift+Reload) clears the cached SW/asset bundle.

## Running all three side-by-side without Docker

Three terminals; assumes each venv/pnpm-install already done:

| Terminal | Command |
|---|---|
| 1 (backend) | `cd apps\backend && .venv\Scripts\Activate.ps1 && uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload` |
| 2 (mcp) | `cd apps\mcp-server && .venv\Scripts\Activate.ps1 && workbench-mcp` |
| 3 (frontend) | `cd apps\frontend && pnpm dev` |

Open `http://localhost:5173`. The Dashboard's "Account" panel proves the backend round-trip; the status bar's heartbeat timestamp proves the WebSocket pipeline.

## Common pitfalls

- **Port in use.** Some other process is holding `:8000` / `:8765` / `:5173`. `netstat -ano | findstr ":8000"` (PowerShell) shows the PID; kill it.
- **`Module not found: app`.** You forgot to `pip install -e .` after switching branches that touched `pyproject.toml`, or you activated the wrong venv.
- **Frontend shows old account JSON / no heartbeat.** Backend isn't running, or `VITE_API_BASE` is wrong. Open DevTools → Network and look at the actual request URL.
- **`pnpm install` complains about Node version.** We pinned pnpm to 10.33.4 because corepack now defaults to pnpm 11 which needs Node 22+. If you're on Node 22+, you can bump the pin in `apps/frontend/package.json` `"packageManager"` field.
- **`alembic upgrade head` says "Can't locate revision".** Your `data/workbench.sqlite` was created by an older migration head. See [`database.md`](database.md) for the reset recipe.
