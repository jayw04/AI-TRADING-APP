"""Permanent-security identity adapter (Phase 2A domain 2).

Maps the PIT-bounded development crosswalk to the frozen ``PitIdentityRegistry`` lineage. A ticker
rename keeps the permanent id (continuity); a new share class / merger / succession does NOT retain
the predecessor identity unless the crosswalk authorizes continuity. Effective dates use the frozen
on-or-after session rule (never at-or-before clamping); a pre-window effective date is retained
explicitly as PRE_WINDOW. No present-day symbol map is back-applied. An unknown relationship type or
ambiguous effective timing fails closed INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS (no fallback).
"""
from __future__ import annotations

from ..calendar import RegisteredCalendar
from ..refusals import refuse
from ..security_identity import LineageRecord, PitIdentityRegistry
from .calendar_adapter import map_effective_session

# crosswalk.relationship_type -> (corporate_action_type, history_continuity_authorized). FROZEN;
# an unrecognized type is NOT guessed.
_REL = {
    "direct": ("ticker_change", True),
    "ticker_rename": ("ticker_change", True),
    "share_class": ("new_share_class", False),
    "successor_cik": ("merger", False),
    "predecessor_cik": ("merger", False),
}


def load_identity_registry(con, calendar: RegisteredCalendar) -> PitIdentityRegistry:  # noqa: ANN001
    rows = con.execute(
        "select permaticker, ticker, effective_from, relationship_type, source_record_id "
        "from crosswalk"
    ).fetchall()
    lineage: dict[str, list[LineageRecord]] = {}
    for permaticker, ticker, eff_from, rel, src in rows:
        rel_s = str(rel)
        if rel_s not in _REL:
            raise refuse(
                "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
                f"unknown crosswalk relationship_type {rel_s!r} for {ticker} "
                "(no corporate-action fallback permitted)",
            )
        action, cont = _REL[rel_s]
        ordinal, disposition = map_effective_session(calendar, str(eff_from))
        lineage.setdefault(str(ticker), []).append(
            LineageRecord(
                predecessor_permanent_id=None,
                successor_permanent_id=f"PSEC-{permaticker}",
                effective_session_ordinal=ordinal,
                corporate_action_type=action,
                history_continuity_authorized=cont,
                source_evidence_identity=f"crosswalk:{disposition}:{src}",
            )
        )
    return PitIdentityRegistry(
        lineage={
            k: tuple(sorted(v, key=lambda r: r.effective_session_ordinal))
            for k, v in lineage.items()
        }
    )
