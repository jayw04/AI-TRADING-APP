"""MR-002 Phase 3C — validation portfolio replay and the two frozen validation gates.

Phase 3C is a THIN real-data wiring of already-frozen machinery. It invents no economics. Every
economic rule it applies is bound by identity elsewhere:

    entry selection      app.research.mr002.runner._candidates          (frozen section-4 rules)
    exit ladder          app.research.mr002.phase3c.exits               (frozen ladder MINUS the
                                                                        retired +/-3.5 sigma trigger)
    construction         app.research.mr002.joint_portfolio.build_joint (v1.1-rev-3, GOVERNING)
    coupling reductions  the ADOPTED v1.1 development mechanics         (see `adopted`)
    costs / borrow       app.research.mr002.execution                   (10 bps/side, 50 bps/yr /360)
    folds                app.research.mr002.phase3c.folds               (5 frozen literal ranges)

Governing authority, in order:

    MR002_ValidationOOS_Preregistration_v1.0.4.json   b2a042d4...
    phase3a/ValidationRunSpecification_v1.0.json      (folds, configs, windows)
    phase3a/ValidationCostExecutionSpecification_v1.0.json
    phase3a/MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json
    phase3bc/MR002_Phase3C_OwnerRulings_v1.2.json     (rulings 1-4, R5/R5A, R6)

WHAT PHASE 3C MUST NOT DO
    - compute net_oos_sharpe, the 0.70 gate, the stationary bootstrap, DSR significance, or any
      cost-stress gate. Those carry sample_stage "sealed OOS" and are PROHIBITED here.
    - search parameters, substitute configs, or reinterpret an integrity stop as an economic result.

An integrity stop is INTEGRITY_FAILURE. It is never VALIDATION_DO_NOT_ADVANCE.
"""

from __future__ import annotations

from datetime import date

# ---- windows -----------------------------------------------------------------------------
# AMENDED 2026-08-20 by MR002_Validation2_ProspectiveAmendmentDrafts_v1.0 Amendment C, under the
# owner ruling that redesignated the pristine former-OOS partition as Validation-2 and reassigned
# the OOS role to prospective post-seal accrual.
#
# ⛔ WHY THIS AMENDMENT WAS NECESSARY, and what it deliberately does NOT do.
# Governance moved the holdout boundary; this module kept enforcing the old one, exactly as it
# should have. The previous OOS_WINDOW_START (2023-05-30) is the FIRST SCORING-ELIGIBLE session of
# what is now Validation-2, so the interlock would have aborted the replay at the very session
# scoring begins. The fix is to move the governed boundary. The interlock itself is UNCHANGED and
# still fatal. `assert_oos_boundary=False` remains PROHIBITED for qualifying or executing
# Validation-2 -- switching off the check that enforces a boundary is not the same as moving it.
#
# Validation-1 (2019-10-03 .. 2023-02-16) is CONSUMED and permanently inadmissible; its literals
# are retained below as history, never as configuration.
VALIDATION_1_WINDOW_START = date(2019, 10, 3)      # CONSUMED - historical record only
VALIDATION_1_WINDOW_END = date(2023, 2, 16)        # CONSUMED - historical record only

VALIDATION_WINDOW_START = date(2023, 2, 17)
VALIDATION_WINDOW_END = date(2026, 7, 10)
SCORING_ELIGIBLE_FIRST = date(2023, 5, 30)
SCORING_ELIGIBLE_LAST = date(2026, 7, 1)
VALIDATION_WINDOW_SESSIONS = 850
ELIGIBLE_SESSIONS = 775

# ⭐ The scoring-eligible bounds above are ordinals 70 and 844 of the 850-session window. They were
# NOT chosen: they are the identical values this module already carried as the OOS scoring window,
# frozen long before Cycle 2C from the same 69-formation / 6-realization arithmetic, and they were
# independently recomputed by MR002_Validation2_StructuralPreflight_v1.0
# (3810e071761a5100fe8cda6754488ebac5230f74b1b5e0f812ec53764d94436a). That agreement is
# corroboration, not the derivation.

# The sealed holdout beyond Validation-2. Touching it is fatal, not advisory.
#
# The new OOS is PROSPECTIVE post-seal accrual and does not exist in the governed corpus, whose
# latest source date is 2026-07-10. A concrete start date therefore CANNOT be derived today and is
# deliberately not invented. The interlock is expressed against the Validation-2 window END, which
# is mechanical and needs no future calendar: any session beyond the Validation-2 partition is out
# of bounds, whether it is unallocated or new OOS.
NEW_OOS_ACCRUAL_RULE = (
    "the first eligible market session under the governing calendar STRICTLY AFTER the Cycle-2C "
    "seal of 2026-08-20. Resolved by the calendar when accrual begins; not hard-coded here, "
    "because the corpus ends 2026-07-10 and any literal would be fabricated."
)
OUT_OF_BOUNDS_AFTER = VALIDATION_WINDOW_END

# ---- frozen economics (phase3a/ValidationCostExecutionSpecification_v1.0.json) -----------
NAV0 = 10_000_000.0
COST_BPS_PER_SIDE = 10.0
BORROW_BPS_PER_YEAR = 50.0
REALIZATION_HORIZON = 6          # next-open exit t+1..t+6
FORMATION_EXCLUDE_SESSIONS = 69

# ---- the three preregistered configurations; B is the ONLY verdict configuration --------
VALIDATION_CONFIGS = ("A", "B", "C")
VERDICT_CONFIG = "B"

# ---- validation-stage verdict domain -----------------------------------------------------
VALIDATION_ADVANCE_REQUEST = "VALIDATION_ADVANCE_REQUEST"
VALIDATION_DO_NOT_ADVANCE = "VALIDATION_DO_NOT_ADVANCE"
VALIDATION_INCONCLUSIVE = "VALIDATION_INCONCLUSIVE"
INTEGRITY_FAILURE = "INTEGRITY_FAILURE"

# ---- integrity stop codes ruled by the owner ---------------------------------------------
DRIFT_REPAIR_QUANTITY_UNDEFINED = "DRIFT_REPAIR_TRIGGERED_BUT_QUANTITY_UNDEFINED"
OOS_BOUNDARY_VIOLATION = "OOS_BOUNDARY_VIOLATION"
FOLD_ASSIGNMENT_MISMATCH = "FOLD_ASSIGNMENT_MISMATCH"


class IntegrityFailure(RuntimeError):
    """A replay-DEFINITION failure. Never converted into an economic verdict."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
