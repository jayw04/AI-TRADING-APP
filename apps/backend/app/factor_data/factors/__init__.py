"""Deterministic factor computation over the P9 §1 PIT spine.

Prices-only for v1 (price momentum). No order path, no broker, no DB session, no
LLM (ADR 0006 v2) — these are pure functions of survivorship-free adjusted prices
from `FactorDataStore`.
"""

from app.factor_data.factors.engine import FactorUnavailable, momentum_scores
from app.factor_data.factors.momentum import compute_momentum, compute_momentum_batch

__all__ = [
    "FactorUnavailable",
    "compute_momentum",
    "compute_momentum_batch",
    "momentum_scores",
]
