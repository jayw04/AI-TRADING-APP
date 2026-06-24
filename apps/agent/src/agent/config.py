"""Env-var-driven configuration for the agent service."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    backend_api_base: str
    workbench_mcp_base: str
    agent_api_key: str
    anthropic_api_key: str | None  # may be empty; the LLM wrapper handles absence

    @classmethod
    def from_env(cls, *, agent_api_key: str | None = None) -> AgentConfig:
        api_key = agent_api_key or os.environ.get("AGENT_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "AGENT_API_KEY env var required. Generate via Settings → "
                "Credentials → Agent API Key in the UI; export to this "
                "process's environment."
            )
        return cls(
            backend_api_base=os.environ.get(
                "BACKEND_API_BASE", "http://127.0.0.1:8000"
            ),
            workbench_mcp_base=os.environ.get(
                "WORKBENCH_MCP_BASE", "http://127.0.0.1:8766"
            ),
            agent_api_key=api_key,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        )
