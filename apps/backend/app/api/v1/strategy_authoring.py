"""Strategy-authoring endpoints (P7 §2).

POST /strategies/author — generate a Python strategy from a plain-English
description (Sonnet tool-use). Generate-and-return only; the trader reviews the
code + assumptions and saves separately (§4). A fresh module, off the P2 gate.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_session
from app.services.strategy_authoring.backtest import backtest_generated_code
from app.services.strategy_authoring.code_safety import UnsafeCodeError, validate_generated_code
from app.services.strategy_authoring.service import (
    BudgetExceededError,
    GenerationError,
    NoApiKeyError,
    generate_strategy,
)
from app.strategies import StrategyLoader, StrategyLoadError

router = APIRouter(tags=["strategy-authoring"])


def _strategies_root() -> Path:
    return Path("strategies_user")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


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


class SaveAuthoredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40000)
    name: str = Field(min_length=1, max_length=128)


@router.post("/strategies/author/save", response_model=dict)
async def save_authored_strategy(
    body: SaveAuthoredRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Persist an AI-generated strategy: re-validate (safety), write the .py,
    validate via the loader, and register it (status IDLE, authoring_method
    nl_generation). The trader saves what they reviewed; the standard
    backtest → paper → activation lifecycle applies (Decision 4)."""
    # 1. Safety — a separate trust boundary from generation.
    try:
        validate_generated_code(body.code)
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"code has a syntax error: {exc}") from exc
    except UnsafeCodeError as exc:
        raise HTTPException(status_code=400, detail=f"unsafe code: {exc}") from exc

    slug = _slugify(body.name)
    if not slug:
        raise HTTPException(status_code=400, detail="name must contain alphanumerics")
    root = _strategies_root()
    rel = f"{slug}.py"
    path = root / rel
    if path.exists():
        raise HTTPException(
            status_code=409, detail="a strategy file by that name already exists"
        )

    root.mkdir(parents=True, exist_ok=True)
    path.write_text(body.code, encoding="utf-8")
    try:
        try:
            cls = StrategyLoader(root).load(rel)
        except StrategyLoadError as exc:
            raise HTTPException(status_code=400, detail=f"strategy file invalid: {exc}") from exc

        now = datetime.now(UTC)
        row = StrategyRow(
            user_id=current_user.id,
            name=body.name,
            version=str(cls.version),
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path=rel,
            params_json=dict(cls.default_params or {}),
            symbols_json=list(cls.symbols or []),
            schedule=cls.schedule,
            authoring_method="nl_generation",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.id),
            action=AuditAction.STRATEGY_REGISTERED,
            target_type="strategy",
            target_id=row.id,
            payload={"name": body.name, "authoring_method": "nl_generation", "code_path": rel},
            user_id=current_user.id,
        )
        await session.commit()
    except Exception:
        # No orphan .py if anything after the write failed.
        path.unlink(missing_ok=True)
        raise

    return {
        "id": row.id,
        "name": row.name,
        "status": row.status.value,
        "code_path": row.code_path,
        "authoring_method": row.authoring_method,
    }
