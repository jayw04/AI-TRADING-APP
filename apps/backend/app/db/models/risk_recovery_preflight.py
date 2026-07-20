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

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskRecoveryPreflight(Base):
    """One recovery attempt (§D5): its request, durable origin, aggregate verdict, authority, and
    transition outcome. PR1 landed the table; PR6 fills the workflow columns.

    Vocabulary lives in ``app/risk/loss_control/constants.py``. Three DISTINCT axes are preserved
    (never conflated): ``status`` (the workflow lifecycle), ``aggregate_verdict`` (the 12-check
    fail-closed result), and the transition-commit outcome (``transition_event_id`` set == the
    PREFLIGHT_* transition committed; ``failure_reason`` = a stable code when it did not).
    """

    __tablename__ = "risk_recovery_preflights"
    __table_args__ = (
        Index("ix_risk_recovery_preflights_account_created", "account_id", "created_at"),
        # Idempotency: one preflight per (account, client key). A retry loads the same row.
        UniqueConstraint(
            "account_id", "idempotency_key", name="uq_risk_recovery_preflight_account_idem"
        ),
        # At most one ACTIVE preflight per account — enforced by a partial unique index created in
        # the migration (SQLite WHERE status IN active-set), not expressible as a plain constraint.
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    # --- request / idempotency ---------------------------------------------------------------
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # The transition this recovery targets ("RECOVERY_REQUEST"), and the state version it was
    # computed against (an idempotency guard — a request naming a stale version is not applied).
    requested_transition: Mapped[str] = mapped_column(String(48), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # OWNER | RISK_OPERATOR | SYSTEM — who REQUESTED (permission to request ≠ permission to pass).
    requested_by_actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- durable recovery origin (§D5 — the from_state of the committed RECOVERY_REQUEST event) --
    origin_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    origin_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The event that entered RECOVERY_PREFLIGHT — the durable provenance of the origin.
    request_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_control_events.id", ondelete="SET NULL"), nullable=True
    )

    # The trip being recovered from (drives the authority decision).
    trip_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trip_cause: Mapped[str | None] = mapped_column(String(48), nullable=True)

    # --- verdict / authority / status --------------------------------------------------------
    # PASS | FAIL | INCOMPLETE — the fail-closed aggregate of the 12 checks (immutable once set).
    aggregate_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The authority class required to pass (owner/operator/human/repair-first…).
    authority_class: Mapped[str] = mapped_column(String(32), nullable=False)
    authorized_by_actor_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    authorized_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Workflow lifecycle: REQUESTED|RUNNING|PASSED|FAILED|INCOMPLETE|AUTHORIZATION_REQUIRED|COMMIT_FAILED
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    # Legacy mirror of ``status`` (the PR1 column was NOT NULL). Kept in sync; ``status`` is
    # authoritative.
    result: Mapped[str] = mapped_column(String(24), nullable=False)

    # --- transition outcome (distinct from the verdict) --------------------------------------
    # The PREFLIGHT_PASS / PREFLIGHT_FAIL event; set == that transition committed.
    transition_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_control_events.id", ondelete="SET NULL"), nullable=True
    )
    # A stable ERR_* / BLOCKED code when the workflow did not complete a clean pass (never raw text).
    failure_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)

    initiator_type: Mapped[str] = mapped_column(String(16), nullable=False)
    initiator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
