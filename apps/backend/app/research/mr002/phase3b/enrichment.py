"""Schema-conforming execution enrichment for Phase 3B.

Two owner rulings govern this module:

* **R-U1** — `ExecutionEnrichmentSchema_v1.0.json` is normative for the PUBLISHED enriched-record
  field surface. `spq1/models.py` governs the frozen decision record and its immutability seam and
  is never edited; the two are not co-normative. This module therefore emits the schema's ten
  fields, built from the immutable decision record.
* **R-U2** — `ExecutionEnrichmentCodeRegistry_v1.0.json` is normative for emitted terminal codes and
  for the census. The legacy `ADMISSIBLE` / `CANCELLED_GAP` / `CANCELLED_MISSING_OPEN` labels are
  internal at most, never published, and signal-production `INTEGRITY_STOP:*` codes never
  masquerade as enrichment dispositions.

Every legacy-to-registry correspondence below is derived from the frozen edge-case specification,
never chosen for plausibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gap import GapInputInvalid, economic_gap

# --- the registered code namespace (ExecutionEnrichmentCodeRegistry v1.0) -----------------------
SUCCESS = "EXECUTION_ENRICHMENT_SUCCESS"
STOP_CORPORATE_ACTION = "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED"
STOP_DELISTING = "EXECUTION_ENRICHMENT_STOP:DELISTING"
STOP_IDENTITY_CONFLICT = "EXECUTION_ENRICHMENT_STOP:IDENTITY_CONFLICT"
STOP_NO_OFFICIAL_OPEN = "EXECUTION_ENRICHMENT_STOP:NO_OFFICIAL_OPEN"
STOP_PRICE_CONFLICT = "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT"
STOP_SOURCE_MISSING = "EXECUTION_ENRICHMENT_STOP:SOURCE_MISSING"
STOP_TRADING_HALT = "EXECUTION_ENRICHMENT_STOP:TRADING_HALT"
FUTURE_INFORMATION = "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED"

REGISTERED_CODES = (
    SUCCESS,
    STOP_CORPORATE_ACTION,
    STOP_DELISTING,
    STOP_IDENTITY_CONFLICT,
    STOP_NO_OFFICIAL_OPEN,
    STOP_PRICE_CONFLICT,
    STOP_SOURCE_MISSING,
    STOP_TRADING_HALT,
    FUTURE_INFORMATION,
)

# R-A2: registered, reserved, no frozen trigger, expected count zero.
RESERVED_CODES = (STOP_SOURCE_MISSING,)

# R-A3: PRICE_CONFLICT has its own category; "other registered disposition" stays for residuals.
CENSUS_CATEGORY = {
    SUCCESS: "successful enrichment",
    STOP_NO_OFFICIAL_OPEN: "no-open",
    STOP_TRADING_HALT: "halt",
    STOP_DELISTING: "delisting",
    STOP_CORPORATE_ACTION: "corporate-action transition",
    STOP_IDENTITY_CONFLICT: "identity conflict",
    STOP_SOURCE_MISSING: "missing source",
    STOP_PRICE_CONFLICT: "price conflict",
    FUTURE_INFORMATION: "future-information stop",
}

REALIZATION_HORIZON = 6  # preregistration v1.0.4 realization_horizon_governing
DISPOSITION_ENRICHED = "ENRICHED"
DISPOSITION_CANCELLED = "CANCELLED"
DISPOSITION_STOPPED = "STOPPED"

TERMINAL_TREATMENT = {
    SUCCESS: DISPOSITION_ENRICHED,
    STOP_CORPORATE_ACTION: DISPOSITION_STOPPED,
    STOP_DELISTING: DISPOSITION_STOPPED,
    STOP_IDENTITY_CONFLICT: DISPOSITION_STOPPED,
    STOP_NO_OFFICIAL_OPEN: DISPOSITION_CANCELLED,
    STOP_PRICE_CONFLICT: DISPOSITION_STOPPED,
    STOP_SOURCE_MISSING: DISPOSITION_STOPPED,
    STOP_TRADING_HALT: DISPOSITION_STOPPED,
    FUTURE_INFORMATION: DISPOSITION_STOPPED,
}


class DecisionRecordMutated(Exception):
    """The bound decision record changed across enrichment. Never caught to retry."""


@dataclass(frozen=True)
class ExecutionFacts:
    """The t+1 facts the enricher is permitted to consult. Nothing here may bear on close t."""

    requested_execution_session: int
    actual_source_session: int | None = None
    official_open: float | None = None
    close_t: float | None = None
    cash_distribution: float = 0.0
    official_open_source_identity: str | None = None
    corporate_action_identity: str | None = None
    corporate_action_kind: str | None = None  # split | dividend | merger | acquisition | ...
    adjusted_open_constructible: bool = True
    halted: bool = False
    delisted_at_or_before_t_plus_1: bool = False
    identity_transition: bool = False
    open_basis_conflict: bool = False
    future_information: bool = False
    conservative_short_flag: bool = False


@dataclass(frozen=True)
class EnrichedRecord:
    """The published record.

    Exactly the ten fields of the frozen ExecutionEnrichmentSchema, plus only those per-record
    bindings the edge-case specification itself lists. Nothing else lives here.

    In particular the gap value and the entry-admissibility outcome are NOT fields of this record:
    the frozen schema provides no place for them, and the gap filter is an ENTRY rule rather than an
    enrichment fact. They belong to the downstream entry adjudication (`admissibility.py`), which
    references this record by `decision_record_sha256`. Carrying them here would have made an
    eleventh and twelfth field on a ten-field frozen surface.
    """

    decision_record_sha256: str
    decision_session_t: int
    execution_session_t_plus_1: int
    official_open_source_identity: str | None
    official_open_price_ref: float | None
    realization_horizon: int
    ExecutionEnrichmentDisposition: str
    ExecutionEnrichmentCode: str
    corporate_action_identity: str | None
    conservative_short_flag: bool
    # per_record_bindings, verbatim from MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification
    requested_execution_session: int = 0
    actual_source_session: int | None = None
    terminal_treatment: str = ""

    def schema_surface(self) -> dict[str, Any]:
        """Only the ten fields the frozen schema declares, for publication and hashing."""
        return {
            "decision_record_sha256": self.decision_record_sha256,
            "decision_session_t": self.decision_session_t,
            "execution_session_t_plus_1": self.execution_session_t_plus_1,
            "official_open_source_identity": self.official_open_source_identity,
            "official_open_price_ref": self.official_open_price_ref,
            "realization_horizon": self.realization_horizon,
            "ExecutionEnrichmentDisposition": self.ExecutionEnrichmentDisposition,
            "ExecutionEnrichmentCode": self.ExecutionEnrichmentCode,
            "corporate_action_identity": self.corporate_action_identity,
            "conservative_short_flag": self.conservative_short_flag,
        }


_CORPORATE_ACTION_KINDS = {
    "split",
    "dividend",
    "spinoffdividend",
    "merger",
    "mergerto",
    "mergerfrom",
    "acquisitionby",
    "acquisitionof",
    "cash_only_acquisition",
    "stock_and_cash_acquisition",
}


def _classify(facts: ExecutionFacts) -> str:
    """Return the single registered terminal code for these facts.

    Precedence follows the frozen edge-case table: an integrity violation outranks an identity
    problem, which outranks a security-level termination, which outranks a session problem, which
    outranks a price problem, which outranks a corporate-action resolution. Each condition maps to
    exactly one code and there is no silent fallback.
    """
    if facts.future_information:
        return FUTURE_INFORMATION
    if facts.identity_transition:  # symbol_or_permsec_transition
        return STOP_IDENTITY_CONFLICT
    if facts.delisted_at_or_before_t_plus_1:  # delisting
        return STOP_DELISTING
    if facts.halted:  # trading_halt
        return STOP_TRADING_HALT
    if (
        facts.actual_source_session is not None
        and facts.actual_source_session != facts.requested_execution_session
    ):
        return STOP_PRICE_CONFLICT  # execution_session_ne_registered_next
    if facts.open_basis_conflict:
        return STOP_PRICE_CONFLICT  # adjusted_vs_unadjusted_open_identity
    if facts.official_open is None:
        return STOP_NO_OFFICIAL_OPEN  # no_official_open
    if facts.close_t is None:
        return STOP_PRICE_CONFLICT  # missing_or_conflicting_open
    if (
        facts.corporate_action_kind in _CORPORATE_ACTION_KINDS
        and not facts.adjusted_open_constructible
    ):
        # dividend_or_distribution / split_close_t_to_open_t1 / merger_consideration /
        # cash_only_acquisition / stock_and_cash_acquisition - the FALSE branch of the two
        # conditional cases, and the unconditional target of the other three.
        return STOP_CORPORATE_ACTION
    return SUCCESS


def enrich(decision: Any, facts: ExecutionFacts) -> EnrichedRecord:
    """Build the published enriched record without recomputing or mutating any decision fact.

    `decision` must expose `record_identity`, `decision_session` and `canonical()` - the frozen
    SignalDecisionRecord surface. It is read, never written, and its identity is re-checked after
    enrichment so a mutation is evidence rather than a silent corruption.
    """
    before_identity = decision.record_identity
    before_canonical = decision.canonical()

    if facts.requested_execution_session != decision.decision_session + 1:
        code = STOP_PRICE_CONFLICT  # calendar_mismatch
    else:
        code = _classify(facts)

    # Enrichment validates the price INPUTS but does not adjudicate the gap. Owner ruling
    # 2026-08-12: a well-formed gap over the frozen threshold is an entry-admissibility outcome,
    # not an enrichment failure, so it never becomes PRICE_CONFLICT and no new code is invented.
    # Malformed, non-finite or internally inconsistent inputs ARE a source-integrity condition and
    # do become PRICE_CONFLICT. The admissibility decision itself lives in `admissibility.py`.
    if code == SUCCESS:
        try:
            economic_gap(
                float(facts.official_open), float(facts.close_t), float(facts.cash_distribution)
            )
        except GapInputInvalid:
            code = STOP_PRICE_CONFLICT  # missing_or_conflicting_open

    record = EnrichedRecord(
        decision_record_sha256=before_identity,
        decision_session_t=decision.decision_session,
        execution_session_t_plus_1=facts.requested_execution_session,
        official_open_source_identity=facts.official_open_source_identity,
        official_open_price_ref=facts.official_open,
        realization_horizon=REALIZATION_HORIZON,
        ExecutionEnrichmentDisposition=TERMINAL_TREATMENT[code],
        ExecutionEnrichmentCode=code,
        corporate_action_identity=facts.corporate_action_identity,
        conservative_short_flag=facts.conservative_short_flag,
        requested_execution_session=facts.requested_execution_session,
        actual_source_session=facts.actual_source_session,
        terminal_treatment=TERMINAL_TREATMENT[code],
    )

    if decision.record_identity != before_identity or decision.canonical() != before_canonical:
        raise DecisionRecordMutated(
            f"{FUTURE_INFORMATION}: enrichment mutated the bound decision record"
        )
    return record
