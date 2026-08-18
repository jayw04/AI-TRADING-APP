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

# ---- windows (phase3a/ValidationRunSpecification_v1.0.json -> "windows") -----------------
VALIDATION_WINDOW_START = date(2019, 10, 3)
VALIDATION_WINDOW_END = date(2023, 2, 16)
SCORING_ELIGIBLE_FIRST = date(2020, 1, 13)
SCORING_ELIGIBLE_LAST = date(2023, 2, 8)
VALIDATION_WINDOW_SESSIONS = 850
ELIGIBLE_SESSIONS = 775

# The sealed OOS window. Touching it is fatal, not advisory.
OOS_WINDOW_START = date(2023, 5, 30)
OOS_WINDOW_END = date(2026, 7, 1)

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
