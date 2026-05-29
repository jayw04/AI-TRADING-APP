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

    # ---------------- read-only endpoints (P3 §2) ----------------

    async def get_account(self) -> dict[str, Any]:
        resp = await self._require_client().get("/api/v1/account")
        resp.raise_for_status()
        return resp.json()

    async def get_positions(self) -> dict[str, Any]:
        resp = await self._require_client().get("/api/v1/positions")
        resp.raise_for_status()
        return resp.json()

    async def get_orders(
        self,
        *,
        status: str | None = None,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        if symbol is not None:
            params["symbol"] = symbol
        if limit is not None:
            params["limit"] = limit
        resp = await self._require_client().get("/api/v1/orders", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_strategies(
        self,
        *,
        status: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        resp = await self._require_client().get(
            "/api/v1/strategies", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_strategy(self, strategy_id: int) -> dict[str, Any]:
        resp = await self._require_client().get(
            f"/api/v1/strategies/{strategy_id}"
        )
        resp.raise_for_status()
        return resp.json()

    async def get_strategy_runs(
        self,
        strategy_id: int,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        resp = await self._require_client().get(
            f"/api/v1/strategies/{strategy_id}/runs", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_strategy_signals(
        self,
        strategy_id: int,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        resp = await self._require_client().get(
            f"/api/v1/strategies/{strategy_id}/signals", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_strategy_backtests(
        self,
        strategy_id: int,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        resp = await self._require_client().get(
            f"/api/v1/strategies/{strategy_id}/backtests", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_signals(
        self,
        *,
        limit: int | None = None,
        strategy_id: int | None = None,
        symbol: str | None = None,
        type_: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if strategy_id is not None:
            params["strategy_id"] = strategy_id
        if symbol is not None:
            params["symbol"] = symbol
        if type_ is not None:
            params["type"] = type_
        if since is not None:
            params["since"] = since
        resp = await self._require_client().get(
            "/api/v1/signals", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        resp = await self._require_client().get(f"/api/v1/quotes/{symbol}")
        resp.raise_for_status()
        return resp.json()

    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if timeframe is not None:
            params["timeframe"] = timeframe
        if limit is not None:
            params["limit"] = limit
        resp = await self._require_client().get(
            f"/api/v1/bars/{symbol}", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_indicators(
        self,
        symbol: str,
        *,
        names: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if names is not None:
            params["names"] = names
        if timeframe is not None:
            params["timeframe"] = timeframe
        resp = await self._require_client().get(
            f"/api/v1/indicators/{symbol}", params=params
        )
        resp.raise_for_status()
        return resp.json()
