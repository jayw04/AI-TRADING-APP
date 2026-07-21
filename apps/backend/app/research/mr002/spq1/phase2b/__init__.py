"""SPQ-1 Phase 2B — development-period signal-production run engine (2B-1 onward).

New package (kept OUT of spq1/ and spq1/adapters/ so the ratified 2B-0 InputIdentityManifest module
hashes remain unchanged). Binds the registered owner-countersigned sic_mapping for SIC->sector->ETF
(superseding the Phase-2A pit_sector placeholder) WITHOUT modifying any closed module. Every unit
(permanent_security_id x decision_session) receives exactly one terminal disposition; no signal value
is ranked or interpreted.
"""
from __future__ import annotations

RUN_ID = "MR002-SPQ1-P2B-DEV-V1"
# The run-spec hash lives ONLY in the artifacts (not in hashed code) to avoid a self-referential
# code-identity loop; the runner reads it from the RunSpecification.

# Terminal dispositions (exactly one per unit).
EMITTED = "SIGNAL_DECISION_RECORD_EMITTED"
INELIGIBLE = "INELIGIBLE"
INTEGRITY_STOP = "INTEGRITY_STOP"
REFUSED = "REFUSED_CODE_OR_DATA_IDENTITY"

DISPOSITION_BY_CLASS = {
    "INELIGIBLE": INELIGIBLE,
    "INTEGRITY_STOP": INTEGRITY_STOP,
    "REFUSED_CODE_OR_DATA_IDENTITY": REFUSED,
}
