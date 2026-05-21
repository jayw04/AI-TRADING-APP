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
