"""Activation lifecycle endpoints under /api/v1/strategies/{id}/ (P5 §7)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.strategy import Strategy
from app.db.session import get_session
from app.services.activation import ActivationError, ActivationService

router = APIRouter(prefix="/strategies", tags=["activation"])


class PrerequisiteResponse(BaseModel):
    name: str
    satisfied: bool
    detail: str


class ActivationStatusResponse(BaseModel):
    strategy_id: int
    status: str
    prerequisites: list[PrerequisiteResponse]
    all_satisfied: bool
    initiated_at: datetime | None
    completes_at: datetime | None
    seconds_remaining: int


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_name: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=8)


class DeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liquidate: bool = False


def _to_response(status) -> ActivationStatusResponse:  # noqa: ANN001
    return ActivationStatusResponse(
        strategy_id=status.strategy_id,
        status=status.status.value,
        prerequisites=[
            PrerequisiteResponse(name=p.name, satisfied=p.satisfied, detail=p.detail)
            for p in status.prerequisites
        ],
        all_satisfied=status.all_satisfied,
        initiated_at=status.initiated_at,
        completes_at=status.completes_at,
        seconds_remaining=status.seconds_remaining,
    )


@router.get("/{strategy_id}/activation", response_model=ActivationStatusResponse)
async def activation_status(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ActivationStatusResponse:
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    status = await ActivationService(session=session).status(strategy_id)
    return _to_response(status)


@router.post("/{strategy_id}/activate", response_model=ActivationStatusResponse)
async def activate_strategy(
    strategy_id: int,
    body: ActivateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ActivationStatusResponse:
    svc = ActivationService(session=session)
    try:
        result = await svc.initiate(
            strategy_id=strategy_id,
            user_id=current_user.id,
            confirmation_name=body.confirmation_name,
            totp_code=body.totp_code,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found") from None
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(result)


@router.post("/{strategy_id}/activate/cancel")
async def cancel_activation(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ActivationService(session=session)
    try:
        await svc.cancel(strategy_id=strategy_id, user_id=current_user.id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found") from None
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "strategy_id": strategy_id}


@router.post("/{strategy_id}/deactivate")
async def deactivate_strategy(
    strategy_id: int,
    body: DeactivateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ActivationService(
        session=session,
        broker_registry=getattr(request.app.state, "broker_registry", None),
        order_router=getattr(request.app.state, "order_router", None),
    )
    try:
        result = await svc.deactivate(
            strategy_id=strategy_id,
            user_id=current_user.id,
            liquidate=body.liquidate,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found") from None
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
