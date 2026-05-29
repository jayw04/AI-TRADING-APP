# Workbench MCP Server — Tool Catalog

The Workbench MCP server exposes a read-only tool catalog usable by:

- The in-app agent (P3, via Anthropic's MCP integration — wired in Session 3).
- [Claude Desktop](https://www.anthropic.com/news/claude-desktop) (via `claude_desktop_config.json`).
- [Claude Code](https://github.com/anthropics/claude-code).
- Any MCP client speaking the standard protocol.

Server URL (local default): `http://127.0.0.1:8765` over SSE.

## Why read-only

P3 ships only tools that *read* state. Mutating tools (submit an order,
start a strategy, cancel an order, etc.) require the autonomous-agent
design that lands in P6. CI enforces this via
[`apps/backend/scripts/check_mcp_readonly.sh`](../../apps/backend/scripts/check_mcp_readonly.sh):
any tool whose declared `name=` matches a mutation verb
(`submit|cancel|start|stop|create|update|delete|modify|set|write|post|put|patch`)
fails the build.

## Catalog

Thirteen tools total. Each is implemented in
`apps/mcp-server/src/workbench_mcp/tools/`; the `name=` strings in
`server.py` are the values agents call. All take their inputs as
JSON-typed kwargs and return a `dict`.

### `get_system_status` (P0)

System health: backend `/healthz`, internal-auth handshake, MCP server timestamp.

- **Inputs:** none.
- **Output:** `{mcp_server, ts, backend: {...}, internal_auth, [internal_auth_error]}`.

### `get_account_state`

The user's current Alpaca account state.

- **Inputs:** none.
- **Output:** `{cash, equity, buying_power, day_change, day_change_pct, status, mode}`.
- **Backend:** `GET /api/v1/account`.

### `list_positions`

Open positions. Capped at 100.

- **Inputs:** none.
- **Output:** `{positions: [{symbol, qty, avg_entry_price, market_value, unrealized_pl, unrealized_plpc, side}], count}`.
- **Backend:** `GET /api/v1/positions`.

### `list_open_orders`

Open (non-terminal) orders. Capped at 100.

- **Inputs:** `symbol?` (string).
- **Output:** `{orders: [...], count}`.
- **Backend:** `GET /api/v1/orders?status=open`.

### `list_recent_orders`

Recent orders including terminal ones (filled / canceled / rejected).

- **Inputs:** `limit?` (int, default 50, max 100), `symbol?`.
- **Output:** `{orders: [...], count}`.
- **Backend:** `GET /api/v1/orders?limit=...`.

### `list_recent_fills`

Recent fills flattened from terminal orders. P3 doesn't add a separate
`/fills` endpoint; the tool pulls history orders (which eager-load
fills) and flattens.

- **Inputs:** `limit?` (int, default 50, max 100), `symbol?`.
- **Output:** `{fills: [{order_id, symbol, side, qty, price, filled_at}], count}`.
- **Backend:** `GET /api/v1/orders?status=history&limit=...`.

### `list_strategies`

All strategies for the user, optionally filtered by status.

- **Inputs:** `status?` (string).
- **Output:** `{strategies: [{id, name, version, type, status, symbols, schedule}], count}`.
- **Backend:** `GET /api/v1/strategies`.

### `get_strategy_detail`

One strategy + its most-recent run + the count of today's signals.

- **Inputs:** `strategy_id` (int, required).
- **Output:** `{strategy: {...}, last_run: {...} | null, signals_today: int}`.
- **Backend:** fans out to
  `GET /api/v1/strategies/{id}` +
  `GET /api/v1/strategies/{id}/runs?limit=1` +
  `GET /api/v1/strategies/{id}/signals?limit=200`
  (the 200-signal lookback bounds today's count without a dedicated aggregate).

### `list_recent_signals`

Recent signals across the user's strategies.

- **Inputs:** `limit?` (int, default 100, max 200), `strategy_id?`, `symbol?`, `type?`, `since?` (ISO datetime).
- **Output:** `{signals: [{id, strategy_id, symbol, type, payload, received_at}], count}`.
- **Backend:** `GET /api/v1/signals?...`.

### `list_recent_backtests`

Recent backtests, summarized to the four headline metrics.

- **Inputs:** `strategy_id?` (int), `limit?` (int, default 20, max 50).
- **Output:** `{backtests: [{id, strategy_id, label, range_start, range_end, metrics_summary: {trade_count, total_return, sharpe_ratio, max_drawdown}, created_at}], count}`.
- **Backend:** with `strategy_id`, `GET /api/v1/strategies/{id}/backtests`; without, fans out across the first 10 strategies. A cross-strategy `/api/v1/backtests` endpoint is P4 polish.

### `get_quote`

Last quote for one symbol.

- **Inputs:** `symbol` (string, required).
- **Output:** `{symbol, bid, ask, last, bid_size?, ask_size?, ts}`.
- **Backend:** `GET /api/v1/quotes/{symbol}`.

### `get_bars`

Historical OHLCV bars. **Always capped at 200 bars** regardless of the
requested `limit` — the agent's context window is precious, and
`get_indicators` exists for aggregated views.

- **Inputs:** `symbol` (required), `timeframe?` (default `"1Min"`), `limit?` (default 50, max 200).
- **Output:** `{symbol, timeframe, bars: [{t, o, h, l, c, v}], count}`.
- **Backend:** `GET /api/v1/bars/{symbol}?timeframe=...&limit=...`.

### `get_indicators`

Latest indicator values + a short sparkline per indicator.

- **Inputs:** `symbol` (required), `names?` (comma-separated str), `timeframe?` (default `"1Min"`).
- **Output:** mirrors `GET /api/v1/indicators/{symbol}`.
- **Backend:** `GET /api/v1/indicators/{symbol}?names=...&timeframe=...`.

## Connecting from Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "workbench": {
      "command": "uvx",
      "args": ["--from", "<path to apps/mcp-server>", "workbench-mcp"]
    }
  }
}
```

If you instead run the MCP server as a long-lived SSE process (e.g. via
`./scripts/dev.sh`), Claude Desktop's HTTP-SSE transport can connect at
`http://127.0.0.1:8765/sse`. Restart Claude Desktop; the tools should
appear in the tool picker.

## Connecting from Claude Code

`claude mcp add workbench --transport sse http://127.0.0.1:8765/sse`

Then any Claude Code session has the same 13 tools available. Same data,
same view, no extra wiring.
