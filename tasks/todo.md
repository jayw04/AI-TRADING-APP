# Trading Workbench — TODO

> Single source of truth for "what's done, what's next" across sessions. Update at the end of each working session. For frozen versioned plans, see `docs/implementation/` and `docs/design/`.

Last updated: 2026-05-31 · branch: `main` · latest tag: `p5-session4-complete`

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
| **S5** | Frontend Strategies pages (CRUD, signals view, backtest modal) | ✅ #18 tag `p2-session5-complete` |
| **S6** | Tests + smoke matrix + runbooks + P2 exit gate | 🚧 PR open: coverage gates + backfill tests + runbooks + README done; smoke matrix + branch-protection promotion + `p2-complete` tag are manual steps after merge |

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
| **§2 Part B** | Async backtest progress UI (frontend) | ✅ #20 tag `p4-async-backtest-complete` |
| **§5** | Backend `source_type` / `source_id` filter on orders + frontend scoped queries | ✅ #22 tag `p4-order-source-filter-complete` |
| **§7** | Typed Params tab form derived from `Strategy.params_schema` | ✅ #23 tag `p4-param-form-complete` |
| **§6** | Backtest charting: drawdown sub-chart + trade markers + Equity/Returns toggle + stats panel | ✅ #24 tag `p4-backtest-charting-complete` |
| **§4** | Strategy hot-reload: file watcher + reload endpoint + UI banner | ✅ #25 tag `p4-strategy-hot-reload-complete` |
| **§3** | Opportunities page: six cross-cutting widgets + aggregator endpoint | ✅ #26 tag `p4-opportunities-page-complete` |
| **§8** | WS bar dispatch: BarStreamService + diff-based subscriptions + cron fallback | ✅ #27 tag `p4-ws-bar-dispatch-complete` |

### P4 §2 ship sequence — DONE 2026-05-26
1. P2 S5 landed the Strategies UI scaffolding (PR #18).
2. P4 §2 Part B layered the WS-driven progress bar + cancel button on top (PR #20).
3. Tag `p4-async-backtest-complete` pushed; both halves shipped.

> Side fix in PR #20: the P2 S5 frontend `BacktestJobStatus` type alias claimed `"done"` but the backend enum serializes `"completed"`. The old modal's success-path check never matched a real backtest — users saw "Running…" forever until dismissing. Type + check both corrected.

---

## 🧱 Cross-cutting work that landed alongside

- **`app/audit/` module** (#15 — `feat(audit): typed AuditLogger`) — introduced `AuditLogger` + `AuditAction` + `AuditActorType` enums. P2 S4 needed them and they weren't built earlier despite the P1.C checkbox above implying they were. Refactored `OrderRouter`, `StrategyEngine`, `TradeUpdateConsumer` to use the typed helper. Cleanup, not new feature.
- **Alembic template fix** (in #14 and re-tweaked in #17) — `script.py.mako` now produces ruff-clean imports on autogenerate; future `alembic revision --autogenerate` calls don't need a manual fixup pass.

---

## ✅ P3 — Agent MVP (B1+B2) — code complete

Six sessions merged; `p3-complete` tag held pending Jay's manual smoke walkthrough (same pattern as P2's open close-out — `p3-session6-complete` ships now; `p3-complete` lands after the smoke log at `docs/runbook/p3-smoke-log.md` records a clean run).

Session docs live under uppercase `Docs/implementation/` (still untracked; six P3 + nine P5 + the P4 checklist are pending an inventory commit).

| Session | Scope | Status |
|---|---|---|
| **S1** | Agent schema (3 tables, 3 enums) + Alembic + pricing helper + DailyBudgetResolver + settings | ✅ #28 tag `p3-session1-complete` |
| **S2** | MCP server read-only tool expansion: 12 new tools + tripwire + runbook (`docs/runbook/mcp-tools.md`) | ✅ #29 tag `p3-session2-complete` |
| **S3** | Agent runtime: Anthropic client + system prompt + session lifecycle + tool-use loop + bilateral cost cap. Constrained by [ADR 0006](../docs/adr/0006-llm-not-in-order-path.md); B3_AUTONOMOUS paused indefinitely. | ✅ #31 tag `p3-session3-complete` |
| **S4** | REST + WS surface: 6 endpoints under `/api/v1/agent` + `agent` WS topic (5 bus events + 128-event replay) | ✅ #32 tag `p3-session4-complete` |
| **S5** | Frontend chat panel at `/agent`: SessionList + ChatPanel + MessageList (role-based + tool cards + suggestion extraction) + CostMeter + WS-driven re-fetches | ✅ #33 tag `p3-session5-complete` |
| **S6** | Tests (E2E + P3 coverage gate) + runbooks (`docs/runbook/agent.md`, `docs/runbook/p3-smoke-log.md`) + README Agent subsection + exit gate prep | ✅ this PR tag `p3-session6-complete` |

### P3 manual steps remaining before `p3-complete` tag
1. Walk `docs/runbook/p3-smoke-log.md` against the live `/agent` page with `ANTHROPIC_API_KEY` configured; commit the filled log.
2. Tag `p3-complete` after the smoke log lands clean.

Step 5 of the smoke (force cost cap) makes a temporary `.env` edit — restore `AGENT_DAILY_BUDGET_USD=2.0` before signing off or the next session opens directly in CAPPED.

### P3 architectural commitment
[ADR 0006 — LLM not in the order path](../docs/adr/0006-llm-not-in-order-path.md) (merged via #30) constrains every future agent-related PR. The CI invariant `apps/backend/scripts/check_no_llm_in_order_path.sh` enforces it: Anthropic SDK use is allowed in `app/agent/`, `app/services/morning_brief.py` (P5.5 §2, future), `app/services/strategy_review.py` (P6, future), `app/services/drift_detection.py` (P6, future) — never in `app/orders/router.py`, `app/risk/`, `app/brokers/`, or strategy execution. **B3 (autonomous order submission) is paused indefinitely** — the `AgentSessionMode.B3_AUTONOMOUS` enum value stays reserved but the runtime rejects sessions started in that mode.

### P3 settled decisions
- **Modes:** B1 (read-only) + B2 (interactive) ship in P3; B3 (autonomous order submission) is paused indefinitely per ADR 0006 (not just deferred — paused).
- **Cost cap:** $2/day per user across all sessions; configurable via `AGENT_DAILY_BUDGET_USD`.
- **Default model:** Haiku 4.5 (`claude-haiku-4-5-20251001`).
- **Anthropic key handling:** env var `ANTHROPIC_API_KEY` only for MVP; per-user encrypted in `system_config` is a P5+ enhancement. Empty key disables agent with a clear runtime error (Session 3).
- **Chat panel placement:** top-level page at `/agent` (settled in Session 5).

### P3 deferred to later phases
- **B3 autonomous trading** — paused indefinitely per ADR 0006.
- **Per-user encrypted API keys** — P5 alongside multi-user auth.
- **Streaming text deltas** — `stream_message` exists but unused; P4+ polish.
- **Multi-session concurrency** — one ACTIVE session per user; multi-session UX is P4+ if it ever becomes a real ask.
- **Tool result expand-to-modal** — replaces the 4000-char truncation; P4+ polish.

## 🚧 P5 — Live trading (in progress)

Master plan: per-session docs under uppercase `Docs/implementation/` (`TradingWorkbench_P5_Session*_v0.1.md`). Session Zero complete (conditional GO, commit `82c1d2c`).

| Session | Scope | Status |
|---|---|---|
| **S0** | Session Zero: static/pytest/live-schema baseline | ✅ `82c1d2c` |
| **S1** | Foundations — LIVE/PAPER distinction: `accounts.broker_mode_locked_at`, `risk_limits.broker_mode` (engine resolves limits scoped by mode), OrderRouter refuses LIVE with `BrokerModeError` before the risk engine, `POST/GET /api/v1/accounts` (live create → 400), red LIVE banner for any live account, Order Ticket disabled-submit for live, `docs/runbook/live-mode.md` | ✅ #37 tag `p5-session1-complete` |

| **S2** | Per-account broker registry — `BrokerAdapter` Protocol (`app/brokers/base.py`, satisfied by existing `AlpacaAdapter` unchanged), `BrokerRegistry` (one adapter per account by `AccountMode`; network-free construct; reuses connected startup paper adapter), OrderRouter resolves per-account after the §1 LIVE guard (fallback keeps paper byte-identical), `credentials_for_mode()` helper, new `check_broker_isolation.sh` CI invariant (trading SDK only; `alpaca.data.*` exempt). Session doc frozen v1.0. | ✅ #38 tag `p5-session2-complete` |

| **S3** | Multi-user auth — replaces the P0 stub: `users.password_hash`(bcrypt 12)/`totp_secret`/`totp_verified_at` + new `sessions` table (SHA-256 token hash, rolling 14-day TTL, revocation); `app/auth/{passwords,tokens,totp}.py`; `stub.py` body replaced (name/exports kept); 6 `/api/v1/auth/*` endpoints + IP rate-limit (5/15min→60min cooldown); WS `/ws` requires cookie → close 4401; `scripts/create_user.py` CLI bootstrap (no web self-signup); frontend `/login`+`RequireAuth`+logout+Vite proxy; `docs/runbook/authentication.md`. | ✅ #39 tag `p5-session3-complete` |

| **S4** | Credential encryption — Fernet store for all per-user secrets at rest. `WORKBENCH_MASTER_KEY` (env) + `app/security/{crypto,credential_store}.py`; new `user_credentials(user_id,kind,ciphertext,…)` table + data migration (`totp_secret`/`pine_webhook_secret` columns dropped, env broker/Anthropic keys captured for user 1); `credentials_for_mode()` → async + store-backed (registry propagates `await`); agent/webhook/auth/`create_user.py` swapped to the store; `/api/v1/users/me/credentials/` (GET/PUT/DELETE, TOTP excluded) + Settings→Credentials page; eighth CI invariant `check_no_env_credentials.sh`; `docs/runbook/credentials.md`; `app/auth/future.py` deleted (S3 close-out). Session doc frozen v1.0. | ✅ #40 tag `p5-session4-complete` |

### P5 §4 deviations from the v1.0 doc (verified against live code)
- **`CredentialKind` is a `StrEnum`** (matches `AccountMode`, satisfies ruff `UP042`); `.value` used at every DB/call site.
- **Migration acquires the master key before any DDL** — a missing key aborts with zero schema changes (eliminates the half-migrated-DB risk of Gotcha #2). Verified on a copy of the dev DB: upgrade/downgrade/upgrade round-trip + encrypt-on-move + plaintext-restore.
- **`users.py` (Pine secret rotate/get) also swapped** to the store — the v1.0 §4.8 named only `alerts.py`, but the write side lives in `users.py`.
- **Credentials router wired via `app/api/v1/__init__.py`** (codebase pattern), not `main.py`; **frontend uses `apiFetch` + React Query** behind the existing `main.tsx` `RequireAuth`.
- **`load_credentials()`/`config.py` left as-is** — only `credentials_for_mode` was the §4 swap-point; the CI invariant forbids only `os.environ.get(<credential-name>)` (none exist).
- §4.14 live-runtime smoke deferred to WSL/CI (Norton + no Docker); in-suite tests are the stand-in. Full suite **419 passed / 9 skipped**; eight invariants + ADR 0002 test green.

### P5 §3 deviations from the v0.1 doc (verified against live code)
- **Test auth**: one autouse `get_current_user` dependency-override in `tests/conftest.py` + a `real_auth` opt-out marker authenticates the whole pre-auth suite as user 1 — **zero per-file edits** (every test client builder imports `create_app` lazily, so patching the factory reaches them all), instead of the doc's "edit ~30 fixtures."
- **CLI**: Docker-free `scripts/create_user.py` (getpass, cross-platform) instead of the doc's `docker compose exec` bash script — the dev box runs without Docker.
- **Cookie transport**: Vite proxy (`/api`,`/ws` → backend) makes the cookie same-origin; `RequireAuth` placed in `main.tsx` so `App`/`App.test` stay unchanged; `apiFetch` defaults to a relative base + `credentials:"include"`; WS bases derive from the page origin.
- Added `email-validator` dep (required by `EmailStr`); test emails use `example.com` (`.local` is rejected by email-validator). `_aware()` UTC coercion in `stub.py` fixes SQLite naive-datetime comparisons. `.gitignore totp_*.png` (QR embeds the secret).
- **Auth-event audit-logging deferred to P5 §8** (structured logs only here, mirrors §1's refusal-audit deferral). TOTP secret stays plaintext until **P5 §4** wraps it in Fernet. §3.10 manual smoke + live paper-order-post-auth unrun (no Docker / Norton).

### P5 §2 deviations from the v0.1 doc (verified against live code; full rationale in the v1.0 session doc §2.0)
- v0.1 wanted a *literal extraction* + async/DTO `BrokerAdapter` rewrite. The Alpaca order logic was **already** extracted (`app/brokers/alpaca/adapter.py`, sync, dict-returning, tested), so v1.0 keeps it untouched and defines the Protocol to match the real surface — the only new capability is **per-account selection** (registry), which is wiring, not an interface rewrite.
- No `app/brokers/{base,alpaca_paper,alpaca_live}.py` split and no `BrokerMode` enum — reused `AccountMode`; the single `AlpacaAdapter` serves paper or live via `paper=` credentials.
- ADR 0002 enforced by `tests/test_adr_0002_invariant.py` + `_router_token` (no `check_adr0002.sh`); all adapter calls stay in `router.py`, so the invariant test needed no edit.
- §2.9 live paper-smoke byte-identical diff deferred to WSL/CI (Norton blocks `data.alpaca.markets`); in-suite routing test is the stand-in.

### P5 §1 deviations from the v0.1 doc (verified against the live codebase)
- `AccountMode{paper,live}` already existed and already typed `accounts.mode`; reused it. No `BrokerMode` enum, no string→enum migration (both already done).
- OrderRouter lives at `app/orders/router.py`; there is no `app/risk/resolver.py` — GLOBAL limits resolve inline in `RiskEngine._load_global_limits`, where the `broker_mode` filter was added.
- Strategy-detail red border / list badge / `StrategyResponse.account_broker_mode` deferred to P5 §7: `strategies` has no `account_id` and no strategy can be LIVE yet.
- Refusal audit-logging deferred to P5 §8 (audit_log is a §8 concern); the refusal is structured-logged via `order_router_refused_live`.

## 🗺️ P5 + P5.5 + P6 + P7 — Roadmap

Captured for orientation; plans land when their turn comes. P5 + P5.5 + P6 + P7 per-session docs are already drafted under uppercase `Docs/implementation/`.

| Phase | Theme | Headline outcome |
|---|---|---|
| **P5** | Live trading toggle | Live creds, live-mode UI, hard gates, reconciliation, audit trail with hash chain. Per-user encrypted Anthropic key lands here. |
| **P5.5** | Morning brief + trading profile + workbench-mcp polish | Scheduled advisory narration; trader profile/preferences; MCP server tightening. The `morning_brief.py` allowlist entry in ADR 0006 anticipates this work. |
| **P6** | Strategy intelligence layer | Periodic strategy review, parameter tuning proposals, drift detection, optional NL → Python exploration. All advisory; all routed through the existing activation flow before anything goes live. Constrained by ADR 0006. |
| **P7** | NL → Python strategy authoring (standalone if not in P6) | "Draft strategy with Claude" UI button; backend generates the strategy file. |

---

## How to use this file

- After each working session, update the top section (Last updated / branch / latest tag) and the relevant phase table.
- When a session lands, link the merging PR + tag in the table; don't expand the row into a checklist.
- Frozen versioned plans live in `docs/implementation/`. This file is the index, not the spec.
