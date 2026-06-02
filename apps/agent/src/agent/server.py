"""Agent control-plane HTTP server (P6 §1b).

ONE endpoint: POST /generate-proposal {proposal_id}, invoked by the backend's
POST /api/v1/strategies/{id}/propose. Per Decision 2 this is the trigger surface
only — the data plane (MCP reads, backend writes) lives in proposal_generation.
Per Decision 1 each request is stateless single-shot.

On any failure (budget rejected / LLM failed / parse error / MCP unreachable) we
return a graceful error response (state stays DRAFT); the backend then deletes
the orphaned DRAFT row.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.proposal_generation import generate_proposal

logger = structlog.get_logger(__name__)

app = FastAPI(title="agent-control-plane", version="0.1.0")


class GenerateProposalRequest(BaseModel):
    proposal_id: int


class GenerateProposalResponse(BaseModel):
    proposal_id: int
    state: str  # "REVIEWING" on success, "DRAFT" on failure
    confidence: str | None = None
    error: str | None = None


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/generate-proposal", response_model=GenerateProposalResponse)
async def generate_proposal_endpoint(
    req: GenerateProposalRequest,
) -> GenerateProposalResponse:
    config = AgentConfig.from_env()
    try:
        result = await generate_proposal(config, req.proposal_id)
        return GenerateProposalResponse(
            proposal_id=req.proposal_id,
            state=result.state,
            confidence=result.confidence,
            error=None,
        )
    except Exception as exc:
        logger.exception("proposal_generation_failed", proposal_id=req.proposal_id)
        return GenerateProposalResponse(
            proposal_id=req.proposal_id,
            state="DRAFT",
            confidence=None,
            error=str(exc)[:500],
        )
