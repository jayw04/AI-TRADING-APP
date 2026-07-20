"""Close-t decision eligibility engine (SIG-20/23 / Ruling 9; Correction 3).

Fixed precedence (rank 1..6):
  1 integrity or identity failure          (raised upstream as a refusal)
  2 missing mandatory signal input         (raised upstream as a refusal)
  3 security or universe ineligibility
  4 event blackout (earnings / corporate action)
  5 liquidity or price rule
  6 signal selection downstream            (NOT eligibility — z threshold / percentile)

decision_eligibility_status is ELIGIBLE | INELIGIBLE at close t and NEVER encodes the z threshold,
the cross-sectional percentile, or the t+1 gap filter (those are downstream / execution-time). Each
outcome carries rule_id, observed_value, threshold, source_identity, availability_timestamp,
decision_cutoff, precedence_rank. No eligibility fact published after close t may be used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .constants import PRECEDENCE
from .refusals import refuse

__all__ = ["ExclusionCheck", "EligibilityEvidence", "EligibilityResult", "evaluate_eligibility"]

ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class ExclusionCheck:
    """A single governed close-t exclusion test."""

    rule_id: str
    precedence_category: str    # key of constants.PRECEDENCE (ranks 3/4/5)
    excludes: bool              # True => this rule would exclude the security
    observed_value: str
    threshold: str
    source_identity: str
    availability_timestamp: str
    evidence_present: bool


@dataclass(frozen=True)
class EligibilityEvidence:
    rule_id: str
    observed_value: str
    threshold: str
    source_identity: str
    availability_timestamp: str
    decision_cutoff: str
    precedence_rank: int
    outcome: str


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    precedence_rank: int
    deciding_rule_id: str
    evidence: tuple[EligibilityEvidence, ...]


def evaluate_eligibility(
    checks: list[ExclusionCheck], decision_cutoff: str
) -> EligibilityResult:
    """Apply the governed checks in fixed precedence; return the close-t eligibility result."""
    trail: list[EligibilityEvidence] = []
    # Deterministic order: precedence rank, then rule_id.
    ordered = sorted(
        checks, key=lambda c: (PRECEDENCE.get(c.precedence_category, 99), c.rule_id)
    )
    for c in ordered:
        rank = PRECEDENCE.get(c.precedence_category)
        if rank is None or rank not in (3, 4, 5):
            raise refuse(
                "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
                f"rule {c.rule_id} has no governed close-t precedence category",
            )
        if not c.evidence_present:
            ev = EligibilityEvidence(
                c.rule_id, c.observed_value, c.threshold, c.source_identity,
                c.availability_timestamp, decision_cutoff, rank, INELIGIBLE,
            )
            raise refuse(
                "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
                f"rule {c.rule_id} missing mandatory evidence identity: {asdict(ev)}",
            )
        # A fact published after the cutoff cannot be used (no look-ahead); it is ignored.
        if c.availability_timestamp > decision_cutoff:
            continue
        if c.excludes:
            ev = EligibilityEvidence(
                c.rule_id, c.observed_value, c.threshold, c.source_identity,
                c.availability_timestamp, decision_cutoff, rank, INELIGIBLE,
            )
            trail.append(ev)
            return EligibilityResult(INELIGIBLE, rank, c.rule_id, tuple(trail))
        trail.append(
            EligibilityEvidence(
                c.rule_id, c.observed_value, c.threshold, c.source_identity,
                c.availability_timestamp, decision_cutoff, rank, ELIGIBLE,
            )
        )
    return EligibilityResult(ELIGIBLE, 0, "", tuple(trail))
