# P0 Session 1 — Pre-flight & Repository Bootstrap

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P0**, **Groups 0 + 1** |
| Predecessor | *TradingWorkbench_P0_Checklist_v0.1.md* |
| Scope | Lock conventions, create GitHub repo, bootstrap empty directory structure, configure branch protection. **No application code in this session.** |
| Estimated wall time | 60–90 minutes |
| Stopping point | `git tag p0-session1-complete` |

---

## Session Goal

After this session you have:
- A GitHub repo `globalcomplyai/trading-workbench` (private) with `main` protected by Rulesets.
- The full directory tree from Implementation Plan §4 committed (empty folders, `.gitkeep`-anchored).
- `.gitignore`, `.env.example`, and a starter `README.md` committed.
- Decisions logged so they don't churn later.

No FastAPI code, no React code, no Docker — those land in Sessions 2–7.

---

## Prerequisites Check

Run these and confirm before proceeding. If any fail, fix before starting.

```bash
# Docker
docker --version            # expect Docker Desktop running
docker compose version      # expect v2.x

# Git + GitHub CLI
git --version               # any recent version
gh --version
gh auth status              # must show authenticated to the right account

# Python
python --version            # 3.11.x or 3.12.x present somewhere
# OR pyenv versions          # if using pyenv

# Node + pnpm
node --version              # v20.x
corepack --version          # if missing: install Node 20 LTS fresh
# After ensuring Node 20:
corepack enable
corepack prepare pnpm@latest --activate
pnpm --version              # any pnpm 9.x or later

# uv
uv --version                # if missing: `pip install uv` or visit astral.sh/uv
```

If you're on Windows, run these in **WSL2 Ubuntu** or **Git Bash**. The rest of this session assumes a Unix-style shell.

---

## Group 0 — Pre-flight Decisions & Tooling

### 0.1 Lock these decisions

These go into the README's "Conventions" section in Group 1. Confirm each before moving on:

| Decision | Locked value |
|---|---|
| Python version | **3.12.x** (3.11 acceptable fallback) |
| Node version | **20 LTS** |
| Python package manager | **uv** |
| Node package manager | **pnpm** |
| GitHub repo | **`globalcomplyai/trading-workbench`** (private) |
| Default branch | **`main`**, PR-required for merge |
| License | Internal/private; no LICENSE file in MVP |
| Issue tracker | GitHub Issues |

If any need to change, change them **now**, before any file is committed.

### 0.2 Working directory

Pick the parent folder where you'll clone (e.g., `~/code/` or `D:\code\` on Windows under WSL `/mnt/d/code/`). Used in §1.2 below.

```bash
# Example:
mkdir -p ~/code && cd ~/code
```

**Group 0 acceptance:** prerequisites all green; decisions locked; working directory chosen.

---

## Group 1 — Repository Bootstrap

### 1.1 Create the repo on GitHub

```bash
gh repo create globalcomplyai/trading-workbench \
  --private \
  --description "Local-first trading workbench (Alpaca + TradingView + Claude Code)" \
  --disable-wiki
```

If the org name differs (`globalcomplyai` vs your actual org), use the actual one. Verify:

```bash
gh repo view globalcomplyai/trading-workbench --json name,visibility,defaultBranchRef
```

### 1.2 Clone locally

```bash
gh repo clone globalcomplyai/trading-workbench
cd trading-workbench
```

### 1.3 Create the `.gitignore`

```bash
cat > .gitignore << 'EOF'
# --- Python ---
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
.coverage.*
coverage.xml

# --- Node ---
node_modules/
dist/
.vite/
.turbo/
.pnpm-store/

# --- Env & secrets ---
.env
.env.local
.env.development
.env.production
!.env.example

# --- App data ---
data/
*.sqlite
*.sqlite-shm
*.sqlite-wal
apps/backend/data/
apps/backend/bars_cache/

# --- OS ---
.DS_Store
Thumbs.db

# --- Editors ---
.idea/
.vscode/*
!.vscode/settings.json
*.swp
*.swo

# --- Build artifacts ---
*.log
build/
out/
EOF
```

### 1.4 Create the directory tree

```bash
# Backend
mkdir -p apps/backend/app/{auth,api/v1,webhooks,ws,db/models,brokers/alpaca,market_data,indicators,orders,risk,strategies,agent,audit,events,utils}
mkdir -p apps/backend/alembic/versions
mkdir -p apps/backend/tests
mkdir -p apps/backend/strategies_user/examples
mkdir -p apps/backend/data
mkdir -p apps/backend/bars_cache

# MCP server
mkdir -p apps/mcp-server/src/tools

# Frontend
mkdir -p apps/frontend/src/{pages,components,api,ws,hooks,store,lib}
mkdir -p apps/frontend/src/pages/{Dashboard,Opportunities,Charts,Orders,Positions,Strategies,Journal,Agent,Settings}
mkdir -p apps/frontend/src/components/{chart,ticket,indicator,opportunities-list,ui}

# Docs
mkdir -p docs/{design,implementation,runbook,adr}

# Scripts
mkdir -p scripts
```

Now drop `.gitkeep` files into every directory that's meant to exist but is currently empty (so git tracks them):

```bash
find apps docs scripts -type d -empty -exec touch {}/.gitkeep \;
# Also keep the data/cache dirs but ignore their contents:
touch apps/backend/data/.gitkeep apps/backend/bars_cache/.gitkeep
```

Verify the tree:

```bash
find apps docs scripts -type d | sort
```

Expected output (abridged):

```
apps
apps/backend
apps/backend/alembic
apps/backend/alembic/versions
apps/backend/app
apps/backend/app/agent
apps/backend/app/api
apps/backend/app/api/v1
apps/backend/app/audit
apps/backend/app/auth
apps/backend/app/brokers
apps/backend/app/brokers/alpaca
apps/backend/app/db
apps/backend/app/db/models
apps/backend/app/events
apps/backend/app/indicators
apps/backend/app/market_data
apps/backend/app/orders
apps/backend/app/risk
apps/backend/app/strategies
apps/backend/app/utils
apps/backend/app/webhooks
apps/backend/app/ws
apps/backend/bars_cache
apps/backend/data
apps/backend/strategies_user
apps/backend/strategies_user/examples
apps/backend/tests
apps/frontend
apps/frontend/src
apps/frontend/src/api
apps/frontend/src/components
apps/frontend/src/components/chart
apps/frontend/src/components/indicator
apps/frontend/src/components/opportunities-list
apps/frontend/src/components/ticket
apps/frontend/src/components/ui
apps/frontend/src/hooks
apps/frontend/src/lib
apps/frontend/src/pages
apps/frontend/src/pages/Agent
apps/frontend/src/pages/Charts
apps/frontend/src/pages/Dashboard
apps/frontend/src/pages/Journal
apps/frontend/src/pages/Opportunities
apps/frontend/src/pages/Orders
apps/frontend/src/pages/Positions
apps/frontend/src/pages/Settings
apps/frontend/src/pages/Strategies
apps/frontend/src/store
apps/frontend/src/ws
apps/mcp-server
apps/mcp-server/src
apps/mcp-server/src/tools
docs
docs/adr
docs/design
docs/implementation
docs/runbook
scripts
```

### 1.5 Create `.env.example`

```bash
cat > .env.example << 'EOF'
# ============================================================
# Trading Workbench — Environment Variables Template
# Copy to .env and fill in values. NEVER commit .env.
# ============================================================

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

# --- Anthropic API ---
# Used by the backend from P6+ for:
#   - Agent Strategy invocations (server-side Claude API calls per scheduled tick)
#   - NL → Python strategy authoring (P7+)
# NOT used by Claude Code in P5 agent panel — that authenticates itself.
ANTHROPIC_API_KEY=

# --- Alpaca (used from P1; placeholder now) ---
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_API_SECRET=
ALPACA_LIVE_API_KEY=
ALPACA_LIVE_API_SECRET=
EOF
```

### 1.6 Create the starter `README.md`

```bash
cat > README.md << 'EOF'
# Trading Workbench

Local-first trading workbench combining manual order placement and strategy-driven automated trading, with a Claude Code agent layer.

- **Broker:** Alpaca (paper first, live behind explicit toggle).
- **Charting & signals:** TradingView (embedded widget + Pine alert webhooks).
- **Agent:** Claude Code, both as developer co-pilot and as runtime agent (advisory and autonomous-via-Strategy).
- **Stack:** FastAPI + SQLite + React/TypeScript + a dedicated MCP server.

> ⚠️ **Status:** Pre-MVP. Not for production trading. Paper trading only by default; live trading requires explicit, audited opt-in.

## Quickstart

> The full dev environment lands in P0 Session 7 (Docker Compose). Until then this section is a placeholder.

```bash
cp .env.example .env
# Edit .env with your local values
./scripts/dev.sh
# Open http://localhost:5173
```

## Documents

- Design: `docs/design/TradingWorkbench_DesignDocument_v0.1.md`
- Implementation plan (current): `docs/implementation/TradingWorkbench_ImplementationPlan_v0.2.md`
- P0 checklist: `docs/implementation/TradingWorkbench_P0_Checklist_v0.1.md`
- Runbook: `docs/runbook/`

## Architecture (one paragraph)

A FastAPI backend hosts the order router, risk engine, strategy engine, and an event-driven WebSocket gateway. A separate MCP server, talking to the backend over HTTP with a shared secret, exposes a curated set of tools to Claude Code (read-only + propose-order for advisory sessions; full action surface inside the strict bounds of an "Agent Strategy" for autonomous trading). A React + TypeScript frontend renders the trader-facing UI. All three services run locally via Docker Compose, bound to `127.0.0.1`. SQLite for MVP; PostgreSQL-ready via SQLAlchemy + Alembic.

## Repository Layout

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
```

## Conventions

| Topic | Choice |
|---|---|
| Python | 3.12.x (3.11 acceptable fallback) |
| Node | 20 LTS |
| Python pkg mgr | `uv` |
| Node pkg mgr | `pnpm` |
| Default branch | `main` (PR-required, CI-checks-required) |
| Code style — Python | `ruff` (lint + format) |
| Code style — TS | ESLint + Prettier defaults |
| Type checking | `mypy` (backend), `tsc --noEmit` (frontend) |
| Tests | `pytest` (backend), `vitest` (frontend) |
| Commit style | Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`) |

## License

Internal / proprietary. Owned by **DigiTech Edge** (IP-holding) and licensed to **GlobalComplyAI** for operation. Not for redistribution.
EOF
```

### 1.7 Stage and commit

```bash
git add .gitignore .env.example README.md
git add -A   # picks up all the .gitkeep files
git status   # sanity-check what's about to be committed
```

Expected `git status` output (abridged): the three top-level files plus a couple dozen `.gitkeep` files. **Critically:** no `.env` file, no application code.

```bash
git commit -m "chore(p0): bootstrap repo skeleton, gitignore, env template, readme"
git push origin main
```

### 1.8 Copy the design and implementation docs into the repo

You already have the four planning docs in `/mnt/user-data/outputs/`. Copy them in so the repo is self-contained:

```bash
# Adjust the source paths to wherever you've saved them locally
cp /path/to/TradingWorkbench_DesignDocument_v0.1.md           docs/design/
cp /path/to/TradingWorkbench_ImplementationPlan_v0.2.md       docs/implementation/
cp /path/to/TradingWorkbench_P0_Checklist_v0.1.md             docs/implementation/
cp /path/to/TradingWorkbench_P0_Session1_v0.1.md              docs/implementation/

git add docs/
git commit -m "docs: design v0.1, implementation plan v0.2, p0 checklist, p0 session 1"
git push origin main
```

### 1.9 Configure branch protection (Rulesets)

GitHub Rulesets are easiest to set up in the web UI. The `gh` CLI's `ruleset` support is limited.

Open: `https://github.com/globalcomplyai/trading-workbench/settings/rules`

Create a new **Branch Ruleset** with these settings:

| Setting | Value |
|---|---|
| Ruleset name | `protect-main` |
| Enforcement status | **Active** |
| Target branches | Include default branch (`main`) |
| **Restrict creations** | ✅ |
| **Restrict updates** | ❌ (we want updates via PRs) |
| **Restrict deletions** | ✅ |
| **Require linear history** | ✅ |
| **Require a pull request before merging** | ✅ |
| → Required approvals | 0 (you're solo; raise later) |
| → Dismiss stale approvals | ✅ |
| → Require review from Code Owners | ❌ (no CODEOWNERS yet) |
| **Require status checks to pass** | ✅ (will add specific checks after CI exists in Session 8) |
| **Block force pushes** | ✅ |

Save.

> If your account doesn't have private Rulesets (some plans require Pro/Team for private repos), fall back to **Branch protection rules** (classic) under `Settings → Branches → Add rule`. Same intent.

Verify:

```bash
# Try a direct push to main (should fail or warn):
git commit --allow-empty -m "test: direct push to main (should fail)"
git push origin main
# If push succeeds, the ruleset isn't enforced — re-check settings.
git reset --hard HEAD~1
```

If the direct push went through, the Ruleset isn't doing its job — fix before continuing.

### 1.10 Optional but recommended: open a dummy PR to validate the workflow

```bash
git checkout -b chore/validate-pr-workflow
echo "" >> README.md   # trivial change
git add README.md
git commit -m "chore: validate PR workflow"
git push -u origin chore/validate-pr-workflow

gh pr create --title "chore: validate PR workflow" --body "Sanity check that PR merges work. No CI yet — will be added in Session 8."
# Merge via UI or:
gh pr merge --merge --delete-branch
git checkout main && git pull
```

If the PR creates, merges, and the branch deletes cleanly, the workflow is healthy.

---

## Verification Checklist

Before tagging the session complete, every box below must be true:

- [ ] `gh repo view globalcomplyai/trading-workbench` shows the repo exists, private.
- [ ] Local clone has the full directory tree from §1.4.
- [ ] `.gitignore`, `.env.example`, `README.md` committed and present at repo root.
- [ ] `docs/design/`, `docs/implementation/`, `docs/runbook/`, `docs/adr/` all exist (with `.gitkeep` if empty).
- [ ] The four planning docs are in `docs/design/` and `docs/implementation/`.
- [ ] **No `.env` file in git** (`git ls-files | grep -E '^\.env$'` returns nothing).
- [ ] **No source code committed yet** (`apps/backend/app/main.py` etc. should not exist).
- [ ] `main` branch protected by a Ruleset (or classic protection): direct push blocked, PRs required.
- [ ] At least one PR has been opened, merged, and the branch deleted cleanly.

---

## Sign-off

When all verification boxes are green:

```bash
git tag -a p0-session1-complete -m "P0 Session 1 (Groups 0 + 1) complete: repo bootstrapped, conventions locked, branch protected"
git push origin p0-session1-complete
```

You can now move on to **Session 2 — Backend Skeleton (Group 2)**, which begins introducing actual application code (FastAPI factory, config, auth stub, healthcheck, first tests).

---

## Notes & Gotchas

1. **Org vs personal repo.** If `globalcomplyai` as a GitHub org doesn't exist or you prefer a personal namespace for now, use your own login (`gh repo create <you>/trading-workbench …`) and update the README accordingly. Easy to transfer to an org later.

2. **Windows line endings.** If you're on Windows and Git is converting line endings, set this once globally:
   ```bash
   git config --global core.autocrlf false
   git config --global core.eol lf
   ```
   Then re-clone or reset the working tree.

3. **`gh auth status` shows the wrong account?** Re-auth: `gh auth login` and select the GlobalComplyAI-owning account.

4. **Don't add a `LICENSE` file** — keeping the repo unlicensed defaults to "all rights reserved" under copyright, which is what we want for private IP held under DigiTech Edge. We'll revisit if any component is ever open-sourced.

5. **Don't pre-commit `.vscode/` or `.idea/` files** even if you set them up. Editor configs go in your personal global settings, not the repo. (Exception: `.vscode/settings.json` is allowed and `.gitignore` permits it.)

6. **If you find yourself wanting to start `apps/backend/app/main.py` while you're "here anyway" — STOP.** That's Session 2. Strict separation between sessions keeps reviews tight and rollbacks cheap.

---

*End of P0 Session 1 v0.1.*
