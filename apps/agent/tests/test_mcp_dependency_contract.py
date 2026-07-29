"""Dependency contract for the `mcp` package, agent edition.

Regression guard for the 2026-07-28 outage. `mcp 2.0.0` reorganised the package and removed
`mcp.server.fastmcp`; every Python FULL job for `mcp-server` and `mcp-workbench` failed at
collection and main was red for ~21 hours with no PR able to merge. This project stayed green
only because it consumes the **client** surface, not FastMCP — luck, not protection. #539 pinned
the other two projects; this one was left on `mcp>=1.0`, one upstream release from the same
failure.

Aligned to what `agent.mcp_client` actually imports (`ClientSession`, `sse_client`) — deliberately
NOT FastMCP, which this project does not use. If these fail, the resolved `mcp` no longer provides
the client API the agent is written against: restore the pin, or port the code. Do not delete
the test to make CI green.
"""

from __future__ import annotations

from importlib.metadata import version

# The exact version verified green in CI run 30347327373 (2026-07-28T09:36Z), pinned in
# pyproject.toml. Keep identical to apps/mcp-server and apps/mcp-workbench.
PINNED_MCP_VERSION = "1.28.1"


def test_resolved_mcp_version_matches_the_pin() -> None:
    """The installed version must be exactly what the pin declares.

    A mismatch means the environment was built from something other than this pyproject.toml —
    a stale venv, a warm cache, or an overriding constraint.
    """
    assert version("mcp") == PINNED_MCP_VERSION, (
        f"resolved mcp=={version('mcp')} but pyproject pins {PINNED_MCP_VERSION}; "
        "rebuild the environment from pyproject.toml"
    )


def test_client_session_imports_from_the_location_the_agent_uses() -> None:
    """`agent/mcp_client.py` does `from mcp import ClientSession` — top-level, not a submodule."""
    from mcp import ClientSession

    assert ClientSession is not None


def test_sse_client_symbol_imports() -> None:
    """`agent/mcp_client.py` does `from mcp.client.sse import sse_client`."""
    from mcp.client.sse import sse_client

    assert callable(sse_client)


def test_agent_mcp_client_module_imports_cleanly() -> None:
    """End-to-end: the module carrying those imports must load."""
    from agent.mcp_client import WorkbenchMcpClient

    assert WorkbenchMcpClient is not None
