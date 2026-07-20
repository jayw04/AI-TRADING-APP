"""Frozen numerical-mechanics constants for the SPQ-1 producer (Phase-0, all FROZEN/RESOLVED).

These are mechanics constants, never performance knobs. The OLS solver identity and its rank
tolerance are preregistered here (census SIG-10 / Ruling 2) and echoed in the implementation
manifest for review.
"""
from __future__ import annotations

# --- window lengths (SIG-08/12/14/16) ---
OLS_WINDOW = 60            # registered sessions t-60..t-1 for both regressions
R5_HORIZON = 5             # residuals summed for R5 (five consecutive registered sessions)
Z_NORM_OBS = 60            # complete overlapping R5 observations ending t-1 for mu/sigma
DDOF = 1                   # sample standard deviation

# --- stock model parameter count (intercept + SPY + u_sector); sector model (intercept + SPY) ---
STOCK_PARAMS = 3
SECTOR_PARAMS = 2

# --- warm-up boundary (SIG-32 / OWNER-A, RATIFIED): first scoreable decision session t ---
WARMUP_RETURN_SESSIONS = 125   # registered return sessions [t-124, t] (124 prior + current)
WARMUP_PRICE_OBSERVATIONS = 126  # registered price observations [t-125, t]

# --- ADV (SIG-25 / OWNER-B, RATIFIED): MEDIAN of raw close x raw volume, windows ending t-1 ---
ADV_SELECTION_WINDOW = 60   # universe + liquidity screen (median)
ADV_CAPACITY_WINDOW = 20    # trailing_adv_dollars (median) -> 2% execution cap

# --- registered OLS solver identity + rank tolerance (SIG-10 / Ruling 2, preregistered) ---
SOLVER_IDENTITY = "numpy.linalg.lstsq[LAPACK_gelsd_SVD,float64]"
RANK_TOLERANCE = 1e-10      # rcond: fail closed when cond(design) > 1/RANK_TOLERANCE (=1e10)

# --- eligibility precedence (SIG-23 / Ruling 9): fixed order 1..6 ---
PRECEDENCE = {
    "integrity_or_identity": 1,
    "missing_mandatory_signal_input": 2,
    "security_or_universe_ineligible": 3,
    "event_blackout": 4,
    "liquidity_or_price": 5,
    "signal_selection_downstream": 6,
}
