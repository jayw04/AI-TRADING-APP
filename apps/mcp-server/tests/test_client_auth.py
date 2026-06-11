"""The chart-MCP backend client must authenticate user-scoped reads.

The read endpoints (GET /api/v1/account, /positions, /orders, /strategies, ...)
require a bearer token the backend resolves to the owning user. The client sets
it as a default header from the reused WORKBENCH_MCP_KEY. Without it the tools
401 (the bug surfaced once Anthropic could dispatch tools over Streamable HTTP;
see ADR 0016). These tests pin the header on (key present) and off (key absent).
"""

from __future__ import annotations

import httpx
import pytest

from workbench_mcp import config
from workbench_mcp.client import WorkbenchBackendClient


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


async def test_client_sets_bearer_header_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKBENCH_MCP_KEY", "secret-key-123")
    async with WorkbenchBackendClient() as client:
        headers = client._require_client().headers
    assert headers.get("Authorization") == "Bearer secret-key-123"


async def test_client_omits_bearer_header_when_key_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKBENCH_MCP_KEY", "")
    async with WorkbenchBackendClient() as client:
        headers = client._require_client().headers
    assert "Authorization" not in headers


async def test_get_account_request_carries_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKBENCH_MCP_KEY", "k-abc")
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"equity": "1"})

    async with WorkbenchBackendClient() as client:
        # Re-wrap the live client with a mock transport, preserving the default
        # headers set in __aenter__, to assert the bearer is actually sent.
        client._client = httpx.AsyncClient(
            base_url=client._base_url,
            headers=client._require_client().headers,
            transport=httpx.MockTransport(handler),
        )
        await client.get_account()

    assert seen["auth"] == "Bearer k-abc"
