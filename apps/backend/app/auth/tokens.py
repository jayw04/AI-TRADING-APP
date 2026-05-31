"""Session token generation and hashing (P5 §3).

The plaintext token is base64url, ~43 chars (256 bits of entropy). The stored
hash is SHA-256(token), base64url-encoded, 44 chars.

Why SHA-256 rather than bcrypt for tokens? Speed. Auth lookup happens on every
request; a bcrypt verify at cost 12 adds ~250ms per request, which makes the
workbench unusably slow. Session tokens are 256-bit random strings — not
vulnerable to dictionary attacks the way passwords are — so a fast hash is
appropriate.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

TOKEN_BYTES = 32  # 256 bits


def generate_session_token() -> str:
    """Return a fresh 32-byte URL-safe token (256 bits of entropy)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """SHA-256(token), base64url-encoded."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def token_hashes_equal(a: str, b: str) -> bool:
    """Constant-time hash comparison."""
    return hmac.compare_digest(a, b)
