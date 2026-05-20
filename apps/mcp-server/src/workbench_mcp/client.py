"""HTTP client for the Workbench backend.

Thin wrapper over httpx so tools can call typed methods instead of building
URLs and headers themselves. One client instance per server process is fine
for P0 (no connection-pool tuning yet).
"""

from __future__ import annotations

from typing import Any

import httpx

from workbench_mcp.auth import auth_headers
from workbench_mcp.config import get_settings


class WorkbenchBackendClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.backend_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.request_timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> WorkbenchBackendClient:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("WorkbenchBackendClient used outside `async with` block")
        return self._client

    async def get_healthz(self) -> dict[str, Any]:
        resp = await self._require_client().get("/healthz")
        resp.raise_for_status()
        return resp.json()

    async def get_internal_ping(self) -> dict[str, Any]:
        resp = await self._require_client().get(
            "/api/v1/internal/ping", headers=auth_headers()
        )
        resp.raise_for_status()
        return resp.json()
