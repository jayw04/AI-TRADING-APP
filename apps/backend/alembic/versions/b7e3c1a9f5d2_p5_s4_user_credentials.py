"""P5 s4: user_credentials table + data migration

Moves four secret families into the encrypted credential store and drops
the plaintext columns:
  - users.totp_secret        -> user_credentials(kind=totp_secret)
  - users.pine_webhook_secret -> user_credentials(kind=pine_webhook_secret)
  - env ALPACA_* / ANTHROPIC_API_KEY -> user_credentials for user_id=1 (best-effort)

Requires WORKBENCH_MASTER_KEY in the environment at migration time — the
data move encrypts each secret with Fernet. The migration fails loudly if
the key is absent rather than leaving a half-migrated DB (see Gotcha #2).

Revision ID: b7e3c1a9f5d2
Revises: 8c1e26e3d0a6
Create Date: 2026-05-31

"""
import os
from collections.abc import Sequence
from datetime import datetime, UTC

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet


# revision identifiers, used by Alembic.
revision: str = 'b7e3c1a9f5d2'
down_revision: str | Sequence[str] | None = '8c1e26e3d0a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fernet() -> Fernet:
    key = os.environ.get("WORKBENCH_MASTER_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "WORKBENCH_MASTER_KEY env var required for the P5 §4 migration. "
            "Run scripts/generate_master_key.py and set it in .env BEFORE upgrade."
        )
    return Fernet(key.encode("ascii"))


def upgrade() -> None:
    """Upgrade schema."""
    # 0) Acquire the master key BEFORE any DDL — a missing key must abort with
    # zero schema changes rather than leaving a half-migrated DB (Gotcha #2).
    fernet = _fernet()

    # 1) Create user_credentials table
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_user_credentials_user_id_users"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_credentials")),
    )
    with op.batch_alter_table("user_credentials", schema=None) as batch_op:
        batch_op.create_index(
            "ix_user_credentials_user_kind", ["user_id", "kind"], unique=False
        )
        batch_op.create_index(
            "ix_user_credentials_revoked_at", ["revoked_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_user_credentials_user_id"), ["user_id"], unique=False
        )

    # 2) Data migration — encrypt each secret with the master key acquired above.
    now = datetime.now(UTC)
    bind = op.get_bind()

    # Move TOTP secrets (any user with a non-null totp_secret).
    totp_rows = bind.execute(
        sa.text("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL")
    ).fetchall()
    for user_id, secret in totp_rows:
        ct = fernet.encrypt(secret.encode("utf-8"))
        bind.execute(
            sa.text(
                "INSERT INTO user_credentials "
                "(user_id, kind, ciphertext, created_at, updated_at) "
                "VALUES (:uid, :kind, :ct, :ts, :ts)"
            ),
            {"uid": user_id, "kind": "totp_secret", "ct": ct, "ts": now},
        )

    # Move Pine webhook secrets.
    pine_rows = bind.execute(
        sa.text(
            "SELECT id, pine_webhook_secret FROM users "
            "WHERE pine_webhook_secret IS NOT NULL"
        )
    ).fetchall()
    for user_id, secret in pine_rows:
        ct = fernet.encrypt(secret.encode("utf-8"))
        bind.execute(
            sa.text(
                "INSERT INTO user_credentials "
                "(user_id, kind, ciphertext, created_at, updated_at) "
                "VALUES (:uid, :kind, :ct, :ts, :ts)"
            ),
            {"uid": user_id, "kind": "pine_webhook_secret", "ct": ct, "ts": now},
        )

    # Best-effort: capture env-var broker + Anthropic keys for user_id=1
    # (the bootstrap user). Multi-user deployments capture nothing here;
    # users set their own credentials via the UI after upgrade.
    has_user_1 = bind.execute(
        sa.text("SELECT 1 FROM users WHERE id = 1")
    ).fetchone()
    if has_user_1:
        env_map = {
            "alpaca_paper_key": os.environ.get("ALPACA_PAPER_API_KEY"),
            "alpaca_paper_secret": os.environ.get("ALPACA_PAPER_API_SECRET"),
            "alpaca_live_key": os.environ.get("ALPACA_LIVE_API_KEY"),
            "alpaca_live_secret": os.environ.get("ALPACA_LIVE_API_SECRET"),
            "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
        }
        for kind, value in env_map.items():
            if value:
                ct = fernet.encrypt(value.encode("utf-8"))
                bind.execute(
                    sa.text(
                        "INSERT INTO user_credentials "
                        "(user_id, kind, ciphertext, created_at, updated_at) "
                        "VALUES (1, :kind, :ct, :ts, :ts)"
                    ),
                    {"kind": kind, "ct": ct, "ts": now},
                )

    # 3) Drop the old plaintext columns now the data is moved.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_pine_webhook_secret"))
        batch_op.drop_column("totp_secret")
        batch_op.drop_column("pine_webhook_secret")


def downgrade() -> None:
    """Emergency rollback. Restores plaintext columns; treat as a
    'data is leaked' state and rotate every credential immediately."""
    # Acquire the master key first — we need it to decrypt before restoring.
    fernet = _fernet()

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("totp_secret", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("pine_webhook_secret", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_users_pine_webhook_secret"),
            ["pine_webhook_secret"],
            unique=True,
        )

    bind = op.get_bind()

    totp = bind.execute(
        sa.text(
            "SELECT user_id, ciphertext FROM user_credentials "
            "WHERE kind = 'totp_secret' AND revoked_at IS NULL"
        )
    ).fetchall()
    for user_id, ct in totp:
        pt = fernet.decrypt(ct).decode("utf-8")
        bind.execute(
            sa.text("UPDATE users SET totp_secret = :pt WHERE id = :uid"),
            {"pt": pt, "uid": user_id},
        )

    pine = bind.execute(
        sa.text(
            "SELECT user_id, ciphertext FROM user_credentials "
            "WHERE kind = 'pine_webhook_secret' AND revoked_at IS NULL"
        )
    ).fetchall()
    for user_id, ct in pine:
        pt = fernet.decrypt(ct).decode("utf-8")
        bind.execute(
            sa.text("UPDATE users SET pine_webhook_secret = :pt WHERE id = :uid"),
            {"pt": pt, "uid": user_id},
        )

    with op.batch_alter_table("user_credentials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_credentials_user_id"))
        batch_op.drop_index("ix_user_credentials_revoked_at")
        batch_op.drop_index("ix_user_credentials_user_kind")
    op.drop_table("user_credentials")
