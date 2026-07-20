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
    reason: str = ""


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    precedence_rank: int
    deciding_rule_id: str
    evidence: tuple[EligibilityEvidence, ...]


def evaluate_eligibility(
    checks: list[ExclusionCheck], decision_cutoff: str
) -> EligibilityResult:
    """Apply the governed checks in fixed precedence; return the close-t eligibility result.

    Each governed rule is PIT-resolved: among a rule's records, the latest with
    availability_timestamp <= close t is used (an earlier valid record is usable when a later
    record exists but is not yet available). A required rule with NO record available by the
    cutoff, or a selected record whose evidence identity is absent, is INELIGIBLE (a post-cutoff
    fact is not valid close-t evidence — its ``excludes`` value is never consulted).
    """
    by_rule: dict[str, list[ExclusionCheck]] = {}
    for c in checks:
        by_rule.setdefault(c.rule_id, []).append(c)

    def _rank(rule_id: str) -> int | None:
        return PRECEDENCE.get(by_rule[rule_id][0].precedence_category)

    trail: list[EligibilityEvidence] = []
    for rule_id in sorted(by_rule, key=lambda r: (_rank(r) or 99, r)):
        group = by_rule[rule_id]
        rank = _rank(rule_id)
        if rank is None or rank not in (3, 4, 5):
            raise refuse(
                "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
                f"rule {rule_id} has no governed close-t precedence category",
            )
        available = [c for c in group if c.availability_timestamp <= decision_cutoff]
        if not available:
            ev = EligibilityEvidence(
                rule_id, "", "", group[0].source_identity,
                max(c.availability_timestamp for c in group), decision_cutoff, rank,
                INELIGIBLE, reason="unavailable_by_cutoff",
            )
            raise refuse(
                "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
                f"rule {rule_id} has no evidence available by cutoff: {asdict(ev)}",
            )
        # PIT selection: latest available record (deterministic tie-break by source_identity).
        selected = max(available, key=lambda c: (c.availability_timestamp, c.source_identity))
        if not selected.evidence_present:
            ev = EligibilityEvidence(
                rule_id, selected.observed_value, selected.threshold, selected.source_identity,
                selected.availability_timestamp, decision_cutoff, rank, INELIGIBLE,
                reason="evidence_absent",
            )
            raise refuse(
                "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
                f"rule {rule_id} missing mandatory evidence identity: {asdict(ev)}",
            )
        if selected.excludes:
            ev = EligibilityEvidence(
                rule_id, selected.observed_value, selected.threshold, selected.source_identity,
                selected.availability_timestamp, decision_cutoff, rank, INELIGIBLE,
                reason="excluded",
            )
            trail.append(ev)
            return EligibilityResult(INELIGIBLE, rank, rule_id, tuple(trail))
        trail.append(
            EligibilityEvidence(
                rule_id, selected.observed_value, selected.threshold, selected.source_identity,
                selected.availability_timestamp, decision_cutoff, rank, ELIGIBLE,
                reason="cleared",
            )
        )
    return EligibilityResult(ELIGIBLE, 0, "", tuple(trail))
