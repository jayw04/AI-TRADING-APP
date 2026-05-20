"""`get_system_status` tool.

Returns the backend's /healthz payload plus a tiny MCP-side envelope so the
caller can tell which MCP server instance answered and when. Also pokes the
internal /api/v1/internal/ping endpoint to prove the shared-secret auth
handshake is wired end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from workbench_mcp.client import WorkbenchBackendClient


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def get_system_status(
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Returns current Trading Workbench system status (DB, broker, WS, halt state).

    The `client` parameter is for tests; production callers leave it None and
    a fresh client is built from settings.
    """
    if client is not None:
        return await _run(client)

    async with WorkbenchBackendClient() as c:
        return await _run(c)


async def _run(client: WorkbenchBackendClient) -> dict[str, Any]:
    health = await client.get_healthz()

    internal_ok: bool
    internal_error: str | None = None
    try:
        ping = await client.get_internal_ping()
        internal_ok = bool(ping.get("pong"))
    except Exception as exc:
        internal_ok = False
        internal_error = type(exc).__name__

    payload: dict[str, Any] = {
        "mcp_server": "ok",
        "ts": _now_iso(),
        "backend": health,
        "internal_auth": "ok" if internal_ok else "failed",
    }
    if internal_error is not None:
        payload["internal_auth_error"] = internal_error
    return payload
