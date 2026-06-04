"""StrategyProposal — the agent's suggested change to a strategy (P6 §1a).

One row per proposal. The agent (P6) generates a proposal for a strategy; a
human reviews and accepts/rejects it; acceptance can later be APPLIED to the
strategy. §1a ships the table and the lifecycle enum only — no row is written
until §1b wires the proposal-generation path.

Schema discipline follows P5.5 §1's ``trading_profiles`` and §2's
``morning_briefs``:
  - JSON columns (``Mapped[dict[str, Any]]``) for shape flexibility; only the
    top level is validated, with defensive ``.get()`` reads on the read side.
  - Enum stored via ``SQLEnum(..., native_enum=False)`` (the NAME, UPPER), the
    same convention as ``Strategy.status``.
  - Composite-unique-per-minute on ``(strategy_id, generated_at→minute)`` so the
    agent may iterate (multiple proposals per strategy per day) while a
    same-minute double-fire is blocked.

Per Decision 3 (P6 Architectural Decisions v0.1). See the §1a validation
corrections doc for the ``sa.text(...)`` functional-index fix (correction #8).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProposalState(StrEnum):
    """The proposal lifecycle (Decision 3).

    DRAFT → REVIEWING → ACCEPTED → APPLIED, or DRAFT/REVIEWING → REJECTED
    (REJECTED has no APPLIED transition). Values == names (UPPER), matching the
    AuditAction / CredentialKind StrEnum conventions.
    """

    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    ACCEPTED = "ACCEPTED"
    # P6b §2a: paper-variant validation in flight (ADR 0007). ACCEPTED →
    # EVALUATING on spawn; → REJECTED on stop/supersede/expiry. §3 adds the
    # EVIDENCE_READY → PROMOTING → PROMOTED promotion path.
    EVALUATING = "EVALUATING"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"
    # P6b §3a-gate (ADR 0007): the 4-criterion promotion gate passed at least
    # once → the evidence bundle is ready for the user's promote decision
    # (sticky; doesn't roll back). §3b adds PROMOTING (24h cooldown in progress)
    # → PROMOTED (variant live). All fit the length=16 column.
    EVIDENCE_READY = "EVIDENCE_READY"
    PROMOTING = "PROMOTING"
    PROMOTED = "PROMOTED"


class StrategyProposal(Base):
    __tablename__ = "strategy_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized for fast tenant filtering (same pattern as morning_briefs).
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    state: Mapped[ProposalState] = mapped_column(
        SQLEnum(ProposalState, native_enum=False, length=16),
        nullable=False,
        default=ProposalState.DRAFT,
    )

    # Decision 3: JSON columns for shape flexibility. §1a creates the columns;
    # §1b is the first session that writes content into them.
    proposal_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    evidence_bundle_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    evaluation_results_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_proposals_strategy_id", "strategy_id"),
        Index("ix_proposals_user_id", "user_id"),
        Index("ix_proposals_user_state", "user_id", "state"),
        # Composite-unique-per-minute (Decision 3). ``generated_at`` MUST be a
        # column reference, so it goes through sa.text(...) — passing the bare
        # string "generated_at" to func.strftime would index a constant string
        # literal (correction #8). SQLite-only; a Postgres move swaps strftime →
        # date_trunc and this becomes a generated column.
        Index(
            "ix_proposals_strategy_minute_unique",
            "strategy_id",
            text("strftime('%Y-%m-%d %H:%M', generated_at)"),
            unique=True,
        ),
    )
