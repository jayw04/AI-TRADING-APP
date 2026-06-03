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

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_session_token
from app.db.models.session import Session as SessionRow
from app.db.models.user import User
from app.db.models.user_credential import UserCredential
from app.db.session import get_session
from app.security.credential_store import CredentialKind, CredentialStore
from app.utils.time import ensure_aware

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
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    # P5.5 §3 / P6 §1a: non-cookie clients authenticate with a per-user bearer
    # token instead of a cookie — the workbench-mcp server (WORKBENCH_MCP_KEY)
    # and the agent service (AGENT_API_KEY). Only consulted when there's no
    # cookie — the web app always sends the cookie, so this never shadows the
    # session path.
    if not workbench_session and authorization and authorization.startswith("Bearer "):
        return await _resolve_from_bearer_token(session, authorization[7:].strip())

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
    aware UTC so comparisons against `now` (aware) never raise.

    Thin wrapper over the shared app.utils.time.ensure_aware (P5 §5 extracted
    the canonical copy); kept here for the existing non-Optional call sites.
    """
    return ensure_aware(dt)  # type: ignore[return-value]  # callers pass non-None


# Bearer-credential kinds, in resolution order. Per Decision 2, AGENT_API_KEY is
# a first-class bearer credential the agent uses for the backend HTTP API; the
# WORKBENCH_MCP_KEY (P5.5 §3) is the workbench-mcp server's. Both resolve to the
# owning user — a bearer-accepting endpoint doesn't care which kind it was.
_BEARER_KINDS = (CredentialKind.AGENT_API_KEY, CredentialKind.WORKBENCH_MCP_KEY)


async def _match_bearer_token(
    session: AsyncSession, token: str, kind: CredentialKind
) -> CurrentUser | None:
    """Constant-time match of ``token`` against every active credential of
    ``kind``; returns the owning user or None. Decrypts via the §4 credential
    store, so rotation/revocation/audit are the same machinery as every other
    CredentialKind."""
    rows = (
        await session.execute(
            select(UserCredential).where(
                UserCredential.kind == kind.value,
                UserCredential.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    store = CredentialStore(session)
    for row in rows:
        stored = await store.get(row.user_id, kind)
        if stored and hmac.compare_digest(stored, token):
            user = await session.get(User, row.user_id)
            if user is not None:
                return CurrentUser(id=user.id, email=user.email)
    return None


async def _resolve_from_bearer_token(session: AsyncSession, token: str) -> CurrentUser:
    """Resolve a bearer token against the known bearer-credential kinds in order
    (P5.5 §3 + P6 §1a). 401 if it matches none."""
    if not token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    for kind in _BEARER_KINDS:
        user = await _match_bearer_token(session, token, kind)
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Invalid bearer token")
