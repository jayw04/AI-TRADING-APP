"""Promotion layer: the lifecycle-aware gate + confidence score (P10 Phase 2 §3)."""

from app.research.promotion.gate import (
    BOOK_BACKTEST_PROFILE,
    FACTOR_IC_PROFILE,
    PROFILES,
    Criterion,
    GateProfile,
    GateResult,
    evaluate,
    gate_experiment,
    ge,
    le,
    predicate,
)

__all__ = [
    "Criterion",
    "GateProfile",
    "GateResult",
    "evaluate",
    "gate_experiment",
    "ge",
    "le",
    "predicate",
    "PROFILES",
    "BOOK_BACKTEST_PROFILE",
    "FACTOR_IC_PROFILE",
]
