"""DISC-001 Phase-1 SEP product surface (candidate watchlist).

Research/Analytics plane (ADR 0051). Produces display candidates only — never
signals, never orders, never strategy-state mutation. Frozen product-admission
rules live in ``spec``; the pure engine in ``engine``; I/O in ``adapter`` /
``snapshot``.
"""

from app.research.disc001.spec import (
    LEDGER_ENTRY_0,
    SCREEN_ID,
    SCREEN_VERSION,
    EvidenceStatus,
    FamilyId,
)

__all__ = [
    "EvidenceStatus",
    "FamilyId",
    "LEDGER_ENTRY_0",
    "SCREEN_ID",
    "SCREEN_VERSION",
]
