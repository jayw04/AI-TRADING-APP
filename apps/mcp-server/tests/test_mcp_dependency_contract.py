"""Dependency contract for the `mcp` package.

Regression guard for the 2026-07-28 outage: `mcp 2.0.0` moved/removed
`mcp.server.fastmcp`, which `workbench_mcp.server` imports. Because the dependency was
declared `mcp>=1.0` with no upper bound, a fresh CI install resolved the major bump and
EVERY Python FULL job failed at collection — main was red and no PR could merge.

These tests give a fast, explicit signal at the dependency layer instead of an opaque
collection error inside an unrelated integration test. If they fail, the resolved `mcp`
version no longer provides the API this project is written against: either restore the
pin or port the code to the new import surface. Do not "fix" this by deleting the test.
"""

from __future__ import annotations

from importlib.metadata import version

import pytest

# The exact version verified green in CI run 30347327373 (2026-07-28T09:36Z) and pinned in
# pyproject.toml. Keep in sync with apps/mcp-workbench.
PINNED_MCP_VERSION = "1.28.1"


def test_fastmcp_import_surface_is_available() -> None:
    """The precise import `workbench_mcp.server` depends on must resolve."""
    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None


def test_resolved_mcp_version_matches_the_pin() -> None:
    """The installed version must be the one the pin declares.

    A mismatch means the environment was built from something other than this
    pyproject.toml — a stale venv, a warm cache, or an overriding constraint.
    """
    assert version("mcp") == PINNED_MCP_VERSION, (
        f"resolved mcp=={version('mcp')} but pyproject pins {PINNED_MCP_VERSION}; "
        "rebuild the environment from pyproject.toml"
    )


def test_server_module_imports_with_the_pinned_dependency() -> None:
    """End-to-end: the module that broke must import cleanly."""
    pytest.importorskip("workbench_mcp.server")
    from workbench_mcp.server import build_server

    assert callable(build_server)
