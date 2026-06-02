"""HTTP client for the Workbench backend.

Unlike P3's chart-MCP client (which sent an ``X-Workbench-Auth`` shared secret
only on the internal endpoint), this client attaches the per-user
``Authorization: Bearer <WORKBENCH_MCP_KEY>`` on EVERY call — the backend's
``get_current_user`` resolves it to the owning user, so the per-user endpoints
(trading-profile, morning-brief, accounts) are correctly scoped. ``/healthz`` is
unauthenticated; the bearer header is harmless there.
"""

from __future__ import annotations

from typing import Any

import httpx

from mcp_workbench.config import get_settings


class WorkbenchClient:
    def __init__(
        self,
        base_url: str | None = None,
        mcp_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        s = get_settings()
        self._base_url = (base_url or s.backend_url).rstrip("/")
        self._key = mcp_key if mcp_key is not None else s.mcp_key
        self._timeout = timeout if timeout is not None else s.timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> WorkbenchClient:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        self._client = httpx.AsyncClient(
            base_url=self._base_url, headers=headers, timeout=self._timeout
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("WorkbenchClient used outside `async with` block")
        return self._client

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._require().get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._require().post(path, json=json or {})
        resp.raise_for_status()
        return resp.json()
