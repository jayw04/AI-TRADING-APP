"""Entry adjudication: the gap filter, kept OUT of the frozen enriched-record surface.

Owner ruling 2026-08-12: a well-formed economic gap exceeding the frozen 6% threshold is an
entry-admissibility outcome, not an enrichment failure. The enrichment disposition stays
`EXECUTION_ENRICHMENT_SUCCESS`; the candidate is simply not admissible for entry.

The frozen `ExecutionEnrichmentSchema` provides no field for the gap value or the admissibility
flag, and R-U1 makes that schema normative for the published record. So they live here, in the
downstream entry-adjudication layer, joined to the enriched record by `decision_record_sha256`.
Adding them to the record would have made an eleventh and twelfth field on a ten-field surface.

Malformed price inputs never reach this layer: they are a source-integrity condition and are
adjudicated upstream as `EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enrichment import SUCCESS
from .gap import GAP_THRESHOLD, GapInputInvalid, economic_gap, gap_cancels

ADMITTED = "ADMITTED"
NOT_ADMITTED_GAP = "NOT_ADMITTED_GAP_FILTER"
NOT_ADJUDICATED = "NOT_ADJUDICATED_ENRICHMENT_DID_NOT_SUCCEED"


@dataclass(frozen=True)
class EntryAdjudication:
    """One entry decision, referencing its enriched record by identity rather than embedding it."""

    decision_record_sha256: str
    execution_session_t_plus_1: int
    entry_admissible: bool | None
    outcome: str
    economic_gap: float | None
    gap_threshold: float
    reason: str

    def as_record(self) -> dict[str, Any]:
        return {
            "decision_record_sha256": self.decision_record_sha256,
            "execution_session_t_plus_1": self.execution_session_t_plus_1,
            "entry_admissible": self.entry_admissible,
            "outcome": self.outcome,
            "economic_gap": self.economic_gap,
            "gap_threshold": self.gap_threshold,
            "reason": self.reason,
        }


def adjudicate_entry(record: Any, facts: Any) -> EntryAdjudication:
    """Adjudicate entry admissibility for one enriched record.

    A record whose enrichment did not succeed is not adjudicated at all - it never reaches the
    entry rule - and that is recorded explicitly rather than defaulted to `False`, so a census can
    tell "rejected by the gap filter" apart from "never got that far".
    """
    if record.ExecutionEnrichmentCode != SUCCESS:
        return EntryAdjudication(
            decision_record_sha256=record.decision_record_sha256,
            execution_session_t_plus_1=record.execution_session_t_plus_1,
            entry_admissible=None,
            outcome=NOT_ADJUDICATED,
            economic_gap=None,
            gap_threshold=GAP_THRESHOLD,
            reason=f"enrichment terminated as {record.ExecutionEnrichmentCode}",
        )

    try:
        gap = economic_gap(
            float(facts.official_open), float(facts.close_t), float(facts.cash_distribution)
        )
    except GapInputInvalid as exc:  # pragma: no cover - upstream already refuses these
        raise AssertionError(
            "a successfully enriched record must have valid gap inputs; enrichment should have "
            f"raised PRICE_CONFLICT: {exc}"
        ) from exc

    cancels = gap_cancels(gap)
    return EntryAdjudication(
        decision_record_sha256=record.decision_record_sha256,
        execution_session_t_plus_1=record.execution_session_t_plus_1,
        entry_admissible=not cancels,
        outcome=NOT_ADMITTED_GAP if cancels else ADMITTED,
        economic_gap=gap,
        gap_threshold=GAP_THRESHOLD,
        reason=(
            f"|economic_gap| >= {GAP_THRESHOLD} - entry cancelled at the t+1 open"
            if cancels
            else "gap within the frozen band"
        ),
    )
