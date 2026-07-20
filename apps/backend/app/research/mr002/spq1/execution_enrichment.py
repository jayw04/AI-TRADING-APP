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
from .refusals import refuse

__all__ = ["GAP_THRESHOLD", "enrich_decision"]

GAP_THRESHOLD = 0.06  # |AdjOpen_t+1 / AdjClose_t - 1| >= 6% cancels (frozen §4)


def enrich_decision(
    decision: SignalDecisionRecord,
    scheduled_execution_session: int,
    official_next_open_price: float | None,
    distribution_adjusted_close_t: float,
    enrichment_timestamp: str = "",
) -> ExecutionEnrichedCandidateRecord:
    """Build the enriched record for t+1 without mutating any decision fact.

    Fails closed on malformed execution inputs: the scheduled session must be the registered t+1
    ordinal; the gap denominator (distribution-adjusted close t) must be finite and positive; a
    present official open must be finite and positive. Only a genuinely MISSING open (None) is a
    governed CANCELLED_MISSING_OPEN — a non-finite/non-positive open is an integrity refusal.
    """
    if scheduled_execution_session != decision.decision_session + 1:
        raise refuse(
            "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
            f"scheduled execution session {scheduled_execution_session} is not the registered "
            f"t+1 ({decision.decision_session + 1})",
        )
    if not (math.isfinite(distribution_adjusted_close_t) and distribution_adjusted_close_t > 0.0):
        raise refuse(
            "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID",
            "distribution-adjusted close-t gap denominator is non-finite or non-positive",
        )
    if official_next_open_price is None:
        price = float("nan")
        status = CANCELLED_MISSING_OPEN
        gap_result = "NOT_EVALUATED_MISSING_OPEN"
        disposition = "cancel entry (missing official open); exits would defer (Increment-2/3)"
    elif not (math.isfinite(official_next_open_price) and official_next_open_price > 0.0):
        raise refuse(
            "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID",
            "official next-open price is present but non-finite or non-positive",
        )
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
