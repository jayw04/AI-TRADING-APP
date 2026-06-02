"""workbench-mcp — read-only MCP server exposing Trading Workbench state.

Separate from P3's chart-data ``apps/mcp-server/`` (one MCP server per concern).
SSE transport on 127.0.0.1:8766; authenticates to the backend with a per-user
WORKBENCH_MCP_KEY bearer token. Read-only — the ``check_workbench_mcp_readonly``
CI invariant enforces that mutating tools stay out until P6.
"""

__version__ = "0.0.1"
