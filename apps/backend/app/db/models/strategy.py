"""Strategy — the registered, configurable definition of a trading strategy.

A row here is one ``(name, version, type)`` triple. The same Python file can
be registered multiple times under different parameter sets; each
registration is a distinct ``strategies`` row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import StrategyStatus, StrategyType


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.1.0")

    # P6b §2a: when set, this row is a paper-variant clone of the referenced
    # parent strategy (status=PAPER_VARIANT), spawned to validate a proposal's
    # params forward on paper (ADR 0007). NULL for normal user strategies — the
    # discriminator that hides variants from user-facing strategy lists.
    parent_strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[StrategyType] = mapped_column(
        SQLEnum(StrategyType, native_enum=False, length=16),
        nullable=False,
        default=StrategyType.PYTHON,
    )
    status: Mapped[StrategyStatus] = mapped_column(
        SQLEnum(StrategyStatus, native_enum=False, length=16),
        nullable=False,
        default=StrategyStatus.IDLE,
    )

    # For PYTHON strategies: a relative path under apps/backend/strategies_user/.
    # PINE (P4) and AGENT (P6) leave this NULL.
    code_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Per-strategy parameter overrides (merged over the strategy class's
    # default_params).
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Symbol universe this strategy may trade. Subset of (or equal to) the
    # strategy class's default symbol list.
    symbols_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Cadence: cron-ish string (e.g. "*/1 * * * *") OR the literal "event"
    # for purely event-driven strategies that only react to fills/signals.
    schedule: Mapped[str] = mapped_column(
        String(64), nullable=False, default="*/1 * * * *"
    )

    # Optional FK to a risk_limits row at STRATEGY scope. When NULL, the
    # engine falls back to the user's GLOBAL row.
    risk_limits_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_limits.id", ondelete="SET NULL"), nullable=True
    )

    # Last error text (when status == ERROR). Cleared on next successful run.
    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # P4 §4: hot-reload signaling. ``has_pending_reload`` flips True when the
    # StrategyFileWatcher detects a modification to the underlying
    # ``code_path``. The user clears it by calling ``POST /reload`` (which
    # also re-imports the module). ``server_default="0"`` keeps the column
    # populated on the SQLite upgrade for existing rows.
    has_pending_reload: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    pending_reload_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # P5 §6: short-term automatic pause after a failed order submission. When
    # set and > now(), this strategy cannot submit orders. Distinct from
    # status=HALTED (indefinite, manual restart only) and status=ERROR
    # (engine-side crash). Cooldown is a self-clearing time-based block.
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # P5 §7: when the activation wizard completed (status → PENDING_LIVE). The
    # scheduler flips PENDING_LIVE → LIVE 24h after this timestamp (ADR 0005).
    # Retained after the LIVE transition for forensic "when did this go live"
    # queries.
    live_activation_initiated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # P6b §3a-gate (ADR 0007): when this strategy was last promoted from a paper
    # variant. Defined here; §3b's promotion endpoint sets it and the 30-day
    # post-promotion lockout reads it. NULL = never promoted.
    last_promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # P6b §4 (ADR 0006 v2): distinguishes eval-harness-spawned clones from §2
    # paper-variants. "mode_a" = the running, LLM-wrapped clone; "mode_b" = the
    # IDLE source_id bucket for B's orders. NULL = a normal strategy / §2 variant.
    harness_role: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # P7 §4: how this strategy was authored — "manual" (hand-written / registered
    # by code_path), "nl_generation" (single-shot AI, P7a), "nl_refinement" (P7b),
    # or "template" (P8). Default "manual"; the authored-save endpoint sets
    # "nl_generation".
    authoring_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default="manual"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    risk_limits = relationship("RiskLimits", foreign_keys=[risk_limits_id])

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Strategy id={self.id} name={self.name!r} v={self.version} "
            f"type={self.type.value} status={self.status.value}>"
        )
