"""Stable identifiers returned by the Risk Engine for UI translation."""

from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    OK = "OK"
    MODE_MISMATCH = "MODE_MISMATCH"
    SYMBOL_DENIED = "SYMBOL_DENIED"
    SHORT_NOT_ALLOWED = "SHORT_NOT_ALLOWED"
    POSITION_CAP_QTY = "POSITION_CAP_QTY"
    POSITION_CAP_NOTIONAL = "POSITION_CAP_NOTIONAL"
    GROSS_EXPOSURE = "GROSS_EXPOSURE"
    HALT_REACHED = "HALT_REACHED"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_INPUT = "INVALID_INPUT"
    NO_LIMITS_CONFIGURED = "NO_LIMITS_CONFIGURED"
    # P5 §5 — live-mode risk gates.
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    MAX_ORDERS_PER_DAY = "MAX_ORDERS_PER_DAY"
    INSUFFICIENT_BUYING_POWER = "INSUFFICIENT_BUYING_POWER"
    # P5 §6 — live order safety (OrderRouter-level rejections, pre-risk-engine).
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    STRATEGY_COOLDOWN = "STRATEGY_COOLDOWN"
    # P5 §7 — live-path guard (replaces the §1 BrokerModeError raise).
    AGENT_LIVE_DISABLED = "AGENT_LIVE_DISABLED"
    STRATEGY_ID_REQUIRED = "STRATEGY_ID_REQUIRED"
    STRATEGY_NOT_FOUND = "STRATEGY_NOT_FOUND"
    STRATEGY_PENDING_LIVE = "STRATEGY_PENDING_LIVE"
    STRATEGY_NOT_LIVE = "STRATEGY_NOT_LIVE"
    # P6b §4.5 (ADR 0015): the global live-auto-dispatch master switch is off, so
    # a LIVE strategy's automatic order is suppressed before the broker.
    LIVE_AUTODISPATCH_DISABLED = "LIVE_AUTODISPATCH_DISABLED"
