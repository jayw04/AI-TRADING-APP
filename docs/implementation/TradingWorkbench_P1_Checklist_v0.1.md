# Trading Workbench — P1 Manual Trading MVP Checklist

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1 — Manual Trading MVP** |
| Predecessor | *TradingWorkbench_P0_Checklist_v0.1.md* (complete, tag `p0-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Phase numbering | **Design Doc §13** (todo.md-aligned). Where Implementation Plan v0.2 §17 used finer-grained P-numbers, see §0.3 for the mapping. |
| Estimated effort | 2–3 weeks FTE-equivalent |
| Goal | Trader can place, modify, and cancel **paper** orders against Alpaca from the UI. Every order traverses a single risk-gated path. Charts and account state are live. (Design Doc §2.3 criteria **S1**, **S2**, partial **S5/S6**.) |

---

## 0. Pre-flight

Three sub-sections: P0 close-out, P1 prereqs, and the phase-number reconciliation. **Do not start Group 1 until §0.1 is green.**

### 0.1 P0 follow-ups (from todo.md)

Carry-over work that wasn't blocking P0 tag but is blocking real P1 work.

- [ ] **Confirm CI green on `6e66ad9`** at https://github.com/jayw04/AI-TRADING-APP/actions. If any job is red, fix before opening any P1 PR.
- [ ] **Branch protection on `main`** at https://github.com/jayw04/AI-TRADING-APP/settings/rules. Required:
  - Require a pull request before merging (0 approvals OK while solo).
  - Require status checks to pass — make these required: `Python (backend)`, `Python (mcp-server)`, `Frontend`, `Build image (backend)`, `Build image (mcp-server)`, `Build image (frontend)`.
  - Require linear history.
  - Block force pushes; restrict deletions.
- [ ] **First validation PR.** Trivial README change → PR → CI green → merge → branch deleted. Proves the protected-branch workflow before the first real P1 PR rides on it.
- [ ] **Migrate Alpaca creds.** Move from `alpaca info.txt` into `.env` (`ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_API_SECRET`). Then `git rm 'alpaca info.txt'` and verify it's not in history (`git log --all -- 'alpaca info.txt'`). If it was ever committed with real keys, **rotate them** in the Alpaca dashboard — same-day, not "later."
- [ ] **Drop Implementation Plan v0.2 into the repo** at `docs/implementation/TradingWorkbench_ImplementationPlan_v0.2.md`. Then add a one-line note in that file's header: *"Phase numbering in this document predates the todo.md convention; see P1 Checklist §0.3 for the canonical mapping."*

### 0.2 P1 prereqs

- [ ] **Re-read ADR 0002 (single order entry point).** This is the load-bearing invariant for every group below. The whole P1 design is built around the rule that *no code path may submit an order without going through `OrderRouter` → `RiskEngine` → audit*. If you find yourself wanting to "just call Alpaca directly here for a quick test," stop — write a test fixture instead.
- [ ] **Re-read Design Doc §8 (UI/UX)** and **§10 (Security, Risk, Compliance)**. The trader-facing behavior in P1.D and P1.E follow these directly.
- [ ] **Confirm Alpaca paper account is alive.** Log into Alpaca paper dashboard; note the account number; verify there's positive paper buying power.
- [ ] **Pick a stable test symbol set.** Suggest `AAPL, MSFT, NVDA, SPY, QQQ` — large-cap, liquid, predictable. Used in smoke tests below.
- [ ] **Create a P1 issue or milestone** on GitHub linking to this checklist. Use it to bundle the PRs.

### 0.3 Phase-numbering map (for record)

This P1 follows todo.md / Design Doc §13:

| This doc | Design Doc §13 | Implementation Plan v0.2 §17 |
|---|---|---|
| **P1 — Manual Trading MVP** ← *you are here* | P1 Manual trading MVP | P1 Manual Trading MVP |
| P2 — Strategy MVP | P2 Strategy MVP | **P3** Strategy Engine + Reference Strategy |
| P3 — Agent MVP (B1+B2) | P3 Agent MVP (B1+B2) | **P5** Agent B1 + B2 |
| P4 — Polish & extend | P4 Polish & extend | **P2+P4+P8** (Opportunities, TV webhooks, polish) |
| P5 — Live trading toggle | P5 Live trading toggle | **P9** Live Mode Toggle |
| P6 — Agent autonomy (B3) | P6 Agent autonomy (B3) | **P6** Agent Strategy (B3) |
| P7 — NL → Python authoring | (stretch) | **P7** NL → Python Strategy Authoring |

**Notable deferral:** Implementation Plan v0.2 §17 had a dedicated "Opportunities Page" phase (its P2) that combined a manual-trading hub with computed indicators. Under the design-doc numbering, that work has been folded into **P4 Polish & extend**. P1 keeps the manual order ticket and Orders/Positions pages, but the rich Opportunities discovery page (movers, vol-surge, agent picks) waits.

**Acceptance for §0:** every P0-follow-up box ticked; ADR 0002 re-read with the invariant fresh; Alpaca paper account live; P1 milestone open on GitHub.

---

## 1. Alpaca Adapter (P1.A)

The Workbench's only outbound interface to Alpaca. Everything else in the system that touches the broker goes through this module.

### 1.1 Wrapper structure

- [ ] `apps/backend/app/brokers/alpaca/__init__.py` — exports `AlpacaAdapter`.
- [ ] `apps/backend/app/brokers/alpaca/adapter.py` — the class. Methods (initial set):
  - `connect()` / `disconnect()`
  - `get_account()`
  - `get_positions()`
  - `list_assets(active_only=True)` for the daily symbol sync
  - `submit_order(order: OrderRequest) -> AlpacaOrderResponse`
  - `cancel_order(broker_order_id)`
  - `replace_order(broker_order_id, new_qty?, new_limit_price?)`
  - `get_order(broker_order_id)`
  - `list_orders(status, since, limit)`
- [ ] `apps/backend/app/brokers/alpaca/credentials.py` — loads paper credentials from `.env` by default; refuses to load live unless `WORKBENCH_TRADING_MODE=live` is set in env.
- [ ] `apps/backend/app/brokers/alpaca/streaming.py` — `TradeUpdatesStream` wrapper subscribing to Alpaca's order/fill WebSocket. Pushes events into the in-process event bus from `app/events/bus.py`.
- [ ] `apps/backend/app/brokers/alpaca/errors.py` — error taxonomy: `TransientAlpacaError` (5xx, timeouts, rate-limit) vs `PermanentAlpacaError` (4xx with bad data, insufficient funds, asset not tradable). Caller decides whether to retry.

### 1.2 Mode gating (paper-first)

- [ ] `WORKBENCH_TRADING_MODE` env var, default `paper`. Acceptable values: `paper`, `live`.
- [ ] On backend startup, log the mode prominently (`structlog` `event="trading_mode_resolved" mode="paper"`).
- [ ] If `mode=live` at startup, emit an `AuditLog` row `action="LIVE_MODE_BOOT"` and require an additional `WORKBENCH_LIVE_ACK=I_UNDERSTAND` env var to actually accept orders. Absence → live mode loads in *blocked* state (account read-only, no submits accepted; UI banner red with a "live mode not acknowledged" message).
- [ ] Document the live-mode boot procedure in `docs/runbook/live-mode.md` (new file).

### 1.3 Daily asset/symbol sync

- [ ] Scheduled job (apscheduler or a simple async task) runs once at backend startup and then daily at 04:00 ET (pre-market).
- [ ] Pulls Alpaca's tradable US-equity asset list and upserts into the `symbols` table.
- [ ] Deactivates symbols no longer in the active asset list (`active=False`) — never deletes, so historical orders remain joinable.
- [ ] Emits a `system.symbols_synced` event with `{count_total, count_added, count_deactivated}`.

### 1.4 Account & positions sync

- [ ] On connect, call `get_account()` and persist to a new `accounts_state` cache row (separate from the static `accounts` table — this is the *live* snapshot: cash, equity, buying power, day P&L).
- [ ] Position poll loop: every 10s during market hours, every 60s after-hours, pulls `get_positions()` and reconciles into the local `positions` table.
- [ ] Trade Updates WS subscription: subscribes on connect; on each event, calls the adapter's `_on_trade_update(event)` handler which translates Alpaca's payload into internal `OrderEvent` / `FillEvent` objects on the event bus.

### 1.5 Reconciliation hooks (light P1, heavier P4)

- [ ] Compare local DB position state with Alpaca position state on each poll; log discrepancies as `WARNING` for now (full reconciliation UI is P4).
- [ ] If a discrepancy persists for >3 polls, emit `system.reconciliation_drift` event for the WS gateway.

**Acceptance:** adapter can connect to Alpaca paper using `.env` creds; `get_account()` returns real numbers; `list_assets()` populates `symbols` (≥ 5000 rows for US equities); position poll loop runs; Trade Updates stream connects and stays connected for ≥ 30 min in a smoke test.

---

## 2. Database Schema for Trading

### 2.1 Models

- [ ] `app/db/models/order.py` — `Order` per Implementation Plan §6.3. Columns: `id, user_id FK, account_id FK, broker_order_id, symbol_id FK, side, qty, type, limit_price, stop_price, tif, extended_hours, status, source_type, source_id, parent_order_id FK NULL, created_at, submitted_at, terminal_at, rejection_reason, risk_check_id FK`.
- [ ] `app/db/models/fill.py` — `Fill`: `id, order_id FK, broker_fill_id, qty, price, commission, filled_at`.
- [ ] `app/db/models/position.py` — `Position`: `id, user_id FK, account_id FK, symbol_id FK, qty, avg_entry_price, market_value, unrealized_pnl, updated_at`; `UNIQUE(account_id, symbol_id)`.
- [ ] `app/db/models/risk_limits.py` — `RiskLimits` per Implementation Plan §6.5: `id, user_id FK, scope_type, scope_id, max_position_qty, max_position_notional, max_gross_exposure, max_daily_loss, max_orders_per_minute, allow_short, allowed_symbols_json, denied_symbols_json, created_at, updated_at`.
- [ ] `app/db/models/risk_check.py` — `RiskCheck`: `id, order_id FK NULL, decision, reason_codes_json, evaluated_at`.

### 2.2 Enums

- [ ] `app/db/enums.py` — `OrderSide`, `OrderType`, `TIF`, `OrderStatus`, `OrderSourceType`, `RiskDecision`. Match Implementation Plan §6.3 / §6.5 exactly.

### 2.3 Migration

- [ ] `alembic revision --autogenerate -m "P1: orders, fills, positions, risk_limits, risk_checks"`.
- [ ] **Review the generated migration line-by-line.** Autogenerate gets foreign-key cascades and unique-constraint names wrong roughly 1 time in 3.
- [ ] Verify indices: `orders(user_id, status, created_at)`, `orders(symbol_id, created_at)`, `orders(broker_order_id) UNIQUE`, `fills(order_id)`, `fills(filled_at)`.
- [ ] `alembic upgrade head` on a fresh DB; verify all tables.
- [ ] `alembic downgrade -1` then `alembic upgrade head` — must round-trip cleanly.

### 2.4 Seed defaults

- [ ] Extend `scripts/seed_dev_data.py` to insert a default `RiskLimits` row for user 1, `scope_type='global'`:
  - `max_position_qty = 1000`
  - `max_position_notional = 25000`
  - `max_gross_exposure = 100000`
  - `max_daily_loss = 2000`
  - `max_orders_per_minute = 10`
  - `allow_short = False`
- [ ] Idempotent: re-running doesn't duplicate.

**Acceptance:** migration applied cleanly forward and back; seed populates the global risk-limits row; queries against new tables succeed via SQLAlchemy session.

---

## 3. Risk Engine v1

Lives at `apps/backend/app/risk/engine.py`. Pre-trade gate called by `OrderRouter`. **No exceptions, no bypasses.**

### 3.1 Engine surface

- [ ] `RiskEngine.evaluate(order_request, source, context) -> RiskDecision` — pure function over an `OrderRequest`, the source (`manual` for P1), and a snapshot of positions/orders/today's-fills.
- [ ] Returns either `RiskDecision(decision='pass', risk_check_id=...)` or `RiskDecision(decision='reject', reason_codes=[...], risk_check_id=...)`.
- [ ] Always writes a `risk_checks` row before returning, regardless of decision.

### 3.2 P1 checks (from Implementation Plan v0.2 §11.2 — drop checks #8, #9 for now since they're agent/strategy-only)

Check in this order; first failure short-circuits:

1. [ ] **Mode/account consistency.** Order's `account_id` matches current active mode.
2. [ ] **Symbol allow/deny.** Global → account scope.
3. [ ] **Side restrictions.** Short selling only if `allow_short=True`. Extended-hours only if explicitly requested AND symbol supports it.
4. [ ] **Position size cap.** Resulting position qty ≤ `max_position_qty`; resulting notional ≤ `max_position_notional`.
5. [ ] **Gross exposure cap.** Σ |position notional| after this order ≤ `max_gross_exposure`.
6. [ ] **Daily loss cap.** If realized + unrealized day P&L is already ≤ `-max_daily_loss`, reject with `HALT_REACHED` *and* set a system-wide halt flag (cancel all open orders, refuse further submits until manual unhalt). UI shows the halt clearly.
7. [ ] **Rate limit.** Orders submitted in last 60s by this user ≤ `max_orders_per_minute`.
8. [ ] **Sanity.** Qty > 0; price > 0 where applicable; TIF valid; market-hours sanity (warn but allow extended-hours when explicitly flagged).

### 3.3 Reason codes

- [ ] `app/risk/reason_codes.py` — enum-style constants: `OK`, `SYMBOL_DENIED`, `SHORT_NOT_ALLOWED`, `POSITION_CAP_QTY`, `POSITION_CAP_NOTIONAL`, `GROSS_EXPOSURE`, `HALT_REACHED`, `RATE_LIMIT`, `INVALID_INPUT`, `MODE_MISMATCH`. Returned in `RiskCheck.reason_codes_json` and surfaced to UI verbatim so the trader knows exactly what tripped.

### 3.4 Unit tests

- [ ] Test file per check; aim for **100% branch coverage** of `engine.py` (this is the safety-critical path).
- [ ] Specifically: a test that asserts every order code path in the system calls `RiskEngine.evaluate` *before* `AlpacaAdapter.submit_order`. Implement as a fixture that monkey-patches `submit_order` to fail if called without an upstream `evaluate`.

**Acceptance:** every check fires correctly in isolation; rejections produce the right reason code; `HALT_REACHED` triggers system halt; 100% branch coverage on `engine.py`.

---

## 4. Order Router — The Single Entry Point (P1.B)

This is ADR 0002 in code. Lives at `apps/backend/app/orders/router.py`.

### 4.1 Class & contract

- [ ] `OrderRouter.submit(order_request: OrderRequest, source: OrderSourceType, source_id: str) -> Order`. The **only** function in the codebase that calls `AlpacaAdapter.submit_order`.
- [ ] Sequence inside `submit`:
  1. Persist an `Order` row, status `pending_risk`, `risk_check_id=NULL`.
  2. Call `RiskEngine.evaluate`. Persist the `RiskCheck`. If `reject`: update the order to `rejected` with `rejection_reason`, write audit, emit `order.rejected` WS event, return.
  3. If `pass`: update order to `pending_submit`, call `AlpacaAdapter.submit_order`. On transient error: retry up to 3 times with backoff (handled in adapter). On permanent error: order `rejected` with broker reason; audit; WS event.
  4. On success: persist `broker_order_id`, status `submitted`, audit, WS event `order.submitted`.
  5. Return the persisted `Order`.
- [ ] `OrderRouter.cancel(order_id) -> Order` and `OrderRouter.replace(order_id, ...)` follow the same pattern (audit on every step, WS on every transition).

### 4.2 Fill ingestion

- [ ] `app/orders/lifecycle.py` — `handle_trade_update(event)` consumes Trade Updates from the event bus. For each event:
  - Find the local `Order` by `broker_order_id`. If missing, log `WARNING` (could be an out-of-band order from before our adapter started — P4 reconciler handles).
  - On `fill` / `partial_fill`: insert `Fill` row, update `Order.status`, recompute `Position`, write audit, emit `fill.created` and `position.updated` WS events.
  - On `canceled` / `expired` / `rejected`: update `Order.status` to terminal, write audit, emit `order.terminal` WS event.

### 4.3 Position recomputation

- [ ] `app/orders/positions.py` — `recompute_position(account_id, symbol_id)`. Reads all fills for that (account, symbol), produces qty, avg entry price (weighted by quantity), updates `Position` row.
- [ ] Called on every fill; idempotent.

**Acceptance:** `OrderRouter.submit` is the only call site for `AlpacaAdapter.submit_order` in the codebase (`grep` proves it); a deliberately bad order (e.g., qty=0) gets rejected by risk and never reaches Alpaca; a successful order in paper produces an `Order` row → `RiskCheck` row → Alpaca submission → Trade Update → `Fill` row → updated `Position` → audit-log chain.

---

## 5. REST API & WebSocket Events

### 5.1 REST endpoints

Per Implementation Plan §7. All mounted under `/api/v1/`, all going through the `auth/stub.py` (returns user 1 for now).

- [ ] `GET /api/v1/account` — replaces the P0 stub. Returns the live `accounts_state` row.
- [ ] `POST /api/v1/orders` — body: `OrderRequest`. Dispatches to `OrderRouter.submit(..., source='manual')`. Returns the persisted order.
- [ ] `GET /api/v1/orders` — query: `status, since, limit, symbol`. List.
- [ ] `GET /api/v1/orders/{id}` — order with embedded fills + the linked risk check.
- [ ] `DELETE /api/v1/orders/{id}` — dispatches to `OrderRouter.cancel`.
- [ ] `PATCH /api/v1/orders/{id}` — body: `{new_qty?, new_limit_price?}`. Dispatches to `OrderRouter.replace`.
- [ ] `GET /api/v1/positions` — list of open positions.
- [ ] `GET /api/v1/quotes/{symbol}` — last quote (use Alpaca free-tier IEX feed). Cache for 1s.
- [ ] `GET /api/v1/bars/{symbol}?timeframe=...&start=...&end=...&limit=...` — historical OHLCV.

### 5.2 Request/response schemas

- [ ] `app/api/v1/schemas/orders.py` — pydantic models: `OrderRequest`, `OrderResponse`, `FillResponse`, `RiskCheckResponse`. Strict; reject unknown fields.
- [ ] `app/api/v1/schemas/positions.py`.
- [ ] `app/api/v1/schemas/account.py`.

### 5.3 WebSocket topics (Implementation Plan §8)

Use the existing event bus and WS gateway. New topics emitted by P1:

- [ ] `orders` — `order.submitted`, `order.rejected`, `order.canceled`, `order.replaced`, `order.terminal`. Per-topic replay window: 60 min (per v0.2 §8).
- [ ] `fills` — `fill.created`. Replay: 60 min.
- [ ] `positions` — `position.updated`. Replay: 10 min.
- [ ] `quote.{symbol}` — `quote.tick`. Replay: 0 (live-only).
- [ ] `system` — keep heartbeat; add `system.trading_mode`, `system.halted`, `system.unhalted`.

### 5.4 Tests

- [ ] OpenAPI generation works (`/docs` and `/openapi.json` load).
- [ ] Per-endpoint happy-path tests using `httpx.AsyncClient` against the FastAPI app.
- [ ] One end-to-end test (in-process, with mocked Alpaca): POST `/api/v1/orders` → assert risk check row → assert order row → assert mocked Alpaca was called → simulate trade update → assert fill row → assert WS event broadcast.

**Acceptance:** every endpoint listed returns correct status codes; OpenAPI docs are complete; WS subscribers receive the expected events in the expected sequence on a happy-path order.

---

## 6. Audit Log (P1.C)

The audit log already exists from P0 (§6.1 of Implementation Plan). P1 adds **content** to it.

### 6.1 Writer

- [ ] `app/audit/logger.py` — `write_audit(actor_type, actor_id, action, target_type, target_id, payload, request=None)`. Typed wrapper; `actor_type ∈ {'user', 'strategy', 'agent', 'system'}`. P1 uses `'user'` and `'system'`.
- [ ] Called from `OrderRouter` on every state transition.
- [ ] Called from `RiskEngine` on every rejection.
- [ ] Called from the mode-switch handlers (paper ↔ live, halt, unhalt).

### 6.2 Read endpoint

- [ ] `GET /api/v1/audit` — query: `since, actor_type, action, target_type, target_id, limit`. Ordered by `ts DESC`. Default limit 100, cap 1000.
- [ ] `GET /api/v1/audit/export` — same query, returns CSV with `Content-Disposition: attachment`.

### 6.3 Coverage check

- [ ] Add a CI test that asserts: for every `Order` state transition in the integration test, at least one matching `audit_log` row exists with the right `action` and `target_id`. Catches "forgot to write audit" regressions.

**Acceptance:** every P1 trading event lands in `audit_log` with the correct actor/action/target; `/api/v1/audit` returns them in reverse-chronological; CSV export works.

---

## 7. Frontend — Order Ticket Component (P1.D, part 1)

The single most-used UI surface. Lives at `apps/frontend/src/components/ticket/`.

### 7.1 Ticket UI

- [ ] `OrderTicket.tsx` — controlled form component with:
  - Symbol search (autocomplete on `/api/v1/symbols/search?q=...`; falls back to plain text if the search endpoint isn't ready).
  - Side: BUY / SELL toggle.
  - Qty (number) **or** notional ($) — toggle. Notional translates to qty using the last quote at submit time.
  - Order type: MKT / LMT / STP / STP_LMT.
  - Limit price (shown when LMT or STP_LMT).
  - Stop price (shown when STP or STP_LMT).
  - TIF: DAY / GTC / IOC / FOK.
  - Extended hours: checkbox (disabled for MKT).
  - Optional bracket section (collapsible): take-profit limit, stop-loss stop.
  - Submit button.
- [ ] Client-side validation mirrors the risk-engine sanity checks (qty > 0 etc.), but the server's risk engine is the source of truth.
- [ ] On submit, calls `POST /api/v1/orders`. While in-flight, button is disabled with a spinner.

### 7.2 Result handling

- [ ] On success (`order.submitted`): green toast "Order submitted (ID #...)", form resets.
- [ ] On risk rejection: amber banner inline with the reason code translated to plain English (`POSITION_CAP_NOTIONAL` → "Position size would exceed your notional limit of $25,000").
- [ ] On broker rejection: red banner with broker message.
- [ ] Listens to `orders` and `fills` WS topics for the submitted order; updates a small status strip ("Submitted → Partial fill 50/100 @ $193.42 → Filled").

### 7.3 Quote strip

- [ ] Small inline component above the ticket: shows last quote for selected symbol, bid/ask, % change, volume. Subscribes to `quote.{symbol}` WS topic.

### 7.4 Tests

- [ ] Vitest + React Testing Library: form validation, submit happy path (mock API), risk-rejection rendering, broker-rejection rendering.

**Acceptance:** ticket renders; can be driven entirely by keyboard; submits successfully to paper; UI reflects fills live; rejection paths render correctly.

---

## 8. Frontend — Orders, Positions, Charts, Dashboard (P1.D, part 2)

### 8.1 Orders page (`src/pages/Orders/`)

- [ ] Two tabs: **Working** (status ∈ {submitted, partial}), **History** (everything else).
- [ ] Table columns: time, symbol, side, qty, type, limit/stop, status, fills (qty avg-price), audit-id link.
- [ ] Row actions on Working tab: Cancel (calls DELETE), Modify (opens a small inline form, calls PATCH).
- [ ] Click row → side drawer with full order detail: all fills, the linked risk-check decision, audit trail subset.
- [ ] Real-time updates via `orders` WS topic.

### 8.2 Positions page (`src/pages/Positions/`)

- [ ] Table: symbol, qty, avg entry, last price, market value, unrealized P&L (with color), unrealized %.
- [ ] Row action: "Close (market)" → opens a confirmation modal → submits a market order for the opposite side via the same `/api/v1/orders` endpoint (no bypass).
- [ ] Footer: aggregate gross exposure, net exposure, today's realized P&L, total unrealized P&L.
- [ ] Real-time via `positions` and `quote.*` WS topics.

### 8.3 Charts page (`src/pages/Charts/`)

- [ ] Embed TradingView Advanced Charts widget (free, loaded from TradingView's CDN per Design Doc §6.1 / TV-1).
- [ ] Symbol picker at top; the widget reloads on change.
- [ ] Symbol mapping: maintain a tiny client-side map for the seed set (`{AAPL: 'NASDAQ:AAPL', SPY: 'AMEX:SPY', ...}`); fall back to TV's auto-resolve for everything else. Track gaps in `docs/runbook/symbol-mapping-gaps.md`.
- [ ] No order-from-chart yet (stretch, P4).

### 8.4 Dashboard (`src/pages/Dashboard/`)

- [ ] Replace P0's stub-JSON dump with real cards:
  - Account: cash, equity, buying power, day P&L (from `/api/v1/account`).
  - Open positions count.
  - Open orders count.
  - Today's filled orders count.
  - System status strip (broker connected, WS heartbeat age, halted/active).

### 8.5 Routing & nav

- [ ] Sidebar nav order: Dashboard, Orders, Positions, Charts, Settings. (Strategies/Agent/Journal stay as placeholders for P2+/P3+.)
- [ ] Mode banner stays AMBER for paper. Color/text driven by `system.trading_mode` WS event.

**Acceptance:** all four pages render real data; Orders cancel/modify work end-to-end against paper; Positions close-out works through the same `/api/v1/orders` path; chart widget loads for at least the seed symbols.

---

## 9. Live Mode UX Gates (P1.E)

P1 doesn't *enable* live trading — that's P5 — but it puts the gates in place so they can't be quietly bypassed later.

### 9.1 Banner

- [ ] Mode banner colors: paper = amber `bg-amber-500`, live = red `bg-red-600 animate-pulse`, halted = gray-and-red strobe.
- [ ] Banner always visible, top of every page, not dismissable.

### 9.2 Submit confirmation in live mode

- [ ] If `system.trading_mode === 'live'`, the ticket's Submit button is wrapped in a confirmation modal:
  - "You are about to place a **REAL** order against Alpaca's live account."
  - Order summary in big text.
  - Two checkboxes (must check both): "I understand this is a live order" + "I understand orders cannot be unsent."
  - Type the symbol in a text field to confirm (e.g., type "AAPL" to confirm an AAPL order).
  - Submit button stays disabled until all three are satisfied.
- [ ] Per-session, the gate resets every time you reload the page — no "remember my acknowledgement" affordance. Annoying by design.

### 9.3 Halt indicator

- [ ] Banner overlay shows "HALTED — daily loss limit reached" with an Unhalt button (Unhalt also requires confirmation modal + audit row).

**Acceptance:** with `WORKBENCH_TRADING_MODE=paper`, no confirmation modal appears (frictionless paper UX). With `WORKBENCH_TRADING_MODE=live` set in env, submitting requires the full confirmation flow, every time.

---

## 10. Tests & Smoke (P1.F)

### 10.1 Unit

- [ ] `RiskEngine`: 100% branch coverage (gate for merge to `main`).
- [ ] `OrderRouter`: every transition; mocked Alpaca; assert audit row on every state change.
- [ ] `app/orders/positions.recompute_position`: edge cases (cross zero, partial close, multiple symbols).
- [ ] `AlpacaAdapter.errors`: classification (transient vs permanent) of representative Alpaca error payloads.

### 10.2 Integration (in-process, mocked Alpaca)

- [ ] End-to-end test as described in §4 Acceptance.
- [ ] Risk-rejection path test (oversized order → reject → no Alpaca call → audit row → WS event).
- [ ] Daily-loss halt test (force unrealized P&L beyond limit → next order rejected with `HALT_REACHED` → system halt flag set).
- [ ] WS replay on reconnect: subscribe to `orders`, submit 3 orders, disconnect, reconnect within 60 min → all 3 events replayed.

### 10.3 Frontend

- [ ] OrderTicket: form happy path, risk rejection rendering, broker rejection rendering, live-mode confirmation flow.
- [ ] Orders page: cancel action, modify action.
- [ ] Positions page: close-out action triggers a market order through the API.

### 10.4 Manual smoke against Alpaca paper

Run before tagging `p1-complete`. Use the seed symbol set.

- [ ] Market BUY 1 share AAPL → fills near market → position appears → audit row exists.
- [ ] Limit BUY 1 share AAPL at a low limit (won't fill) → working order appears → cancel it → audit row exists.
- [ ] Submit an order that violates `max_position_qty` (e.g., BUY 10000 AAPL) → risk rejection inline → no Alpaca call.
- [ ] Set `max_daily_loss=1` (artificially low), trigger an unrealized loss → next order rejected with `HALT_REACHED` → unhalt path works.
- [ ] Replace working order's limit price → reflected in Alpaca dashboard.
- [ ] Close position via Positions page → market order fires → position goes to zero.

### 10.5 CI

- [ ] Add backend test coverage badge target ≥ 80% (the risk engine pulls this up; frontend coverage can be lower).
- [ ] All P1 PRs must pass the existing 6 CI jobs (Python backend, Python mcp-server, Frontend, plus the 3 image builds).

**Acceptance:** test suites green; all 6 manual smoke steps pass against Alpaca paper; coverage ≥ 80% backend.

---

## 11. Documentation

- [ ] `docs/runbook/live-mode.md` — how to enable live mode (env vars, ack flag), how to disable, recovery from accidental enable.
- [ ] `docs/runbook/symbol-mapping-gaps.md` — keep updating as you find TV ↔ Alpaca mismatches.
- [ ] `docs/runbook/risk-limits.md` — how to read/edit the default risk-limits row; what each reason code means.
- [ ] Update `README.md` Quickstart section: now mentions Alpaca paper setup steps.
- [ ] Update `todo.md`: mark P1 in progress; expand its in-line items into pointer to this doc.

---

## 12. P1 Exit Gate

Before tagging `p1-complete`:

- [ ] All P0 follow-ups from §0.1 closed.
- [ ] Every checkbox above ticked or explicitly deferred (with rationale).
- [ ] Design Doc §2.3 success criteria green:
  - **S1** Place, modify, cancel paper orders from UI ✅
  - **S2** TradingView chart visible for any seed Alpaca symbol ✅
  - **S5 partial** Risk controls block out-of-policy orders with clear UI feedback ✅
  - **S6 partial** All trading actions persisted and exportable ✅
- [ ] Risk engine has 100% branch coverage (CI-enforced).
- [ ] No code path submits an order without going through `OrderRouter` (CI-enforced grep/lint check).
- [ ] All 6 manual smoke steps from §10.4 pass.
- [ ] CI green on `main`.
- [ ] `docker compose up` from a clean checkout still brings up a fully working system end-to-end.
- [ ] `git tag -a p1-complete -m "P1 Manual Trading MVP complete: paper trading via UI, risk-gated, audited"`.
- [ ] Update `todo.md`: mark P1 complete; add P2 prereqs section.

**On all checks green → P1 is done. Move to P2 (Strategy MVP).**

---

## 13. Deferred to later phases (so we don't lose them)

- **Opportunities page** (movers / vol-surge / curated discovery lists with indicator panels) → **P4**.
- **Server-side indicator computation** (RSI/MACD/SMA via pandas-ta) → **P2** (needed for backtest harness) and **P4** (UI surface).
- **Pine alert webhooks from TradingView** → **P4**.
- **Hotkeys** → **P4**.
- **Full reconciler UI** (this P1 logs drift; the UI surface lands in P4).
- **Journal v2 (auto-prefill via agent)** → **P4 / P3-tail**.
- **Bracket-order semantics confirmation against Alpaca paper** → **during P1** (Implementation Plan v0.2 §19 #4). Add findings to `docs/runbook/alpaca-quirks.md`.

---

## Notes for Claude Code execution

Same pattern as P0:

1. **One group at a time**, one PR per group. Roughly: §0 → §1 → §2+§3+§4 (these three are tightly coupled, may need to land together) → §5 → §6 → §7 → §8 → §9 → §10 → §11 → §12.
2. **Acceptance-first**: after each group, before opening the PR, paste that group's Acceptance line and verify each clause is true. Same pattern that worked for the LF module todo reviews.
3. **Commit message style** (continuing from P0):
   - `feat(brokers): alpaca adapter with paper mode gating`
   - `feat(db): orders, fills, positions, risk_limits, risk_checks schemas`
   - `feat(risk): risk engine v1 with eight pre-trade checks`
   - `feat(orders): order router as single submission entry point`
   - `feat(api): order/position/account endpoints + ws events`
   - `feat(audit): structured audit writer and read endpoints`
   - `feat(frontend): order ticket component with risk-reason rendering`
   - `feat(frontend): orders, positions, charts, dashboard pages`
   - `feat(ux): live-mode confirmation gates`
   - `test: p1 unit + integration + paper smoke coverage`
   - `docs(p1): runbooks for live mode, risk limits, symbol mapping`
4. **Don't sprawl.** If the urge to start P2 (Strategy MVP) appears mid-P1 — stop. Strategy work depends on this risk gate being rock-solid; P1 is the foundation for everything autonomous later.

---

*End of P1 Checklist v0.1.*
