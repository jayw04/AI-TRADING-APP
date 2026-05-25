# Trading Workbench — TODO

> Single source of truth for "what's done, what's next" across sessions. Update at the end of each working session. For frozen versioned plans, see `docs/implementation/` and `docs/design/`.

Last updated: 2026-05-25 · branch: `main` · latest tag: `p4-async-backtest-backend-complete`

---

## ✅ P0 — Scaffolding (complete)

Tag `p0-complete` → `6e66ad9`. (Original 10-group breakdown lives in the v0.1 of this file in git history.)

---

## ✅ P1 — Manual Trading MVP (complete)

Tag `p1-session4-complete` → `48ea67d`. Sessions 1–4 all merged. Trader can place/modify/cancel paper orders against Alpaca from the UI; OrderRouter is the single dispatch path (ADR 0002); risk engine + trade-update consumer + position recompute all live; full REST surface; WS topic publishing; live-mode gates.

| Session | Scope | PR |
|---|---|---|
| **S1** | Alpaca read-only adapter + creds | #1 |
| **S2** | Account/position polling + scheduler + lifespan | #2 |
| **S3** | Trade-updates WS lifecycle | #3 |
| **S4** | Trading DB schema | #4, #5 |
| **S5** | RiskEngine + OrderRouter + trade-update consumer + drift detector | #6 |
| **S5/6** | Full REST + WS topic publishing | #7 |
| **S6 frontend** | Order ticket, orders + positions pages, typed API client | #8 |
| **S6 frontend** | Charts page, real dashboard, live-mode UX gates | #9 |
| **S6 tests** | Coverage gates, REST + e2e tests, runbooks, exit gate | #10 |

---

## 🚧 P2 — Strategy MVP (in progress)

Goal per Design Doc §13: *"One reference systematic strategy runs end-to-end on paper, with backtest harness + deploy."*

Master plan: [`docs/implementation/TradingWorkbench_P2_Checklist_v0.1.md`](../docs/implementation/TradingWorkbench_P2_Checklist_v0.1.md). Session docs alongside it.

| Session | Scope | Status |
|---|---|---|
| **S1** | Bar cache + IndicatorComputer | ✅ #11 |
| **S2** | Strategies framework skeleton (schema, base/context/engine/loader, fixtures) | ✅ #12 |
| **S3** | Reference RSI strategy + backtest harness | ✅ #13 tag `p2-session3-complete` |
| **S4** | Strategies + signals REST surface + WS topic routing | ✅ #16 tag `p2-session4-complete` |
| **S5** | Frontend Strategies pages (CRUD, signals view, backtest modal) | ⏳ **next** |
| **S6** | TBD (haven't read the doc yet) | ⏳ |

### P2 known blockers
- AAPL fixture parquets for `tests/strategies/test_backtest_reproducibility.py` and the live smoke step — Norton SSL inspection on Jay's dev machine blocks `data.alpaca.markets`. Generating from any other env (WSL, CI, a non-Norton machine) populates the three parquets and flips two skipped tests to required.
- Live smoke step in P2 S3 / P2 S4 docs is still pending behind that same SSL blocker.

---

## ⏳ P4 — Polish & extend (partially started, out of stated order)

We ran ahead of the doc order on P4 items because they unblock UI work later. Items are independently mergeable.

| Item | Scope | Status |
|---|---|---|
| **§1** | TradingView Pine webhook receiver | ✅ #14 tag `p4-tv-webhooks-complete` |
| **§2 Part A** | Async backtest job queue (backend) | ✅ #17 tag `p4-async-backtest-backend-complete` |
| **§2 Part B** | Async backtest progress UI (frontend) | ⏳ blocked on P2 S5 (Strategies UI doesn't exist yet) |
| **§3+** | Opportunities page, hot reload, source filter (doc files exist) | ⏳ |

### P4 §2 ship sequence
1. P2 S5 lands the Strategies UI scaffolding (BacktestRunModal, BacktestsTab, etc.)
2. P4 §2 Part B layers the async progress bar + cancel button on top
3. Final tag `p4-async-backtest-complete` after both halves merge

---

## 🧱 Cross-cutting work that landed alongside

- **`app/audit/` module** (#15 — `feat(audit): typed AuditLogger`) — introduced `AuditLogger` + `AuditAction` + `AuditActorType` enums. P2 S4 needed them and they weren't built earlier despite the P1.C checkbox above implying they were. Refactored `OrderRouter`, `StrategyEngine`, `TradeUpdateConsumer` to use the typed helper. Cleanup, not new feature.
- **Alembic template fix** (in #14 and re-tweaked in #17) — `script.py.mako` now produces ruff-clean imports on autogenerate; future `alembic revision --autogenerate` calls don't need a manual fixup pass.

---

## 🗺️ P3 / P5–P7 — Roadmap (untouched)

Captured for orientation; plans land when their turn comes.

| Phase | Theme | Headline outcome |
|---|---|---|
| **P3** | Agent MVP (B1+B2) | Claude Code agent chat panel inside the UI; advisory + propose-and-approve flows. |
| **P5** | Live trading toggle | Live creds, live-mode UI, hard gates, recon. |
| **P6** | Agent autonomy (B3, gated) | Per-strategy autonomous mode with hard budgets + extra audit. Backend-side Anthropic SDK calls with MCP attached. Paper-only by default. |
| **P7** | NL → Python strategy authoring | "Draft strategy with Claude" UI button; backend generates the strategy file. |

---

## How to use this file

- After each working session, update the top section (Last updated / branch / latest tag) and the relevant phase table.
- When a session lands, link the merging PR + tag in the table; don't expand the row into a checklist.
- Frozen versioned plans live in `docs/implementation/`. This file is the index, not the spec.
