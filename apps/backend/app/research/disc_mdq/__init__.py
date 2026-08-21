"""DISC-MDQ-001 — governed MDQ microstructure enrichment for DISC-001.

Phase A: the exploration policy, the constrained reader, and the append-only
discovery ledger that both bind to. No feature is computed, no DISC-001
candidate is re-ranked, and no DISC-001 admission threshold moves —
``disc001.spec.SCREEN_VERSION`` remains ``v0.3.0``.

Research/Analytics plane (ADR 0051). Outputs are INADMISSIBLE to MDQ-001's
K1–K6 (registration §8.1 two-way evidence firewall).
"""

from app.research.disc_mdq.ledger import (
    CodeIdentity,
    DiscoveryLedger,
    LedgerError,
    LedgerEvent,
    LedgerInitError,
    LedgerIntegrityError,
    LedgerRecord,
    LedgerRecordError,
    conditions_examined,
)
from app.research.disc_mdq.policy import (
    ArtifactAttestation,
    AuthorizedScope,
    MdqExplorationPolicy,
    PolicyDecision,
    PolicyError,
    ReviewWindow,
    UnauthorizedReadError,
    verify_governed_artifacts,
)
from app.research.disc_mdq.reader import (
    MdqFeatureReader,
    MdqReaderError,
    PartitionIntegrityError,
    PartitionNotFrozenError,
    PartitionProvenance,
    QuoteObservation,
    ReadResult,
    UnledgeredReadError,
)
from app.research.disc_mdq.spec import (
    ENRICHMENT_UNAVAILABLE,
    LEDGER_VERSION,
    POLICY_VERSION,
    PROGRAM_ID,
    READER_VERSION,
    Decision,
    ReadPurpose,
)

__all__ = [
    "ENRICHMENT_UNAVAILABLE",
    "LEDGER_VERSION",
    "POLICY_VERSION",
    "PROGRAM_ID",
    "READER_VERSION",
    "ArtifactAttestation",
    "AuthorizedScope",
    "CodeIdentity",
    "Decision",
    "DiscoveryLedger",
    "LedgerError",
    "LedgerEvent",
    "LedgerInitError",
    "LedgerIntegrityError",
    "LedgerRecord",
    "LedgerRecordError",
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
    "UnledgeredReadError",
    "conditions_examined",
    "verify_governed_artifacts",
]
