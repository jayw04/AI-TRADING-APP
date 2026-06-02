"""/api/v1/users/me/trading-profile endpoints (P5.5 §1).

The router prefixes only ``/users/me`` — the ``/api/v1`` prefix is applied by
``app/api/v1/__init__.py`` when this router is included. Do NOT add a second
``prefix="/api/v1"`` (that would yield ``/api/v1/api/v1/...``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.trading_profile import TradingProfileData, TradingProfileService

router = APIRouter(prefix="/users/me", tags=["trading_profile"])


class TradingProfileResponse(BaseModel):
    user_id: int
    watchlist: dict[str, Any]
    bias_criteria: dict[str, Any]
    bias_thresholds: dict[str, Any]
    session_preferences: dict[str, Any]
    risk_preferences: dict[str, Any]
    # P6 §1a (Decision 4): agent behavioral envelope. The Settings *form* for it
    # is 1b; the API field ships in 1a so the budget envelope is settable.
    agent_envelope: dict[str, Any]


class UpdateTradingProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist: dict[str, Any] | None = None
    bias_criteria: dict[str, Any] | None = None
    bias_thresholds: dict[str, Any] | None = None
    session_preferences: dict[str, Any] | None = None
    risk_preferences: dict[str, Any] | None = None
    agent_envelope: dict[str, Any] | None = None


def _to_response(profile: TradingProfileData) -> TradingProfileResponse:
    """Explicit construction — deliberately omits created_at/updated_at, which
    the response model doesn't declare."""
    return TradingProfileResponse(
        user_id=profile.user_id,
        watchlist=profile.watchlist,
        bias_criteria=profile.bias_criteria,
        bias_thresholds=profile.bias_thresholds,
        session_preferences=profile.session_preferences,
        risk_preferences=profile.risk_preferences,
        agent_envelope=profile.agent_envelope,
    )


@router.get("/trading-profile", response_model=TradingProfileResponse)
async def get_my_trading_profile(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TradingProfileResponse:
    svc = TradingProfileService(session)
    profile = await svc.get(current_user.id)
    return _to_response(profile)


@router.put("/trading-profile", response_model=TradingProfileResponse)
async def update_my_trading_profile(
    body: UpdateTradingProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TradingProfileResponse:
    # Translate request field names (watchlist) -> column names (watchlist_json).
    changes = {
        f"{k}_json": v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None
    }

    svc = TradingProfileService(session)

    if not changes:
        # No-op PUT (empty/all-null body): return current state, no audit row.
        profile = await svc.get(current_user.id)
        return _to_response(profile)

    try:
        profile = await svc.update(
            current_user.id,
            changes=changes,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_response(profile)
