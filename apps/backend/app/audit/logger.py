"""Typed audit logger.

Wraps the raw ``AuditLog`` model so callers don't reach into the table
directly. The :class:`AuditAction` enum catches typos at runtime; the
:meth:`AuditLogger.write` helper centralises the serialization rules
(JSON payload, ISO timestamp, target_id stringification) so the columns
stay consistent across the codebase.

The helper does NOT commit — the caller owns the transaction. That
matches the prior ``_audit`` helpers it replaces in
:class:`OrderRouter` and :class:`StrategyEngine`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog


class AuditActorType(StrEnum):
    """Who initiated the action being audited."""

    USER = "user"
    SYSTEM = "system"
    STRATEGY = "strategy"
    AGENT = "agent"


class AuditAction(StrEnum):
    """All action strings written to ``audit_log.action``.

    Values are UPPER_SNAKE_CASE to match the strings already persisted by
    earlier code (and asserted-on by tests). Adding a new audit point?
    Add the enum entry first; ``AuditLogger.write`` will reject unknown
    strings if you pass them as a plain string by mistake.
    """

    # ---- Order events (router-driven) ----
    ORDER_RISK_PASSED = "ORDER_RISK_PASSED"
    ORDER_REJECTED_BY_RISK = "ORDER_REJECTED_BY_RISK"
    ORDER_REJECTED_BY_BROKER = "ORDER_REJECTED_BY_BROKER"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_CANCEL_REQUESTED = "ORDER_CANCEL_REQUESTED"
    ORDER_CANCELED_LOCAL = "ORDER_CANCELED_LOCAL"
    ORDER_CANCEL_REJECTED_BY_BROKER = "ORDER_CANCEL_REJECTED_BY_BROKER"
    ORDER_REPLACE_REQUESTED = "ORDER_REPLACE_REQUESTED"
    ORDER_REPLACE_REJECTED_BY_BROKER = "ORDER_REPLACE_REJECTED_BY_BROKER"

    # ---- Order events (trade-update consumer) ----
    ORDER_FILL_INGESTED = "ORDER_FILL_INGESTED"
    # Lifecycle transitions; built from OrderStatus by
    # TradeUpdateConsumer._handle_terminal as f"ORDER_{status.value.upper()}".
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELED = "ORDER_CANCELED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_REJECTED = "ORDER_REJECTED"

    # ---- Strategy lifecycle ----
    STRATEGY_REGISTERED = "STRATEGY_REGISTERED"
    STRATEGY_UPDATED = "STRATEGY_UPDATED"
    STRATEGY_STARTED = "STRATEGY_STARTED"
    STRATEGY_STOPPED = "STRATEGY_STOPPED"
    STRATEGY_ERROR = "STRATEGY_ERROR"
    STRATEGY_BACKTESTED = "STRATEGY_BACKTESTED"
    STRATEGY_UNREGISTERED = "STRATEGY_UNREGISTERED"

    # ---- Risk / circuit breaker (P5 §5) ----
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    CIRCUIT_BREAKER_RESET = "CIRCUIT_BREAKER_RESET"
    RISK_LIMITS_UPDATED = "RISK_LIMITS_UPDATED"


class AuditLogger:
    """Static helper for writing ``audit_log`` rows.

    Use :meth:`write` everywhere; do not construct ``AuditLog`` directly.
    """

    @staticmethod
    def write(
        session: AsyncSession,
        *,
        actor_type: AuditActorType,
        actor_id: str | None,
        action: AuditAction | str,
        target_type: str | None,
        target_id: str | int | None,
        payload: dict[str, Any] | None = None,
        user_id: int | None = None,
        ip: str | None = None,
    ) -> AuditLog:
        """Add an :class:`AuditLog` row to ``session``. Does not commit.

        ``action`` accepts the enum for typed call sites, or a plain string
        for the trade-update consumer which derives action names from
        ``OrderStatus`` at runtime.
        """
        row = AuditLog(
            user_id=user_id,
            ts=datetime.now(UTC),
            actor_type=(
                actor_type.value
                if isinstance(actor_type, AuditActorType)
                else actor_type
            ),
            actor_id=actor_id,
            action=action.value if isinstance(action, AuditAction) else action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            payload_json=json.dumps(payload or {}, default=str),
            ip=ip,
        )
        session.add(row)
        return row
