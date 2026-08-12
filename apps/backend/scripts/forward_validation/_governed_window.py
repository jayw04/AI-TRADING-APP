"""The governed decision window, derived once and shared.

PR #589 generalized the session constants it knew about. It did not catch
`DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))` in `build_universe_crosswalk`, because that
one is a **tuple**, and the sweep that found the others looked for scalar assignments. A window is the
same hazard as a session in a different shape: a crosswalk built for 2026-07-28 while silently scored
over the window ending 2026-07-27 produces evidence that is internally consistent and wrong, and no
digest downstream can tell.

So the window is not a literal anywhere. It is DERIVED from the governed session by the same rule the
construction already uses in `layer2_step5_exclusion_impact_273` — the last
:data:`REQUIRED_HISTORY_SESSIONS` sessions present in the corpus, ending exactly on the session — and
that rule now lives here so there is exactly one definition of it to keep correct.
"""

from __future__ import annotations

from datetime import date
from typing import Any

#: The governed decision-window length in trading sessions. The strategy inputs are formed over this
#: many sessions ending on the governed session; `layer2_step5_exclusion_impact_273` measures the
#: exclusion impact over the identical window, and the two must not be able to drift apart.
REQUIRED_HISTORY_SESSIONS = 273


class GovernedWindowError(RuntimeError):
    """The corpus cannot supply the exact governed window for the requested session.

    FAILS CLOSED. A short window, or one that does not end on the session, means the corpus does not
    cover what the run was asked to measure — which is a refusal, never a narrower measurement.
    """


def governed_decision_window(con: Any, session: date) -> tuple[date, date]:
    """Return ``(window_start, session)`` for the governed decision window.

    ``con`` is any DB-API connection over the governed corpus (DuckDB in every current caller).

    The window is the last :data:`REQUIRED_HISTORY_SESSIONS` distinct SEP sessions dated at or before
    ``session``. It is a REFUSAL, not a truncation, when the corpus yields fewer sessions than the
    window requires or when the newest session in range is not ``session`` itself — either condition
    means the corpus does not actually cover the session being built.
    """
    rows = con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [session, REQUIRED_HISTORY_SESSIONS]).fetchall()
    sessions = sorted(r[0] for r in rows)
    if len(sessions) != REQUIRED_HISTORY_SESSIONS:
        raise GovernedWindowError(
            f"the corpus yields {len(sessions)} sessions at or before {session.isoformat()}; the "
            f"governed decision window needs exactly {REQUIRED_HISTORY_SESSIONS}. The corpus does not "
            f"cover this session — build the corpus first, do not measure a shorter window.")
    if sessions[-1] != session:
        raise GovernedWindowError(
            f"the newest corpus session at or before {session.isoformat()} is "
            f"{sessions[-1].isoformat()}, so the corpus does not contain the governed session. A "
            f"window ending on an earlier session would score the WRONG session and every digest "
            f"computed from it would still verify.")
    return sessions[0], sessions[-1]
