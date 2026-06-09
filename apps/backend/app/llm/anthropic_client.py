"""Thin wrapper around the Anthropic AsyncAnthropic client.

This module is the *only* location in the backend permitted to import the
Anthropic SDK, alongside the rest of ``app/llm/``. The CI invariant
``check_no_llm_in_order_path.sh`` enforces this — see
``docs/adr/0006-llm-not-in-order-path.md`` for the architectural reasoning.

Design notes:

* **Lazy construction.** ``AsyncAnthropic`` is not built at import time. A
  new contributor with an empty ``ANTHROPIC_API_KEY`` must be able to
  import the module without an exception; the runtime catches the empty
  key at ``start_session`` and refuses with a clear message rather than
  crashing on the first API call.
* **MCP integration.** Anthropic's API handles MCP tool dispatch
  server-side. We pass an ``mcp_servers`` block pointing at the workbench
  MCP server URL; the API calls the MCP server, threads the result back
  into the conversation, and returns. The "tool-use loop" in
  ``runtime.py`` is for orchestrating multi-turn exchanges (when the
  model needs an extra turn to summarize), not for dispatching individual
  tools locally.
* **Streaming surface is present but unused in P3.** ``stream_message``
  is exposed for Session 4/5's UI work to wire up later. P3's runtime
  uses ``create_message`` (non-streaming) — combining streaming with MCP
  tool use is genuinely complex and the UX can render full messages with
  acceptable latency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AnthropicClientError(Exception):
    """Base error for the agent-side Anthropic wrapper."""


class AnthropicClientNotConfigured(AnthropicClientError):
    """Raised when the runtime tries to call Anthropic without an API key."""


_client_singleton: Any | None = None


def get_anthropic_client(api_key: str | None) -> Any:
    """Return the singleton ``AsyncAnthropic`` client, constructing lazily.

    Raises :class:`AnthropicClientNotConfigured` if ``api_key`` is empty.
    """
    global _client_singleton
    if not api_key:
        raise AnthropicClientNotConfigured(
            "ANTHROPIC_API_KEY is not set. Set it in .env to enable the agent."
        )
    if _client_singleton is None:
        from anthropic import AsyncAnthropic

        _client_singleton = AsyncAnthropic(api_key=api_key)
        logger.info("anthropic_client_constructed")
    return _client_singleton


def reset_anthropic_client_for_tests() -> None:
    """Drop the cached singleton so tests can construct a fresh client.

    Production callers should never need this.
    """
    global _client_singleton
    _client_singleton = None


class AnthropicCall:
    """Wraps one API response. Exposes usage and the assistant message's
    content blocks normalized to plain dicts (ready for storage in
    ``agent_messages.content_json``).

    Defensive ``getattr`` reads so the wrapper survives SDK shape shifts
    without crashing — a missing ``usage`` becomes ``0`` rather than an
    ``AttributeError``.
    """

    def __init__(self, raw_response: Any) -> None:
        self.raw = raw_response

    @property
    def input_tokens(self) -> int:
        usage = getattr(self.raw, "usage", None)
        return int(getattr(usage, "input_tokens", 0)) if usage is not None else 0

    @property
    def output_tokens(self) -> int:
        usage = getattr(self.raw, "usage", None)
        return int(getattr(usage, "output_tokens", 0)) if usage is not None else 0

    @property
    def stop_reason(self) -> str:
        return str(getattr(self.raw, "stop_reason", "") or "")

    @property
    def content_blocks(self) -> list[dict[str, Any]]:
        """Normalize the assistant message's content into plain dicts."""
        out: list[dict[str, Any]] = []
        for block in getattr(self.raw, "content", None) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                out.append({"type": "text", "text": getattr(block, "text", "")})
            elif block_type == "tool_use":
                out.append(
                    {
                        "type": "tool_use",
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}),
                    }
                )
            elif block_type == "tool_result":
                # Tool results in an assistant response are unusual (they
                # normally arrive on the user side after the tool runs),
                # but capture defensively.
                out.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": getattr(block, "tool_use_id", ""),
                        "content": getattr(block, "content", ""),
                    }
                )
            else:
                out.append({"type": block_type or "unknown", "raw": str(block)})
        return out


# The MCP connector (``mcp_servers``) is a *beta* feature: it is only accepted
# by ``client.beta.messages.create`` / ``.stream`` with this beta flag, never by
# the stable ``client.messages.create``. Passing ``mcp_servers`` to the stable
# endpoint raises ``TypeError: ... unexpected keyword argument 'mcp_servers'``.
# Verified against anthropic SDK 0.107.1 (the SDK also exposes the newer
# ``mcp-client-2025-11-20``; this one matches the ``{type:url}`` connector shape
# we build below).
MCP_CONNECTOR_BETA = "mcp-client-2025-04-04"


def _mcp_servers_kwarg(mcp_server_url: str | None) -> dict[str, Any]:
    """Build the ``mcp_servers`` kwarg block, or empty dict if no URL.

    When this returns a non-empty dict the call MUST go through the
    ``client.beta.messages.*`` surface with ``betas=[MCP_CONNECTOR_BETA]``
    (see ``create_message`` / ``stream_message``); the stable endpoint
    rejects ``mcp_servers``. Centralized here so one update fixes every
    call site.
    """
    if not mcp_server_url:
        return {}
    return {
        "mcp_servers": [
            {
                "type": "url",
                "url": mcp_server_url,
                "name": "workbench",
            }
        ]
    }


async def create_message(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    mcp_server_url: str | None = None,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | None = None,
) -> AnthropicCall:
    """One non-streaming Anthropic API call. Returns an :class:`AnthropicCall`.

    ``tools`` + ``tool_choice`` (P7 §2) enable structured output via tool-use:
    pass a tool schema and ``{"type": "tool", "name": ...}`` to force the model
    to return a parseable ``tool_use`` block (see ``AnthropicCall.content_blocks``).
    Both default to ``None`` and are only sent when provided, so existing callers
    are unaffected.
    """
    client = get_anthropic_client(api_key)
    mcp_kwargs = _mcp_servers_kwarg(mcp_server_url)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        **mcp_kwargs,
    }
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    if mcp_kwargs:
        # ``mcp_servers`` is beta-only — must go through the beta surface.
        response = await client.beta.messages.create(
            betas=[MCP_CONNECTOR_BETA], **kwargs
        )
    else:
        response = await client.messages.create(**kwargs)
    return AnthropicCall(raw_response=response)


async def stream_message(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    mcp_server_url: str | None = None,
    max_tokens: int = 4096,
) -> AsyncIterator[dict[str, Any]]:
    """Stream events from one Anthropic API call.

    Yields ``{type, raw}`` dicts where ``raw`` is the SDK event object —
    intentionally loose so the consumer can decide what to surface. P3
    doesn't wire this up (see module docstring); reserved for Session 4/5.
    """
    client = get_anthropic_client(api_key)
    mcp_kwargs = _mcp_servers_kwarg(mcp_server_url)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        **mcp_kwargs,
    }
    # ``mcp_servers`` is beta-only — route streaming through the beta surface too.
    stream_ctx = (
        client.beta.messages.stream(betas=[MCP_CONNECTOR_BETA], **kwargs)
        if mcp_kwargs
        else client.messages.stream(**kwargs)
    )
    async with stream_ctx as stream:
        async for event in stream:
            yield {"type": getattr(event, "type", "unknown"), "raw": event}
