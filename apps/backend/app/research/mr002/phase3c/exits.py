"""The frozen exit ladder as it applies to MR-002 VALIDATION, with the retired trigger removed.

Owner ruling 1 (MR002_Phase3C_OwnerRulings_v1.0.json, `ruling_1_exit_confirmation_3p5sigma`):

    EXIT_CONFIRMATION_3P5SIGMA: RETIRED / NOT EXECUTABLE, because the frozen specification omitted
    the market/sector sigma estimator required to determine the confirmation condition.

    "remove this branch from the validation replay explicitly rather than silently leaving it
     permanently false"

That is why this function takes NO `confirm` argument. The development harness passed
`inp.confirm.get(permaticker, False)` into `execution.exit_reason`, and `confirm` was never
populated (`dataset.py:261` builds it empty and nothing fills it), so the branch was unreachable in
practice. Leaving an unreachable branch in place would misrepresent the replay as implementing a
rule it cannot apply. It is removed here instead.

The retirement is behaviour-preserving, and that is a measured claim rather than an assumption: in
the owner-authorized 1,700-session v1.1 A/B/C development run, `exit_hypothesis_failure` appears
ZERO times in the exit-reason census for every configuration.

Every other rung, and the ordering, is preserved exactly as `execution.exit_reason` states it.
"""

from __future__ import annotations

import numpy as np

from app.research.mr002.execution import EXIT_Z, MAX_HOLD_SESSIONS

# Recorded so the removal is discoverable from the code, not only from the governance record.
RETIRED_TRIGGER = "exit_hypothesis_failure"
RETIRED_BY = "MR002_Phase3C_OwnerRulings_v1.0.json / ruling_1_exit_confirmation_3p5sigma"
RETIREMENT_REASON = (
    "the frozen specification omitted the market/sector sigma estimator required to determine the "
    "'>= 1 sigma same-direction move in SPY or the sector ETF' confirmation condition"
)


def exit_reason_validation(
    z_now: float,
    sessions_held: int,
    blackout: bool,
    action_announced: bool,
) -> str | None:
    """Frozen section-4 exit ladder, FIRST occurrence wins, minus the retired trigger.

    Rungs, in the frozen order:
        1. earnings blackout engages
        2. a newly announced prohibited corporate action
        3. |z| back inside +/-0.35
        -- the +/-3.5 hypothesis-failure rung is RETIRED and deliberately absent --
        4. time stop: exit at the open of session 6

    Mandatory section-5 reduction is NOT a rung here: it is produced by the joint construction as a
    retention decision and executed under the adopted coupling-reduction semantics.
    """
    if blackout:
        return "exit_earnings_blackout"
    if action_announced:
        return "exit_corporate_action"
    if np.isfinite(z_now) and abs(z_now) <= EXIT_Z:
        return "exit_z_reverted"
    if sessions_held >= MAX_HOLD_SESSIONS:
        return "exit_time_stop"
    return None
