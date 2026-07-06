"""Bootstrap or rotate a user's login credentials (P5 §3/§4).

`seed_dev_data.py` creates the user row but leaves `password_hash` and the
TOTP secret unset, so browser login is impossible on a freshly rebuilt DB
(login refuses while `totp_verified_at` is NULL). This is the CLI that the
login and activation error messages point at ("Run scripts/create_user.py").
It fills in the bcrypt password hash, writes the TOTP secret into the encrypted
credential store, and marks `totp_verified_at` so login works immediately.

Run it after `alembic upgrade head` (and optionally `seed_dev_data.py`), from
the backend container or the host backend venv. It needs `WORKBENCH_MASTER_KEY`
in the environment / root `.env` to encrypt the TOTP secret.

Examples:
    # Bootstrap the dev user; password from --password or $WORKBENCH_DEV_USER_PASSWORD,
    # else a strong random one is generated and printed. A fresh TOTP secret is
    # generated and its provisioning URI printed for enrollment.
    python scripts/create_user.py

    # Reuse an existing TOTP secret so your phone's QR / authenticator entry
    # stays valid across a DB rebuild (recommended for the dev user).
    python scripts/create_user.py --totp-secret HLY7NC3UFQFHPTB3G2EAUP3Y3Y2WQTTO

    # A different user, explicit password.
    python scripts/create_user.py --email trader@example.com --password 'S3cret!pass'

    # Force a brand-new TOTP secret even though one is already verified.
    python scripts/create_user.py --rotate-totp

Idempotent: re-running leaves an already-set password and an already-verified
TOTP untouched unless you pass --password / --totp-secret / --rotate-totp.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# Make the backend importable when run as `python scripts/create_user.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import EmailStr, TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.auth.totp import (  # noqa: E402
    generate_secret,
    make_provisioning_uri,
)
from app.config import get_settings  # noqa: E402
from app.db.enums import RiskScopeType  # noqa: E402
from app.db.models import RiskLimits, User  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.security.credential_store import CredentialKind, CredentialStore  # noqa: E402

# Default dev password env var (avoids baking a secret into this committed file;
# conservative default is to generate a random one if neither flag nor env set).
PASSWORD_ENV_VAR = "WORKBENCH_DEV_USER_PASSWORD"


def _generate_password() -> str:
    """A strong URL-safe random password (stays under bcrypt's 72-byte cap)."""
    return secrets.token_urlsafe(18)


_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _validate_email(email: str) -> str:
    """Reject an email the /auth/login route would later refuse.

    The login request body is validated with Pydantic ``EmailStr`` (e.g. a
    domain with no dot like ``range@local`` is invalid). Without this check
    create_user would happily create an account that then **cannot log in** —
    the 422 surfaces in the UI as a confusing "Invalid credentials". Validating
    here with the same ``EmailStr`` fails fast with a clear message instead."""
    try:
        return _EMAIL_ADAPTER.validate_python(email)
    except ValidationError as exc:
        reason = exc.errors()[0].get("msg", "invalid email") if exc.errors() else "invalid email"
        raise ValueError(
            f"invalid --email {email!r}: {reason.rstrip('.')}. Use a full address "
            f"with a valid domain, e.g. name@example.com (the login page "
            f"validates the same way)."
        ) from exc


def _parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Bootstrap or rotate a user's login credentials (password + TOTP).",
    )
    parser.add_argument(
        "--email",
        default=settings.dev_user_email,
        help=f"User email (default: {settings.dev_user_email}).",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Display name, only used when creating a new user.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help=(
            f"Plaintext password. Falls back to ${PASSWORD_ENV_VAR}, else a "
            "random one is generated and printed. An existing password is left "
            "untouched unless this is given."
        ),
    )
    parser.add_argument(
        "--totp-secret",
        default=None,
        help=(
            "Reuse an existing base32 TOTP secret (keeps your authenticator "
            "entry valid across a DB rebuild)."
        ),
    )
    parser.add_argument(
        "--rotate-totp",
        action="store_true",
        help="Generate a fresh TOTP secret even if one is already verified.",
    )
    args = parser.parse_args()
    # Fail fast on an email the login route would later reject — see
    # _validate_email. parser.error() prints usage and exits non-zero.
    try:
        _validate_email(args.email)
    except ValueError as exc:
        parser.error(str(exc))
    return args


async def create_user(args: argparse.Namespace) -> None:
    settings = get_settings()
    email = args.email.lower()
    Session = get_sessionmaker()

    async with Session() as session:
        # --- User row (find or create) ---
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=args.display_name)
            session.add(user)
            await session.flush()
            print(f"  + created user id={user.id} email={email}")
        else:
            print(f"  = user id={user.id} email={email} already present")

        # --- Password ---
        env_password = os.environ.get(PASSWORD_ENV_VAR)
        chosen_password = args.password or env_password
        generated = False
        if chosen_password is None and user.password_hash is None:
            chosen_password = _generate_password()
            generated = True

        if chosen_password is not None:
            user.password_hash = hash_password(chosen_password)
            await session.commit()
            if generated:
                print(f"  + password (generated): {chosen_password}")
            else:
                print("  + password set")
        else:
            print("  = password unchanged (already set; pass --password to reset)")

        # --- TOTP secret (encrypted credential store) ---
        store = CredentialStore(session)
        existing_secret = await store.get(user.id, CredentialKind.TOTP_SECRET)
        already_verified = user.totp_verified_at is not None and existing_secret

        if args.totp_secret:
            secret = args.totp_secret.strip().upper()
            await store.set(user.id, CredentialKind.TOTP_SECRET, secret)
            action = "reused (provided)"
        elif args.rotate_totp or not already_verified:
            secret = generate_secret()
            await store.set(user.id, CredentialKind.TOTP_SECRET, secret)
            action = "rotated" if already_verified else "generated"
        else:
            secret = existing_secret
            action = None  # left untouched

        # Mark verified so login works immediately. This is an admin-trust
        # bootstrap; the interactive /auth/totp/verify flow is for self-service.
        if user.totp_verified_at is None:
            user.totp_verified_at = datetime.now(UTC)
            await session.commit()

        if action is None:
            print("  = TOTP unchanged (already verified; pass --rotate-totp to replace)")
        else:
            uri = make_provisioning_uri(secret, account_name=user.email)
            print(f"  + TOTP secret {action}: {secret}")
            print(f"    enroll with: {uri}")

        # --- Default GLOBAL paper risk limits ---
        # The risk engine FAILS CLOSED: a user with no resolvable RiskLimits row
        # has every order rejected (NO_LIMITS_CONFIGURED). seed_dev_data seeds the
        # dev user's limits, but a freshly-created profile user (e.g. a Risk Profile)
        # otherwise has none — so seed the same conservative global paper caps here,
        # idempotently, so a new book can actually trade once activated.
        existing_limits = await session.scalar(
            select(RiskLimits).where(
                RiskLimits.user_id == user.id,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )
        if existing_limits is None:
            now = datetime.now(UTC)
            session.add(
                RiskLimits(
                    user_id=user.id,
                    scope_type=RiskScopeType.GLOBAL,
                    scope_id=None,
                    max_position_qty=Decimal("1000"),
                    max_position_notional=Decimal("25000"),
                    max_gross_exposure=Decimal("100000"),
                    max_daily_loss=Decimal("2000"),
                    max_orders_per_minute=10,
                    allow_short=False,
                    allowed_symbols=None,
                    denied_symbols=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            print("  + risk_limits global (default paper caps)")
        else:
            print("  = risk_limits global already present")

    print("Done. Login should now succeed at /api/v1/auth/login.")
    print(f"  email: {email}")
    print("  (TOTP codes via any authenticator app loaded with the secret above)")
    if settings.env != "development":
        print("  NOTE: env is not 'development' — make sure this is intentional.")


if __name__ == "__main__":
    asyncio.run(create_user(_parse_args()))
