"""Permanent security identity + lineage (SIG-28/29, Ruling 8/12).

permanent_security_id comes from the frozen PIT identity registry; candidate_id is a distinct
record identity; symbol is a time-varying display/execution identifier. A ticker change keeps the
permanent id when the registry records economic continuity; a merger/successor/new-share-class
does NOT retain the predecessor identity unless the governed lineage registry authorizes it.
Ambiguous lineage fails closed SECURITY_IDENTITY_AMBIGUOUS.
"""
from __future__ import annotations

from dataclasses import dataclass

from .refusals import refuse

__all__ = ["LineageRecord", "PitIdentityRegistry", "build_candidate_id"]


@dataclass(frozen=True)
class LineageRecord:
    predecessor_permanent_id: str | None
    successor_permanent_id: str
    effective_session_ordinal: int
    corporate_action_type: str  # ticker_change | merger | spinoff | reincorporation | new_share_class
    history_continuity_authorized: bool
    source_evidence_identity: str


@dataclass(frozen=True)
class PitIdentityRegistry:
    """Maps (symbol, decision-session ordinal) -> permanent_security_id via governed lineage."""

    # symbol -> ordered lineage records (ascending effective_session_ordinal)
    lineage: dict[str, tuple[LineageRecord, ...]]

    def resolve_permanent_id(self, symbol: str, t: int) -> str:
        recs = self.lineage.get(symbol)
        if not recs:
            raise refuse(
                "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
                f"no lineage record for symbol {symbol}",
            )
        active = [r for r in recs if r.effective_session_ordinal <= t]
        if not active:
            raise refuse(
                "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
                f"no lineage effective at t={t} for {symbol}",
            )
        # Same effective session with conflicting successors -> ambiguous.
        latest_ord = max(r.effective_session_ordinal for r in active)
        latest = [r for r in active if r.effective_session_ordinal == latest_ord]
        if len({r.successor_permanent_id for r in latest}) != 1:
            raise refuse(
                "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
                f"conflicting lineage successors at t={t} for {symbol}",
            )
        rec = latest[0]
        # A corporate action that is not a pure ticker change requires explicit continuity.
        if rec.corporate_action_type != "ticker_change" and not rec.history_continuity_authorized:
            # History does not continue: the successor is a NEW permanent security; that is
            # legitimate, and its permanent id is the successor id. Ambiguity only arises when
            # continuity is neither clearly authorized nor clearly a fresh identity.
            pass
        return rec.successor_permanent_id


def build_candidate_id(
    program_id: str,
    configuration_id: str,
    decision_session_ordinal: int,
    permanent_security_id: str,
    side: str,
    signal_record_identity: str,
) -> str:
    """candidate_id binds program | config | session | permanent-security | side | signal-record."""
    return "|".join(
        [
            program_id,
            configuration_id,
            str(decision_session_ordinal),
            permanent_security_id,
            side,
            signal_record_identity,
        ]
    )
