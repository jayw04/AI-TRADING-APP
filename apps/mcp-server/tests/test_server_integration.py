"""Server registration integration test (P3 §2).

Builds the FastMCP server and asserts the full catalog is advertised
via ``list_tools()``. Catches the common bug where a tool is added to
the file system but forgotten in ``server.py``'s registration loop.
"""

from __future__ import annotations

from workbench_mcp.server import build_server

EXPECTED_TOOLS = {
    "get_system_status",
    "get_account_state",
    "list_positions",
    "list_open_orders",
    "list_recent_orders",
    "list_recent_fills",
    "list_strategies",
    "get_strategy_detail",
    "list_recent_signals",
    "list_recent_backtests",
    "get_quote",
    "get_bars",
    "get_indicators",
}


async def test_server_advertises_full_catalog() -> None:
    server = build_server()
    tools = await server.list_tools()
    advertised = {t.name for t in tools}
    missing = EXPECTED_TOOLS - advertised
    assert not missing, f"Missing tools: {sorted(missing)}"


async def test_no_mutating_tool_names_registered() -> None:
    """Same invariant as check_mcp_readonly.sh, exercised in-process."""
    server = build_server()
    tools = await server.list_tools()
    mutation_prefixes = (
        "submit_",
        "cancel_",
        "start_",
        "stop_",
        "create_",
        "update_",
        "delete_",
        "modify_",
        "set_",
        "write_",
        "post_",
        "put_",
        "patch_",
    )
    offenders = [
        t.name
        for t in tools
        if any(t.name.startswith(p) for p in mutation_prefixes)
    ]
    assert offenders == [], f"Mutating tools registered: {offenders}"
