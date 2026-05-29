"""`get_account_state` tool.

Returns the user's current Alpaca account state (cash, equity, buying power,
day P&L). Mirrors the GET /api/v1/account payload.
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient


async def get_account_state(
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Returns the user's current Alpaca account state.

    The `client` parameter is for tests; production callers leave it None.
    """
    if client is not None:
        return await client.get_account()
    async with WorkbenchBackendClient() as c:
        return await c.get_account()
