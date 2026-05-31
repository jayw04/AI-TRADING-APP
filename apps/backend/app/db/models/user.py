from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Password authentication (P5 §3). bcrypt hash, cost 12. Nullable so the
    # migration doesn't break the pre-P5 seeded user; the CLI bootstrap fills it.
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # TOTP secret moved to the encrypted credential store in P5 §4 (kind=
    # TOTP_SECRET); the plaintext users.totp_secret / users.pine_webhook_secret
    # columns were dropped by that migration. totp_verified_at stays here: it's
    # a non-secret status flag, not the secret itself. Until the user verifies
    # their TOTP setup with a current code, the secret is set in the store but
    # totp_verified_at is NULL — and login refuses.
    totp_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
