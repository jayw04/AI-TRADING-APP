"""User credential management — set, list metadata, revoke (P5 §4).

Endpoints under ``/api/v1/users/me/credentials/``:

* ``GET /``          — list metadata for every kind (NEVER plaintext).
* ``PUT /{kind}``    — set or rotate a credential. TOTP is excluded (the auth
                       flow owns it).
* ``DELETE /{kind}`` — revoke a credential. TOTP excluded.

The plaintext a user submits via PUT is encrypted by the credential store and
never echoed back. GET returns set/not-set state and timestamps only.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.security import CredentialKind, CredentialStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users/me/credentials", tags=["credentials"])


# Broker credential kinds trigger a registry refresh so a running adapter
# picks up rotated keys without a backend restart.
_BROKER_KINDS = {
    CredentialKind.ALPACA_PAPER_KEY,
    CredentialKind.ALPACA_PAPER_SECRET,
    CredentialKind.ALPACA_LIVE_KEY,
    CredentialKind.ALPACA_LIVE_SECRET,
}


class CredentialIn(BaseModel):
    value: str


class CredentialMetadataOut(BaseModel):
    kind: str
    has_value: bool
    created_at: str | None
    updated_at: str | None
    last_used_at: str | None
    revoked_at: str | None


def _reject_totp(ck: CredentialKind) -> None:
    if ck == CredentialKind.TOTP_SECRET:
        raise HTTPException(
            status_code=400,
            detail="TOTP secret is managed via /auth/totp/setup, not this endpoint.",
        )


def _parse_kind(kind: str) -> CredentialKind:
    try:
        return CredentialKind(kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Unknown credential kind: {kind}"
        ) from exc


@router.get("/", response_model=list[CredentialMetadataOut])
async def list_credentials(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CredentialMetadataOut]:
    store = CredentialStore(session)
    items = await store.list_kinds(current_user.id)
    return [
        CredentialMetadataOut(
            kind=item.kind.value,
            has_value=item.has_value,
            created_at=item.created_at.isoformat() if item.created_at else None,
            updated_at=item.updated_at.isoformat() if item.updated_at else None,
            last_used_at=item.last_used_at.isoformat() if item.last_used_at else None,
            revoked_at=item.revoked_at.isoformat() if item.revoked_at else None,
        )
        for item in items
    ]


@router.put("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def set_credential(
    kind: str,
    body: CredentialIn,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    ck = _parse_kind(kind)
    _reject_totp(ck)
    if not body.value:
        raise HTTPException(status_code=400, detail="Value cannot be empty")
    store = CredentialStore(session)
    await store.set(current_user.id, ck, body.value)

    # If this is a broker credential, refresh the registry so the adapter picks
    # up the new keys without restarting. Best-effort: the registry only exists
    # when alpaca-startup is enabled (it's absent in tests / data-only boots).
    if ck in _BROKER_KINDS:
        registry = getattr(request.app.state, "broker_registry", None)
        if registry is not None:
            from sqlalchemy import select

            from app.db.models.account import Account

            # Refresh every account belonging to this user (a key change can
            # affect any of their adapters). Cheap for the single-tenant MVP.
            account_ids = (
                await session.execute(
                    select(Account.id).where(Account.user_id == current_user.id)
                )
            ).scalars().all()
            for account_id in account_ids:
                try:
                    await registry.refresh(account_id)
                except Exception:
                    logger.exception(
                        "credential_registry_refresh_failed", account_id=account_id
                    )


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_credential(
    kind: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    ck = _parse_kind(kind)
    _reject_totp(ck)
    store = CredentialStore(session)
    await store.revoke(current_user.id, ck)
