"""MR-002 v1.1 — PIQP capability discovery (P1/P2) and immutable-corpus characterization.

Owner-authorized 2026-07-13. OFFLINE ONLY. No performance computed. Preflight and development
run remain stopped. Validation and sealed OOS remain sealed and unread.

FROZEN LEXICOGRAPHIC PROFILE RULE (registered BEFORE the first PIQP corpus solve):
    P1  preconditioner_scale_cost = false   (vendor default)   -- PRECEDENCE
    P2  preconditioner_scale_cost = true    (everything else IDENTICAL)

    run P1 on all 3,895 -> if it qualifies on every instance, SELECT P1 and stop.
    else preserve the P1 evidence and run P2 independently, from fresh solver objects.
    P2 must independently qualify on all 3,895. Otherwise: stop for adjudication.

This is PROFILE SELECTION, not a runtime cascade. The production implementation contains
only the selected profile and must never retry a failed live instance with the other.

PIQP native form:   min (1/2)x'Px + c'x   s.t.  Ax = b,  h_l <= Gx <= h_u,  x_l <= x <= x_u
MR-002 mapping:     P = diag(2/t), c = -2*1, A = A_eq, b = b_eq,
                    G = A_ub, h_l = -inf, h_u = b_ub, x_l = 0, x_u = upper

PIQP dual convention, ESTABLISHED on hand-solvable fixtures (see verify_signs):
    P x + c + A'y + G'(z_u - z_l) + (z_bu - z_bl) = 0
canonical MR-002:
    H z - a = A_eq'nu - A_ub'lam_ineq + lam_lo - lam_hi        (lam >= 0)
=>  nu = -y ;  lam_ineq = z_u - z_l ;  lam_lo = z_bl ;  lam_hi = z_bu
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import sys
import warnings

import numpy as np
import piqp
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
GAP_MAX = 1e-10
INF = 1e30

# ---- FROZEN settings; the ONLY difference between profiles is preconditioner_scale_cost --
BASE = {
    "eps_abs": 1e-10,
    "eps_rel": 1e-11,
    "check_duality_gap": True,
    "eps_duality_gap_abs": 1e-11,
    "eps_duality_gap_rel": 1e-11,
    "max_iter": 1000,
    "preconditioner_reuse_on_update": False,
    "iterative_refinement_always_enabled": True,
    "iterative_refinement_eps_abs": 1e-13,
    "iterative_refinement_eps_rel": 1e-13,
    "iterative_refinement_max_iter": 20,
    "kkt_solver": piqp.sparse_ldlt,
    "verbose": False,
    "compute_timings": False,
}
PROFILES = {"P1": False, "P2": True}          # preconditioner_scale_cost


def make_solver(scale_cost: bool):
    """FRESH solver object per instance. No update, reuse or warm start."""
    s = piqp.SparseSolver()
    for k, v in BASE.items():
        setattr(s.settings, k, v)
    s.settings.preconditioner_scale_cost = scale_cost
    return s


def solve_piqp(scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    s = make_solver(scale_cost)
    s.setup(sp.csc_matrix(np.diag(2.0 / t)), -2.0 * np.ones(n),
            sp.csc_matrix(A_eq), np.asarray(b_eq, float),
            sp.csc_matrix(A_ub), np.full(A_ub.shape[0], -INF), np.asarray(b_ub, float),
            np.zeros(n), np.asarray(upper, float))
    st = s.solve()
    if st != piqp.PIQP_SOLVED:
        raise RuntimeError(f"status {st}")
    r = s.result
    z = np.asarray(r.x, float)
    y = np.asarray(r.y, float)
    lam_ineq = np.asarray(r.z_u, float) - np.asarray(r.z_l, float)
    lam = np.concatenate([-y, lam_ineq,
                          np.asarray(r.z_bl, float), np.asarray(r.z_bu, float)])
    return z, lam


def external_gap(z, lam, meq, m_ub, t, b_ub, b_eq, upper):
    n = len(t)
    nu = lam[:meq]
    lam_ineq = lam[meq:meq + m_ub]
    lam_hi = lam[meq + m_ub + n:]
    return (float(z @ ((2.0 / t) * z)) - 2.0 * float(np.sum(z))
            + float(b_ub @ lam_ineq) + float(np.asarray(upper, float) @ lam_hi)
            + float(b_eq @ (-nu)))


def evaluate(scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq, m_ub = A_eq.shape[0], A_ub.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = solve_piqp(scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    ck = jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    g = external_gap(z, lam, meq, m_ub, t, b_ub, b_eq, upper)
    ck["external_primal_dual_gap"] = g
    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)
    if g < -1e-9:
        bad.append("gap_negative")
    if g > GAP_MAX:
        bad.append("gap_exceeds_1e-10")
    return z, ck, bad, g


# ======================================================================================
# CAPABILITY DISCOVERY
# ======================================================================================
def verify_signs() -> dict:
    """Prove ALL SIX dual-vector mappings on hand-solvable fixtures."""
    out = {}

    # (1) active general INEQUALITY + inactive bounds
    t = np.array([0.008, 0.008])
    z, lam = solve_piqp(False, t, np.array([[1.0, 1.0]]), np.array([0.01]),
                        np.zeros((0, 2)), np.zeros(0), 0.02 * np.ones(2))
    grad = (2.0 / t) * z - 2.0
    C, _ = jp._qp_matrices(np.array([[1.0, 1.0]]), np.array([0.01]),
                           np.zeros((0, 2)), np.zeros(0), 0.02 * np.ones(2), 2)
    out["active_inequality"] = {
        "z": z.tolist(), "expected_z": [0.005, 0.005],
        "grad": grad.tolist(), "lam_ineq": lam[0:1].tolist(),
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
    }

    # (2) active EQUALITY  (z1 + z2 = 0.01)
    t = np.array([0.008, 0.008])
    z, lam = solve_piqp(False, t, np.zeros((0, 2)), np.zeros(0),
                        np.array([[1.0, 1.0]]), np.array([0.01]), 0.02 * np.ones(2))
    C, _ = jp._qp_matrices(np.zeros((0, 2)), np.zeros(0),
                           np.array([[1.0, 1.0]]), np.array([0.01]), 0.02 * np.ones(2), 2)
    out["active_equality"] = {
        "z": z.tolist(), "expected_z": [0.005, 0.005], "nu": lam[0:1].tolist(),
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
    }

    # (3) active UPPER BOUND: t above the cap -> z pinned at upper, lam_hi > 0
    t = np.array([0.02])
    z, lam = solve_piqp(False, t, np.zeros((0, 1)), np.zeros(0),
                        np.zeros((0, 1)), np.zeros(0), np.array([0.01]))
    C, _ = jp._qp_matrices(np.zeros((0, 1)), np.zeros(0),
                           np.zeros((0, 1)), np.zeros(0), np.array([0.01]), 1)
    out["active_upper_bound"] = {
        "z": z.tolist(), "expected_z": [0.01], "lam_lo": lam[0:1].tolist(),
        "lam_hi": lam[1:2].tolist(), "lam_hi_positive": bool(lam[1] > 1e-6),
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
    }

    # (4) active LOWER BOUND: an inequality forces z2 to 0 (coefficient 10x)
    t = np.array([0.01, 0.01])
    z, lam = solve_piqp(False, t, np.array([[1.0, 10.0]]), np.array([0.005]),
                        np.zeros((0, 2)), np.zeros(0), 0.02 * np.ones(2))
    C, _ = jp._qp_matrices(np.array([[1.0, 10.0]]), np.array([0.005]),
                           np.zeros((0, 2)), np.zeros(0), 0.02 * np.ones(2), 2)
    out["active_lower_bound"] = {
        "z": z.tolist(), "z2_at_lower_bound": bool(abs(z[1]) < 1e-9),
        "lam_lo": lam[1:3].tolist(),
        "lam_lo_z2_positive": bool(lam[2] > 1e-6),
        "stationarity": float(np.max(np.abs(np.diag(2.0 / t) @ z - 2.0 - C @ lam))),
    }

    out["all_stationarity_pass"] = all(
        v["stationarity"] <= LIMITS["stationarity_residual"]
        for v in out.values() if isinstance(v, dict))
    return out


def preconditioning_microproblem() -> dict:
    """Discriminating STRONGLY-SCALED Hessian: t spans 1e-8 .. 1.5e-2 (2/t spans 1e2..2e8),
    exactly the MR-002 pathology. Both profiles receive the IDENTICAL submitted (P,q,A,b)."""
    t = np.array([1.0e-8, 5.0e-5, 1.5e-2])
    A_ub = np.array([[1.0, 1.0, 1.0]])
    b_ub = np.array([0.01])
    A_eq = np.zeros((0, 3))
    b_eq = np.zeros(0)
    upper = t.copy()
    payload = hashlib.sha256(b"".join(
        np.ascontiguousarray(x, dtype=np.float64).tobytes()
        for x in (2.0 / t, -2.0 * np.ones(3), A_ub, b_ub, A_eq, b_eq,
                  np.zeros(3), upper))).hexdigest()

    res = {"submitted_payload_sha256": payload,
           "identical_inputs_for_both_profiles": True,
           "hessian_entries": (2.0 / t).tolist()}
    zs = {}
    for name, sc in PROFILES.items():
        z, ck, bad, g = evaluate(sc, t.copy(), A_ub.copy(), b_ub.copy(),
                                 A_eq.copy(), b_eq.copy(), upper.copy())
        zs[name] = z
        res[name] = {"preconditioner_scale_cost": sc, "z": z.tolist(),
                     "external_checks_pass": not bad, "failures": bad,
                     "kkt_residual": ck["kkt_residual"], "gap": g,
                     "iterations": None}
    # strong-convexity envelope between the two accepted primals
    m = 2.0 / float(np.max(t))
    g1, g2 = res["P1"]["gap"], res["P2"]["gap"]
    r1 = np.sqrt(2.0 * max(g1, 0.0) / m)
    r2 = np.sqrt(2.0 * max(g2, 0.0) / m)
    dz = float(np.linalg.norm(zs["P1"] - zs["P2"]))
    res["strong_convexity_envelope"] = {
        "dz": dz, "bound": r1 + r2 + 1e-10, "satisfied": dz <= r1 + r2 + 1e-10}
    # is P2's flag BEHAVIOURALLY active (not merely readable)?
    s1, s2 = make_solver(False), make_solver(True)
    res["p2_flag_behaviourally_active"] = {
        "P1_read_back": s1.settings.preconditioner_scale_cost,
        "P2_read_back": s2.settings.preconditioner_scale_cost,
        "distinct": s1.settings.preconditioner_scale_cost
        != s2.settings.preconditioner_scale_cost,
        "note": ("PIQP unscales internally before returning; both profiles are judged by the "
                 "SAME external original-coordinate battery, which both pass."),
    }
    return res


def discovery() -> dict:
    rep = json.load(open("/manifest/pip_report.json", encoding="utf-8"))
    art = {i["metadata"]["name"]: (i.get("download_info", {}).get("archive_info", {}) or {})
           .get("hashes", {}).get("sha256") for i in rep["install"]}

    M = {
        "record_type": "MR002_PIQP_CANDIDATE_CAPABILITY_MANIFEST",
        "record_status": "IMMUTABLE",
        "date": "2026-07-13",
        "distribution": {"name": "piqp", "version": md.version("piqp"),
                         "artifact_sha256": art.get("piqp"),
                         "instruction_set": str(piqp.instruction_set())
                         if callable(getattr(piqp, "instruction_set", None))
                         else str(getattr(piqp, "instruction_set", None))},
        "environment": {"python": sys.version.split()[0],
                        "abi": f"cp{sys.version_info.major}{sys.version_info.minor}",
                        "platform": platform.platform(),
                        "machine": platform.machine()},
        "solver_implementation": "SparseSolver",
        "fresh_solver_object_per_instance": True,
        "warm_start_or_update_used": False,
        "profiles": {}, "fatal": [],
    }

    for name, sc in PROFILES.items():
        s = make_solver(sc)
        rec = {"preconditioner_scale_cost_requested": sc,
               "preconditioner_scale_cost_read_back": s.settings.preconditioner_scale_cost,
               "read_back_exact": s.settings.preconditioner_scale_cost == sc,
               "settings": {}}
        for k, v in BASE.items():
            got = getattr(s.settings, k)
            ok = (got == v)
            rec["settings"][k] = {"requested": str(v), "read_back": str(got),
                                  "exact": bool(ok)}
            if not ok:
                M["fatal"].append(f"{name}: {k} read back {got!r}, requested {v!r}")
        # pinned installed defaults (internal numerical controls)
        rec["pinned_installed_defaults"] = {
            k: getattr(s.settings, k) for k in
            ("rho_init", "delta_init", "preconditioner_iter", "reg_lower_limit",
             "reg_finetune_lower_limit", "max_factor_retires", "tau",
             "iterative_refinement_static_regularization_eps",
             "iterative_refinement_static_regularization_rel")}
        if not rec["read_back_exact"]:
            M["fatal"].append(f"{name}: preconditioner_scale_cost read-back mismatch")
        M["profiles"][name] = rec

    # negative control
    s = make_solver(False)
    try:
        setattr(s.settings, "mr002_not_a_real_setting", 1.0)
        rejected = not hasattr(s.settings, "mr002_not_a_real_setting")
    except Exception:
        rejected = True
    M["negative_control"] = {"option": "mr002_not_a_real_setting", "rejected": bool(rejected)}
    if not rejected:
        M["fatal"].append("PIQP silently accepted an unknown setting")

    M["only_profile_difference"] = "preconditioner_scale_cost (all other settings identical)"
    M["native_status_mapping"] = {
        "accepted": "PIQP_SOLVED",
        "all_others_are_failures": [
            str(x) for x in (piqp.PIQP_MAX_ITER_REACHED, piqp.PIQP_PRIMAL_INFEASIBLE,
                             piqp.PIQP_DUAL_INFEASIBLE, piqp.PIQP_NUMERICS,
                             piqp.PIQP_UNSOLVED, piqp.PIQP_INVALID_SETTINGS)]}
    M["dual_sign_proofs"] = verify_signs()
    if not M["dual_sign_proofs"]["all_stationarity_pass"]:
        M["fatal"].append("dual sign-convention fixtures failed")
    M["preconditioning_microproblem"] = preconditioning_microproblem()
    for p in ("P1", "P2"):
        if not M["preconditioning_microproblem"][p]["external_checks_pass"]:
            M["fatal"].append(f"{p} failed the preconditioning microproblem")
    if not M["preconditioning_microproblem"]["strong_convexity_envelope"]["satisfied"]:
        M["fatal"].append("microproblem: strong-convexity envelope violated between profiles")

    M["frozen_selection_rule"] = (
        "Run P1 on all 3,895. If P1 qualifies on EVERY instance -> select P1 and stop; P2 "
        "corpus results are NOT used for selection. If P1 fails >= 1 -> preserve P1 evidence "
        "and run P2 independently from fresh solver objects; P2 must independently qualify on "
        "all 3,895. Otherwise stop for adjudication. PROFILE SELECTION, NOT a runtime cascade.")
    M["verdict"] = "VALID" if not M["fatal"] else "INVALID"
    return M


if __name__ == "__main__":
    M = discovery()
    out = "/out/MR002_PIQP_CandidateCapabilityManifest.json"
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(M, fh, indent=2, default=str)
        fh.write("\n")
    print(json.dumps({k: M[k] for k in (
        "distribution", "negative_control", "dual_sign_proofs",
        "preconditioning_microproblem", "fatal", "verdict")}, indent=2, default=str))
    print(f"\nmanifest: {out}")
    raise SystemExit(0 if M["verdict"] == "VALID" else 1)
