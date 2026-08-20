"""DISC-MDQ-001 — governed MDQ microstructure enrichment for DISC-001.

Phase A: the exploration policy and the constrained reader. No feature is
computed, no DISC-001 candidate is re-ranked, and no DISC-001 admission
threshold moves — ``disc001.spec.SCREEN_VERSION`` remains ``v0.3.0``.

Research/Analytics plane (ADR 0051). Outputs are INADMISSIBLE to MDQ-001's
K1–K6 (registration §8.1 two-way evidence firewall).
"""

from app.research.disc_mdq.policy import (
    AuthorizedScope,
    MdqExplorationPolicy,
    PolicyDecision,
    PolicyError,
    ReviewWindow,
    UnauthorizedReadError,
)
from app.research.disc_mdq.reader import (
    MdqFeatureReader,
    MdqReaderError,
    PartitionIntegrityError,
    PartitionNotFrozenError,
    PartitionProvenance,
    QuoteObservation,
    ReadResult,
)
from app.research.disc_mdq.spec import (
    ENRICHMENT_UNAVAILABLE,
    POLICY_VERSION,
    PROGRAM_ID,
    READER_VERSION,
    Decision,
    ReadPurpose,
)

__all__ = [
    "ENRICHMENT_UNAVAILABLE",
    "POLICY_VERSION",
    "PROGRAM_ID",
    "READER_VERSION",
    "AuthorizedScope",
    "Decision",
    "MdqExplorationPolicy",
    "MdqFeatureReader",
    "MdqReaderError",
    "PartitionIntegrityError",
    "PartitionNotFrozenError",
    "PartitionProvenance",
    "PolicyDecision",
    "PolicyError",
    "QuoteObservation",
    "ReadPurpose",
    "ReadResult",
    "ReviewWindow",
    "UnauthorizedReadError",
]
