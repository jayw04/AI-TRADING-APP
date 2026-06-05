"""LLM-driven live trading opt-in endpoints (P6b §5, ADR 0006 v2 §5).

POST /strategies/{id}/llm-opt-in  — initiate (typed-ack + TOTP; eligibility-gated).
POST /strategies/{id}/llm-opt-out — frictionless opt-out.
GET  /strategies/{id}/llm-opt-in  — status + eligibility + budget headroom (the
     opt-in dialog + the MCP tool read this).

A fresh module (off the P2 branch-coverage gate), mirroring §4.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.llm_opt_in import OPT_IN_PENDING, LLMOptIn
from app.db.models.strategy import Strategy
from app.db.session import get_session
from app.services.eval_harness.eligibility import check_eligibility, verdict_to_dict
from app.services.eval_harness.service import find_active_harness
from app.services.llm_live_gate.gate import (
    LLM_OPT_IN_COOLDOWN_DAYS,
    _user_live_spend_today_cents,
)
from app.services.llm_live_gate.service import (
    find_non_terminal_opt_in,
    initiate_opt_in,
    opt_out,
)
from app.utils.time import ensure_aware

router = APIRouter(tags=["llm-opt-in"])

_OPT_IN_ERROR_CODES = {
    "strategy_not_found": 404,
    "parent_not_live": 409,
    "no_eligible_harness": 409,
    "opt_in_already_active": 409,
    "acknowledgment_mismatch": 400,
    "totp_invalid": 400,
}


class OptInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledgment_text: str = Field(min_length=1, max_length=256)
    totp_code: str = Field(min_length=6, max_length=8)


@router.post("/strategies/{strategy_id}/llm-opt-in", response_model=dict)
async def llm_opt_in(
    strategy_id: int,
    body: OptInRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Opt in to LLM-driven LIVE trading for a strategy (ADR 0006 v2 §5). Starts
    the 7-day cooldown; the LLM gate switches on when it elapses."""
    try:
        opt_in = await initiate_opt_in(
            session, strategy_id=strategy_id, user_id=current_user.id,
            acknowledgment_text=body.acknowledgment_text, totp_code=body.totp_code,
        )
    except ValueError as exc:
        code = _OPT_IN_ERROR_CODES.get(str(exc), 400)
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    activates_at = opt_in.initiated_at + timedelta(days=LLM_OPT_IN_COOLDOWN_DAYS)
    return {
        "status": opt_in.state,
        "opt_in_id": opt_in.id,
        "initiated_at": opt_in.initiated_at.isoformat(),
        "activates_at": activates_at.isoformat(),
    }


@router.post("/strategies/{strategy_id}/llm-opt-out", response_model=dict)
async def llm_opt_out(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Frictionless opt-out — the deterministic strategy resumes live duty."""
    engine = getattr(request.app.state, "strategy_engine", None)
    try:
        await opt_out(
            session, strategy_id=strategy_id, user_id=current_user.id, engine=engine
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "opted_out", "strategy_id": strategy_id}


@router.get("/strategies/{strategy_id}/llm-opt-in", response_model=dict)
async def get_llm_opt_in(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The opt-in status + the §4 eligibility verdict + the per-user budget
    headroom. Read-only — the opt-in dialog and the MCP tool consume it."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    harness = await find_active_harness(session, strategy_id)
    eligibility = (
        verdict_to_dict(await check_eligibility(session, harness))
        if harness is not None
        else None
    )

    opt_in: LLMOptIn | None = await find_non_terminal_opt_in(session, strategy_id)
    if opt_in is None:
        return {
            "status": "none",
            "strategy_id": strategy_id,
            "eligibility": eligibility,
        }

    now = datetime.now(UTC)
    seconds_remaining = 0
    if opt_in.state == OPT_IN_PENDING:
        initiated = ensure_aware(opt_in.initiated_at)
        assert initiated is not None
        activates_at = initiated + timedelta(days=LLM_OPT_IN_COOLDOWN_DAYS)
        seconds_remaining = max(0, int((activates_at - now).total_seconds()))
    spend = await _user_live_spend_today_cents(session, current_user.id, now)
    return {
        "status": opt_in.state,
        "strategy_id": strategy_id,
        "opt_in_id": opt_in.id,
        "seconds_remaining": seconds_remaining,
        "daily_cap_cents": opt_in.daily_cap_cents,
        "spend_today_cents": float(spend),
        "eligibility": eligibility,
    }
