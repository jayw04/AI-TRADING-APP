"""Unit tests for agent.server — the FastAPI control-plane.

generate_proposal is monkeypatched (the full flow is covered in
test_proposal_generation); here we only assert the endpoint's success/error
mapping. AGENT_API_KEY is set so AgentConfig.from_env() succeeds.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import server as server_mod
from agent.proposal_generation import ProposalGenerationResult


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "agt-key")


def test_healthz():
    client = TestClient(server_mod.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_generate_proposal_returns_reviewing_on_success(monkeypatch):
    async def fake_generate(config, proposal_id, **kwargs):
        return ProposalGenerationResult(
            state="REVIEWING",
            confidence="HIGH",
            proposal_payload={},
            evidence_bundle={},
            llm_usage={},
        )

    monkeypatch.setattr(server_mod, "generate_proposal", fake_generate)
    client = TestClient(server_mod.app)
    r = client.post("/generate-proposal", json={"proposal_id": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "REVIEWING"
    assert body["confidence"] == "HIGH"
    assert body["error"] is None


def test_generate_proposal_returns_error_on_exception(monkeypatch):
    async def boom(config, proposal_id, **kwargs):
        raise RuntimeError("budget exceeded")

    monkeypatch.setattr(server_mod, "generate_proposal", boom)
    client = TestClient(server_mod.app)
    r = client.post("/generate-proposal", json={"proposal_id": 7})
    assert r.status_code == 200  # graceful failure, not HTTP error
    body = r.json()
    assert body["state"] == "DRAFT"
    assert "budget exceeded" in body["error"]
