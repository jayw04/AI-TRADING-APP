"""Workbench-mcp SSE client (P6 §1b).

Per Decision 2 / ADR-0010 the agent reads workbench state **via workbench-mcp**,
never the DB directly. workbench-mcp is a FastMCP server speaking the MCP
protocol over SSE (NOT a REST `/tools/{name}` surface — see §1b validation
correction #2), so this is a real MCP client built on the `mcp` SDK
(`sse_client` + `ClientSession.call_tool`). The tool's return value arrives as a
JSON-serialized text content block, which we parse back to a dict.

Inbound SSE needs no bearer: workbench-mcp uses its own env `WORKBENCH_MCP_KEY`
to reach the backend (single-user MVP).

The live SSE handshake is Norton/Docker-deferred; unit tests inject a fake with
the same method surface, so this module's wire details are exercised only in the
live smoke.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client

logger = structlog.get_logger(__name__)


class WorkbenchMcpClient:
    def __init__(self, base_url: str) -> None:
        self._sse_url = base_url.rstrip("/") + "/sse"
        self._sse_cm: Any = None
        self._session_cm: Any = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> WorkbenchMcpClient:
        self._sse_cm = sse_client(self._sse_url)
        read, write = await self._sse_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(*exc)
            self._session_cm = None
            self._session = None
        if self._sse_cm is not None:
            await self._sse_cm.__aexit__(*exc)
            self._sse_cm = None

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("WorkbenchMcpClient used outside `async with`")
        result = await self._session.call_tool(name, arguments=arguments)
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                return json.loads(text)
        return {}

    # ----- typed helpers -----

    async def get_trading_profile(self) -> dict[str, Any]:
        return await self.call("workbench_trading_profile_get", {})

    async def get_strategy_history(self, strategy_id: int, limit: int = 30) -> dict[str, Any]:
        return await self.call(
            "workbench_strategy_history", {"strategy_id": strategy_id, "limit": limit}
        )

    async def get_recent_proposals(
        self, strategy_id: int, limit: int = 5
    ) -> list[dict[str, Any]]:
        result = await self.call(
            "workbench_recent_proposals_for_strategy",
            {"strategy_id": strategy_id, "limit": limit},
        )
        return result.get("items", []) if isinstance(result, dict) else result

    async def get_strategy_recent_orders(
        self, strategy_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        result = await self.call(
            "workbench_strategy_recent_orders",
            {"strategy_id": strategy_id, "limit": limit},
        )
        return result.get("items", []) if isinstance(result, dict) else result
