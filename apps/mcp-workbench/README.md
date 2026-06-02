# workbench-mcp

Read-only MCP server exposing **Trading Workbench state** to Claude Code / Claude
Desktop (P5.5 §3). Separate from the chart-data `apps/mcp-server/` (one MCP
server per concern).

- **Transport:** SSE on `127.0.0.1:8766` (the chart MCP is on 8765).
- **Auth to backend:** per-user `WORKBENCH_MCP_KEY` bearer token. The backend's
  `get_current_user` resolves it to the owning user, so per-user endpoints
  (trading profile, morning brief, accounts) are correctly scoped. Generate the
  key via **Settings → Credentials** in the UI (`CredentialKind.WORKBENCH_MCP_KEY`).
- **Read-only by CI invariant:** `apps/backend/scripts/check_workbench_mcp_readonly.sh`
  enforces GET-only, with one allowlisted idempotent POST
  (`/api/v1/morning-brief/generate`). Mutating tools are P6 (agent autonomy).

## Tools (12)

`workbench_status`, `workbench_morning_brief_today`,
`workbench_morning_brief_generate`, `workbench_trading_profile_get`,
`workbench_list_accounts`, `workbench_list_strategies`,
`workbench_list_positions`, `workbench_list_orders`,
`workbench_account_risk_state`, `workbench_strategy_activation_status`,
`workbench_recent_briefs`, `workbench_audit_recent`.

Each is a thin adapter over one backend HTTP endpoint — no business logic, no DB
access. See `CLAUDE.md` (this directory) for the agent decision tree.

## Run

```bash
export WORKBENCH_MCP_KEY="<key from Settings → Credentials>"
export WORKBENCH_API_BASE="http://127.0.0.1:8000"   # default
mcp-workbench            # SSE on 127.0.0.1:8766
```

Or via Docker: `docker compose up -d workbench-mcp` (the compose service injects
`WORKBENCH_MCP_KEY` from `.env`).

### Claude Code / Desktop config (SSE)

```json
{
  "mcpServers": {
    "workbench-state": { "url": "http://127.0.0.1:8766/sse" }
  }
}
```

## Dev

```bash
pip install -e ".[dev]"
ruff check . && mypy src && pytest -q
```

Layout: `src/mcp_workbench/{config,client,server}.py`. Tools are module-level
functions in `server.py` (unit-tested with `pytest-httpx` against a mocked
backend); `build_server()` registers them on the FastMCP instance.
