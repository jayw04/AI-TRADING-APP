"""Eligibility-evidence adapter (Phase 2A domain 7).

Maps development earnings/event evidence to frozen ``ExclusionCheck`` inputs. Each fact carries a
source identity, availability timestamp (acceptance_utc), and BMO/AMC basis. The frozen eligibility
engine enforces the close-t cutoff — a record unavailable by close t remains
INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING; a future-published fact is never consulted.
"""
from __future__ import annotations

from ..eligibility import ExclusionCheck
from . import normalize_utc_iso


def load_earnings_checks(con, cik: int, decision_session_date: str) -> list[ExclusionCheck]:  # noqa: ANN001
    """Earnings-blackout checks: exclude when the cooling window covers the decision session."""
    rows = con.execute(
        "select accession, acceptance_utc, event_time_basis, cooling_start_session, "
        "cooling_end_session from earnings_anchors where cik = ? order by acceptance_utc",
        [cik],
    ).fetchall()
    checks: list[ExclusionCheck] = []
    for accession, acceptance_utc, basis, cool_start, cool_end in rows:
        excludes = (
            cool_start is not None
            and cool_end is not None
            and str(cool_start) <= decision_session_date <= str(cool_end)
        )
        checks.append(
            ExclusionCheck(
                rule_id=f"EARN-BLACKOUT:{accession}",
                precedence_category="event_blackout",
                excludes=excludes,
                observed_value=f"basis={basis};window={cool_start}..{cool_end}",
                threshold="no earnings within [t+1 open, session-6 open]",
                source_identity=f"earnings_anchor:{accession}",
                availability_timestamp=normalize_utc_iso(acceptance_utc),
                evidence_present=True,
            )
        )
    return checks
