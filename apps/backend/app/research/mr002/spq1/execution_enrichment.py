"""Session-t+1 execution enrichment (SIG-22/26/27 §13; Correction 3).

Appends the official next-open price, applies the frozen gap test, records the missing-open
disposition, and sets execution admissibility. It reads the decision record but recomputes NONE of
its facts (z / sigma / beta / sector / eligibility / ADV / side / configuration / decision session);
``verify_decision_unchanged`` proves the bound decision record was not mutated. Missing-open
behavior matches the closed Increment-2/3 contract: a missing entry open cancels.
"""
from __future__ import annotations

import math

from .models import (
    ADMISSIBLE,
    CANCELLED_GAP,
    CANCELLED_MISSING_OPEN,
    ExecutionEnrichedCandidateRecord,
    SignalDecisionRecord,
)

__all__ = ["GAP_THRESHOLD", "enrich_decision"]

GAP_THRESHOLD = 0.06  # |AdjOpen_t+1 / AdjClose_t - 1| >= 6% cancels (frozen §4)


def enrich_decision(
    decision: SignalDecisionRecord,
    scheduled_execution_session: int,
    official_next_open_price: float | None,
    distribution_adjusted_close_t: float,
    enrichment_timestamp: str = "",
) -> ExecutionEnrichedCandidateRecord:
    """Build the enriched record for t+1 without mutating any decision fact."""
    if official_next_open_price is None or not math.isfinite(official_next_open_price):
        price = float("nan")
        status = CANCELLED_MISSING_OPEN
        gap_result = "NOT_EVALUATED_MISSING_OPEN"
        disposition = "cancel entry (missing official open); exits would defer (Increment-2/3)"
    else:
        price = float(official_next_open_price)
        ratio = abs(price / distribution_adjusted_close_t - 1.0)
        if ratio >= GAP_THRESHOLD:
            status = CANCELLED_GAP
            gap_result = "EXCEEDED"
        else:
            status = ADMISSIBLE
            gap_result = "PASSED"
        disposition = "official open present"
    enriched = ExecutionEnrichedCandidateRecord(
        decision_record_canonical=decision.canonical(),
        decision_record_identity=decision.record_identity,
        scheduled_execution_session=scheduled_execution_session,
        official_next_open_price=price,
        execution_admissibility_status=status,
        gap_filter_result=gap_result,
        missing_open_disposition=disposition,
        enrichment_timestamp=enrichment_timestamp,
    )
    enriched.verify_decision_unchanged(decision)
    return enriched
