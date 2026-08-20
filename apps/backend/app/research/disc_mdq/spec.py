"""DISC-MDQ-001 frozen constants — MDQ microstructure enrichment for DISC-001.

Phase A is **infrastructure only**: an exploration policy that decides what may
be read, and a reader that can only read what the policy authorized. No feature
is computed here, no DISC-001 candidate is re-ranked, and no DISC-001 admission
threshold is touched. ``disc001.spec.SCREEN_VERSION`` stays ``v0.3.0``.

Governing constraints this module encodes (all pre-existing, none invented here):

* **Two-way evidence firewall** (registration §8.1, ratified 2026-08-17) —
  value-extraction outputs are INADMISSIBLE to K1–K6, and no K definition,
  threshold, tolerance, denominator or evaluability clause may be revised once
  value-extraction work begins.
* **Exploration never reads the holdout** (§4.10.2, ratified 2026-08-17) — the
  10 symbol holdout and the final-12-day period holdout are quarantined from
  ALL exploratory / value-extraction access. A graduating hypothesis is
  evaluated on the holdout **once**, through a separate explicit act.
* **Discovery ledger** (§4.10.2) — every condition examined is recorded, dated,
  with its disposition; a later pre-registration must cite its ledger entry and
  the number of conditions examined in that family.
* **Research plane** (ADR 0051) — this package imports no order-path module and
  holds no broker capability.

⚠ ``ReadPurpose`` deliberately has exactly ONE member. Graduating-hypothesis
evaluation against the holdout is **not** a purpose value and must never be
added as one: the owner's design puts it on a separate explicit one-time path,
not behind a flag on the exploratory reader. Adding a member here would create
precisely the kind of bypass this codebase has repeatedly paid to remove.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

PROGRAM_ID = "DISC-MDQ-001"
POLICY_VERSION = "mdq-exploration-policy/0.1.0"
READER_VERSION = "mdq-feature-reader/0.1.0"

# The DISC-001 screen this overlays. Phase A must not change it.
ENRICHES_SCREEN_ID = "DISC-001-WATCHLIST"
ENRICHES_SCREEN_VERSION = "v0.3.0"

# --- Governed review window ------------------------------------------------
# D0 is the first admissible governed frozen partition, adjudicated
# 2026-08-19 (mdq-admissibility/0.1.0, report sha 5f30c446…, S3 VersionId
# GgmfUfUOFfnkSOhpsGhF15hvtYt_eeNP) and stamped in
# docs/design/MDQ-001_ProgramStart_Record_v0_2.md. Program start is the first
# admissible partition — not the deployment, not the first write.
REVIEW_D0 = date(2026, 8, 19)
REVIEW_END_EXCLUSIVE = date(2026, 10, 18)
REVIEW_WINDOW_DAYS = 60

# Period holdout = final 20% (12 calendar days) of the 60-day window, i.e.
# 2026-10-06 .. 2026-10-17 inclusive. Derived here from the frozen rule rather
# than hardcoded, and cross-checked against the holdout artifact when that
# artifact carries concrete dates (see policy.load_holdout_artifact).
PERIOD_HOLDOUT_DAYS = 12

# The holdout artifact ships this literal until someone stamps the concrete
# dates into it. It has NOT been stamped since D0, so the period holdout is not
# machine-readable from the artifact alone — the policy fails closed rather
# than guessing. See policy.load_holdout_artifact.
PERIOD_HOLDOUT_UNSTAMPED = "STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE"

HOLDOUT_ARTIFACT_ID = "MDQ001_EXPLORATION_HOLDOUT"
UNIVERSE_SYMBOLS_SHA256 = "0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4"


class ReadPurpose(StrEnum):
    """Why a read is being attempted.

    EXPLORATION is the only sanctioned purpose in Phase A. See the module
    docstring for why holdout evaluation is not — and must not become — a
    member of this enum.
    """

    EXPLORATION = "exploration"


class Decision(StrEnum):
    """Outcome of a policy check. Everything except ALLOWED denies the read."""

    ALLOWED = "allowed"

    # Not a denial in spirit: the symbol is simply outside MDQ's 50-name Phase-A
    # universe. DISC-001 candidates carrying this value are perfectly valid
    # candidates and must NEVER be demoted for it (owner, 2026-08-20).
    UNAVAILABLE_NOT_IN_UNIVERSE = "unavailable_not_in_universe"

    DENIED_HOLDOUT_SYMBOL = "denied_holdout_symbol"
    DENIED_HOLDOUT_PERIOD = "denied_holdout_period"
    DENIED_OUTSIDE_REVIEW_WINDOW = "denied_outside_review_window"
    DENIED_UNRESOLVED_HOLDOUT_PERIOD = "denied_unresolved_holdout_period"


#: Decisions that permit a read. Exactly one, deliberately.
ALLOWING_DECISIONS = frozenset({Decision.ALLOWED})

#: The value DISC-001 snapshots carry for a candidate MDQ cannot observe.
#: Additive only — it never participates in ranking or admission.
ENRICHMENT_UNAVAILABLE = Decision.UNAVAILABLE_NOT_IN_UNIVERSE.value


def period_holdout_bounds(
    end_exclusive: date = REVIEW_END_EXCLUSIVE,
    holdout_days: int = PERIOD_HOLDOUT_DAYS,
) -> tuple[date, date]:
    """Return ``(start_inclusive, end_exclusive)`` of the period holdout.

    The frozen rule is "the final 12 calendar days of the 60-day review
    window", so the holdout is the last ``holdout_days`` days before the
    window's exclusive end.
    """
    from datetime import timedelta

    if holdout_days <= 0:
        raise ValueError(f"holdout_days must be positive, got {holdout_days}")
    return end_exclusive - timedelta(days=holdout_days), end_exclusive
