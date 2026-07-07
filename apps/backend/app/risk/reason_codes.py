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
    NON_FRACTIONABLE_SUB_SHARE = "NON_FRACTIONABLE_SUB_SHARE"  # fractional qty on a non-fractionable asset floored to 0 whole shares
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
    # P6b §5 (ADR 0006 v2 §5): an opted-in strategy's LLM gate declined to fire
    # this order (act/skip → skip). The deterministic strategy wanted it; the LLM
    # suppressed it.
    LLM_SKIPPED = "LLM_SKIPPED"
    # §9A.3 (design doc): defense-in-depth market-session gate. The order's
    # account/strategy is not permitted to trade in the current session — the
    # market is CLOSED (overnight/weekend/holiday), or it is pre/after-market
    # and the order did not opt into extended hours. Fails closed: an
    # unknown/unclassifiable session also rejects with this code.
    MARKET_SESSION_CLOSED = "MARKET_SESSION_CLOSED"
