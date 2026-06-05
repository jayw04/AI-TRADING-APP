"""Live-auto-dispatch master switch endpoints (P6b §4.5, ADR 0015).

GET  /system/live-autodispatch — read the global switch.
POST /system/live-autodispatch — flip it (TOTP-gated; audited). Turning it on
     permits LIVE strategies to auto-dispatch real-money orders; default is OFF.

A fresh module (off the P2 branch-coverage gate), mirroring the §1b/§4 pattern.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.security import CredentialKind, CredentialStore
from app.services.live_autodispatch import (
    is_live_autodispatch_enabled,
    set_live_autodispatch_enabled,
)

router = APIRouter(tags=["live-autodispatch"])


class LiveAutodispatchResponse(BaseModel):
    enabled: bool


class SetLiveAutodispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    totp_code: str = Field(min_length=6, max_length=8)


@router.get("/system/live-autodispatch", response_model=LiveAutodispatchResponse)
async def get_live_autodispatch(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LiveAutodispatchResponse:
    return LiveAutodispatchResponse(enabled=await is_live_autodispatch_enabled(session))


@router.post("/system/live-autodispatch", response_model=LiveAutodispatchResponse)
async def set_live_autodispatch(
    body: SetLiveAutodispatchRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LiveAutodispatchResponse:
    """Flip the global live-auto-dispatch master switch. TOTP-gated — it is an
    account-level safety control (cf. live activation)."""
    from app.auth.totp import verify_code

    secret = await CredentialStore(session).get(
        current_user.id, CredentialKind.TOTP_SECRET
    )
    if secret is None or not verify_code(secret, body.totp_code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")

    await set_live_autodispatch_enabled(
        session, body.enabled, actor_user_id=current_user.id
    )
    await session.commit()
    return LiveAutodispatchResponse(enabled=body.enabled)
