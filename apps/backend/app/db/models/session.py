"""Server-side session tracking (P5 §3).

Tokens are NEVER stored in plaintext. The cookie holds the plaintext token;
this table holds SHA-256(token), base64url-encoded. Comparison is constant-time.

A session is valid iff:
  - The token hash matches.
  - revoked_at IS NULL.
  - expires_at > now().
  - last_used_at is within the rolling TTL (14 days).

`last_used_at` updates on each successful auth lookup, extending the session
implicitly. A user who logs in and stays active never re-auths. A user who walks
away for two weeks is forced to re-auth.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256(token) base64url-encoded. 44 chars; we store up to 64 to allow a
    # future hash-alg change without migrating the column.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Forensics only: IP + UA of the originating request. Truncated; never used
    # for an auth decision, only for the user's "my sessions" view.
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_sessions_user_active", "user_id", "revoked_at", "expires_at"),
    )
