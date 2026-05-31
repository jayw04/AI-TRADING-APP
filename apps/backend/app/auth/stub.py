"""Auth dependency: cookie -> session -> User (P5 §3).

This module replaced the P0 stub (which returned a fixed user_id=1). The
function name `get_current_user` and the `CurrentUser` type are preserved for
compatibility with every import in the codebase — the body is now real.

The dependency works as follows:
  1. Read the session cookie (name: 'workbench_session').
  2. Hash the cookie value (SHA-256).
  3. Look up the matching session row, joined to its User.
  4. Validate: not revoked, not expired, within the rolling TTL.
  5. Roll last_used_at + expires_at forward, return a CurrentUser.
  6. On any failure, raise 401.

Cookie attributes set in /auth/login:
  - httpOnly=True       — JS cannot read it
  - secure=True         — only on HTTPS (relaxed for localhost in dev)
  - SameSite=Strict     — no cross-site request includes it

The module name remains `stub.py` for import-stability across the codebase;
the docstring above is the record that it is no longer a stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_session_token
from app.db.models.session import Session as SessionRow
from app.db.models.user import User
from app.db.session import get_session

logger = structlog.get_logger(__name__)

SESSION_COOKIE_NAME = "workbench_session"
SESSION_TTL = timedelta(days=14)


@dataclass(frozen=True)
class CurrentUser:
    """Lightweight container for the authenticated user. We return this rather
    than the ORM User row to avoid leaking columns like password_hash into
    endpoint handlers."""

    id: int
    email: str
    display_name: str | None = None
    session_id: int | None = None


async def get_current_user(
    workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    if not workbench_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Cookie"},
        )

    token_hash = hash_session_token(workbench_session)
    now = datetime.now(UTC)

    # Single indexed query: token_hash is unique.
    result = await session.execute(
        select(SessionRow, User)
        .join(User, SessionRow.user_id == User.id)
        .where(SessionRow.token_hash == token_hash)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    sess_row, user_row = row

    if sess_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session revoked")
    if _aware(sess_row.expires_at) <= now:
        raise HTTPException(status_code=401, detail="Session expired")
    if (now - _aware(sess_row.last_used_at)) > SESSION_TTL:
        raise HTTPException(status_code=401, detail="Session inactive")

    # Roll the session: extend last_used_at + expires_at.
    sess_row.last_used_at = now
    sess_row.expires_at = now + SESSION_TTL
    await session.commit()

    return CurrentUser(
        id=user_row.id,
        email=user_row.email,
        display_name=user_row.display_name,
        session_id=sess_row.id,
    )


def _aware(dt: datetime) -> datetime:
    """SQLite round-trips timezone-aware datetimes as naive UTC. Coerce back to
    aware UTC so comparisons against `now` (aware) never raise."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
