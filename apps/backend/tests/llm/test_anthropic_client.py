"""Tests for the Anthropic client wrapper's endpoint routing.

The MCP connector (``mcp_servers``) is beta-only: it must go through
``client.beta.messages.create`` with ``betas=[MCP_CONNECTOR_BETA]``. Passing
it to the stable ``client.messages.create`` raises ``TypeError: ... unexpected
keyword argument 'mcp_servers'`` — the bug the live P3 smoke walk caught
(2026-06-09). These tests pin the routing so it can't regress.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.anthropic_client import (
    MCP_CONNECTOR_BETA,
    create_message,
)

MCP_URL = "http://127.0.0.1:8765"
_MESSAGES = [{"role": "user", "content": "hi"}]


def _fake_response() -> MagicMock:
    raw = MagicMock()
    raw.usage = MagicMock(input_tokens=1, output_tokens=1)
    raw.stop_reason = "end_turn"
    raw.content = []
    return raw


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_fake_response())
    client.beta.messages.create = AsyncMock(return_value=_fake_response())
    return client


async def test_mcp_url_routes_through_beta_endpoint_with_flag() -> None:
    client = _fake_client()
    with patch(
        "app.llm.anthropic_client.get_anthropic_client", return_value=client
    ):
        await create_message(
            api_key="k",
            model="m",
            system="s",
            messages=_MESSAGES,
            mcp_server_url=MCP_URL,
        )

    # Beta endpoint used, stable endpoint untouched.
    client.beta.messages.create.assert_awaited_once()
    client.messages.create.assert_not_awaited()

    _, kwargs = client.beta.messages.create.call_args
    assert kwargs["betas"] == [MCP_CONNECTOR_BETA]
    assert kwargs["mcp_servers"][0]["url"] == MCP_URL


async def test_no_mcp_url_routes_through_stable_endpoint() -> None:
    client = _fake_client()
    with patch(
        "app.llm.anthropic_client.get_anthropic_client", return_value=client
    ):
        await create_message(
            api_key="k",
            model="m",
            system="s",
            messages=_MESSAGES,
            mcp_server_url=None,
        )

    # Stable endpoint used; no beta flag, no mcp_servers kwarg.
    client.messages.create.assert_awaited_once()
    client.beta.messages.create.assert_not_awaited()

    _, kwargs = client.messages.create.call_args
    assert "mcp_servers" not in kwargs
    assert "betas" not in kwargs
