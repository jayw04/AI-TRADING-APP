"""Strategy-authoring endpoints (P7 §2).

POST /strategies/author — generate a Python strategy from a plain-English
description (Sonnet tool-use). Generate-and-return only; the trader reviews the
code + assumptions and saves separately (§4). A fresh module, off the P2 gate.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.strategy_authoring.backtest import backtest_generated_code
from app.services.strategy_authoring.service import (
    BudgetExceededError,
    GenerationError,
    NoApiKeyError,
    generate_strategy,
)

router = APIRouter(tags=["strategy-authoring"])


class AuthorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=4000)


@router.post("/strategies/author", response_model=dict)
async def author_strategy(
    body: AuthorRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate a strategy from a description, then backtest it (Direction
    Decision 2 — never present code without a backtest). Generate-and-return; the
    trader saves it via the normal create-strategy flow (§4)."""
    try:
        result = await generate_strategy(
            session, user_id=current_user.id, description=body.description
        )
    except BudgetExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except NoApiKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # P7 §3: auto-backtest the generated code. A backtest failure is returned with
    # the code (the trader sees it), not raised.
    outcome = await backtest_generated_code(
        code=result.code,
        bar_cache=getattr(request.app.state, "bar_cache", None),
        indicator_computer=getattr(request.app.state, "indicator_computer", None),
    )
    return {
        "code": result.code,
        "assumptions": result.assumptions,
        "explanation": result.explanation,
        "cost_usd": float(result.cost_usd),
        "prompt_version": result.prompt_version,
        "model": result.model,
        "backtest": {
            "status": outcome.status,
            "metrics": outcome.metrics,
            "trade_count": outcome.trade_count,
            "error": outcome.error,
        },
    }
