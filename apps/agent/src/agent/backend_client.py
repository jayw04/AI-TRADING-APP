"""Backend HTTP client — proposal reads/writes + the budget check (P6 §1b).

Per Decision 2: the agent writes via the backend HTTP API (which carries audit
+ risk gates). Authenticated with the agent's bearer token (AGENT_API_KEY).
"""
from __future__ import annotations

from typing import Any

import httpx


class BackendClient:
    """Async context manager over an httpx client bearer-authed as the agent."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BackendClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    @property
    def http(self) -> httpx.AsyncClient:
        """The underlying bearer-authed client — reused for the budget check
        (agent.llm_call.call_with_budget calls GET /api/v1/agent/cost-envelope)."""
        if self._client is None:
            raise RuntimeError("BackendClient used outside `async with`")
        return self._client

    async def get_proposal(self, proposal_id: int) -> dict[str, Any]:
        r = await self.http.get(f"/api/v1/proposals/{proposal_id}")
        r.raise_for_status()
        return r.json()

    async def update_proposal_to_reviewing(
        self,
        proposal_id: int,
        *,
        proposal_payload: dict[str, Any],
        evidence_bundle: dict[str, Any],
        llm_usage: dict[str, Any],
    ) -> dict[str, Any]:
        """Transition DRAFT → REVIEWING with the populated payload + evidence +
        cost telemetry (the backend folds llm_usage into the audit payload)."""
        r = await self.http.patch(
            f"/api/v1/proposals/{proposal_id}",
            json={
                "target_state": "REVIEWING",
                "proposal_payload": proposal_payload,
                "evidence_bundle": evidence_bundle,
                "llm_usage": llm_usage,
            },
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
