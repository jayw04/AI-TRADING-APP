"""ADR 0043 Phase-0 reachability — CLI/script façade over WP2 adjudicator.

Implementation lives in ``app.risk.loss_control.phase0_reachability`` (Controlling
Design v1.1). This module re-exports the public API so existing imports keep working.

Displayed-spread assessment is Tier D: never binding; would-be REACHABLE → INDETERMINATE.
"""

from __future__ import annotations

from app.risk.loss_control.phase0_reachability import (
    MAX_QUOTE_AGE_S,
    VERDICT_INDETERMINATE,
    VERDICT_REACHABLE,
    VERDICT_UNREACHABLE,
    VERDICT_UNREACHABLE_WITHIN_CAPS,
    Caps,
    Reachability,
    SymbolReachability,
    assess,
    price_symbol,
    remaining_to_target,
)

__all__ = [
    "Caps",
    "MAX_QUOTE_AGE_S",
    "Reachability",
    "SymbolReachability",
    "VERDICT_INDETERMINATE",
    "VERDICT_REACHABLE",
    "VERDICT_UNREACHABLE",
    "VERDICT_UNREACHABLE_WITHIN_CAPS",
    "assess",
    "price_symbol",
    "remaining_to_target",
]
