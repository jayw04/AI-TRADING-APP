"""User-self endpoints for credential management.

P4 introduces the Pine webhook secret (rotate / fetch). The auth stub
resolves ``current_user`` to user id 1 in dev; P5 replaces the stub with
real per-request auth.
"""

from __future__ import annotations

from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter(prefix="/users", tags=["users"])


class WebhookSecretResponse(BaseModel):
    pine_webhook_secret: str
    # Surfaced in the response so a fresh user discovers the setup flow
    # without having to read the runbook first.
    instructions: str


_INSTRUCTIONS = (
    "Place this secret in the JSON body of your TradingView alert as the "
    "'secret' field. See docs/runbook/tv-webhooks.md for the full template."
)


@router.post("/me/regenerate-webhook-secret", response_model=WebhookSecretResponse)
async def regenerate_webhook_secret(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WebhookSecretResponse:
    """Generate or rotate the current user's Pine webhook secret.

    The new secret invalidates the previous one immediately. Treat it like
    a password — anyone with it can deliver alerts as you.
    """
    row = await session.get(User, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    new_secret = token_urlsafe(32)  # 256-bit, ~43 url-safe chars
    row.pine_webhook_secret = new_secret
    await session.commit()

    return WebhookSecretResponse(
        pine_webhook_secret=new_secret,
        instructions=_INSTRUCTIONS,
    )


@router.get("/me/webhook-secret", response_model=WebhookSecretResponse)
async def get_webhook_secret(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WebhookSecretResponse:
    """Return the current Pine webhook secret, or 404 if none is set.

    P5 multi-user will remove this GET — at that point rotation becomes
    write-only and the secret is shown exactly once.
    """
    row = await session.get(User, current_user.id)
    if row is None or not row.pine_webhook_secret:
        raise HTTPException(
            status_code=404,
            detail=(
                "No Pine webhook secret set. POST "
                "/api/v1/users/me/regenerate-webhook-secret to create one."
            ),
        )
    return WebhookSecretResponse(
        pine_webhook_secret=row.pine_webhook_secret,
        instructions=_INSTRUCTIONS,
    )
