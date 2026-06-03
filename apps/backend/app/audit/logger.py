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

    # ---- Live order safety (P5 §6) ----
    # Recorded for every LIVE order submission attempt, regardless of outcome.
    # Paper submissions are NOT audited here (the orders table is their trail).
    LIVE_ORDER_SUBMITTED = "LIVE_ORDER_SUBMITTED"
    STRATEGY_COOLDOWN_CLEARED = "STRATEGY_COOLDOWN_CLEARED"

    # ---- Activation lifecycle (P5 §7) ----
    STRATEGY_ACTIVATION_INITIATED = "STRATEGY_ACTIVATION_INITIATED"
    STRATEGY_ACTIVATION_CANCELED = "STRATEGY_ACTIVATION_CANCELED"
    STRATEGY_LIVE_ACTIVATED = "STRATEGY_LIVE_ACTIVATED"
    STRATEGY_DEACTIVATED = "STRATEGY_DEACTIVATED"
    LIVE_ACCOUNT_CREATED = "LIVE_ACCOUNT_CREATED"

    # ---- Trader preferences (P5.5 §1) ----
    # Soft-preferences profile edit. Payload carries an old/new diff of the
    # changed JSON sections; replay all entries for a user to reconstruct.
    TRADING_PROFILE_UPDATED = "TRADING_PROFILE_UPDATED"

    # ---- Morning brief (P5.5 §2) ----
    # One row per generated brief (scheduled or manual). Payload carries brief
    # metadata + the LLM cost record (model/tokens/cents) when the optional
    # Haiku narration ran — the platform's first sustained LLM cost surface.
    MORNING_BRIEF_GENERATED = "MORNING_BRIEF_GENERATED"

    # ---- Agent autonomy (P6 §1a) ----
    # A strategy_proposal moved between lifecycle states (Decision 3). Payload
    # carries an old/new diff (§1 shape), so replaying reconstructs the path
    # DRAFT → REVIEWING → ACCEPTED/REJECTED → APPLIED.
    STRATEGY_PROPOSAL_TRANSITIONED = "STRATEGY_PROPOSAL_TRANSITIONED"
    # The agent's LLM call failed (timeout/refusal/parse/schema). The proposal
    # is dropped, not retried (Decision 7); payload carries error_type + context.
    AGENT_LLM_CALL_FAILED = "AGENT_LLM_CALL_FAILED"
    # A pre-call budget check rejected an agent LLM invocation (Decision 6 hard
    # cap). Payload carries the rejected estimate, the running 24h spend, and the
    # envelope.
    AGENT_BUDGET_REJECTED = "AGENT_BUDGET_REJECTED"
    # P6 §2a: a scheduled (opt-in) proposal-cadence cron fired for a user. One
    # row per strategy per fire (or one for no_api_key). Payload carries
    # {strategy_id, cadence, outcome, estimated_cost_cents, details, proposal_id}.
    # Distinct from AGENT_BUDGET_REJECTED (user-driven reject) so "what did my
    # cron do?" is a single-action query.
    AGENT_CADENCE_FIRED = "AGENT_CADENCE_FIRED"
    # P6 §2b-review: the user submitted a thumbs-up/down review for a proposal
    # that the weekly 10%-sampling cron queued (Decision 8 human-review
    # supplement). Payload carries {proposal_id, rating, reason}. The sampling
    # sweep itself is silent (routine maintenance); only the user's review is
    # the meaningful, audit-worthy event.
    PROPOSAL_REVIEW_RECORDED = "PROPOSAL_REVIEW_RECORDED"


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
