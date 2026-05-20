# workbench-mcp

Trading Workbench MCP (Model Context Protocol) server.

Exposes a curated set of tools that:
1. **Claude Code** in your IDE can call during interactive development sessions.
2. The **backend's runtime Agent Strategy engine** (P6+) attaches via the Anthropic SDK so the model can call them autonomously during a scheduled run.

The MCP server itself doesn't store trading state — it's a thin tool surface in front of the FastAPI backend, calling the backend over HTTP with a shared-secret header (`X-Workbench-Auth`). Backend is the single source of truth.

## Local dev

```bash
cd apps/mcp-server
python -m venv .venv
.venv\Scripts\activate              # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Run (requires backend up on $MCP_BACKEND_URL):
workbench-mcp
# or: python -m workbench_mcp.server
```

## Tools

| Name | What it does |
|---|---|
| `get_system_status` | Returns backend `/healthz` payload + internal `/api/v1/internal/ping` echo, augmented with `{mcp_server: "ok", ts: <iso>}`. |

## Env

See repo-root `.env.example` for `MCP_HOST`, `MCP_PORT`, `MCP_BACKEND_URL`, `MCP_BACKEND_TOKEN`.
