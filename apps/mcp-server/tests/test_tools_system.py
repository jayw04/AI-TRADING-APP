"""Unit tests for get_system_status.

Use a fake backend client so we don't need a live FastAPI process. The real
end-to-end smoke test (MCP server + backend in two terminals) is documented
in the README and run manually in P0.
"""

from __future__ import annotations

from typing import Any

import pytest

from workbench_mcp.tools.system import get_system_status


class FakeBackendClient:
    def __init__(
        self,
        healthz: dict[str, Any],
        ping: dict[str, Any] | None = None,
        ping_error: Exception | None = None,
    ) -> None:
        self._healthz = healthz
        self._ping = ping or {"pong": True}
        self._ping_error = ping_error

    async def __aenter__(self) -> "FakeBackendClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get_healthz(self) -> dict[str, Any]:
        return self._healthz

    async def get_internal_ping(self) -> dict[str, Any]:
        if self._ping_error is not None:
            raise self._ping_error
        return self._ping


async def test_get_system_status_happy_path() -> None:
    client = FakeBackendClient(
        healthz={"status": "ok", "db": "ok", "version": "0.0.1"},
    )
    result = await get_system_status(client=client)

    assert result["mcp_server"] == "ok"
    assert "ts" in result
    assert result["backend"] == {"status": "ok", "db": "ok", "version": "0.0.1"}
    assert result["internal_auth"] == "ok"
    assert "internal_auth_error" not in result


async def test_get_system_status_marks_internal_auth_failed() -> None:
    import httpx

    client = FakeBackendClient(
        healthz={"status": "ok", "db": "ok", "version": "0.0.1"},
        ping_error=httpx.HTTPStatusError(
            "401",
            request=httpx.Request("GET", "http://test/api/v1/internal/ping"),
            response=httpx.Response(401),
        ),
    )
    result = await get_system_status(client=client)

    assert result["mcp_server"] == "ok"
    assert result["backend"]["status"] == "ok"
    assert result["internal_auth"] == "failed"
    assert result["internal_auth_error"] == "HTTPStatusError"


@pytest.mark.parametrize("db_state", ["ok", "down"])
async def test_get_system_status_passes_through_db_state(db_state: str) -> None:
    client = FakeBackendClient(
        healthz={"status": "ok" if db_state == "ok" else "degraded",
                 "db": db_state, "version": "0.0.1"},
    )
    result = await get_system_status(client=client)
    assert result["backend"]["db"] == db_state
