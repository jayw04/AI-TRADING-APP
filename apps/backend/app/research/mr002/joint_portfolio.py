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


class InvalidRun(RuntimeError):
    """FATAL. Stops the run. A solver failure is NEVER converted into a no-trade day."""


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


def _solve_qp(
    H_diag: np.ndarray,
    targets: np.ndarray,
    A_ub: np.ndarray,
    b_ub: np.ndarray,
    A_eq: np.ndarray,
    b_eq: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Stage 3. quadprog is a NUMERICAL Goldfarb-Idnani dual active-set solver -- never
    an exact one. Acceptance rests on the registered residual checks below."""
    n = len(targets)

    # D = sum (z-t)^2 / t = sum z^2/t - 2 sum z + const
    # quadprog minimizes 1/2 z' H z - a' z   =>   H = diag(2/t), a = 2 * 1
    H = np.diag(H_diag)
    a = 2.0 * np.ones(n)

    kappa = float(np.linalg.cond(H)) if n else 1.0
    if kappa > HESSIAN_CONDITION_MAX:
        raise InvalidRun(
            f"hessian_condition_number kappa(H)={kappa:.3e} > {HESSIAN_CONDITION_MAX:.0e}"
        )

    # quadprog form: C' z >= b, first meq rows are equalities.
    #   equalities : A_eq z = b_eq
    #   inequality : A_ub z <= b_ub   ->   -A_ub z >= -b_ub
    #   bounds     : z >= 0 ; -z >= -upper
    C_rows = [A_eq, -A_ub, np.eye(n), -np.eye(n)]
    b_rows = [b_eq, -b_ub, np.zeros(n), -upper]
    C = np.vstack([r for r in C_rows if r.size]).T
    b = np.concatenate([r for r in b_rows if r.size])
    meq = A_eq.shape[0]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = quadprog.solve_qp(H, a, C, b, meq)
    except Warning as w:
        raise InvalidRun(f"stage3: solver warning is fatal: {w!r}") from w
    except ValueError as exc:
        # Both registered fatal exceptions. "constraints are inconsistent" MUST NOT occur
        # here: stages 1 and 2 already proved the region non-empty.
        raise InvalidRun(f"stage3: quadprog failed: {exc}") from exc

    z = np.asarray(out[0], dtype=float)
    lam = np.asarray(out[4], dtype=float)

    primal = _primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
    ineq_lam = lam[meq:]
    dual = float(np.max(np.maximum(-ineq_lam, 0.0))) if ineq_lam.size else 0.0
    stationarity = float(np.max(np.abs(H @ z - a - C @ lam))) if n else 0.0
    slack = C.T @ z - b
    comp = float(np.max(np.abs(ineq_lam * slack[meq:]))) if ineq_lam.size else 0.0
    kkt = max(primal, dual, stationarity, comp)

    checks = {
        "primal_residual": (primal, PRIMAL_RESIDUAL_MAX),
        "dual_residual": (dual, DUAL_RESIDUAL_MAX),
        "stationarity_residual": (stationarity, STATIONARITY_RESIDUAL_MAX),
        "complementarity_residual": (comp, COMPLEMENTARITY_RESIDUAL_MAX),
        "kkt_residual": (kkt, KKT_RESIDUAL_MAX),
    }
    for name, (val, lim) in checks.items():
        if val > lim:
            raise InvalidRun(f"stage3: {name} {val:.3e} > {lim:.0e}")

    info = {k: v[0] for k, v in checks.items()}
    info["hessian_condition_number"] = kappa
    info["qp_iterations"] = [int(i) for i in np.asarray(out[3]).ravel()]
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
    zero = np.zeros(n)
    if A_ub.size and float(np.max(A_ub @ zero - b_ub)) > PRIMAL_RESIDUAL_MAX:
        breaches = [
            labels[i]
            for i in range(len(labels))
            if (A_ub[i] @ zero - b_ub[i]) > PRIMAL_RESIDUAL_MAX
        ]
        diag["unavoidable_coupling_breaches"] = breaches
        return JointResult(EXECUTION_CONSTRAINED_INFEASIBLE, {}, {}, diag)

    if n == 0:
        diag["R_star"] = 0.0
        diag["Q_star"] = 0.0
        return JointResult(VALID_ZERO_ENTRY_OUTCOME, {}, {}, diag)

    # ---- Stage 1: maximize R = sum(y) -------------------------------------------------
    c1 = np.concatenate([-np.ones(n_y), np.zeros(n_x)])
    z1, i1 = _solve_lp(c1, A_ub, b_ub, A_eq, b_eq, upper, "stage1")
    if z1 is None:
        # The zero probe above already proved a feasible point exists, so the LP cannot
        # be infeasible here. This is a defect, not a market condition.
        raise InvalidRun("stage1: LP infeasible although z=0 satisfies every constraint")
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
    band = EPS_RETENTION + PRIMAL_RESIDUAL_MAX
    if not (R_star - band <= R <= R_star + band):
        raise InvalidRun(f"retention band violated: R={R!r} vs R*={R_star!r}")
    band_q = EPS_NEW + PRIMAL_RESIDUAL_MAX
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

    outcome = VALID_ZERO_ENTRY_OUTCOME if Q <= EPS_NEW else FEASIBLE
    return JointResult(outcome, y, x, diag)


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
    book += [(h.sector, float(z[i]), h.d, h.beta) for i, h in enumerate(tradable)]
    book += [(c.sector, float(z[n_y + i]), c.d, c.beta) for i, c in enumerate(cands)]

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
