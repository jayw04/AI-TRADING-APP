# Trading Workbench — P0 Scaffolding Checklist

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P0 — Scaffolding** |
| Predecessor docs | Design Doc v0.1; Implementation Plan v0.2 |
| Estimated effort | 3–5 working days FTE-equivalent |
| Goal | `docker compose up` brings up a working empty Trading Workbench: backend health green, frontend loads, MCP server responds, CI green. **No trading logic in P0.** |

---

## How to Use This Checklist

Each task is independently executable. Work through groups roughly in order — groups within the same number can be parallelized, but the numbered groups have dependencies (e.g., DB exists before WS gateway uses it for nothing yet, but the wiring is in place).

Convention:
- `- [ ]` Open task
- `- [x]` Completed task
- **Acceptance** at the end of each group is the gate to move on.
- Hand the relevant group to Claude Code in your IDE; review and commit after each group.

---

## 0. Pre-flight Decisions & Tooling

Lock these before writing any code so they don't churn later.

### 0.1 Decisions to confirm

- [ ] **Python version:** target `3.12.x` (default). Fallback `3.11.x`.
- [ ] **Node version:** `20 LTS`.
- [ ] **Python package manager:** `uv` (recommend) or `pip`. Pick one and stick to it across backend + mcp-server.
- [ ] **Node package manager:** `pnpm` (recommend, fast + lockfile-clean).
- [ ] **GitHub repo name:** suggest `globalcomplyai/trading-workbench` (private). Confirm or override.
- [ ] **Default branch:** `main`. PRs required for merge (same Rulesets pattern as `RAG-APP`).
- [ ] **License posture:** internal/private; no LICENSE file needed for MVP. (Revisit if open-sourcing components later.)
- [ ] **Issue tracker:** GitHub Issues for now; revisit if scope grows.

### 0.2 Local environment prerequisites

- [ ] Docker Desktop installed and running.
- [ ] Python 3.12 available (`pyenv` or system).
- [ ] Node 20 + pnpm available (`corepack enable && corepack prepare pnpm@latest --activate`).
- [ ] `uv` installed (`pip install uv` or via standalone installer).
- [ ] `gh` CLI authenticated (for repo creation + Rulesets).

**Acceptance:** all the above decisions logged in the project README's "Conventions" section before any other task runs.

---

## 1. Repository Bootstrap

### 1.1 Create the repo

- [ ] `gh repo create globalcomplyai/trading-workbench --private --description "Local-first trading workbench (Alpaca + TradingView + Claude Code)"`.
- [ ] `git clone` locally to your dev workspace.
- [ ] Add base `.gitignore` (Python, Node, OS, editor, env files — at minimum: `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.env`, `.env.*` except `.env.example`, `*.sqlite`, `*.sqlite-*`, `bars_cache/`, `.DS_Store`, `.idea/`, `.vscode/*` minus `settings.json`).
- [ ] Create top-level directory structure from Implementation Plan §4 (empty folders with `.gitkeep` where needed).
- [ ] Create `README.md` with: project name, one-line description, link to design doc & implementation plan, dev-setup quickstart placeholder, conventions section (versions from 0.1).
- [ ] Initial commit on `main`.

### 1.2 Branch protection (Rulesets)

- [ ] Configure Rulesets on `main` matching the `RAG-APP` pattern:
  - Require PR before merging.
  - Require status checks to pass (will be empty until CI exists; loop back after group 8).
  - Block force pushes.
  - Restrict deletions.

### 1.3 Root config files

- [ ] `.env.example` at repo root listing every env var the system will read (placeholders only, no real secrets). Initial set:
  ```
  # --- Backend ---
  WORKBENCH_ENV=development
  WORKBENCH_HOST=127.0.0.1
  WORKBENCH_PORT=8000
  WORKBENCH_DB_URL=sqlite+aiosqlite:///./data/workbench.sqlite
  WORKBENCH_LOG_LEVEL=INFO
  WORKBENCH_DEV_USER_EMAIL=jay@globalcomplyai.com

  # --- MCP server ---
  MCP_HOST=127.0.0.1
  MCP_PORT=8765
  MCP_BACKEND_URL=http://127.0.0.1:8000
  MCP_BACKEND_TOKEN=change-me-shared-secret

  # --- Frontend ---
  VITE_API_BASE=http://127.0.0.1:8000
  VITE_WS_BASE=ws://127.0.0.1:8000

  # --- Anthropic (used from P5+, placeholder now) ---
  ANTHROPIC_API_KEY=
  ```
- [ ] Copy `.env.example` to a local `.env` (not committed) with dev values.
- [ ] Document in README that `.env` is required.

**Acceptance:** repo exists on GitHub; cloned locally; directory tree matches Implementation Plan §4 skeleton; `.env.example` and `.gitignore` committed; Rulesets configured.

---

## 2. Backend Skeleton (FastAPI)

Work in `apps/backend/`.

### 2.1 Python project bootstrap

- [ ] `apps/backend/pyproject.toml` with:
  - Project metadata.
  - Deps: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy[asyncio]>=2`, `aiosqlite`, `alembic`, `structlog`, `httpx`, `python-multipart`.
  - Dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `types-requests`.
- [ ] `uv venv .venv && uv pip install -e ".[dev]"`.
- [ ] `ruff.toml` (or `[tool.ruff]` in pyproject) with sensible config (line length 100, Python 3.12 target).
- [ ] `mypy.ini` (or `[tool.mypy]`) — strict-ish, but allow `--ignore-missing-imports` for third-party.

### 2.2 App factory & config

- [ ] `app/__init__.py` empty.
- [ ] `app/config.py`: `pydantic-settings` `Settings` class reading `WORKBENCH_*` env vars; cached via `lru_cache`.
- [ ] `app/main.py`: `create_app()` factory that returns FastAPI instance with CORS for `http://localhost:5173`, JSON logging middleware, request-ID middleware, `/healthz` endpoint returning `{"status":"ok","version":"0.0.1"}`.
- [ ] `app/deps.py`: placeholder dependency-injection helpers.
- [ ] `app/utils/logging.py`: structlog JSON setup.

### 2.3 Auth stub

- [ ] `app/auth/__init__.py` exporting `get_current_user`.
- [ ] `app/auth/stub.py`: `get_current_user()` returns the seeded user (`id=1`).
- [ ] `app/auth/future.py`: file with a `TODO: real auth` docstring.

### 2.4 First API surface (placeholders, returning empty/static)

- [ ] `app/api/v1/__init__.py`: router registry.
- [ ] `app/api/v1/account.py`: `GET /api/v1/account` returns a stubbed account `{"id":1,"mode":"paper","status":"connected_stub"}`.
- [ ] Mount the v1 router under `/api/v1` in the app factory.

### 2.5 Basic tests

- [ ] `tests/conftest.py` with an `httpx.AsyncClient` fixture against the FastAPI app.
- [ ] `tests/test_health.py` asserting `GET /healthz` returns 200 + expected JSON.
- [ ] `tests/test_account_stub.py` asserting `GET /api/v1/account` returns 200 + the stub.

### 2.6 Run locally (no Docker yet)

- [ ] `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload` works.
- [ ] `curl http://127.0.0.1:8000/healthz` → 200 + JSON.
- [ ] `pytest` → all green.

**Acceptance:** backend boots locally; healthcheck and stub account endpoint return 200; tests pass.

---

## 3. Database Skeleton (SQLAlchemy 2.x + Alembic)

Still in `apps/backend/`.

### 3.1 SQLAlchemy base & session

- [ ] `app/db/__init__.py`.
- [ ] `app/db/base.py`: `class Base(DeclarativeBase)` with naming conventions for constraints (so Alembic emits stable names).
- [ ] `app/db/session.py`: async engine factory bound to `WORKBENCH_DB_URL`; `get_session()` FastAPI dependency.
- [ ] `app/db/models/__init__.py`: import all model modules so Alembic autogenerate sees them.

### 3.2 P0 models (from Implementation Plan §6.1 + §6.7)

Create minimal models for **P0 only** — full schema lands in later phases.

- [ ] `app/db/models/user.py`: `User(id, email, display_name, created_at)`.
- [ ] `app/db/models/account.py`: `Account(id, user_id FK, broker, mode ENUM[paper,live], credentials_ref NULL, label, created_at)`; unique(user_id, broker, mode).
- [ ] `app/db/models/symbol.py`: `Symbol(id, ticker UNIQUE, exchange, asset_class, name, active)`.
- [ ] `app/db/models/system_config.py`: `SystemConfig(id, user_id FK NULL, key, value, updated_at)`.
- [ ] `app/db/models/audit_log.py`: `AuditLog(id, user_id FK NULL, ts, actor_type, actor_id, action, target_type, target_id, payload_json, ip)`.
- [ ] Use proper SQLAlchemy 2.x typed `Mapped[...]` declarations; enums as `Enum(...)` from sqlalchemy.

### 3.3 Alembic setup

- [ ] `alembic init -t async alembic` (run from `apps/backend/`).
- [ ] Edit `alembic.ini` to read `sqlalchemy.url` from env (not hardcoded).
- [ ] Edit `alembic/env.py` to import `app.db.base.Base` and set `target_metadata = Base.metadata`.
- [ ] Run `alembic revision --autogenerate -m "P0 initial schema"`.
- [ ] Review the generated migration: types correct, indices for FKs present, UNIQUE constraints named.
- [ ] Run `alembic upgrade head`; verify `data/workbench.sqlite` is created with expected tables (`sqlite3 data/workbench.sqlite ".tables"`).

### 3.4 Seed data

- [ ] `scripts/seed_dev_data.py`: on first run, insert:
  - User `id=1, email=<WORKBENCH_DEV_USER_EMAIL>`.
  - Account `id=1, user_id=1, broker='alpaca', mode='paper', label='Alpaca Paper'`.
  - 5–10 sample symbols (`AAPL, MSFT, NVDA, SPY, QQQ, TSLA, AMD, GOOGL, AMZN, META`).
  - SystemConfig row `key='mode', value='paper'`.
- [ ] Make script idempotent (no duplicates on rerun).
- [ ] Document in README how to run it.

### 3.5 DB-aware healthcheck

- [ ] Extend `/healthz` to include a quick `SELECT 1` against the DB; return `{"status":"ok","db":"ok"}` or `degraded` accordingly.
- [ ] Test for the degraded path (point env var to bad URL, expect 503).

**Acceptance:** `alembic upgrade head` produces a fresh SQLite DB with all P0 tables; `seed_dev_data.py` populates baseline rows; `/healthz` reports DB status; tests pass.

---

## 4. WebSocket Gateway Skeleton

### 4.1 Event bus

- [ ] `app/events/bus.py`: in-process async pub/sub. `publish(topic, event_dict)` + `subscribe(topic) -> async iterator`. No persistence in P0.

### 4.2 WS endpoint

- [ ] `app/ws/gateway.py`: `@router.websocket("/ws")` accepting connections; per-connection subscription registry; sends JSON messages.
- [ ] On connect, immediately emit a `system.connected` event `{ts, server_version}`.
- [ ] Heartbeat task: every 5 seconds publish to `system` topic an event `{type:"system.heartbeat", ts}`. Every subscribed client receives.
- [ ] Mount under `/ws` in app factory.

### 4.3 Replay buffer placeholder

- [ ] `app/ws/replay.py`: empty class `ReplayBuffer` with the per-topic windows from Implementation Plan §8 in a constant dict. Don't implement replay logic yet; just the shape. (Used from P1+.)

### 4.4 Verify

- [ ] Use `wscat -c ws://127.0.0.1:8000/ws` (or a small Python test client) to connect; see `system.connected` immediately and `system.heartbeat` every ~5s.
- [ ] Add a test `tests/test_ws_heartbeat.py` using FastAPI's `TestClient.websocket_connect` that receives at least one heartbeat in 7 seconds.

**Acceptance:** WS endpoint accepts connections; emits heartbeats; test green.

---

## 5. MCP Server Skeleton

Work in `apps/mcp-server/`. **Separate Python project**, separate venv, separate Dockerfile.

### 5.1 Project bootstrap

- [ ] `apps/mcp-server/pyproject.toml` with deps: `mcp` (Anthropic MCP Python SDK), `httpx`, `pydantic`, `pydantic-settings`, `structlog`. Dev: `pytest`, `ruff`.
- [ ] `uv venv .venv && uv pip install -e ".[dev]"`.

### 5.2 Server entrypoint

- [ ] `src/server.py`: instantiates the MCP server, registers tools from `src/tools/`, runs over HTTP/SSE on `MCP_HOST:MCP_PORT`.
- [ ] `src/config.py`: `pydantic-settings` Settings (`MCP_*` env vars).
- [ ] `src/auth.py`: outbound shared-secret header for backend calls (`X-Workbench-Auth: <MCP_BACKEND_TOKEN>`).

### 5.3 Backend client

- [ ] `src/client.py`: thin `httpx.AsyncClient` wrapper around `MCP_BACKEND_URL`; methods used by tools.

### 5.4 First tool: `get_system_status`

- [ ] `src/tools/system.py` registering one tool:
  - **Name:** `get_system_status`
  - **Description:** "Returns current Trading Workbench system status (DB, broker, WS, halt state)."
  - **Input schema:** no params.
  - **Behavior:** calls `GET /healthz` on the backend, returns the JSON augmented with `{"mcp_server":"ok","ts": <iso>}`.
- [ ] Register the tool in `server.py`.

### 5.5 Run locally and smoke test

- [ ] Run backend on `:8000` and MCP server on `:8765` simultaneously (two terminals).
- [ ] Use a minimal MCP client (or `curl` against the SSE endpoint, depending on transport chosen) to invoke `get_system_status` and verify it returns a sensible payload.
- [ ] Add a basic test that mocks the backend client and asserts the tool returns the expected shape.

### 5.6 Backend auth check

- [ ] In backend, add a dependency that validates `X-Workbench-Auth` header matches `MCP_BACKEND_TOKEN` (loaded from env). Apply to a new `/api/v1/internal/ping` endpoint (returns `{"pong":true}`); MCP server's `get_system_status` *also* calls this to prove the auth wiring works end-to-end.
- [ ] Test: missing/wrong header → 401.

**Acceptance:** MCP server runs alongside backend; `get_system_status` tool call returns a successful response that includes the backend's healthz output; auth header is enforced.

---

## 6. Frontend Skeleton (React + Vite + Tailwind)

Work in `apps/frontend/`.

### 6.1 Bootstrap

- [ ] `pnpm create vite . --template react-ts` (note the `.` so it scaffolds in the current folder, or use a temp folder and copy).
- [ ] `pnpm add tailwindcss postcss autoprefixer` + `pnpm dlx tailwindcss init -p`.
- [ ] Configure `tailwind.config.ts` content globs.
- [ ] Add Tailwind directives to `src/index.css`.
- [ ] `pnpm add react-router-dom zustand @tanstack/react-query`.
- [ ] Dev deps: `pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom @types/node eslint @typescript-eslint/eslint-plugin @typescript-eslint/parser eslint-plugin-react eslint-plugin-react-hooks`.

### 6.2 Routing & empty pages

- [ ] `src/routes.tsx` defining routes for: `/`, `/opportunities`, `/charts`, `/orders`, `/positions`, `/strategies`, `/journal`, `/agent`, `/settings`.
- [ ] Per-page stub components under `src/pages/<Page>/index.tsx` rendering the page name in a centered card.
- [ ] `src/App.tsx`: shell with left-nav sidebar, top header showing mode banner ("PAPER" amber), main content router outlet.
- [ ] Tailwind dark theme default (body bg, text color).

### 6.3 API client foundation

- [ ] `src/api/client.ts`: `axios` or `fetch` wrapper with `VITE_API_BASE` baseURL.
- [ ] `src/api/account.ts`: `getAccount()` calling `GET /api/v1/account`.
- [ ] Dashboard page calls `getAccount()` via React Query and displays the result (proves end-to-end wiring).

### 6.4 WebSocket client

- [ ] `src/ws/client.ts`: thin WS wrapper that connects to `VITE_WS_BASE/ws`, auto-reconnects with exponential backoff, exposes a subscribe-to-topic API.
- [ ] Bottom-of-screen status bar shows the latest `system.heartbeat` timestamp (proves the WS pipeline).

### 6.5 Tests

- [ ] One Vitest test: renders `App`, asserts the sidebar links are present and the PAPER banner shows.

### 6.6 Run locally

- [ ] `pnpm dev` boots on `:5173`.
- [ ] Visit `http://localhost:5173/` → sees Dashboard, account JSON, heartbeat updating.

**Acceptance:** frontend boots; renders nav + mode banner; Dashboard shows stub account from backend; status bar shows live WS heartbeats.

---

## 7. Docker Compose Orchestration

### 7.1 Per-service Dockerfiles

- [ ] `apps/backend/Dockerfile` (multi-stage: build deps via `uv`, slim runtime, exposes `8000`).
- [ ] `apps/mcp-server/Dockerfile` (same pattern; exposes `8765`).
- [ ] `apps/frontend/Dockerfile.dev` (Node 20; runs `pnpm dev`; exposes `5173`). Use a dev-only image in P0 to keep iteration fast; production build later.

### 7.2 docker-compose.yml at repo root

- [ ] Services: `backend`, `mcp-server`, `frontend`.
- [ ] All bound to `127.0.0.1` (not `0.0.0.0`) per the local-first design (Implementation Plan §10.6, §12).
- [ ] Volumes:
  - `./data:/app/data` on backend (SQLite persistence).
  - `./apps/backend/strategies_user:/app/strategies_user` on backend (so the strategies folder is host-editable).
  - `./apps/backend/bars_cache:/app/bars_cache` on backend.
- [ ] Env files: each service uses the root `.env`.
- [ ] Healthchecks: backend hits `/healthz`; mcp-server hits its own healthcheck endpoint (add a trivial one); frontend doesn't need one.
- [ ] Depends-on with `condition: service_healthy` so mcp-server waits for backend.

### 7.3 Bring-up script

- [ ] `scripts/dev.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  cp -n .env.example .env || true
  docker compose up --build
  ```
- [ ] Document in README.

### 7.4 Verify end-to-end

- [ ] From a clean checkout: `cp .env.example .env`, edit `.env` minimally, run `docker compose up --build`.
- [ ] All three services come up healthy.
- [ ] Browser at `http://localhost:5173` shows the dashboard with stub data and live heartbeat.
- [ ] `curl http://localhost:8000/healthz` → 200 OK.
- [ ] MCP server's `get_system_status` tool invocation returns success.
- [ ] `docker compose down` cleans up; `docker compose up` again preserves SQLite data (volume persistence).

**Acceptance:** one-command bring-up works on a clean machine; all three services live; data persists across restarts.

---

## 8. CI Pipeline (GitHub Actions)

### 8.1 Workflow file

- [ ] `.github/workflows/ci.yml` triggered on PR + push to `main`. Jobs:
  1. **lint-backend**: setup Python 3.12, install `ruff`, run `ruff check apps/backend apps/mcp-server`.
  2. **typecheck-backend**: setup Python 3.12, install backend deps, run `mypy apps/backend/app apps/mcp-server/src` (start lenient; tighten later).
  3. **test-backend**: setup Python 3.12, install backend deps, run `pytest apps/backend -q --cov=apps/backend/app`.
  4. **lint-frontend**: setup Node 20, `pnpm install --frozen-lockfile`, `pnpm -C apps/frontend lint`.
  5. **typecheck-frontend**: `pnpm -C apps/frontend tsc --noEmit`.
  6. **test-frontend**: `pnpm -C apps/frontend test`.
  7. **build-images**: matrix-build the three Dockerfiles (no push in P0; just confirm they build).
- [ ] Use `actions/setup-python@v5`, `actions/setup-node@v4`, `pnpm/action-setup@v4`.
- [ ] Cache `~/.cache/uv` and pnpm store for speed.

### 8.2 Branch protection wiring

- [ ] Re-open the Rulesets configured in 1.2 and add these jobs as **required** status checks.
- [ ] Confirm a "Dependabot bumps something trivial" PR can land via these checks.

### 8.3 First green PR

- [ ] Create a no-op PR (small README edit), watch CI run, merge once green. Establishes baseline.

**Acceptance:** CI runs and is green on `main`; required checks enforced; merging requires a PR.

---

## 9. Documentation Seeds

Make future-Jay's life easier.

### 9.1 README

- [ ] Top-level README covers:
  - One-paragraph project intro (lift from design doc §1).
  - **Quickstart:** clone, copy env, `./scripts/dev.sh`, open `http://localhost:5173`.
  - Architecture diagram link (design doc §4.1).
  - Folder map (one-line per top-level folder).
  - Conventions (Python/Node versions, package managers, branching).
  - Links to design doc and implementation plan.

### 9.2 Runbook

- [ ] `docs/runbook/README.md` index.
- [ ] `docs/runbook/local-dev.md`: how to run each service standalone (outside Docker) for debugging.
- [ ] `docs/runbook/database.md`: how to reset DB (`rm data/workbench.sqlite && alembic upgrade head && python scripts/seed_dev_data.py`).
- [ ] `docs/runbook/symbol-mapping-gaps.md`: empty placeholder per Implementation Plan v0.2 §19.

### 9.3 Architecture decision records (optional but recommended)

- [ ] `docs/adr/0001-stack-choices.md`: a one-pager that explains why FastAPI + SQLite + React + MCP-as-separate-process. Stops re-litigation later.
- [ ] `docs/adr/0002-single-order-entry-point.md`: documents the §11.1 invariant.

**Acceptance:** anyone (you, Claude Code in a fresh session, or a future hire) can clone the repo and be productive in ≤30 minutes.

---

## 10. P0 Exit Gate

Before declaring P0 done, run through every check:

- [ ] `git pull` on a clean machine, `cp .env.example .env`, `./scripts/dev.sh` brings up all three services healthy.
- [ ] `http://localhost:5173/` shows the Dashboard with stub account JSON and a live WS heartbeat.
- [ ] `curl http://localhost:8000/healthz` returns 200 with `{"status":"ok","db":"ok"}`.
- [ ] MCP server's `get_system_status` tool returns a sensible payload that includes backend status.
- [ ] `apps/backend/data/workbench.sqlite` exists and contains the P0 tables (`users`, `accounts`, `symbols`, `system_config`, `audit_log`).
- [ ] `pytest apps/backend` and `pnpm -C apps/frontend test` both pass locally.
- [ ] CI is green on `main`.
- [ ] Branch protection on `main` enforces PR + required CI checks.
- [ ] README quickstart followed by a clean reader actually works (test this).
- [ ] All files under version control; no committed `.env` or secrets.
- [ ] Tag the commit: `git tag -a p0-complete -m "P0 scaffolding complete"`.

**On all checks green → P0 is done. Proceed to P1 (Manual Trading MVP).**

---

## Notes for Claude Code Execution

If you're handing this to Claude Code in your IDE, useful prompting patterns:

1. **One group at a time.** Don't paste the whole file; paste the group you're working on. Keeps context tight.
2. **Acceptance-driven.** After each group, paste the "Acceptance" line and ask Claude Code to verify each item is true before moving on. Same pattern as your ComplyGen LF module todo reviews.
3. **Commit after each group.** Suggested commit messages:
   - `chore(p0): bootstrap repo and tooling`
   - `feat(backend): fastapi skeleton + auth stub`
   - `feat(backend): initial DB schema + alembic + seed`
   - `feat(backend): websocket gateway with heartbeat`
   - `feat(mcp): mcp server skeleton with get_system_status tool`
   - `feat(frontend): vite + tailwind + routing + ws status bar`
   - `chore(infra): docker compose orchestration`
   - `chore(ci): github actions pipeline`
   - `docs: readme, runbook, adrs`
4. **Don't let it sprawl.** P0 is intentionally narrow. If you find yourself reaching for "let me also add the order ticket while I'm here" — stop. That's P1.

---

*End of P0 checklist v0.1.*
