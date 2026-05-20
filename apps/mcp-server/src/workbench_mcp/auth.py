"""Outbound auth header for MCP -> backend calls."""

from workbench_mcp.config import get_settings


def auth_headers() -> dict[str, str]:
    """Headers carrying the shared secret for internal backend endpoints."""
    return {"X-Workbench-Auth": get_settings().backend_token}
