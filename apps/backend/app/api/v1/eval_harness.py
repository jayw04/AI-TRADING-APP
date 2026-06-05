"""Eval-harness endpoints (P6b §4, ADR 0006 v2).

POST /strategies/{id}/start-eval — begin an LLM eval (spawn Mode A + Mode B).
GET  /strategies/{id}/eval-harness — the active harness's state + 6 metrics +
     eligibility verdict (the §5 opt-in dialog + the MCP tool read this).
POST /eval-harness/{id}/stop — manual stop.

A fresh module (not strategies.py) keeps these off the P2 branch-coverage gate
(the §1b/§2c/drift pattern).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.eval_harness import EvalHarness
from app.db.models.strategy import Strategy
from app.db.session import get_session
from app.services.eval_harness.eligibility import check_eligibility, verdict_to_dict
from app.services.eval_harness.metrics import (
    comparison_to_dict,
    compute_eval_harness_comparison,
)
from app.services.eval_harness.service import (
    find_active_harness,
    start_eval_harness,
    stop_eval_harness,
)

router = APIRouter(tags=["eval-harness"])

_START_ERROR_CODES = {
    "parent_not_found": 404,
    "parent_not_live": 409,
    "paper_variant_in_flight": 409,
    "eval_harness_already_active": 409,
}


@router.post("/strategies/{strategy_id}/start-eval", response_model=dict)
async def start_eval(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start an LLM eval harness on a LIVE strategy (ADR 0006 v2). Spawns Mode A
    (running, LLM-gated) + Mode B (bucket). Mutually exclusive with a §2 paper
    variant."""
    engine = getattr(request.app.state, "strategy_engine", None)
    try:
        harness = await start_eval_harness(
            session, parent_strategy_id=strategy_id, user_id=current_user.id,
            engine=engine,
        )
    except ValueError as exc:
        code = _START_ERROR_CODES.get(str(exc), 400)
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {
        "status": "active",
        "harness_id": harness.id,
        "mode_a_strategy_id": harness.mode_a_strategy_id,
        "mode_b_strategy_id": harness.mode_b_strategy_id,
        "started_at": harness.started_at.isoformat(),
    }


@router.post("/eval-harness/{harness_id}/stop", response_model=dict)
async def stop_eval(
    harness_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Manually stop an eval harness (terminates Mode A; the rows + orders stay
    as read-only data)."""
    engine = getattr(request.app.state, "strategy_engine", None)
    try:
        await stop_eval_harness(
            session, harness_id=harness_id, user_id=current_user.id, engine=engine
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "terminated", "harness_id": harness_id}


@router.get("/strategies/{strategy_id}/eval-harness", response_model=dict)
async def get_eval_harness(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The active harness for a strategy: state + 6 metrics + eligibility. Read-
    only. ``{"status": "no_active_harness"}`` when none."""
    parent = await session.get(Strategy, strategy_id)
    if parent is None or parent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    harness: EvalHarness | None = await find_active_harness(session, strategy_id)
    if harness is None:
        return {"status": "no_active_harness", "strategy_id": strategy_id}

    bar_cache = getattr(request.app.state, "bar_cache", None)
    comparison = await compute_eval_harness_comparison(session, harness, bar_cache)
    eligibility = await check_eligibility(session, harness)
    return {
        "status": harness.state,
        "harness_id": harness.id,
        "strategy_id": strategy_id,
        "mode_a_strategy_id": harness.mode_a_strategy_id,
        "mode_b_strategy_id": harness.mode_b_strategy_id,
        "started_at": harness.started_at.isoformat(),
        "comparison": comparison_to_dict(comparison),
        "eligibility": verdict_to_dict(eligibility),
    }
