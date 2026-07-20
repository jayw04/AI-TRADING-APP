"""ADR 0043 §D5 — a recovery preflight (the checked, authority-gated path out of a lock).

WHY THIS TABLE EXISTS
---------------------
Recovery today is a reflexive reset: an owner types the account label and
``circuit_breaker_tripped_at`` is cleared. Nothing verifies the world is safe to resume, and the
incident rulings forbid reflexive resets precisely because no such check exists.

ADR 0043 replaces that with a preflight whose **result is immutable**: a `PREFLIGHT_PASS` /
`PREFLIGHT_FAIL` / `PREFLIGHT_INCOMPLETE` verdict, with every individual check and its evidence
recorded in ``risk_recovery_preflight_checks``. Authority is class-dependent (an artifact trip may
self-heal after a full PASS; a real-loss trip needs a human; a broker/integrity trip must be
*repaired*, not approved). A successful preflight grants only the transition into
``RECOVERY_COOLDOWN`` — recovery is not "trading resumes".

IDEMPOTENCY
-----------
A recovery request carries ``expected_state_version`` (and, via the checks, the transition it
targets). A duplicate or replayed request naming a stale version is ignored, not re-applied — a
stale preflight can never authorize a later reset.

PR 1 lands the table only; the preflight logic and API arrive in a later increment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskRecoveryPreflight(Base):
    """One recovery attempt: its requested transition, authority class, and immutable verdict."""

    __tablename__ = "risk_recovery_preflights"
    __table_args__ = (
        Index(
            "ix_risk_recovery_preflights_account_created", "account_id", "created_at"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    # The transition this recovery targets, and the state version it was computed against
    # (the idempotency guard — a request naming a stale version is ignored).
    requested_transition: Mapped[str] = mapped_column(String(48), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # The trip being recovered from (drives the authority class).
    trip_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trip_cause: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # ARTIFACT_AUTO | HUMAN_REQUIRED | REPAIR_FIRST | MANUAL_SAME_OR_HIGHER.
    authority_class: Mapped[str] = mapped_column(String(32), nullable=False)

    # PREFLIGHT_PASS | PREFLIGHT_FAIL | PREFLIGHT_INCOMPLETE — immutable once written.
    result: Mapped[str] = mapped_column(String(20), nullable=False)

    # SYSTEM (self-heal) | USER — who initiated the recovery.
    initiator_type: Mapped[str] = mapped_column(String(16), nullable=False)
    initiator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
