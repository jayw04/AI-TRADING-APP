"""Typed records (SIG-27 seam; schema draft v1.1). Decision facts vs execution facts.

``SignalDecisionRecord`` carries only close-t decision facts and STRUCTURALLY rejects any future
field (official_next_open_price, actual_execution_session, gap_filter_result,
execution_admissibility_status, or any unknown/post-cutoff key) ->
INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED. ``ExecutionEnrichedCandidateRecord`` binds the decision
record by canonical embedding + SHA-256 and appends only the allowed t+1 execution facts without
mutating any decision fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from .identities import canonical_sha256
from .refusals import refuse

__all__ = [
    "SignalDecisionRecord",
    "ExecutionEnrichedCandidateRecord",
    "FORBIDDEN_DECISION_FIELDS",
    "ADMISSIBLE",
    "CANCELLED_GAP",
    "CANCELLED_MISSING_OPEN",
]

# Structurally forbidden in a decision record (future / execution facts).
FORBIDDEN_DECISION_FIELDS: frozenset[str] = frozenset(
    {
        "official_next_open_price",
        "actual_execution_session",
        "scheduled_execution_session",
        "gap_filter_result",
        "execution_admissibility_status",
        "missing_open_disposition",
        "enrichment_timestamp",
    }
)

ADMISSIBLE = "ADMISSIBLE"
CANCELLED_GAP = "CANCELLED_GAP"
CANCELLED_MISSING_OPEN = "CANCELLED_MISSING_OPEN"


def _hexify(value: object) -> object:
    """Canonical exact-float encoding: floats -> float.hex(); recurse into containers."""
    if isinstance(value, float):
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {k: _hexify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hexify(v) for v in value]
    return value


@dataclass(frozen=True)
class SignalDecisionRecord:
    candidate_id: str
    permanent_security_id: str
    symbol: str
    decision_session: int
    signal_origin_session: int
    side: str
    registered_signal_value: float
    registered_sigma_resid: float
    sector_id: str
    beta: float
    decision_eligibility_status: str
    eligibility_evidence_identity: str
    eligibility_precedence_rank: int
    configuration_id: str
    trailing_adv_dollars: float
    normalization_window_identity: str
    computation_record_identity: str
    warmup_return_sessions: int
    warmup_price_observations: int

    def canonical(self) -> dict[str, object]:
        return {f.name: _hexify(getattr(self, f.name)) for f in fields(self)}

    @property
    def record_identity(self) -> str:
        return canonical_sha256(self.canonical())


_ALLOWED_DECISION_KEYS: frozenset[str] = frozenset(
    f.name for f in fields(SignalDecisionRecord)
)


def build_signal_decision_record(data: dict[str, object]) -> SignalDecisionRecord:
    """Structural constructor. Any forbidden or unknown key fails closed FUTURE_INFORMATION_DETECTED."""
    forbidden = FORBIDDEN_DECISION_FIELDS & data.keys()
    if forbidden:
        raise refuse(
            "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
            f"forbidden future/execution field(s) in decision record: {sorted(forbidden)}",
        )
    unknown = data.keys() - _ALLOWED_DECISION_KEYS
    if unknown:
        raise refuse(
            "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
            f"unknown post-cutoff field(s) in decision record: {sorted(unknown)}",
        )
    missing = _ALLOWED_DECISION_KEYS - data.keys()
    if missing:
        raise refuse(
            "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
            f"decision record missing required fields: {sorted(missing)}",
        )
    return SignalDecisionRecord(**data)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ExecutionEnrichedCandidateRecord:
    decision_record_canonical: dict[str, object]
    decision_record_identity: str
    scheduled_execution_session: int
    official_next_open_price: float
    execution_admissibility_status: str
    gap_filter_result: str
    missing_open_disposition: str
    enrichment_timestamp: str = field(default="")

    def canonical(self) -> dict[str, object]:
        return {
            "decision_record_canonical": self.decision_record_canonical,
            "decision_record_identity": self.decision_record_identity,
            "scheduled_execution_session": self.scheduled_execution_session,
            "official_next_open_price": _hexify(self.official_next_open_price),
            "execution_admissibility_status": self.execution_admissibility_status,
            "gap_filter_result": self.gap_filter_result,
            "missing_open_disposition": self.missing_open_disposition,
            "enrichment_timestamp": self.enrichment_timestamp,
        }

    @property
    def record_identity(self) -> str:
        return canonical_sha256(self.canonical())

    def verify_decision_unchanged(self, decision: SignalDecisionRecord) -> None:
        if (
            self.decision_record_canonical != decision.canonical()
            or self.decision_record_identity != decision.record_identity
        ):
            raise refuse(
                "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
                "enrichment mutated the bound decision record",
            )
