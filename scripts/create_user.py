#!/usr/bin/env python
"""Bootstrap a Trading Workbench user (P5 §3).

Creates (or rotates the credentials of) a user with a bcrypt password and a
TOTP secret. Self-signup is intentionally NOT exposed on the web — this script
is the only way to mint the first user (and any subsequent one).

This is the Docker-free path: it runs directly against the configured database
via the backend's own session factory, so it works on a local (non-Docker)
dev box as well as inside the container. Run it with the backend venv:

    # from the repo root
    apps/backend/.venv/Scripts/python.exe scripts/create_user.py            # Windows
    apps/backend/.venv/bin/python scripts/create_user.py                    # Linux/macOS

    # inside the container (equivalent to the original docker recipe)
    docker compose exec backend python scripts/create_user.py

Flags (all optional; missing values are prompted for):
    --email EMAIL              lowercased automatically
    --display-name NAME
    --db-url URL               override WORKBENCH_DB_URL for this run

On success:
    - The user row is inserted/updated.
    - A TOTP secret is generated and marked verified (the operator just saw it).
    - A QR PNG is written to ./totp_<id>.png and the otpauth:// URI is printed.

The target database must already be migrated to head (`alembic upgrade head`)
so the password_hash / totp columns exist.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the backend package importable when run from the repo root.
_BACKEND = Path(__file__).resolve().parent.parent / "apps" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if not pw:
            print("Password cannot be empty.")
            continue
        if pw != getpass.getpass("Password again: "):
            print("Passwords don't match. Try again.")
            continue
        return pw


async def _run(email: str, display_name: str | None, password: str) -> None:
    # Imported after sys.path is set up.
    from sqlalchemy import select

    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret, make_provisioning_uri, make_qr_png_bytes
    from app.db.models.user import User
    from app.db.session import get_sessionmaker
    from app.security import CredentialKind, CredentialStore

    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalars().first()
        if existing is not None:
            print(f"User {email} already exists (id={existing.id}). Rotating password and TOTP.")
            user = existing
        else:
            user = User(email=email, display_name=display_name or None)
            session.add(user)

        user.password_hash = hash_password(password)
        # CLI bootstrap is implicitly verified: the operator just saw the secret.
        user.totp_verified_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(user)

        # P5 §4: the TOTP secret lives in the encrypted credential store, not a
        # plaintext users column. set() rotates in place for an existing user.
        totp_secret = generate_secret()
        await CredentialStore(session).set(
            user.id, CredentialKind.TOTP_SECRET, totp_secret
        )

        uri = make_provisioning_uri(totp_secret, account_name=user.email)
        out_path = Path.cwd() / f"totp_{user.id}.png"
        out_path.write_bytes(make_qr_png_bytes(uri))

        print()
        print(f"User created/updated: id={user.id} email={user.email}")
        print()
        print("TOTP otpauth URI (paste into your authenticator, or scan the QR):")
        print(f"  {uri}")
        print()
        print(f"QR code saved to: {out_path}")
        print()
        print("Scan it with your authenticator app, then log in at /login with")
        print("email + password + the current 6-digit code.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a Trading Workbench user.")
    parser.add_argument("--email")
    parser.add_argument("--display-name")
    parser.add_argument("--db-url", help="Override WORKBENCH_DB_URL for this run.")
    args = parser.parse_args()

    if args.db_url:
        os.environ["WORKBENCH_DB_URL"] = args.db_url

    email = (args.email or input("Email: ")).strip().lower()
    if not email:
        parser.error("email is required")
    display_name = args.display_name
    if display_name is None:
        display_name = input("Display name (optional): ").strip() or None
    password = _prompt_password()

    asyncio.run(_run(email, display_name, password))


if __name__ == "__main__":
    main()
