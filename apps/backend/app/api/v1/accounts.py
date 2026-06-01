"""GET /api/v1/accounts and POST /api/v1/accounts.

The list endpoint backs the frontend's LIVE banner — it filters for any
account with mode='live'. The create endpoint allows paper account creation
only; LIVE creation goes through the activation wizard (P5 §7), which is not
yet shipped, so it returns 400 here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.accounts import (
    AccountListResponse,
    AccountResponse,
    CreateAccountRequest,
)
from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.session import get_session
from app.security import CredentialKind, CredentialStore

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountListResponse:
    rows = (
        await session.execute(
            select(Account)
            .where(Account.user_id == current_user.id)
            .order_by(Account.id)
        )
    ).scalars().all()
    return AccountListResponse(
        items=[AccountResponse.model_validate(r) for r in rows],
        count=len(rows),
    )


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: CreateAccountRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    # P5 §7: LIVE account creation is permitted, gated by a fresh TOTP code
    # (re-verified server-side). Layered defense against "someone with the
    # session cookie creates a live account and submits an order."
    if body.mode == AccountMode.live:
        if not body.totp_code:
            raise HTTPException(
                status_code=400,
                detail="totp_code is required for LIVE account creation.",
            )
        from app.auth.totp import verify_code

        store = CredentialStore(session)
        totp_secret = await store.get(current_user.id, CredentialKind.TOTP_SECRET)
        if totp_secret is None or not verify_code(totp_secret, body.totp_code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code.")

    # One account per (user, broker, mode) — mirrors the DB UniqueConstraint
    # (uq_accounts_user_broker_mode) and returns a clean 409 instead of an
    # opaque IntegrityError.
    existing = (
        await session.execute(
            select(Account).where(
                Account.user_id == current_user.id,
                Account.broker == body.broker,
                Account.mode == body.mode,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A {body.mode.value} account for broker "
                f"'{body.broker}' already exists."
            ),
        )

    account = Account(
        user_id=current_user.id,
        broker=body.broker,
        mode=body.mode,
        label=body.label,
        created_at=datetime.now(UTC),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    # P5 §7: audit LIVE account creation (immutable record of "a live account
    # was opened, by whom, when").
    if account.mode == AccountMode.live:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.id),
            action=AuditAction.LIVE_ACCOUNT_CREATED,
            target_type="account",
            target_id=account.id,
            payload={"broker": account.broker, "label": account.label},
            user_id=current_user.id,
        )
        await session.commit()

    # P5 §2: make the new account immediately routable — construct its
    # adapter in the registry. Live creation 400s above (P5 §1), so refresh only
    # ever runs for paper accounts here. Best-effort: registry may be absent in
    # tests / alpaca-startup-disabled runs.
    registry = getattr(request.app.state, "broker_registry", None)
    if registry is not None:
        await registry.refresh(account.id)

    return AccountResponse.model_validate(account)
