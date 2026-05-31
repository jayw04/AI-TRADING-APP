"""Authentication endpoints under /api/v1/auth/ (P5 §3).

login / logout / me / totp-setup / totp-verify / session-revoke.

Session tokens are credentials: never logged in plaintext, never returned in a
response body, never echoed in audit payloads. The cookie is the only place the
plaintext token lives.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password
from app.auth.stub import (
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    CurrentUser,
    get_current_user,
)
from app.auth.tokens import generate_session_token, hash_session_token
from app.auth.totp import (
    generate_secret,
    make_provisioning_uri,
    make_qr_data_url,
    verify_code,
)
from app.db.models.session import Session as SessionRow
from app.db.models.user import User
from app.db.session import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------- Rate limit (in-memory, per IP) ----------------

LOGIN_RATE_LIMIT_WINDOW = 15 * 60.0  # 15 min
LOGIN_RATE_LIMIT_MAX = 5
LOGIN_COOLDOWN_SECONDS = 60 * 60.0  # 60 min cooldown after exceeding

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_cooldown_until: dict[str, float] = {}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the rate limit. Always records the
    current attempt."""
    now = time.time()
    cooldown = _login_cooldown_until.get(ip, 0.0)
    if cooldown > now:
        retry_in = int(cooldown - now)
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {retry_in}s.",
            headers={"Retry-After": str(retry_in)},
        )
    # Sliding window.
    cutoff = now - LOGIN_RATE_LIMIT_WINDOW
    fresh = [t for t in _login_attempts[ip] if t > cutoff]
    fresh.append(now)
    _login_attempts[ip] = fresh
    if len(fresh) > LOGIN_RATE_LIMIT_MAX:
        _login_cooldown_until[ip] = now + LOGIN_COOLDOWN_SECONDS
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Cooldown {int(LOGIN_COOLDOWN_SECONDS)}s.",
            headers={"Retry-After": str(int(LOGIN_COOLDOWN_SECONDS))},
        )


def _reset_rate_limit_for_tests() -> None:
    _login_attempts.clear()
    _login_cooldown_until.clear()


def _is_secure_context(request: Request) -> bool:
    """In dev (localhost over http) browsers refuse Secure cookies. Relax the
    flag for localhost; everywhere else it stays true."""
    host = request.url.hostname or ""
    return host not in ("localhost", "127.0.0.1", "0.0.0.0")


# ---------------- Schemas ----------------


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp_code: str = Field(min_length=6, max_length=8)


class LoginResponse(BaseModel):
    user_id: int
    email: str
    display_name: str | None


class MeResponse(BaseModel):
    user_id: int
    email: str
    display_name: str | None
    session_id: int | None


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_data_url: str


class TotpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


# ---------------- /auth/login ----------------


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    ip = _client_ip(request)
    _check_login_rate_limit(ip)

    email = body.email.lower()
    user_row = (
        await session.execute(select(User).where(User.email == email))
    ).scalars().first()

    # Constant-time path even if the user doesn't exist: bcrypt always runs.
    fake_hash = "$2b$12$" + "x" * 53
    user_hash = (
        user_row.password_hash if user_row and user_row.password_hash else fake_hash
    )
    if not verify_password(body.password, user_hash):
        logger.warning("auth_login_bad_password", ip=ip, email=email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user_row is None:
        # Defensive: shouldn't be reached after the verify above.
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user_row.totp_secret or user_row.totp_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail="TOTP is not set up for this account. Run scripts/create_user.py "
            "or contact your admin to bootstrap TOTP.",
        )

    if not verify_code(user_row.totp_secret, body.totp_code):
        logger.warning("auth_login_bad_totp", ip=ip, user_id=user_row.id)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # All checks pass — mint a session.
    plaintext_token = generate_session_token()
    now = datetime.now(UTC)
    sess = SessionRow(
        user_id=user_row.id,
        token_hash=hash_session_token(plaintext_token),
        created_at=now,
        last_used_at=now,
        expires_at=now + SESSION_TTL,
        ip=ip[:64],
        user_agent=(request.headers.get("user-agent") or "")[:256],
    )
    session.add(sess)
    await session.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=plaintext_token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=_is_secure_context(request),
        samesite="strict",
        path="/",
    )

    logger.info("auth_login_success", user_id=user_row.id, ip=ip)
    return LoginResponse(
        user_id=user_row.id,
        email=user_row.email,
        display_name=user_row.display_name,
    )


# ---------------- /auth/logout ----------------


@router.post("/logout")
async def logout(
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    await session.execute(
        update(SessionRow)
        .where(SessionRow.id == current_user.session_id)
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    logger.info("auth_logout", user_id=current_user.id)
    return {"ok": True}


# ---------------- /auth/me ----------------


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        session_id=current_user.session_id,
    )


# ---------------- /auth/totp/setup ----------------


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TotpSetupResponse:
    """Generate a new TOTP secret. Refused once totp_verified_at is set (rotate
    via the CLI script instead)."""
    user_row = await session.get(User, current_user.id)
    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user_row.totp_verified_at is not None:
        raise HTTPException(
            status_code=409,
            detail="TOTP is already verified for this user. Use the CLI script to rotate.",
        )
    secret = generate_secret()
    user_row.totp_secret = secret
    user_row.totp_verified_at = None
    await session.commit()

    provisioning_uri = make_provisioning_uri(secret, account_name=user_row.email)
    return TotpSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        qr_data_url=make_qr_data_url(provisioning_uri),
    )


# ---------------- /auth/totp/verify ----------------


@router.post("/totp/verify")
async def totp_verify(
    body: TotpVerifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Verify the setup code. On success, mark TOTP verified."""
    user_row = await session.get(User, current_user.id)
    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user_row.totp_secret:
        raise HTTPException(status_code=400, detail="No pending TOTP setup")
    if user_row.totp_verified_at is not None:
        raise HTTPException(status_code=409, detail="TOTP already verified")
    if not verify_code(user_row.totp_secret, body.code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    user_row.totp_verified_at = datetime.now(UTC)
    await session.commit()
    logger.info("auth_totp_verified", user_id=current_user.id)
    return {"ok": True}


# ---------------- /auth/sessions/{id}/revoke ----------------


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Revoke a specific session belonging to the current user."""
    sess = await session.get(SessionRow, session_id)
    if sess is None or sess.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.revoked_at is None:
        sess.revoked_at = datetime.now(UTC)
        await session.commit()
    logger.info("auth_session_revoked", user_id=current_user.id, session_id=session_id)
    return {"ok": True}
