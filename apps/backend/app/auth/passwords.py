"""Password hashing with bcrypt (P5 §3).

Cost factor 12 is the current OWASP recommendation as of 2025-2026. Hashing one
password at cost=12 takes ~250ms on modern hardware; bumping to 13 doubles that.

We use bcrypt directly rather than passlib (which wraps multiple algorithms)
because the deployment is simple, single-tenant, and we don't need migration
between hash schemes.
"""

from __future__ import annotations

import bcrypt

BCRYPT_COST = 12
# bcrypt truncates input at 72 bytes; reject longer input explicitly so users
# get a clear error rather than a silently truncated hash.
MAX_PASSWORD_BYTES = 72


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password. Returns the encoded hash including salt+cost.

    Raises ValueError on empty or excessively long input.
    """
    if not plaintext:
        raise ValueError("Password cannot be empty")
    pw_bytes = plaintext.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError(
            "Password is too long (max 72 bytes UTF-8). Use a shorter password "
            "or a passphrase that fits the limit."
        )
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    return bcrypt.hashpw(pw_bytes, salt).decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time comparison. Returns False on any malformed input."""
    if not (plaintext and hashed):
        return False
    try:
        pw_bytes = plaintext.encode("utf-8")
        if len(pw_bytes) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(pw_bytes, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False
