"""MDQ-001 market-data acquisition (Option 2A, owner ruling 2026-08-15).

Account 7 is the platform's single SIP acquisition identity. The collector in
this package captures raw SIP + paired IEX observations over REST (Phase A —
no websocket; streaming arrives with Phase B/K2) and persists them into an
immutable, time-partitioned local store on the governed AWS host. MDQ-001 and
every other consumer read frozen partitions only; nothing here touches the
order path, and per ADR 0051 this research-plane package holds no broker
mutation capability.

See docs/design/MDQ-001_Registration_v1_0_DRAFT.md §6–§7 for the governing
controls (single acquisition identity, raw-first, provenance, freeze,
subordinate ceiling).
"""

from app.research.capture.admissibility import (
    MAX_CONTIGUOUS_GAP_MINUTES,
    MIN_COMPLETENESS,
    AdmissibilityReport,
    ConditionResult,
    Outcome,
    Verdict,
    assess_partition,
)
from app.research.capture.collector import (
    PHASE_A_UNIVERSE,
    fetch_session_bars,
    sample_quotes_cycle,
)
from app.research.capture.identity import (
    AcquisitionPins,
    IdentityError,
    key_fingerprint,
    verify_identity,
)
from app.research.capture.store import (
    COLLECTOR_VERSION,
    CaptureStore,
    FrozenPartitionError,
    PartitionRef,
)

__all__ = [
    "COLLECTOR_VERSION",
    "MAX_CONTIGUOUS_GAP_MINUTES",
    "MIN_COMPLETENESS",
    "PHASE_A_UNIVERSE",
    "AcquisitionPins",
    "AdmissibilityReport",
    "CaptureStore",
    "ConditionResult",
    "FrozenPartitionError",
    "IdentityError",
    "Outcome",
    "PartitionRef",
    "Verdict",
    "assess_partition",
    "fetch_session_bars",
    "key_fingerprint",
    "sample_quotes_cycle",
    "verify_identity",
]
