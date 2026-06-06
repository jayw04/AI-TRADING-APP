"""Strategy-authoring endpoints (P7 §2).

POST /strategies/author — generate a Python strategy from a plain-English
description (Sonnet tool-use). Generate-and-return only; the trader reviews the
code + assumptions and saves separately (§4). A fresh module, off the P2 gate.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
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
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate a strategy from a description. The result is returned for review,
    not saved — the trader saves it via the normal create-strategy flow (§4)."""
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
    return {
        "code": result.code,
        "assumptions": result.assumptions,
        "explanation": result.explanation,
        "cost_usd": float(result.cost_usd),
        "prompt_version": result.prompt_version,
        "model": result.model,
    }
