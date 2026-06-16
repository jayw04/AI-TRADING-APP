# Trading Workbench — System Design Document

> **Working title.** Final product name TBD.

| Field | Value |
|---|---|
| Document version | v0.2 — adds §9A Market Session Model (design-review response) |
| Date | 2026-06-15 |
| Author | Jay Wang (with Claude) |
| Status | Draft — pending review & open-question resolution |
| Successor doc | *Detailed Implementation Plan v0.1* (to be created after this doc is approved) |

---

## 1. Executive Summary

The Trading Workbench is a local-first trading application for active equity traders. It pairs:

1. **A trader-facing web UI** with charting (via TradingView), order management, position & P&L views, watchlists, alerts, a trade journal, and a strategy console.
2. **A Claude Code–powered agent layer** that helps the trader develop, monitor, and (optionally) execute systematic strategies, and that operates as an interactive co-pilot inside the workbench.
3. **Broker integration with Alpaca** — starting with paper trading, with a clear, gated path to live trading.

The system is built on the same stack Jay uses for ComplyGen Lab (FastAPI + React/TypeScript, SQLite for local persistence, optional Postgres later), so it is operationally consistent and reuses known deployment, security, and DevOps patterns.

The MVP target is a single-trader workstation deployment that runs locally, executes paper trades against Alpaca, displays real-time charts and order activity, and lets the trader define and run at least one systematic strategy under agent supervision.

---

## 2. Goals & Non-Goals

### 2.1 Goals (in scope)

- **G1.** Provide a clean, low-latency UI for a discretionary day trader to monitor the market, place manual orders, and review activity.
- **G2.** Integrate TradingView for charting and (where possible) signal generation.
- **G3.** Integrate Alpaca for order execution; **paper trading first**, with live trading gated behind explicit configuration and risk acknowledgements.
- **G4.** Provide a Claude Code agent layer that can: (a) read strategy definitions, market data, and positions; (b) propose / monitor / (optionally) execute trades; (c) surface explanations and audit trail for every agent-initiated action.
- **G5.** Support systematic strategy lifecycle: author → backtest → paper trade → live, with metrics at each stage.
- **G6.** Provide robust risk controls (pre-trade and post-trade) that cannot be bypassed by the agent.
- **G7.** Persist a complete, queryable audit log of every order, fill, agent decision, and strategy run.
- **G8.** Run entirely on a local workstation in the MVP; allow future migration to a hosted deployment without rewriting core logic.

### 2.2 Non-Goals (out of scope for MVP)

- **NG1.** Multi-user / multi-tenant operation. The MVP is single-user.
- **NG2.** Brokers other than Alpaca.
- **NG3.** Asset classes other than US equities and (optionally) US equity options. No futures, FX, or non-US markets in MVP. *(Crypto via Alpaca is a stretch goal — see §13.)*
- **NG4.** Hosting trading as a service to third parties. Doing so introduces RIA / broker-dealer / FINRA implications well outside MVP scope.
- **NG5.** Ultra-low-latency / HFT execution. Target end-to-end signal-to-order latency is "comfortable for discretionary and intraday systematic trading," not microsecond-class.
- **NG6.** Replacing TradingView for charting. We integrate, we don't reimplement.

### 2.3 Success Criteria for MVP

| # | Criterion |
|---|---|
| S1 | Trader can place, modify, and cancel paper orders against Alpaca from the UI. |
| S2 | Trader can view a TradingView chart for any Alpaca-tradable symbol within the UI. |
| S3 | At least one systematic strategy runs end-to-end: signal → risk check → paper order → fill → journal entry. |
| S4 | Claude Code agent can answer "what did I do today and why" with reference to actual stored data. |
| S5 | Risk controls block trades that violate configured limits, with clear UI feedback. |
| S6 | All trading actions and agent decisions are persisted and exportable for review. |

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Workbench** | The overall application described in this document. |
| **Agent layer** | Claude Code–powered components that read, reason, and act on trading data. |
| **Strategy** | A named, versioned set of rules that generate trading signals and (optionally) orders. |
| **Signal** | A timestamped, symbol-scoped event produced by a strategy or external source (e.g., TradingView alert). |
| **Order** | An instruction submitted to Alpaca to buy or sell. |
| **Fill** | A (partial or full) execution of an order, reported back by Alpaca. |
| **Position** | Net holdings in a symbol, derived from fills. |
| **Risk gate** | A pre-trade check that must pass before an order is submitted to Alpaca. |
| **Kill switch** | A one-click action that cancels open orders, halts strategies, and flattens positions (optional). |
| **MCP** | Model Context Protocol — the standard by which Claude Code/agents access external tools. |

---

## 4. High-Level Architecture

### 4.1 Conceptual diagram (described)

```
                   ┌──────────────────────────────────────────────┐
                   │             Trader (Browser, local)          │
                   │   React/TypeScript UI (Vite + Tailwind)      │
                   └──────────┬──────────────────────────┬────────┘
                              │ HTTPS / WSS               │ Embedded
                              ▼                           ▼
                   ┌────────────────────────┐    ┌──────────────────────┐
                   │  Workbench Backend     │    │ TradingView Charting │
                   │  (FastAPI, Python)     │    │ (Widget / Library)   │
                   │  - Auth                │    └──────────┬───────────┘
                   │  - REST API            │               │
                   │  - WebSocket gateway   │               │ Alerts / webhooks
                   │  - Risk engine         │◀──────────────┘
                   │  - Strategy runner     │
                   │  - Order router        │
                   │  - Audit log writer    │
                   └─────┬──────────────┬───┘
                         │              │
                ┌────────▼───┐     ┌────▼─────────────────┐
                │  SQLite    │     │ Alpaca API           │
                │  (local)   │     │  - REST (orders,     │
                │            │     │    positions, acct)  │
                │            │     │  - WS (mkt data,     │
                │            │     │    trade updates)    │
                └────────────┘     └──────────────────────┘
                         ▲
                         │ tool calls (MCP)
                         │
                   ┌─────┴────────────────────┐
                   │  Claude Code Agent Layer │
                   │  - workbench MCP server  │
                   │  - tradingview MCP       │
                   │  - alpaca MCP (optional) │
                   └──────────────────────────┘
```

### 4.2 Component summary

| # | Component | Responsibility |
|---|---|---|
| C1 | **Trader UI** | Renders charts, watchlists, orders, positions, strategy console, journal, agent chat. |
| C2 | **Workbench Backend** | Single FastAPI service hosting REST + WebSocket endpoints, risk engine, strategy runner, audit logger. |
| C3 | **Workbench MCP Server** | Exposes Workbench data and actions to Claude Code as MCP tools. Same machine, separate process. |
| C4 | **TradingView Integration** | Either (a) embedded charting via TradingView widget/library, and/or (b) Pine Script alerts → local webhook → Workbench. |
| C5 | **Alpaca Adapter** | Thin Python wrapper around Alpaca REST + streaming APIs; provides order submission, position sync, market data. |
| C6 | **Strategy Engine** | Hosts user-defined strategies (Python), runs them on a schedule or event-driven, emits signals/orders. |
| C7 | **Risk Engine** | Pre-trade and post-trade checks against configured limits; cannot be bypassed by the agent. |
| C8 | **Data Layer** | SQLite database for orders, fills, positions, signals, journal entries, agent traces, configuration. |
| C9 | **Claude Code Agent** | Runs as a separate Claude Code process the trader invokes; connects to Workbench MCP server. |

### 4.3 Data flow examples

**Manual order placement (happy path):**
UI → POST `/orders` → Risk Engine → Alpaca Adapter → Alpaca REST → response → DB write → WebSocket push back to UI.

**Strategy-driven order:**
Strategy Engine → emits Signal → Strategy decides to act → request to Order Router → Risk Engine → Alpaca → DB write → WS push to UI → Audit log entry.

**Agent-assisted question ("Why am I down today?"):**
Trader chats with Claude Code → Claude Code calls Workbench MCP tools (`get_positions`, `get_fills_today`, `get_recent_signals`) → reasons over results → returns answer with cited data.

---

## 5. Claude Code's Role — Proposed Split

This is one of the most important design decisions. I'm proposing a **two-mode** model:

### 5.1 Mode A — Dev-time co-pilot (always on)
Claude Code is used to **build and maintain** the Workbench itself, the strategies, and the MCP server. This is just how Jay uses Claude Code today.

### 5.2 Mode B — Runtime agent (in-app, opt-in per session)

A long-running Claude Code session that the trader invokes from inside the Workbench, with access to a curated set of MCP tools. Within Mode B, we further distinguish:

| Sub-mode | What the agent can do | What it cannot do |
|---|---|---|
| **B1. Read-only / advisory** | Inspect positions, orders, signals, journal, market data. Answer questions. Suggest trades. | Place, modify, or cancel orders. |
| **B2. Approval-required** | Propose orders that appear in the UI as "Agent Suggestion" cards. Trader clicks Approve/Reject. | Submit orders without human click. |
| **B3. Autonomous (gated)** | Place orders directly via MCP, *subject to the Risk Engine and a per-session "agent budget"* (max orders/hour, max notional/day, allowed symbols, allowed strategies). | Bypass the Risk Engine. Modify risk limits. Move to live trading without explicit toggle. |

**Recommendation:** MVP ships **B1 + B2**. B3 is added in a later phase with extra guardrails, and is **disabled for live trading by default**.

### 5.3 Agent transparency requirements

For every agent action (suggested or executed):
- The tool calls the agent made are persisted.
- The reasoning summary (final assistant message) is persisted.
- The trader can view a timeline of "what the agent looked at and what it decided" for any time window.

---

## 6. TradingView Integration

This is the area with the most open questions. I'm proposing options; we should pick one before implementation planning.

### 6.1 What "TradingView" can mean here

| Option | What it is | Pros | Cons |
|---|---|---|---|
| **TV-1. Advanced Charts widget** | Free embeddable chart widget (iframe). | Fast to integrate, no license. | Limited customization, no programmatic access to drawings, no native Pine signals back into our system. |
| **TV-2. Charting Library** | Licensed JS library, self-hosted. | Full control, custom data feeds, integrate Pine signals. | Requires TV approval / license; bigger build effort. |
| **TV-3. TradingView Desktop app** | Standalone desktop client. | Best charting UX. | Hard to integrate programmatically; not really an SDK. |
| **TV-4. Pine Script alerts → webhook** | Premium TradingView feature; alerts call a URL. | Simple, decoupled, works alongside any of the above. | Requires TV Premium plan; alert latency is seconds, not ms. |

**Suggested MVP:** **TV-1 (Advanced Charts widget) for in-app charting** + **TV-4 (Pine alerts via webhook) for signals from TradingView strategies the trader already runs.** Re-evaluate TV-2 if we hit limits.

### 6.2 TradingView MCP

> **Open question for Jay:** Do you have a specific TradingView MCP server in mind, or do you expect us to build a thin one?

To my knowledge there isn't an official TradingView MCP. Options:

1. **Use a community TradingView MCP** if one exists and is acceptable.
2. **Build a thin "TradingView MCP"** ourselves that exposes a small surface area:
   - `tv_get_quote(symbol)` (via Alpaca or other data source, not TV directly)
   - `tv_get_recent_alerts(strategy_id, since)` (from our webhook-stored alerts)
   - `tv_describe_chart(symbol)` (synthesizes recent OHLCV summary)

   In practice this is less a "TradingView" MCP and more a **Market & Signals MCP**, which may be fine.

3. **Skip a dedicated TV MCP** and have the agent talk to the Workbench MCP server, which internally knows about TV alerts.

**Recommendation:** Option 3 for MVP — fewest moving parts, agent sees a unified view. We can split out a TV-specific MCP later if useful.

---

## 7. Alpaca Integration

### 7.1 Surfaces used
- **Trading API (REST):** account, orders, positions, activity. Both paper (`paper-api.alpaca.markets`) and live (`api.alpaca.markets`).
- **Market Data API (REST + WebSocket):** real-time and historical bars/quotes/trades (subject to data plan).
- **Trade Updates stream (WebSocket):** order/fill events.

### 7.2 Paper vs. live separation

- Two distinct credential sets, stored separately in the local secrets store (see §10.1).
- A single configuration switch `mode ∈ {paper, live}` controls which endpoint is used.
- The UI **always** shows the current mode prominently (banner / color theme), so the trader cannot confuse paper and live.
- Switching to live requires:
  1. Explicit toggle in settings.
  2. A "live trading" risk acknowledgement.
  3. Re-entering credentials.
  4. Audit log entry.

### 7.3 Alpaca MCP

Alpaca's API is straightforward enough that we don't strictly need an MCP wrapper. The Workbench MCP server can expose `place_order`, `cancel_order`, `get_positions`, etc., backed by the Alpaca adapter. **Recommendation:** no separate Alpaca MCP in MVP.

---

## 8. UI / UX Design

### 8.1 Information architecture (top-level navigation)

1. **Dashboard** — at-a-glance: equity curve, today's P&L, open positions, open orders, alerts.
2. **Charts** — TradingView-powered chart with symbol search and watchlist.
3. **Orders** — order ticket, working orders, order history.
4. **Positions** — open positions with live P&L, close-position quick actions.
5. **Strategies** — list of strategies, status, last run, performance, enable/disable.
6. **Journal** — chronological log of trades, with notes (manual + auto from agent).
7. **Agent** — chat panel for the Claude Code agent (Mode B); shows tool-call timeline.
8. **Settings** — API keys, risk limits, paper/live mode, alerts, account.

### 8.2 Common daily-trader features (MVP scope)

| Feature | Description |
|---|---|
| **Watchlist** | User-defined symbol lists with live last/bid/ask/%change. |
| **Order ticket** | Buy/Sell, qty or notional, market/limit/stop/stop-limit, TIF, extended hours toggle, bracket orders. |
| **Hotkeys** | Configurable shortcuts for common actions (e.g., flatten, cancel all, buy 100 @ ask). *Stretch for MVP.* |
| **DOM / Level II** | Out of scope for MVP (Alpaca's data plan dependent). |
| **Quick chart** | Inline mini-chart for any symbol in watchlist. |
| **Alerts** | Price alerts and indicator alerts; deliver to UI toast + (optional) desktop notification. |
| **P&L by symbol/strategy** | Today / this week / all-time. |
| **Trade replay** | Visualize entries/exits on a chart for review. *Stretch.* |
| **Journal entries** | Free-text notes per trade; agent can pre-fill with context. |

### 8.3 Strategy console features

| Feature | Description |
|---|---|
| **Strategy list** | Name, status (idle/paper/live), last signal, today's P&L, equity curve sparkline. |
| **Strategy detail** | Code/config view, recent signals, trades generated, params, risk limits. |
| **Backtest** | Run strategy over historical data, see metrics (Sharpe, max DD, win rate, trade count). |
| **Paper deploy** | One click to run strategy live against paper account. |
| **Live promote** | Requires risk acknowledgement; logs audit entry. |
| **Agent supervision toggle** | Set mode per strategy: B1 / B2 / B3 (see §5.2). |

### 8.4 Agent panel features

- Chat history persisted per session.
- "What is the agent looking at" panel — live view of recent tool calls.
- Suggested-action cards (for Mode B2): symbol, side, qty, rationale, Approve / Reject / Modify.
- Hard stop button: "Disconnect agent from trading tools."

### 8.5 Look-and-feel direction

- Dark theme default (trader-standard).
- Information density tunable (compact / comfortable).
- Color discipline: green for buys/long, red for sells/short, **amber banner for paper, distinct color for live**.
- Keyboard-first where possible.

---

## 9. Strategy Engine

### 9.1 Strategy model

A Strategy is a Python module that conforms to a small interface:

```python
class Strategy:
    name: str
    version: str
    symbols: list[str]
    schedule: str | "event"      # cron-ish, or event-driven on signals/bars
    params: dict
    risk_limits: RiskLimitsConfig

    def on_bar(self, ctx, bar): ...
    def on_signal(self, ctx, signal): ...
    def on_fill(self, ctx, fill): ...
```

`ctx` provides safe accessors: read positions, read recent bars, **request** an order (which goes through the Risk Engine).

### 9.2 Signal sources
- Internal: produced by `on_bar` / `on_signal`.
- External: TradingView Pine alerts via webhook (mapped to a strategy by alert payload).
- Agent: a Claude Code agent action (Mode B2/B3) is recorded as a signal type "agent_action".

### 9.3 Backtesting

- Uses Alpaca historical bars (or cached parquet for repeatability).
- Same `Strategy` interface as live; only `ctx` differs.
- Reports: equity curve, trade list, basic metrics (PnL, Sharpe, max drawdown, win rate, avg win/loss). Slippage and commission models start simple (configurable bps).

### 9.4 Strategy authoring with Claude Code

Jay writes a description in natural language → Claude Code (Mode A, dev-time) scaffolds the strategy module, including tests and a backtest harness. Same pattern Jay already uses in ComplyGen Lab.

---

## 9A. Market Session Model

> *Added v0.2 in response to the design review (the largest missing architectural topic) and the Range Trader paper-activation Finding 9. The trading path has no session-awareness today; this section defines the target model and the gap.*

A trading system must have an explicit model of **when the market is open** and what each strategy is allowed to do in each session. Without it, an interval-scheduled strategy (e.g. `*/5 * * * *`) fires around the clock, intraday "open/close" guards are meaningless, and orders can be sent into illiquid or closed sessions.

### 9A.1 Current state (honest assessment)

Session-awareness is **partial and display-only**:

- `pandas_market_calendars` is a dependency but is used **only in `app/services/equity_curve.py`** (analytics/plotting), **not** in the order or dispatch path.
- `OrderRouter.submit()` carries an `extended_hours` field, but it is a **passthrough flag set by the caller** — the risk engine does **not** check whether the market is open, and there is no Alpaca `get_clock` consultation anywhere in `app/brokers/`.
- The `StrategyEngine` dispatches purely on the cron/interval schedule with **no RTH gate** — a `*/5 * * * *` strategy would attempt `on_bar` 24/7.

**Consequence:** an intraday strategy's `no_trade_open_minutes` / `hard_exit_before_close_minutes` guards rely on the strategy *self-policing* against wall-clock time, with no engine-level enforcement. This is acceptable for the current weekly momentum book (it fires once on a Monday well inside RTH) but is a correctness gap for any intraday strategy — exactly the Range Trader case.

### 9A.2 Target model

A single source of session truth, consulted by the engine before dispatch and available to strategies via `ctx`:

| Session | Definition | Default strategy behavior |
|---|---|---|
| **Regular (RTH)** | 09:30–16:00 ET on a trading day | normal `on_bar` dispatch + order submission |
| **Pre-market** | 04:00–09:30 ET | **no dispatch** unless a strategy explicitly opts in (`allow_extended_hours`) |
| **After-hours** | 16:00–20:00 ET | as pre-market |
| **Closed** | overnight / weekends | no dispatch; no order submission |
| **Holiday** | full-day exchange holiday | no dispatch |
| **Half-day** | early-close session (e.g. day after Thanksgiving) | RTH rules with the early close as the "close" for end-of-day guards |

Session source: `pandas_market_calendars` (XNYS schedule) for the *calendar* (trading days, half-days, holidays), cross-checked against the Alpaca `get_clock` / `get_calendar` endpoints for the *authoritative open/close* at runtime (broker is the final word on a surprise close). The calendar gives advance scheduling; the clock gives the live gate.

### 9A.3 Where the gate lives

- **Engine dispatch gate (primary):** `StrategyEngine` consults a `MarketSession` service before firing `on_bar`. If the session is not one the strategy is allowed to act in, the tick is skipped (logged, not an error). This makes the open/close guards real.
- **Risk-engine session check (defense in depth):** a session check in `OrderRouter.submit()` that fails closed — reject an order whose account/strategy is not permitted to trade in the current session. Like every risk check, it is additive and centralized (composes with the existing checks; ADR 0002 / risk-engine conventions). New typed rejection reason: `MARKET_SESSION_CLOSED`.
- **Strategy-visible:** `ctx.session` exposes the current session + next open/close so strategies can compute their own open/close offsets against an authoritative clock rather than `datetime.now()`.

### 9A.4 Implementation scope (code task — not in this doc)

This section is the *design*; the build is a separate, gated work item:

1. `app/market/session.py` — `MarketSession` service wrapping `pandas_market_calendars` (XNYS) + an Alpaca-clock cross-check, with a small cache (calendar is stable intraday; the clock is polled).
2. Wire the **engine dispatch gate** (skip-and-log out-of-session ticks) — the highest-leverage single change; it makes intraday open/close guards enforceable.
3. Add the **`MARKET_SESSION_CLOSED`** risk check (fail-closed) + tests at the risk-engine ≥95% bar; update `RejectionReason` enum, frontend i18n, audit allowlist, and `docs/runbook/risk-checks.md`.
4. Expose `ctx.session`.
5. **Conservative default:** strategies are **RTH-only** unless they explicitly opt into extended hours — matching the platform's "conservative defaults" posture.

This is a **prerequisite for activating any intraday strategy** (Range Trader); the weekly momentum book is unaffected by its absence but benefits from the defense-in-depth check.

---

## 10. Security, Risk, and Compliance

### 10.1 Credential management
- API keys (Alpaca paper, Alpaca live, TradingView, etc.) stored in OS keychain (`keyring` library) or an encrypted local store. **Never** in the SQLite DB or any config file checked into git.
- Backend reads credentials at startup; UI never sees raw keys.

### 10.2 Risk engine — pre-trade checks
Configurable limits include:
- Max position size (shares and notional) per symbol.
- Max total gross exposure.
- Max daily loss (kill switch trigger).
- Max orders per minute (rate limit, throttles runaway strategies).
- Symbol allow/deny lists.
- Order type restrictions (e.g., no short selling in MVP unless toggled).
- Per-strategy and per-agent-session budgets.

**Every** order — manual, strategy, or agent — passes through this engine. There is no fast path that bypasses it.

### 10.3 Post-trade checks
- Periodic reconciliation: positions/orders from Alpaca compared to our DB; mismatches raise an alert.
- Daily P&L vs. limit; auto-halt if exceeded.

### 10.4 Kill switch
- UI button to: cancel all open orders, halt all strategies, optionally flatten all positions. Confirmation required. Audit logged.

### 10.5 Audit log
Every meaningful event is appended to an immutable-ish (append-only) audit table:
- Order submitted / modified / cancelled / filled
- Strategy started / stopped / errored
- Agent session started / tool call / action proposed / action executed
- Configuration change
- Mode change (paper ↔ live)
- Kill switch invoked

Exportable to CSV/JSON for offline review.

### 10.6 Authentication
- MVP runs on localhost; bound to `127.0.0.1`. Local-only basic auth on the UI (so a casual passerby can't trade).
- If we ever expose remotely: SSO + per-user accounts + audit ownership. Not in MVP.

### 10.7 Regulatory note (informational, not legal advice)

A single-user, personal-account, paper/live trading tool operating on the user's own Alpaca account is materially different from operating a service for others. Anything beyond personal use likely triggers RIA / broker-dealer / FINRA considerations. *Out of MVP scope; flagging now so we don't accidentally architect into it.*

---

## 11. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | React + TypeScript + Vite + Tailwind | Matches ComplyGen Lab stack; ecosystem is huge. |
| Charting | TradingView Advanced Charts widget (MVP) | Best charting UX, minimal effort. |
| Backend | FastAPI (Python) | Matches existing stack; async, easy WebSocket. |
| Realtime | WebSockets (server-pushed) | Live orders, fills, positions, signals. |
| Database | SQLite (MVP), with migration path to Postgres | Matches ComplyGen Lab; trivial to deploy locally. |
| Broker SDK | `alpaca-py` (official) | Maintained, supports paper & live, market data. |
| Strategy runtime | Plain Python in-process (MVP), with `asyncio` scheduling | Simple; can split to subprocess later if needed. |
| Agent runtime | Claude Code (separate process) | Aligned with how Jay already works. |
| MCP | Custom Workbench MCP server in Python | Single integration surface for the agent. |
| Secrets | `keyring` + (fallback) encrypted local file | Standard practice. |
| Packaging | `uv`/`pip` for backend, `pnpm` for frontend, `docker compose` for one-command bring-up | Local-first, reproducible. |
| Logging | Structured JSON logs + audit DB table | Investigable later. |

---

## 12. Deployment & Operations

### 12.1 Local-first MVP
- One `docker compose up` (or one script) starts: backend, frontend dev server, SQLite, MCP server.
- Browser opens to `http://localhost:5173` (or similar).
- Claude Code session is launched separately; configured with the Workbench MCP server URL.

### 12.2 Backup & recovery
- SQLite DB nightly snapshot to a local backups folder, with retention.
- Config and secrets backed up separately.

### 12.3 Observability
- Local Grafana / Prometheus is overkill for MVP; we'll use structured logs + a small "system status" panel in the UI (queue depths, last broker heartbeat, last data tick).

### 12.4 Future hosted deployment
- Same stack, runnable on a single VM behind Cloudflare Tunnel (same pattern Jay already uses for `compliance.globalcomplyai.com`).
- Requires auth hardening and per-user accounts.

---

## 13. Phased Roadmap

| Phase | Theme | Outcome |
|---|---|---|
| **P0. Scaffolding** | Repo, CI, basic FastAPI + React skeleton, Alpaca adapter (paper, read-only). | App boots, account & positions visible. |
| **P1. Manual trading MVP** | Order ticket, working orders, positions, basic dashboard, TradingView chart embed, audit log, risk engine v1. | Trader can paper-trade fully from UI. |
| **P2. Strategy MVP** | Strategy engine, one reference strategy, backtest harness, paper deploy. | First strategy runs end-to-end on paper. |
| **P3. Agent MVP (B1+B2)** | Workbench MCP server, agent chat panel, suggestion cards, audit of agent actions. | Agent assists; human approves. |
| **P4. Polish & extend** | TradingView Pine alert webhooks, watchlist enhancements, hotkeys, kill switch, reconciliation, journal v2. | Production-feel daily-driver. |
| **P5. Live trading toggle** | Live credentials separation, live-mode UI, hard gates, recon. | Cautious move to live trading. |
| **P6. Agent autonomy (B3, gated)** | Per-strategy autonomous mode, hard budgets, extra audit, paper-only by default. | Optional autonomous paper trading. |
| **P7. (Stretch)** | Options, crypto, charting library upgrade, multi-account, hosted deployment. | — |

---

## 14. Open Questions — Need Jay's Input Before Implementation Plan

These are the decisions I'd like locked before we move to the detailed implementation plan:

1. **TradingView "local install"** — which of TV-1 / TV-2 / TV-3 / TV-4 (§6.1) is the intent? My recommendation: **TV-1 + TV-4**.
2. **TradingView MCP** — confirm: build a thin one ourselves, use an existing community one, or skip (recommendation: skip for MVP, route through Workbench MCP)?
3. **Claude Code agent mode for MVP** — confirm B1 + B2 only, with B3 deferred? Or do you want B3 from day one (paper only)?
4. **Asset classes for MVP** — US equities only, or equities + options? Crypto via Alpaca?
5. **Strategy authoring language** — Python only, or do you also want a "natural-language → strategy" UX in MVP?
6. **Single user or eventually multi-user?** This affects auth and DB shape now even if multi-user isn't built yet.
7. **Real-time data plan** — Alpaca's free data is IEX-only and delayed for some symbols. Are you willing to pay for the paid data plan, or do we design around free-tier limits in MVP?
8. **Hosting** — confirm fully local for MVP (no Cloudflare Tunnel exposure)?
9. **Naming** — keep "Trading Workbench" as working name, or do you have a product name in mind? (Anything related to GlobalComplyAI's brand family, or fully separate?)
10. **IP ownership** — Same DigiTech Edge IP-holding-company pattern as ComplyGen Lab, or different?

---

## 15. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Agent places unintended live orders | Low | Severe | Hard separation of paper/live credentials; B3 disabled by default; risk engine is unbypassable; live mode requires explicit toggle. |
| R2 | TradingView integration constrained by license / TOS | Medium | Medium | Start with the free widget (TV-1); evaluate Charting Library only if needed. |
| R3 | Alpaca outage during a strategy run | Medium | Medium | Strategy engine handles connection loss; halt strategies on broker disconnect; reconciliation on reconnect. |
| R4 | Free-tier market data inadequate for the trader's needs | Medium | Medium | Document the limitation; budget for paid plan if needed. |
| R5 | Local SQLite corruption | Low | Medium | Nightly snapshots; clear restore procedure. |
| R6 | Strategy bug causes runaway orders | Medium | High | Rate limit in risk engine; daily loss limit; auto-halt; kill switch. |
| R7 | Scope creep into multi-user / hosted | Medium | Medium | This document explicitly scopes MVP as single-user/local. |
| R8 | Regulatory drift if shared with others | Medium | High | Keep MVP strictly personal-use; revisit before any external user. |

---

## 16. What Comes Next

If this document is approved (or approved with edits), the next deliverable is the **Detailed Implementation Plan v0.1**, which will include:

- Concrete module structure and file layout for backend, frontend, and MCP server.
- API surface (REST endpoints + WebSocket event types).
- Database schema (tables, indices, retention).
- Workbench MCP tool catalog with exact inputs/outputs.
- Test plan (unit + integration + paper-trading smoke tests).
- Phase-by-phase task breakdown with rough effort estimates and dependencies.
- Initial reference strategy spec.

---

*End of v0.1 draft.*
