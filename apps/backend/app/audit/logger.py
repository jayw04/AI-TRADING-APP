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
    # ADR 0043 PR4 — the persisted loss-control state machine contributed to a rejection in ENFORCE
    # mode. Durable provenance (state, version, outcome, mode, verified-reduction) in the payload.
    LOSS_CONTROL_ENFORCED = "LOSS_CONTROL_ENFORCED"

    # ---- Operations & Reliability (P11 §3) ----
    # Recorded when reconciliation finds the broker's reality diverges from local state
    # (or an automation's intended vs achieved). ALERT-ONLY — never triggers a corrective
    # order (ADR 0021 property 4). See docs/runbook/on-call.md.
    RECONCILIATION_DISCREPANCY = "RECONCILIATION_DISCREPANCY"

    # ---- Operations & Reliability (P11 §4) ----
    # Recorded when replay finds a logged automated decision does NOT reproduce from its
    # recorded inputs (the recorded decision is not justified by its recorded evidence).
    # Read-only verification — never triggers any order (ADR 0021). CRITICAL severity.
    # See docs/runbook/on-call.md.
    REPLAY_MISMATCH = "REPLAY_MISMATCH"

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
    # P6b §1a-drift: a live strategy's recent behavior diverged from its
    # backtest baseline beyond the user's drift_thresholds. One row per drifted
    # strategy per detection run (written only when drift fires, on the
    # morning-brief cadence). Advisory — surfaces the divergence; takes no
    # action. Payload carries the breached metric(s) + live/baseline values.
    STRATEGY_DRIFT_DETECTED = "STRATEGY_DRIFT_DETECTED"
    # P6 §2b-review: the user submitted a thumbs-up/down review for a proposal
    # that the weekly 10%-sampling cron queued (Decision 8 human-review
    # supplement). Payload carries {proposal_id, rating, reason}. The sampling
    # sweep itself is silent (routine maintenance); only the user's review is
    # the meaningful, audit-worthy event.
    PROPOSAL_REVIEW_RECORDED = "PROPOSAL_REVIEW_RECORDED"
    # P6b §2a: a paper-variant strategy clone was spawned to validate a
    # proposal's params forward on paper (ADR 0007). Payload carries
    # {proposal_id, parent_strategy_id, variant_strategy_id}.
    PAPER_VARIANT_SPAWNED = "PAPER_VARIANT_SPAWNED"
    # P6b §2a: a running paper-variant was terminated (user stop / superseded /
    # parent params changed / 90-day expiry). Payload carries {reason,
    # parent_strategy_id}.
    PAPER_VARIANT_TERMINATED = "PAPER_VARIANT_TERMINATED"
    # P6b §3a-gate (ADR 0007): defined here; WRITTEN by §3b's promotion endpoint
    # when a paper variant is promoted live after the 24h cooldown. §3a's gate
    # only writes STRATEGY_PROPOSAL_TRANSITIONED (EVALUATING → EVIDENCE_READY).
    STRATEGY_PROMOTED = "STRATEGY_PROMOTED"
    # P6b §4 (ADR 0006 v2): an LLM eval harness was started for a strategy (Mode
    # A + Mode B spawned). Stop/terminate is a state change on the harness row
    # (no separate action). Per-signal decisions live in eval_harness_decisions,
    # NOT the hash chain (volume).
    EVAL_HARNESS_STARTED = "EVAL_HARNESS_STARTED"

    # P6b §4.5 (ADR 0015): operator flip of the global live-auto-dispatch master
    # switch. Suppressed live orders (switch off) are logged, not audited (a
    # spinning live strategy would flood the chain — cf. STRATEGY_COOLDOWN).
    LIVE_AUTODISPATCH_ENABLED_CHANGED = "LIVE_AUTODISPATCH_ENABLED_CHANGED"

    # P6b §5 (ADR 0006 v2 §5): LLM-driven LIVE trading opt-in. Initiated (7-day
    # cooldown starts) / Activated (cooldown elapsed, LLM gate live) / opted out.
    # LLM_LIVE_DECISION audits EVERY live LLM act/skip with the full prompt +
    # response + deterministic baseline + outcome (ADR line 79 — forensic) and is
    # the source the per-user daily budget sums; the live volume is low (one
    # opted-in strategy) so the hash chain is the single record.
    LLM_OPT_IN_INITIATED = "LLM_OPT_IN_INITIATED"
    LLM_OPT_IN_ACTIVATED = "LLM_OPT_IN_ACTIVATED"
    LLM_OPT_OUT = "LLM_OPT_OUT"
    LLM_LIVE_DECISION = "LLM_LIVE_DECISION"

    # P7 §2 (NL → Python authoring): one row per strategy-generation request, with
    # the full prompt context + the generated code/assumptions/explanation + cost
    # (forensic capture of every AI authoring call). The per-user authoring budget
    # sums cost_usd from these rows.
    STRATEGY_GENERATED = "STRATEGY_GENERATED"

    # P8 §2 (Discovery scanner): one row per scan run, capturing the criterion +
    # universe + matched symbols so "why did this symbol appear" is
    # reconstructible from the criterion alone (P8 Decision 1). Read-only scan;
    # no orders, no state change beyond the scanner_runs row.
    SCANNER_RUN = "SCANNER_RUN"


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
