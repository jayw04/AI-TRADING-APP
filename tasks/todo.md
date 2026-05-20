# Trading Workbench — TODO

> Single source of truth for "what's done, what's next" across sessions. Update at the end of each working session. For frozen versioned plans, see `docs/implementation/` and `docs/design/`.

Last updated: 2026-05-20 · tag at HEAD: `p0-complete` · branch: `main`

---

## ✅ P0 — Scaffolding (complete)

All ten groups landed across 12 commits on `main`. Tag `p0-complete` → `6e66ad9`.

| Group | Status | Commit |
|---|---|---|
| 1. Repo bootstrap | ✅ | `4dbde1f` |
| 2. FastAPI backend skeleton | ✅ | `b7e5cbf` |
| 3. SQLAlchemy 2.x + Alembic + seed | ✅ | `cce4e03` |
| 3.5 (reconciliation) | ✅ | `bc08792`, `1681547` |
| 4. WebSocket gateway + event bus + ReplayBuffer placeholder | ✅ | `e57b27c` |
| 5. MCP server (`get_system_status` tool) + backend `/internal/ping` | ✅ | `d1194de` |
| 6. React 19 + Vite 6 + Tailwind + 9 routes + WS status bar | ✅ | `d061aab` |
| 7. Docker Compose orchestration (`./scripts/dev.sh`) | ✅ | `54e42a3` |
| 8. GitHub Actions CI (6 parallel jobs) | ✅ | `25a2318` |
| 9. README polish + runbooks + ADRs (0001 stack, 0002 single order entry) | ✅ | `6e66ad9` |
| 10. Exit gate + tag | ✅ | `p0-complete` |

**Exit-gate verification (2026-05-20, local):** `docker compose up` → all 3 services healthy → `/healthz` `{status:ok,db:ok}` → MCP `get_system_status` returns `{mcp_server:ok, backend:{...}, internal_auth:ok}` → frontend HTTP 200 → WS `system.connected` + `system.heartbeat` received live → 13/13 tests pass → no committed `.env`/secrets.

---

## ⏳ P0 follow-ups (you, when you have a minute)

These don't block P1 starts, but they close the loop on the §10 exit gate.

- [ ] **Confirm CI green** on https://github.com/jayw04/AI-TRADING-APP/actions for commit `6e66ad9`. If anything's red, paste the failing job's log and I'll fix.
- [ ] **Set up branch protection** at https://github.com/jayw04/AI-TRADING-APP/settings/rules (or `/settings/branches`). Configure for `main`:
  - Require a pull request before merging (0 approvals OK while solo)
  - Require status checks to pass — make these required: `Python (backend)`, `Python (mcp-server)`, `Frontend`, `Build image (backend)`, `Build image (mcp-server)`, `Build image (frontend)`
  - Require linear history
  - Block force pushes
  - Restrict deletions
- [ ] **First validation PR** (P0 Checklist §8.3): a trivial change (e.g., README typo fix) opened as a PR to validate the protection + CI flow end-to-end. Merge once green, delete branch.
- [ ] **Migrate Alpaca creds** out of `alpaca info.txt` into `.env` (the four `ALPACA_*` vars are already in `.env.example`). After migration, delete `alpaca info.txt`.
- [ ] **Implementation Plan v0.2** doc is referenced throughout the planning docs but isn't in the repo yet. Drop it into `docs/implementation/` when ready.

---

## 🚧 P1 — Manual Trading MVP (next phase)

Goal per Design Doc §13 / S1: *"Trader can place, modify, and cancel paper orders against Alpaca from the UI."*

P1 is the first phase with real trading code. Once it ships, the workbench is genuinely useful (paper) rather than just a healthy shell.

### P1 prereqs

- [ ] Detailed implementation plan for P1 (this file's scope is just a roadmap — the actual P1 should get the same checklist + sessions treatment P0 got).
- [ ] **ADR 0002 (single order entry point)** is the load-bearing invariant for everything below. Re-read before writing the first line of order code.

### P1.A — Alpaca adapter

- [ ] `apps/backend/app/brokers/alpaca/` — thin `alpaca-py` wrapper. One module that owns *all* outbound calls to Alpaca.
- [ ] Mode gating: paper credentials default; live credentials require an explicit `WORKBENCH_TRADING_MODE=live` env flag + on-startup risk acknowledgement.
- [ ] Account sync: pull account info on connect, expose at `/api/v1/account` (replacing the stub).
- [ ] Position sync: poll loop + Trade Updates WebSocket subscription. Persist to local DB.
- [ ] Asset/symbol sync: pull Alpaca's asset universe into the `symbols` table on a daily refresh.
- [ ] Error taxonomy: distinguish transient (retryable) from permanent (don't retry; surface to UI) Alpaca errors.

### P1.B — Order pipeline (the invariant in code)

- [ ] `app/orders/router.py` — `OrderRouter` class. Single point of dispatch for all orders.
- [ ] `app/risk/engine.py` — `RiskEngine` v1: position limits, max order size, max daily loss, kill-switch. Called inline by `OrderRouter` pre-trade.
- [ ] `app/db/models/order.py`, `app/db/models/fill.py`, `app/db/models/position.py` — schema.
- [ ] Alembic migration for the new models.
- [ ] `POST /api/v1/orders` — accepts an OrderIntent, dispatches to `OrderRouter`. Returns the persisted order row (with status).
- [ ] `GET /api/v1/orders` — list with filters (open/all, by symbol, by date).
- [ ] `DELETE /api/v1/orders/{id}` — cancel.
- [ ] `PATCH /api/v1/orders/{id}` — modify (price, qty) via Alpaca's replace endpoint where supported.
- [ ] Fill ingestion from Trade Updates WS → persist fills → recompute position.
- [ ] WS event emission: `orders.*` and `fills.*` and `positions.*` topics (using the existing event bus + WS gateway).

### P1.C — Audit log

- [ ] `app/audit/` — typed writer with `actor_type` ∈ {user, strategy, agent}. Used by `OrderRouter` and any risk decision.
- [ ] Every order placement, fill, and risk rejection gets a row in `audit_log`.
- [ ] `GET /api/v1/audit` — read-only query with filters.

### P1.D — Frontend (real pages)

- [ ] `src/pages/Orders/` — list of working + recent orders, with row actions (cancel, modify).
- [ ] `src/pages/Positions/` — live positions, P&L per symbol, aggregate.
- [ ] `src/components/ticket/` — order ticket. Symbol search, side, qty, limit/market, TIF, optional bracket. Submit goes to `POST /api/v1/orders`.
- [ ] `src/pages/Charts/` — TradingView Advanced Charts widget embedded. Per-symbol switch.
- [ ] `src/pages/Dashboard/` — real account summary (cash, equity, day P&L) instead of the stub JSON dump.
- [ ] Wire WS subscriptions: ticket UI listens for `orders.*`/`fills.*` for the order it just submitted; positions page subscribes to `positions.*`.

### P1.E — UX gates for live trading

- [ ] Mode banner stays AMBER for paper; if live mode is enabled, banner turns RED and a confirmation modal fires on every order ticket submit.
- [ ] Live mode requires checking a "I understand this will place a real order" box per session.

### P1.F — Tests + acceptance

- [ ] Unit tests for `OrderRouter` (every path persists before Alpaca call; risk-rejected orders never reach Alpaca; audit row always written).
- [ ] Mock Alpaca adapter for integration tests (don't hit real Alpaca in CI; use `pytest-httpx` style fixtures).
- [ ] One end-to-end paper-trade test: ticket → router → risk → mocked Alpaca → fill ingestion → position update → WS push.
- [ ] Manual smoke against Alpaca paper: place a market order on a low-priced symbol, observe fill, verify position + audit log.

### P1 exit criteria (acceptance, per design doc §2.3)

| # | Criterion |
|---|---|
| S1 | Trader can place, modify, and cancel paper orders against Alpaca from the UI. |
| S2 | Trader can view a TradingView chart for any Alpaca-tradable symbol within the UI. |
| S5 (partial) | Risk controls block trades that violate configured limits, with clear UI feedback. |
| S6 (partial) | All trading actions are persisted and exportable for review. |

---

## 🗺️ P2+ — Roadmap (from Design Doc §13)

Captured for orientation; each gets its own plan when its turn comes.

| Phase | Theme | Headline outcome |
|---|---|---|
| **P2** | Strategy MVP | One reference systematic strategy runs end-to-end on paper, with backtest harness + deploy. |
| **P3** | Agent MVP (B1+B2) | Claude Code agent chat panel inside the UI; advisory + propose-and-approve flows. |
| **P4** | Polish & extend | TradingView Pine alert webhooks, watchlists, hotkeys, kill switch, reconciliation, journal v2. |
| **P5** | Live trading toggle | Live creds, live-mode UI, hard gates, recon. |
| **P6** | Agent autonomy (B3, gated) | Per-strategy autonomous mode with hard budgets + extra audit. Backend-side Anthropic SDK calls with MCP attached. Paper-only by default. |
| **P7** | NL → Python strategy authoring | "Draft strategy with Claude" UI button; backend generates the strategy file. |

---

## How to use this file

- After each working session, update the top section (Last updated / tag) and tick off P0-follow-up boxes as you finish them.
- When P1 starts, replace the P1 roadmap with the actual P1 checklist (a `docs/implementation/TradingWorkbench_P1_Checklist_v0.1.md`-style doc) and shrink this section to a one-liner pointer.
- Don't let this file grow unbounded. Move detail into proper checklist docs as it solidifies.
