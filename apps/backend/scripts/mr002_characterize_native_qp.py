"""MR-002 v1.1 — NATIVE HiGHS-QP and CLARABEL CHARACTERIZATION (immutable 3,895 corpus).

Authorized after capability discovery. OFFLINE ONLY. No performance is computed. Preflight
and development run remain stopped. Validation and sealed OOS remain sealed and unread.

Bound records:
  MR002_QP_CandidateCapabilityManifest.json                       5f422175…  (HiGHS VALID)
  MR002_QP_CandidateCapabilityManifest_ClarabelRemediation.json   8c1d83ec…
  MR002_QP_CapabilityManifest_Amendment_ClarabelFieldMapping.json cc3de7db…  (Clarabel VALID)

PREDECLARED before the first instance is solved:
  * HiGHS tolerance configuration = H1  (kkt_tolerance = 1e-10; individual tolerances left at
    documented defaults). HiGHS documents that a NON-DEFAULT kkt_tolerance is used for ALL KKT
    measures, so H1 is the unambiguous configuration. H1 and H2 are NOT combined.
  * qp_regularization_value = 0        (default 1e-7 WOULD alter the submitted objective)
  * small_matrix_value = 1e-12         (corpus min |nonzero| = 2.93e-4, safely above)
  * Selection rule: HiGHS has precedence, fixed BEFORE characterization.

REVISED AGREEMENT GATES (strong convexity). Coordinate distance is a DIAGNOSTIC, not a
qualification gate: for D(z) = (1/2)z'Hz + q'z with H = diag(2/t), the strong-convexity
modulus is m = 2/max(t) ~ 133, so an objective gap g certifies only ||z - z*|| <= sqrt(2g/m)
~ 1.2e-6 at g = 1e-10 -- NOT 1e-8.
"""
from __future__ import annotations

import hashlib
import json
import sys
import warnings
from collections import Counter

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
TOL = 1e-10
GAP_MAX = 1e-10
TIME_LIMIT = 60.0
CLARABEL_PROPORTIONAL = 4.930380657631324e-32


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def external_gap(z, lam, meq, m_ub, t, A_ub, b_ub, A_eq, b_eq, upper) -> float:
    """External original-coordinate primal-dual gap.

    f(z) = (1/2) z'Pz + q'z ,  P = diag(2/t), q = -2*1
    Standard Lagrangian: Pz + q + G'lam + A_eq'nu_std = 0 with G = [A_ub; -I; I],
    h = [b_ub; 0; upper], lam >= 0.  At a KKT point w = q + G'lam + A_eq'nu_std = -Pz, so
        gap = f(z) - dual(lam, nu) = z'Pz + q'z + h'lam + b_eq'nu_std
    Our canonical convention has nu_std = -nu.
    """
    n = len(t)
    P_z = (2.0 / t) * z
    nu = lam[:meq]
    lam_ineq = lam[meq:meq + m_ub]
    lam_lo = lam[meq + m_ub:meq + m_ub + n]
    lam_hi = lam[meq + m_ub + n:]
    f_quad = float(z @ P_z)                      # z'Pz
    q_z = float(-2.0 * np.sum(z))                # q'z
    h_lam = float(b_ub @ lam_ineq) + 0.0 + float(np.asarray(upper, float) @ lam_hi)
    b_nu = float(b_eq @ (-nu))
    _ = lam_lo                                   # h component is exactly 0
    return f_quad + q_z + h_lam + b_nu


# ======================================================================================
def solve_highs(t, A_ub, b_ub, A_eq, b_eq, upper):
    import highspy

    n = len(t)
    m_ub, meq = A_ub.shape[0], A_eq.shape[0]
    h = highspy.Highs()
    for k, v in (("output_flag", False), ("log_to_console", False),
                 ("solver", "qpasm"), ("presolve", "off"), ("parallel", "off"),
                 ("threads", 1), ("random_seed", 0), ("time_limit", TIME_LIMIT),
                 ("qp_allow_hot_start", False),
                 ("qp_regularization_value", 0.0),      # default 1e-7 WOULD alter the QP
                 ("small_matrix_value", 1e-12),
                 ("kkt_tolerance", TOL)):               # H1 -- NOT combined with H2
        st = h.setOptionValue(k, v)
        if "kOk" not in str(st):
            raise RuntimeError(f"option {k} rejected: {st}")

    inf = highspy.kHighsInf
    A = np.vstack([A_eq, A_ub]) if m_ub else A_eq
    lp = highspy.HighsLp()
    lp.num_col_ = n
    lp.num_row_ = A.shape[0]
    lp.col_cost_ = -2.0 * np.ones(n)
    lp.col_lower_ = np.zeros(n)
    lp.col_upper_ = np.asarray(upper, float)
    lp.row_lower_ = np.concatenate([b_eq, np.full(m_ub, -inf)])
    lp.row_upper_ = np.concatenate([b_eq, b_ub])
    S = sp.csr_matrix(A)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = S.indptr.tolist()
    lp.a_matrix_.index_ = S.indices.tolist()
    lp.a_matrix_.value_ = S.data.tolist()

    hess = highspy.HighsHessian()
    hess.dim_ = n
    hess.format_ = highspy.HessianFormat.kTriangular
    hess.start_ = list(range(n + 1))
    hess.index_ = list(range(n))
    hess.value_ = (2.0 / t).tolist()

    model = highspy.HighsModel()
    model.lp_ = lp
    model.hessian_ = hess
    if "kOk" not in str(h.passModel(model)):
        raise RuntimeError("passModel failed")
    if "kOk" not in str(h.run()):
        raise RuntimeError("run status not kOk")
    ms = str(h.getModelStatus())
    if "kOptimal" not in ms:
        raise RuntimeError(f"model status {ms}")

    sol = h.getSolution()
    z = np.asarray(sol.col_value, float)
    rd = np.asarray(sol.row_dual, float)
    cd = np.asarray(sol.col_dual, float)

    # HiGHS QP dual convention, ESTABLISHED EMPIRICALLY on a hand-solvable problem
    # (min (1/2)z'diag(2/t)z - 2'z s.t. z1+z2 <= 0.01, 0<=z<=0.02; optimum z=(0.005,0.005),
    #  grad = (-0.75,-0.75), row_dual = -0.75):
    #
    #       H z - a  =  A' y_row  +  y_col
    #
    # i.e. the dual of an ACTIVE `<=` row is NEGATIVE. Canonical MR-002 convention is
    #       H z - a  =  A_eq' nu  -  A_ub' lam_ineq  +  lam_lo  -  lam_hi      (lam >= 0)
    # Matching term by term:
    #       nu       =  y_eq                    (NOT -y_eq)
    #       lam_ineq = -y_ub                    (NOT +y_ub)   -- y_ub <= 0 for active rows
    #       lam_lo   =  max(+y_col, 0)          (NOT max(-y_col, 0))
    #       lam_hi   =  max(-y_col, 0)          (NOT max(+y_col, 0))
    lam = np.concatenate([rd[:meq], -rd[meq:],
                          np.maximum(cd, 0.0), np.maximum(-cd, 0.0)])
    return z, lam


def solve_clarabel(t, A_ub, b_ub, A_eq, b_eq, upper):
    import clarabel

    n = len(t)
    m_ub, meq = A_ub.shape[0], A_eq.shape[0]
    P = sp.csc_matrix(np.diag(2.0 / t))
    q = -2.0 * np.ones(n)
    A = sp.csc_matrix(np.vstack([A_eq, A_ub, -np.eye(n), np.eye(n)]))
    b = np.concatenate([b_eq, b_ub, np.zeros(n), np.asarray(upper, float)])
    cones = [clarabel.ZeroConeT(meq), clarabel.NonnegativeConeT(m_ub + 2 * n)]

    s = clarabel.DefaultSettings()
    s.max_threads = 1
    s.max_iter = 500
    s.time_limit = TIME_LIMIT
    s.verbose = False
    s.tol_gap_abs = TOL
    s.tol_gap_rel = TOL
    s.tol_feas = TOL
    s.tol_infeas_abs = TOL
    s.tol_infeas_rel = TOL
    s.equilibrate_enable = True
    s.presolve_enable = False
    s.direct_kkt_solver = True
    s.direct_solve_method = "qdldl"
    # AMENDED FIELD MAPPING (owner-approved): the Python binding's base static-regularization
    # control is `static_regularization_constant` (documented as `static_regularization_eps`).
    # It is pinned SEPARATELY from `static_regularization_proportional` -- neither is aliased.
    s.static_regularization_enable = True
    s.static_regularization_constant = 1e-8
    s.static_regularization_proportional = CLARABEL_PROPORTIONAL
    s.dynamic_regularization_enable = True
    s.dynamic_regularization_eps = 1e-13
    s.dynamic_regularization_delta = 2e-7
    s.iterative_refinement_enable = True

    sol = clarabel.DefaultSolver(P, q, A, b, cones, s).solve()
    if str(sol.status) != "Solved":
        raise RuntimeError(f"status {sol.status}")
    z = np.asarray(sol.x, float)
    y = np.asarray(sol.z, float)
    # Clarabel: Px + q + A'y = 0, A = [A_eq; A_ub; -I; I]
    lam = np.concatenate([-y[:meq], y[meq:meq + m_ub],
                          y[meq + m_ub:meq + m_ub + n], y[meq + m_ub + n:]])
    return z, lam


# ======================================================================================
def evaluate(fn, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq, m_ub = A_eq.shape[0], A_ub.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    ck = jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    g = external_gap(z, lam, meq, m_ub, t, A_ub, b_ub, A_eq, b_eq, upper)
    ck["external_primal_dual_gap"] = g
    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)
    if g < -1e-9:
        bad.append("gap_negative")
    if g > GAP_MAX:
        bad.append("gap_exceeds_1e-10")
    return z, ck, bad, g


def main() -> int:
    with open("/out/MR002_Stage3_Corpus_Hashes.json", encoding="utf-8") as fh:
        HH = json.load(fh)
    npz = np.load("/out/MR002_Stage3_Corpus.npz")
    N = len(HH["instance_hashes"])
    inst, ok = [], 0
    for i in range(N):
        rec = tuple(npz[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        if _hash_instance(*rec) == HH["instance_hashes"][i]:
            ok += 1
        inst.append(rec)
    print(f"corpus {N} instances | per-instance hashes verified: {ok}/{N}")
    if ok != N:
        print("CORPUS VERIFICATION FAILED", file=sys.stderr)
        return 1

    R = {"instances": N, "corpus_verified": True,
         "predeclared": {"highs_tolerance_config": "H1 (kkt_tolerance=1e-10)",
                         "qp_regularization_value": 0.0,
                         "selection_rule": "HiGHS precedence, fixed before characterization"},
         "candidates": {}}
    P = {}

    for name, fn in (("HIGHS_QPASM", solve_highs), ("CLARABEL", solve_clarabel)):
        print(f"\n=== {name} ===", flush=True)
        c = {"qualified_instances": 0, "failed": 0, "failure_kinds": Counter(),
             "worst_kkt": 0.0, "worst_stationarity": 0.0, "worst_primal": 0.0,
             "worst_gap": 0.0}
        zs, gs = {}, {}
        for i, rec in enumerate(inst):
            try:
                z, ck, bad, g = evaluate(fn, *(x.copy() for x in rec))
                c["worst_kkt"] = max(c["worst_kkt"], ck["kkt_residual"])
                c["worst_stationarity"] = max(c["worst_stationarity"],
                                              ck["stationarity_residual"])
                c["worst_primal"] = max(c["worst_primal"], ck["primal_residual"])
                c["worst_gap"] = max(c["worst_gap"], abs(g))
                if bad:
                    c["failed"] += 1
                    c["failure_kinds"]["+".join(bad)] += 1
                else:
                    c["qualified_instances"] += 1
                    zs[i], gs[i] = z, g
            except Exception as e:
                c["failed"] += 1
                c["failure_kinds"][f"{type(e).__name__}:{str(e)[:60]}"] += 1
            if (i + 1) % 1000 == 0:
                print(f"  {i+1}/{N} qualified={c['qualified_instances']} "
                      f"failed={c['failed']}", flush=True)
        c["failure_kinds"] = dict(c["failure_kinds"])
        c["solves_all"] = c["failed"] == 0
        R["candidates"][name] = c
        P[name] = (zs, gs)
        print(f"  QUALIFIED {c['qualified_instances']}/{N}  FAILED {c['failed']}")
        print(f"  worst KKT {c['worst_kkt']:.3e} | stationarity {c['worst_stationarity']:.3e} "
              f"| gap {c['worst_gap']:.3e}")

    # ---- strong-convexity consistency envelope ----------------------------------------
    hz, hg = P["HIGHS_QPASM"]
    cz, cg = P["CLARABEL"]
    both = sorted(set(hz) & set(cz))
    env_ok = obj_ok = True
    worst_ratio = worst_dz = worst_dobj = 0.0
    for i in both:
        t = inst[i][0]
        m = 2.0 / float(np.max(t))
        r1 = np.sqrt(2.0 * max(hg[i], 0.0) / m)
        r2 = np.sqrt(2.0 * max(cg[i], 0.0) / m)
        dz = float(np.linalg.norm(hz[i] - cz[i]))
        bound = r1 + r2 + 1e-10
        worst_dz = max(worst_dz, dz)
        worst_ratio = max(worst_ratio, dz / bound if bound > 0 else 0.0)
        if dz > bound:
            env_ok = False
        d1 = float(np.sum((hz[i] - t) ** 2 / t))
        d2 = float(np.sum((cz[i] - t) ** 2 / t))
        dobj = abs(d1 - d2)
        worst_dobj = max(worst_dobj, dobj)
        if dobj > hg[i] + cg[i] + 1e-12:
            obj_ok = False
    R["agreement"] = {
        "instances_both_qualified": len(both),
        "strong_convexity_envelope_satisfied": env_ok,
        "worst_dz_over_envelope_bound": worst_ratio,
        "worst_L2_primal_disagreement_DIAGNOSTIC": worst_dz,
        "objective_agreement_satisfied": obj_ok,
        "worst_objective_disagreement": worst_dobj,
    }

    q = [k for k in ("HIGHS_QPASM", "CLARABEL") if R["candidates"][k]["solves_all"]]
    R["qualified"] = q
    if len(q) == 2 and env_ok and obj_ok:
        sel = "HIGHS_QPASM — both qualify and agree; Clarabel retained as offline verifier"
    elif "HIGHS_QPASM" in q:
        sel = "HIGHS_QPASM"
    elif "CLARABEL" in q:
        sel = "CLARABEL"
    else:
        sel = "NEITHER — STOP FOR ADJUDICATION"
    R["selection"] = sel
    R["VERDICT"] = "PASS" if q and env_ok and obj_ok else "FAIL"

    dst = "/out/MR002_NativeQP_Characterization.json"
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(R, fh, indent=2, default=str)
        fh.write("\n")
    print("\n" + json.dumps({k: R[k] for k in
          ("candidates", "agreement", "qualified", "selection", "VERDICT")},
          indent=2, default=str))
    print(f"\nreport: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
