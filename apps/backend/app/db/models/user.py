from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pine_webhook_secret: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    # Password authentication (P5 §3). bcrypt hash, cost 12. Nullable so the
    # migration doesn't break the pre-P5 seeded user; the CLI bootstrap fills it.
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # TOTP secret (RFC 6238). Plaintext for P5 §3; P5 §4 wraps it in Fernet
    # encryption when the credential store ships (column renamed then).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Until the user verifies their TOTP setup with a current code, totp_secret
    # is set but totp_verified_at is NULL — and login refuses.
    totp_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
