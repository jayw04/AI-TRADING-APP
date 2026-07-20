"""Permanent-security identity adapter (Phase 2A domain 2).

Maps the development crosswalk to the frozen ``PitIdentityRegistry`` lineage. A ticker rename keeps
the permanent id (continuity); a new share class / merger / succession does NOT retain the
predecessor identity unless the crosswalk authorizes continuity. No present-day symbol map is
back-applied historically. Ambiguity remains INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS (raised by
the frozen resolver).
"""
from __future__ import annotations

from ..calendar import RegisteredCalendar
from ..security_identity import LineageRecord, PitIdentityRegistry
from .calendar_adapter import date_to_ordinal

# crosswalk.relationship_type -> (corporate_action_type, history_continuity_authorized)
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
        action, cont = _REL.get(str(rel), ("ticker_change", False))
        lineage.setdefault(str(ticker), []).append(
            LineageRecord(
                predecessor_permanent_id=None,
                successor_permanent_id=f"PSEC-{permaticker}",
                effective_session_ordinal=date_to_ordinal(calendar, str(eff_from)),
                corporate_action_type=action,
                history_continuity_authorized=cont,
                source_evidence_identity=f"crosswalk:{src}",
            )
        )
    return PitIdentityRegistry(
        lineage={
            k: tuple(sorted(v, key=lambda r: r.effective_session_ordinal))
            for k, v in lineage.items()
        }
    )
