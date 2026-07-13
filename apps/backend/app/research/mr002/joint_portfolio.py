"""MR-002 v1.1 — joint retention-and-entry portfolio construction.

Registered by MR-002 Pre-Registration v1.1 rev 3 (countersigned 2026-07-12,
artifact sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5).

Replaces the v1.0 whole-candidate removal cascade, which was structurally infeasible:
the ratio constraints are scale-invariant, so removing a candidate shrinks G and RAISES
every remaining ratio -- a self-reinforcing cascade that consumed every batch and
produced zero orders on all 124 development sessions.

The correction is a JOINT, DOWNWARD-ONLY, three-stage lexicographic optimization over
existing retention y and new orders x, evaluated on the COMPLETE post-trade book against
ACTUAL gross:

    Stage 1 (LP)  maximize R = sum(y)                    minimize forced liquidation
    Stage 2 (LP)  maximize Q = sum(x)   s.t. R >= R* - eps_retention
    Stage 3 (QP)  minimize D = sum((y-c)^2/c) + sum((x-w)^2/w)
                                        s.t. R >= R* - eps_retention
                                             Q >= Q* - eps_new

x participates in Stage-1 feasibility by design: eligible new positions may supply the
diversification that permits existing positions to be retained.

The constraints are written HOMOGENEOUSLY (expr - k*G <= 0) rather than as ratios
(expr/G <= k). The two are equivalent for G > 0, but the homogeneous form is well-defined
at G = 0 -- which is exactly the state v1.0 could never escape.

THE 1.5% LIMIT IS A NEW-ENTRY SIZING CAP. It bounds x only. Existing positions are never
trimmed merely because mark-to-market exposure exceeds it; they decrease only through a
registered exit or a combined-book coupling-constraint reduction.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import struct
import warnings
from dataclasses import dataclass, field

import numpy as np
import quadprog
from scipy.optimize import linprog

# --------------------------------------------------------------------------------------
# Frozen constants (Pre-Registration v1.1 rev 3). None may be tuned on development
# performance.
# --------------------------------------------------------------------------------------
SECTOR_GROSS_CAP = 0.20          # sector_gross_k <= 0.20 * G
SECTOR_NET_CAP = 0.05            # |sector_net_k|  <= 0.05 * G
BETA_CAP = 0.10                  # |portfolio_beta| <= 0.10 * G
DRIFT_BAND = 0.05                # |portfolio_net|  <= 0.05 * G
MAX_GROSS_NAV = 1.00             # G <= 1.00
NEW_ENTRY_CAP = 0.015            # w_i <= 0.015  -- NEW ENTRIES ONLY

EPS_RETENTION = 1e-8
EPS_NEW = 1e-8
EPS_INCLUDE = 1e-8
EPS_ACTIVE_SECTOR = 1e-6         # reporting threshold only; never a constraint input

PRIMAL_RESIDUAL_MAX = 1e-9
TAU_PRIMAL = PRIMAL_RESIDUAL_MAX  # the lexicographic-band audit inherits the primal
#   feasibility tolerance, because the retention/deployment bands are ROWS OF THE PRIMAL
#   SYSTEM. Owner erratum 2026-07-12 (non-economic; changes no objective and no exposure).
DUAL_RESIDUAL_MAX = 1e-9
STATIONARITY_RESIDUAL_MAX = 1e-8
COMPLEMENTARITY_RESIDUAL_MAX = 1e-8
KKT_RESIDUAL_MAX = 1e-8
HESSIAN_CONDITION_MAX = 1e10

LP_OPTIONS = {
    "presolve": True,
    "primal_feasibility_tolerance": 1e-10,
    "dual_feasibility_tolerance": 1e-10,
    "simplex_dual_edge_weight_strategy": "devex",
    "time_limit": 60.0,
    "maxiter": 100000,
    "disp": False,
}

# Day outcomes
VALID_ZERO_ENTRY_OUTCOME = "VALID_ZERO_ENTRY_OUTCOME"
EXECUTION_CONSTRAINED_INFEASIBLE = "EXECUTION_CONSTRAINED_INFEASIBLE"
FEASIBLE = "FEASIBLE"

# fixed_reason
NO_EXECUTABLE_OPEN = "NO_EXECUTABLE_OPEN"
BELOW_NUMERICAL_INCLUSION_FLOOR = "BELOW_NUMERICAL_INCLUSION_FLOOR"

# zero_entry_reason -- sub-classification of VALID_ZERO_ENTRY_OUTCOME, so that every
# session reconciles to a mutually exclusive registered state (owner audit, 2026-07-12).
SOLVED_ZERO_DEPLOYMENT = "SOLVED_ZERO_DEPLOYMENT"                 # LP ran; Q* = 0
NO_MATCHED_INCREMENT = "NO_MATCHED_INCREMENT"                     # one-sided pool: the
#   dollar-neutrality equality admits no positive new increment, so there are no decision
#   variables. Inherited from v1.0 sizing; NOT a solver outcome.
NO_TRADABLE_HOLDINGS_NO_CANDIDATES = "NO_TRADABLE_HOLDINGS_NO_CANDIDATES"


class InvalidRun(RuntimeError):
    """FATAL. Stops the run. A solver failure is NEVER converted into a no-trade day."""


# --------------------------------------------------------------------------------------
# Stage-3 Equivalent-Formulation Retry -- countersigned implementation erratum
# (2026-07-12, artifact sha256 9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb)
# --------------------------------------------------------------------------------------
RAW = "RAW"
SCALED_RESCUE = "SCALED_RESCUE"

# The rescue trigger is EXACT and FAIL-CLOSED. A reworded message, a different exception
# type, a package-version drift or an artifact mismatch is immediately fatal -- NEVER
# eligible for rescue. In particular "matrix G is not positive definite" must not trigger.
FALSE_INCONSISTENCY = "constraints are inconsistent, no solution"

REGISTERED_QUADPROG_VERSION = "0.1.13"
REGISTERED_QUADPROG_SHA256 = (
    "cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff"
)
_PIP_REPORT = "/manifest/pip_report.json"

_solver_pin_checked = False


def _assert_registered_solver() -> None:
    """The cascade trigger is a version-pinned exact-message match, so a silent version
    drift could otherwise reinterpret a DIFFERENT failure as a rescuable one. Verify both
    the version and the installed Linux artifact against the frozen runtime manifest."""
    global _solver_pin_checked
    if _solver_pin_checked:
        return

    # NOTE: the quadprog MODULE exposes no __version__ attribute. The installed
    # DISTRIBUTION metadata is the authoritative version record and is what the frozen
    # runtime manifest reports, so the pin is read from there.
    try:
        got = importlib.metadata.version("quadprog")
    except importlib.metadata.PackageNotFoundError as exc:
        raise InvalidRun("quadprog distribution metadata not found") from exc
    if got != REGISTERED_QUADPROG_VERSION:
        raise InvalidRun(
            f"quadprog version {got!r} != registered {REGISTERED_QUADPROG_VERSION!r}"
        )

    try:
        with open(_PIP_REPORT, encoding="utf-8") as fh:
            report = json.load(fh)
    except OSError as exc:
        # The registered runtime is the frozen Linux research image, which always carries
        # the in-image pip report. Its absence means we are NOT in the frozen runtime.
        raise InvalidRun(
            f"frozen-runtime manifest {_PIP_REPORT} not readable ({exc}); MR-002 v1.1 "
            "must run inside the frozen mr002-research image"
        ) from exc

    for item in report.get("install", []):
        meta = item.get("metadata", {})
        if meta.get("name") == "quadprog":
            sha = (item.get("download_info", {}).get("archive_info", {})
                   .get("hashes", {}).get("sha256"))
            if sha != REGISTERED_QUADPROG_SHA256:
                raise InvalidRun(
                    f"installed quadprog artifact sha256 {sha!r} != registered "
                    f"{REGISTERED_QUADPROG_SHA256!r}"
                )
            _solver_pin_checked = True
            return

    raise InvalidRun("quadprog not found in the frozen-runtime manifest")


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Holding:
    """An existing position at the execution open, AFTER hard exits are processed."""

    permaticker: int
    d: int                 # +1 long, -1 short  (direction is fixed; never a variable)
    c: float               # current exposure, ABSOLUTE non-negative NAV weight
    sector: str
    beta: float
    entry_weight: float
    tradable: bool         # has an executable open at this session


@dataclass(frozen=True)
class NewCandidate:
    permaticker: int
    d: int
    w: float               # registered unconstrained weight; w <= 0.015, ADV-clip embedded
    sector: str
    beta: float


@dataclass
class Fixed:
    permaticker: int
    d: int
    f: float
    sector: str
    beta: float
    fixed_reason: str


@dataclass
class JointResult:
    outcome: str
    y: dict[int, float] = field(default_factory=dict)     # retained existing exposure
    x: dict[int, float] = field(default_factory=dict)     # new order exposure
    diagnostics: dict = field(default_factory=dict)


def _f64_hex(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


# --------------------------------------------------------------------------------------
# Constraint assembly (Appendix A)
# --------------------------------------------------------------------------------------
def _build(
    fixed: list[Fixed],
    tradable: list[Holding],
    cands: list[NewCandidate],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Return (A_ub, b_ub, A_eq, b_eq, upper_bounds, row_labels).

    z = (y, x) in canonical permaticker order. All coefficients are on ABSOLUTE
    non-negative weights; direction is carried by d.
    """
    n_y, n_x = len(tradable), len(cands)
    n = n_y + n_x

    # per-variable coefficient vectors
    v_d = np.array([h.d for h in tradable] + [c.d for c in cands], dtype=float)
    v_beta = np.array([h.beta for h in tradable] + [c.beta for c in cands], dtype=float)
    v_sector = [h.sector for h in tradable] + [c.sector for c in cands]

    # fixed (constant) contributions
    F_gross = sum(p.f for p in fixed)
    F_net = sum(p.d * p.f for p in fixed)
    F_beta = sum(p.d * p.beta * p.f for p in fixed)
    F_gross_k: dict[str, float] = {}
    F_net_k: dict[str, float] = {}
    for p in fixed:
        F_gross_k[p.sector] = F_gross_k.get(p.sector, 0.0) + p.f
        F_net_k[p.sector] = F_net_k.get(p.sector, 0.0) + p.d * p.f

    sectors = sorted(set(v_sector) | set(F_gross_k))

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    labels: list[str] = []

    ones = np.ones(n)

    def add(coef: np.ndarray, const: float, label: str) -> None:
        # constraint is:  const + coef . z <= 0   ->   coef . z <= -const
        rows.append(coef)
        rhs.append(-const)
        labels.append(label)

    for k in sectors:
        ind = np.array([1.0 if s == k else 0.0 for s in v_sector])
        # sector_gross_k - 0.20 * G <= 0
        add(
            ind - SECTOR_GROSS_CAP * ones,
            F_gross_k.get(k, 0.0) - SECTOR_GROSS_CAP * F_gross,
            f"sector_gross[{k}]",
        )
        # +/- sector_net_k - 0.05 * G <= 0
        net = ind * v_d
        add(
            net - SECTOR_NET_CAP * ones,
            F_net_k.get(k, 0.0) - SECTOR_NET_CAP * F_gross,
            f"sector_net+[{k}]",
        )
        add(
            -net - SECTOR_NET_CAP * ones,
            -F_net_k.get(k, 0.0) - SECTOR_NET_CAP * F_gross,
            f"sector_net-[{k}]",
        )

    beta_c = v_d * v_beta
    add(beta_c - BETA_CAP * ones, F_beta - BETA_CAP * F_gross, "beta+")
    add(-beta_c - BETA_CAP * ones, -F_beta - BETA_CAP * F_gross, "beta-")

    add(v_d - DRIFT_BAND * ones, F_net - DRIFT_BAND * F_gross, "net_drift+")
    add(-v_d - DRIFT_BAND * ones, -F_net - DRIFT_BAND * F_gross, "net_drift-")

    add(ones.copy(), F_gross - MAX_GROSS_NAV, "gross<=1")

    A_ub = np.array(rows, dtype=float) if rows else np.zeros((0, n))
    b_ub = np.array(rhs, dtype=float) if rhs else np.zeros(0)

    # new entries dollar-neutral:  sum_{new long} x - sum_{new short} x = 0
    eq = np.zeros(n)
    for i, c in enumerate(cands):
        eq[n_y + i] = float(c.d)
    A_eq = eq.reshape(1, n)
    b_eq = np.zeros(1)

    upper = np.array([h.c for h in tradable] + [c.w for c in cands], dtype=float)
    return A_ub, b_ub, A_eq, b_eq, upper, labels


def _primal_residual(
    z: np.ndarray,
    A_ub: np.ndarray,
    b_ub: np.ndarray,
    A_eq: np.ndarray,
    b_eq: np.ndarray,
    upper: np.ndarray,
) -> float:
    r = 0.0
    if A_ub.size:
        r = max(r, float(np.max(A_ub @ z - b_ub)) if A_ub.shape[0] else 0.0)
    if A_eq.size:
        r = max(r, float(np.max(np.abs(A_eq @ z - b_eq))))
    r = max(r, float(np.max(np.maximum(-z, 0.0))) if z.size else 0.0)
    r = max(r, float(np.max(np.maximum(z - upper, 0.0))) if z.size else 0.0)
    return max(r, 0.0)


def _solve_lp(
    c_obj: np.ndarray,
    A_ub: np.ndarray,
    b_ub: np.ndarray,
    A_eq: np.ndarray,
    b_eq: np.ndarray,
    upper: np.ndarray,
    label: str,
) -> tuple[np.ndarray | None, dict]:
    """Frozen LP solve. ANY warning is FATAL. Returns (z, info); z is None iff infeasible."""
    bounds = [(0.0, float(u)) for u in upper]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            res = linprog(
                c=c_obj,
                A_ub=A_ub if A_ub.size else None,
                b_ub=b_ub if A_ub.size else None,
                A_eq=A_eq,
                b_eq=b_eq,
                bounds=bounds,
                method="highs-ds",
                options=LP_OPTIONS,
            )
    except Warning as w:  # a silently-rejected option must never reach a result
        raise InvalidRun(f"{label}: solver warning is fatal: {w!r}") from w

    info = {"status": int(res.status), "success": bool(res.success), "message": res.message}
    if res.status == 2:                       # infeasible -- the ONLY non-fatal non-zero
        return None, info
    if not (res.success and res.status == 0):
        raise InvalidRun(f"{label}: LP status {res.status} ({res.message})")

    z = np.asarray(res.x, dtype=float)
    pr = _primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
    if pr > PRIMAL_RESIDUAL_MAX:
        raise InvalidRun(f"{label}: primal residual {pr:.3e} > {PRIMAL_RESIDUAL_MAX:.0e}")
    info["primal_residual"] = pr
    info["objective"] = float(res.fun)
    return z, info


def _qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n):
    """quadprog form: C' z >= b, first meq rows equalities.
        equalities : A_eq z = b_eq
        inequality : A_ub z <= b_ub   ->   -A_ub z >= -b_ub
        bounds     : z >= 0 ; -z >= -upper
    """
    C = np.vstack([A_eq, -A_ub, np.eye(n), -np.eye(n)]).T
    b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper])
    return C, b


def _qp_call(H, a, C, b, meq):
    """Every solve executes under the frozen fatal-warning policy."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def _acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper):
    """ALL residuals, in ORIGINAL z coordinates. Registered as the ONLY basis for
    acceptance (erratum §4) -- scaled-coordinate residuals are diagnostic only."""
    n = len(z)
    primal = _primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
    ineq = lam[meq:]
    dual = float(np.max(np.maximum(-ineq, 0.0))) if ineq.size else 0.0
    stat = float(np.max(np.abs(H @ z - a - C @ lam))) if n else 0.0
    slack = C.T @ z - b
    comp = float(np.max(np.abs(ineq * slack[meq:]))) if ineq.size else 0.0
    kkt = max(primal, dual, stat, comp)
    return {
        "primal_residual": primal,
        "dual_residual": dual,
        "stationarity_residual": stat,
        "complementarity_residual": comp,
        "kkt_residual": kkt,
    }


def _enforce(checks: dict, where: str) -> None:
    limits = {
        "primal_residual": PRIMAL_RESIDUAL_MAX,
        "dual_residual": DUAL_RESIDUAL_MAX,
        "stationarity_residual": STATIONARITY_RESIDUAL_MAX,
        "complementarity_residual": COMPLEMENTARITY_RESIDUAL_MAX,
        "kkt_residual": KKT_RESIDUAL_MAX,
    }
    for name, lim in limits.items():
        if checks[name] > lim:
            raise InvalidRun(f"{where}: {name} {checks[name]:.3e} > {lim:.0e}")


def _solve_qp(
    H_diag: np.ndarray,
    targets: np.ndarray,
    A_ub: np.ndarray,
    b_ub: np.ndarray,
    A_eq: np.ndarray,
    b_eq: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Stage 3 — the COUNTERSIGNED raw -> feasibility-probe -> scaled-rescue cascade.

    Implementation Erratum "Stage-3 Equivalent-Formulation Retry", countersigned
    2026-07-12, artifact sha256 9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb.

    quadprog is a NUMERICAL Goldfarb-Idnani dual active-set solver -- never an exact one.
    It falsely reports "constraints are inconsistent, no solution" on regions that are
    provably feasible (4 of 1,275 solves; 52/52 proven feasible by HiGHS; 0 infeasible).

    The rescue is the SAME solver under a positive-diagonal coordinate transformation, so
    the feasible set and the unique minimizer are IDENTICAL. It is not a fallback solver,
    not regularization, and not a tolerance change.
    """
    _assert_registered_solver()
    n = len(targets)
    t = np.asarray(targets, dtype=float)

    H = np.diag(H_diag)                      # diag(2 / t)
    a = 2.0 * np.ones(n)
    C, b = _qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]

    kappa = float(np.linalg.cond(H)) if n else 1.0
    if kappa > HESSIAN_CONDITION_MAX:
        raise InvalidRun(
            f"hessian_condition_number kappa(H)={kappa:.3e} > {HESSIAN_CONDITION_MAX:.0e}"
        )

    # ---- STEP 1: the REGISTERED RAW formulation, always attempted first -----------------
    try:
        out = _qp_call(H, a, C, b, meq)
        z = np.asarray(out[0], dtype=float)
        lam = np.asarray(out[4], dtype=float)
        checks = _acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
        _enforce(checks, "stage3(raw)")
        info = dict(checks)
        info.update({
            "stage3_formulation": RAW,
            "raw_exception_class": None,
            "raw_exception_message": None,
            "feasibility_probe_status": None,
            "scaled_solver_status": None,
            "raw_coordinate_objective": float(np.sum((z - t) ** 2 / t)),
            "hessian_condition_number": kappa,
            "qp_iterations": [int(i) for i in np.asarray(out[3]).ravel()],
        })
        return z, info

    # ---- STEP 2: the trigger is EXACT and FAIL-CLOSED -----------------------------------
    # A warning is raised as a Warning (fatal-warning policy) -- a DIFFERENT exception type
    # from the registered ValueError -- so it can never reach the cascade. Likewise
    # "matrix G is not positive definite" must never trigger a rescue.
    except ValueError as exc:
        if type(exc) is not ValueError or str(exc) != FALSE_INCONSISTENCY:
            raise InvalidRun(f"stage3: fatal raw exception (not the registered "
                             f"rescue trigger): {type(exc).__name__}: {exc}") from exc
        raw_exc_class, raw_exc_msg = type(exc).__name__, str(exc)
    except Warning as w:
        raise InvalidRun(f"stage3: solver warning is fatal, never a rescue trigger: "
                         f"{w!r}") from w

    # ---- STEP 3.1: transformation guards (bitwise, not approximate) ---------------------
    if not np.all(np.isfinite(t)):
        raise InvalidRun("stage3(rescue): non-finite target -> T not invertible")
    if not np.all(t > EPS_INCLUDE):
        raise InvalidRun("stage3(rescue): target <= eps_include -> T not invertible")
    if t.tobytes() != np.asarray(upper, dtype=float).tobytes():
        raise InvalidRun("stage3(rescue): t_i is not BITWISE IDENTICAL to the registered "
                         "upper bound -- the transformation 0<=z<=t <=> 0<=u<=1 is invalid")

    # ---- STEP 3-4: zero-objective HiGHS feasibility probe on the ORIGINAL region --------
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            probe = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                            bounds=[(0.0, float(u)) for u in upper],
                            method="highs-ds", options=LP_OPTIONS)
    except Warning as w:
        raise InvalidRun(f"stage3(probe): solver warning is fatal: {w!r}") from w
    if not (probe.success and probe.status == 0):
        raise InvalidRun(f"stage3(probe): not optimal (status {probe.status}) -> INVALID_RUN")
    probe_pr = _primal_residual(np.asarray(probe.x, dtype=float),
                                A_ub, b_ub, A_eq, b_eq, upper)
    if probe_pr > PRIMAL_RESIDUAL_MAX:
        raise InvalidRun(f"stage3(probe): primal feasibility {probe_pr:.3e} > "
                         f"{PRIMAL_RESIDUAL_MAX:.0e} -> INVALID_RUN")

    # ---- STEP 5: ONE scaled retry, same solver ------------------------------------------
    #   u = T^-1 z ;  H_s = T H T = diag(2t) ;  a_s = T a = 2t ;  A_s = A T ;  0 <= u <= 1
    T = np.diag(t)
    H_s = np.diag(2.0 * t)
    a_s = 2.0 * t
    A_s = A_ub @ T
    Aeq_s = A_eq @ T
    up_s = upper / t                          # == 1.0 exactly, by the bitwise guard above
    C_s, b_s = _qp_matrices(A_s, b_ub, Aeq_s, b_eq, up_s, n)

    try:
        out = _qp_call(H_s, a_s, C_s, b_s, meq)
    except Warning as w:
        raise InvalidRun(f"stage3(rescue): solver warning is fatal: {w!r}") from w
    except ValueError as exc:
        raise InvalidRun(f"stage3(rescue): quadprog failed: {exc}") from exc

    u = np.asarray(out[0], dtype=float)
    lam_u = np.asarray(out[4], dtype=float)

    # ---- STEP 6: map back ---------------------------------------------------------------
    z = T @ u

    # ---- multiplier transform: ROWS keep their association; BOUNDS divide by t_i --------
    n_rows = meq + A_ub.shape[0]
    lam_z = lam_u.copy()
    lam_z[n_rows:n_rows + n] /= t             # lower-bound multipliers
    lam_z[n_rows + n:] /= t                   # upper-bound multipliers

    # ---- STEP 7: EVERY acceptance check, in ORIGINAL coordinates ------------------------
    checks = _acceptance(z, lam_z, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    _enforce(checks, "stage3(rescue)")        # STEP 8: any failure -> INVALID_RUN

    scaled_diag = _acceptance(u, lam_u, meq, H_s, a_s, C_s, b_s,
                              A_s, b_ub, Aeq_s, b_eq, up_s)   # diagnostic ONLY

    info = dict(checks)
    info.update({
        "stage3_formulation": SCALED_RESCUE,
        "raw_exception_class": raw_exc_class,
        "raw_exception_message": raw_exc_msg,
        "feasibility_probe_status": int(probe.status),
        "scaled_solver_status": "returned",
        "raw_coordinate_objective": float(np.sum((z - t) ** 2 / t)),
        "hessian_condition_number": kappa,
        "qp_iterations": [int(i) for i in np.asarray(out[3]).ravel()],
        "scaled_coordinate_residuals_DIAGNOSTIC_ONLY": scaled_diag,
    })
    # STEP 9: no third attempt, no alternate solver, no regularization -- the function ends.
    return z, info


# --------------------------------------------------------------------------------------
# The registered construction
# --------------------------------------------------------------------------------------
def build_joint(
    holdings: list[Holding],
    candidates: list[NewCandidate],
) -> JointResult:
    """Joint three-stage lexicographic construction. `holdings` must already have hard
    exits removed -- exits are processed BEFORE inclusion-floor classification."""

    # ---- canonical ordering: permanent identifier, everywhere -------------------------
    holdings = sorted(holdings, key=lambda h: h.permaticker)
    candidates = sorted(candidates, key=lambda c: c.permaticker)

    held = {h.permaticker for h in holdings}
    if any(c.permaticker in held for c in candidates):
        raise InvalidRun("no pyramiding / no same-open re-entry: a held symbol appeared "
                         "as a new-order variable")
    for c in candidates:
        if c.w > NEW_ENTRY_CAP + 1e-12:
            raise InvalidRun(
                f"new candidate {c.permaticker} weight {c.w} exceeds the 1.5% entry cap"
            )

    # ---- fixed vs tradable (inclusion floor applies AFTER exits) ----------------------
    fixed: list[Fixed] = []
    tradable: list[Holding] = []
    for h in holdings:
        if not h.tradable:
            fixed.append(Fixed(h.permaticker, h.d, h.c, h.sector, h.beta, NO_EXECUTABLE_OPEN))
        elif h.c <= EPS_INCLUDE:
            # carried as a FIXED constant -- never deleted from the accounting, never
            # increased, never in the Hessian.
            fixed.append(
                Fixed(h.permaticker, h.d, h.c, h.sector, h.beta, BELOW_NUMERICAL_INCLUSION_FLOOR)
            )
        else:
            tradable.append(h)

    below_floor_cands = [c for c in candidates if c.w <= EPS_INCLUDE]
    cands = [c for c in candidates if c.w > EPS_INCLUDE]

    excluded_mass = {
        "below_floor_existing_count": sum(
            1 for p in fixed if p.fixed_reason == BELOW_NUMERICAL_INCLUSION_FLOOR
        ),
        "below_floor_existing_total_weight": sum(
            p.f for p in fixed if p.fixed_reason == BELOW_NUMERICAL_INCLUSION_FLOOR
        ),
        "below_floor_candidate_count": len(below_floor_cands),
        "below_floor_candidate_total_weight": sum(c.w for c in below_floor_cands),
    }

    # ---- EXISTING_POSITION_OVER_ENTRY_CAP: a DIAGNOSTIC, never a constraint -----------
    over_cap = [
        {
            "permaticker": h.permaticker,
            "current_weight": h.c,
            "entry_weight": h.entry_weight,
            "amount_above_1_5pct": h.c - NEW_ENTRY_CAP,
            "tradable_at_open": h.tradable,
            "reduction_due_to_other_constraints": None,   # filled in after the solve
        }
        for h in holdings
        if h.c > NEW_ENTRY_CAP
    ]

    A_ub, b_ub, A_eq, b_eq, upper, labels = _build(fixed, tradable, cands)
    n_y, n_x = len(tradable), len(cands)
    n = n_y + n_x

    diag: dict = {
        "n_fixed": len(fixed),
        "n_tradable": n_y,
        "n_candidates": n_x,
        "fixed_reasons": {p.permaticker: p.fixed_reason for p in fixed},
        "excluded_mass": excluded_mass,
        "existing_position_over_entry_cap": over_cap,
        "constraint_labels": labels,
    }

    # ---- fixed-only coupling feasibility probe (y = 0, x = 0) -------------------------
    # EXECUTION_CONSTRAINED_INFEASIBLE is defined EXCLUSIVELY against the coupling
    # constraints. The 1.5% entry cap can never halt a day.
    # ---- the y = 0, x = 0 probe is a DIAGNOSTIC ONLY (erratum, Defect B) ---------------
    # It shows whether the FIXED BOOK ALONE breaches. It has NO classification authority:
    # z = 0 infeasible does NOT imply the LP is infeasible, because new entries INCREASE
    # gross and DIVERSIFY a fixed exposure, lowering every ratio. Using it to classify the
    # day falsely suppressed 261 of 1,371 ECI sessions.
    # NOTE: with n == 0 the matrix has ZERO COLUMNS, so `A_ub.size` is 0 even though the
    # rows still carry the fixed-book constants in b_ub. The guard must therefore key on
    # the ROW COUNT, never on the element count -- otherwise a fixed-only book is silently
    # treated as unconstrained. (A_ub @ zero == 0, so the test reduces to -b_ub > tol.)
    zero = np.zeros(n)
    fixed_breaches = (
        [labels[i] for i in range(len(labels))
         if (float(A_ub[i] @ zero) - b_ub[i]) > PRIMAL_RESIDUAL_MAX]
        if A_ub.shape[0] else []
    )
    diag["fixed_book_breaches_at_zero_DIAGNOSTIC"] = fixed_breaches
    diag["fixed_by_reason"] = {
        "fixed_no_open_count": sum(1 for p in fixed if p.fixed_reason == NO_EXECUTABLE_OPEN),
        "fixed_no_open_weight": sum(p.f for p in fixed
                                    if p.fixed_reason == NO_EXECUTABLE_OPEN),
        "fixed_below_floor_count": sum(
            1 for p in fixed if p.fixed_reason == BELOW_NUMERICAL_INCLUSION_FLOOR),
        "fixed_below_floor_weight": sum(
            p.f for p in fixed if p.fixed_reason == BELOW_NUMERICAL_INCLUSION_FLOOR),
    }

    def _eci_or_fatal(z_for_topology, where: str) -> JointResult:
        """FROZEN (erratum §2): Stage-1 status 2 WITH a fixed exposure -> ECI.
        Stage-1 status 2 with NO fixed exposure -> INVALID_RUN, because with no fixed
        exposure y=0,x=0 MUST satisfy the homogeneous constraints, the bounds and the
        neutrality equality. Infeasibility there is a malformed model or a numerical
        defect -- never an execution-constrained market state."""
        if not fixed:
            raise InvalidRun(
                f"{where}: LP infeasible with NO fixed exposure -- y=0,x=0 must be "
                "feasible, so this is a malformed model or a numerical defect"
            )
        diag["unavoidable_coupling_breaches"] = fixed_breaches
        diag.update(_topology(fixed, tradable, cands, z_for_topology, n_y))
        diag["determinism_hash"] = _determinism_hash({}, {})
        return JointResult(EXECUTION_CONSTRAINED_INFEASIBLE, {}, {}, diag)

    if n == 0:
        # No decision variables. Feasibility is then decided by the fixed book alone.
        if fixed_breaches:
            return _eci_or_fatal(np.zeros(0), "stage1(no variables)")
        # Sub-classified so the funnel reconciles to mutually exclusive registered states.
        reason = (NO_TRADABLE_HOLDINGS_NO_CANDIDATES if not candidates
                  else NO_MATCHED_INCREMENT)
        diag["R_star"] = 0.0
        diag["Q_star"] = 0.0
        diag["zero_entry_reason"] = reason
        diag.update(_topology(fixed, tradable, cands, np.zeros(0), 0))
        diag["determinism_hash"] = _determinism_hash({}, {})
        return JointResult(VALID_ZERO_ENTRY_OUTCOME, {}, {}, diag)

    # ---- Stage 1: maximize R = sum(y) -- AND the sole authority on ECI ------------------
    c1 = np.concatenate([-np.ones(n_y), np.zeros(n_x)])
    z1, i1 = _solve_lp(c1, A_ub, b_ub, A_eq, b_eq, upper, "stage1")
    diag["stage1_status"] = i1["status"]
    if z1 is None:                               # HiGHS status 2 -- genuinely infeasible
        return _eci_or_fatal(zero, "stage1")
    R_star = float(np.sum(z1[:n_y]))

    # ---- Stage 2: maximize Q = sum(x)  s.t.  R >= R* - eps ----------------------------
    row_R = np.concatenate([-np.ones(n_y), np.zeros(n_x)])
    A2 = np.vstack([A_ub, row_R]) if A_ub.size else row_R.reshape(1, n)
    b2 = np.concatenate([b_ub, [-(R_star - EPS_RETENTION)]])
    c2 = np.concatenate([np.zeros(n_y), -np.ones(n_x)])
    z2, i2 = _solve_lp(c2, A2, b2, A_eq, b_eq, upper, "stage2")
    if z2 is None:
        raise InvalidRun("stage2: LP infeasible although the stage-1 optimum is feasible")
    Q_star = float(np.sum(z2[n_y:]))

    # ---- Stage 3: unique closest allocation -------------------------------------------
    row_Q = np.concatenate([np.zeros(n_y), -np.ones(n_x)])
    A3 = np.vstack([A2, row_Q])
    b3 = np.concatenate([b2, [-(Q_star - EPS_NEW)]])

    targets = np.array([h.c for h in tradable] + [c.w for c in cands], dtype=float)
    H_diag = 2.0 / targets                                     # every target > EPS_INCLUDE
    z3, i3 = _solve_qp(H_diag, targets, A3, b3, A_eq, b_eq, upper)

    R = float(np.sum(z3[:n_y]))
    Q = float(np.sum(z3[n_y:]))

    # ---- two-sided lexicographic band audit -------------------------------------------
    # The bands  R >= R* - eps_retention  and  Q >= Q* - eps_new  are ROWS OF THE PRIMAL
    # SYSTEM, so they are satisfied to the registered primal tolerance -- not exactly.
    # Stage 3 legitimately spends the full eps of slack (that is what the registered
    # formulation permits it to do), landing ON the boundary; auditing that boundary with
    # ZERO tolerance would contradict the registered acceptance rule primal_residual <=
    # PRIMAL_RESIDUAL_MAX and would fail on floating-point noise of order 1e-19.
    # FROZEN AUDIT (owner erratum, 2026-07-12):
    #   R* - eps_retention - tau_primal <= realized_R <= R* + eps_retention + tau_primal
    #   Q* - eps_new       - tau_primal <= realized_Q <= Q* + eps_new       + tau_primal
    #   tau_primal = PRIMAL_RESIDUAL_MAX = 1e-9
    band = EPS_RETENTION + TAU_PRIMAL
    if not (R_star - band <= R <= R_star + band):
        raise InvalidRun(f"retention band violated: R={R!r} vs R*={R_star!r}")
    band_q = EPS_NEW + TAU_PRIMAL
    if not (Q_star - band_q <= Q <= Q_star + band_q):
        raise InvalidRun(f"deployment band violated: Q={Q!r} vs Q*={Q_star!r}")

    # ---- downward-only invariants ------------------------------------------------------
    for i, h in enumerate(tradable):
        if z3[i] > h.c + PRIMAL_RESIDUAL_MAX:
            raise InvalidRun(f"existing position {h.permaticker} increased: {z3[i]} > {h.c}")
    for i, c in enumerate(cands):
        if z3[n_y + i] > c.w + PRIMAL_RESIDUAL_MAX:
            raise InvalidRun(
                f"new candidate {c.permaticker} exceeded its registered weight: "
                f"{z3[n_y + i]} > {c.w}"
            )

    y = {h.permaticker: float(z3[i]) for i, h in enumerate(tradable)}
    x = {c.permaticker: float(z3[n_y + i]) for i, c in enumerate(cands)}

    for rec in over_cap:
        if rec["permaticker"] in y:
            rec["reduction_due_to_other_constraints"] = rec["current_weight"] - y[rec["permaticker"]]
        else:
            rec["reduction_due_to_other_constraints"] = 0.0     # fixed: cannot trade

    # ---- post-target constraint re-check, DIVISION-FREE (the registered measure) -------
    # Every homogeneous coupling row re-evaluated on the realized allocation. This -- not
    # any ratio -- is what attests compliance, and it is well-defined at G = 0.
    viol = A_ub @ z3 - b_ub
    max_violation = float(np.max(viol)) if viol.size else 0.0
    if max_violation > PRIMAL_RESIDUAL_MAX:
        worst = labels[int(np.argmax(viol))]
        raise InvalidRun(
            f"post-target constraint breach on {worst}: {max_violation:.3e} > "
            f"{PRIMAL_RESIDUAL_MAX:.0e}"
        )
    binding = [labels[i] for i in range(len(labels)) if viol[i] > -1e-9]

    diag.update(
        {
            "R_star": R_star,
            "Q_star": Q_star,
            "realized_R": R,
            "realized_Q": Q,
            "stage1": i1,
            "stage2": i2,
            "stage3": i3,
            "retained_existing_gross": R + sum(p.f for p in fixed),
            "new_gross": Q,
            "max_homogeneous_violation": max_violation,
            "binding_constraints": binding,
        }
    )
    diag.update(_topology(fixed, tradable, cands, z3, n_y))
    diag["determinism_hash"] = _determinism_hash(y, x)

    if Q <= EPS_NEW:
        diag["zero_entry_reason"] = SOLVED_ZERO_DEPLOYMENT
        return JointResult(VALID_ZERO_ENTRY_OUTCOME, y, x, diag)
    return JointResult(FEASIBLE, y, x, diag)


def _topology(
    fixed: list[Fixed],
    tradable: list[Holding],
    cands: list[NewCandidate],
    z: np.ndarray,
    n_y: int,
) -> dict:
    """Sector topology and binding-constraint report (permitted structural inspection)."""
    book: list[tuple[str, float, int, float]] = [
        (p.sector, p.f, p.d, p.beta) for p in fixed
    ]
    book += [(h.sector, float(z[i]), h.d, h.beta)
             for i, h in enumerate(tradable) if i < len(z)]
    book += [(c.sector, float(z[n_y + i]), c.d, c.beta)
             for i, c in enumerate(cands) if n_y + i < len(z)]

    G = sum(w for _s, w, _d, _b in book)
    sg: dict[str, float] = {}
    sn: dict[str, float] = {}
    for s, w, d, _b in book:
        sg[s] = sg.get(s, 0.0) + w
        sn[s] = sn.get(s, 0.0) + d * w
    beta = sum(d * b * w for _s, w, d, b in book)
    net = sum(d * w for _s, w, d, _b in book)

    active = sorted(s for s, g in sg.items() if g > EPS_ACTIVE_SECTOR)

    # RATIOS ARE REPORTING ONLY, AND ARE UNDEFINED AT NEAR-ZERO GROSS.
    # The registered constraints are HOMOGENEOUS (expr - k*G <= 0) precisely so that no
    # division by G ever occurs -- that division is the pathology that invalidated v1.0.
    # Re-introducing it in the REPORT would manufacture meaningless ratios out of solver
    # dust (e.g. 2e-19 / 1e-20 = 20). Ratios are therefore emitted only when gross is
    # materially positive; constraint satisfaction itself is attested by the
    # division-free primal residual, never by these.
    material = G > EPS_ACTIVE_SECTOR
    return {
        "total_gross": G,
        "gross_is_material": material,
        "active_sectors": active,
        "active_sector_count": len(active),
        "active_sector_note": (
            "theoretical positive-sector count is >= 5 for any positive feasible "
            "portfolio; the reported count applies the frozen 1e-6 reporting threshold "
            "and may differ solely because of it"
        ),
        "max_sector_gross_ratio": (max(sg.values()) / G) if material else None,
        "max_sector_net_ratio": (max(abs(v) for v in sn.values()) / G) if material else None,
        "normalized_beta": (beta / G) if material else None,
        "normalized_net": (net / G) if material else None,
        "sector_gross": sg,
        "sector_net": sn,
    }


def _determinism_hash(y: dict[int, float], x: dict[int, float]) -> str:
    """Canonical IEEE-754 hex serialization in permanent-identifier order."""
    parts: list[str] = []
    for tag, book in (("y", y), ("x", x)):
        for pt in sorted(book):
            parts.append(f"{tag}:{pt}:{_f64_hex(book[pt])}")
    return hashlib.sha256("|".join(parts).encode("ascii")).hexdigest()
