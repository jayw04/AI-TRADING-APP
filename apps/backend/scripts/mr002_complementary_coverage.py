"""MR-002 v1.1 — COMPLEMENTARY-COVERAGE REPORT (owner ruling §13, revised adjudication).

Production cascade under adjudication:   QUADPROG_SQRT  ->  PIQP_P2   (no third attempt)
Offline verifiers only:                  Clarabel, HiGHS

Produces every item §13 requires before countersign:

  * immutable corpus + sidecar hashes                (re-captured, verified EXACTLY)
  * canonical acceptance-module hash                 (§8)
  * wrapper + dual-mapping hashes                    (§8)
  * per-instance qualification matrix, all solvers   (§13)
  * five primary-failure CONTENT hashes              (§10 — identity is the hash, NOT the index)
  * QUADPROG_SQRT -> PIQP_P2 unresolved count        (must be 0)
  * same-image determinism                           (§15)
  * shuffle invariance                               (§10)
  * strong-convexity agreement                       (§9)
  * explicit correction of the "2765 requires HiGHS" statement (§1, §13)

THE CANONICAL PREDICATE (owner ruling §7 + §9). ONE implementation — `app.research.mr002.
certificate` — governs primary, fallback, offline characterization, fixtures and preflight:

    primal / dual / stationarity / complementarity / aggregate-KKT   <= registered LIMITS
    CERTIFIED dual-lower-bound gap  G = upper(f) - lower(d_cert)     in [0, 1e-10]
    interval widths of f and d_cert                                  <= 1e-30

⚠ THIS SUPERSEDES THE SIGNED-GAP PREDICATE, which was INVALIDATED. That quantity came from
approximate solver duals and could be NEGATIVE; `max(g, 0)` then assigned zero uncertainty and
collapsed the agreement radius to a bare 1e-10, demanding that an active-set and an interior-point
method agree below double-precision reproducibility. It was never a certificate. The replacement
is a rigorous dual lower bound from weak duality, valid for ANY dual-feasible multipliers.

The KKT gates and the certified gap are SEPARATE hard conditions. The gap does not replace KKT
verification, and the KKT tolerance does not inflate the gap.

The prior artifact (`MR002_ComplementaryCoverage.json`, sha256 790002c0…) is IMMUTABLE and keeps
its disposition: CASCADE COVERAGE PASSED / AGREEMENT GATE FAILED / SPECIFICATION INVALIDATED /
NOT COUNTERSIGNED. This run writes a NEW file.

DIAGNOSTIC ONLY. No performance computed, printed or persisted. Preflight and the development
run remain STOPPED. Validation and sealed OOS remain sealed and unread.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import warnings
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

# ---- IMPORTED, never re-derived (§9). This discipline is not decorative: a hand-rolled
# ---- Clarabel produced a false "structural, close v1.1" verdict earlier in this program.
from app.research.mr002.certificate import (  # noqa: E402
    CERTIFIED_GAP_MAX,
    MAX_INTERVAL_WIDTH,
    CertificateDefect,
    agreement,
    bound_intervals,
    certify,
    objective_agreement,
    project_dual,
    verify_canonical_hessian,
)
from scripts.mr002_characterize_native_qp import (  # noqa: E402
    solve_clarabel as _clarabel_raw,
)
from scripts.mr002_characterize_native_qp import (
    solve_highs as _highs_raw,
)
from scripts.mr002_piqp import solve_piqp as _piqp_raw  # noqa: E402
from scripts.mr002_solver_intersection import (  # noqa: E402
    LIMITS,
    REGISTERED_CORPUS_HASH,
    _hash_instance,
    solve_raw,
    solve_sqrt,
    solve_tscaled,
)

CORPUS: list[dict] = []


# ======================================================================================
# §9 — the ONE canonical predicate
#
# ⚠ SUPERSEDES the signed external gap. That quantity was formed from approximate solver duals
# and could come out NEGATIVE — at which point max(g, 0) assigned zero uncertainty and collapsed
# the agreement radius. It was never a certificate. The replacement is the certified dual LOWER
# BOUND (weak duality, interval endpoints, >= 100 digits), which is valid for ANY dual-feasible
# multipliers and does not borrow validity from the solver's own optimality claim.
#
# The KKT gates and the certified gap are SEPARATE hard conditions. The gap does not replace KKT
# verification, and the KKT tolerance does not inflate the gap — the rejected proposal did exactly
# that, treating a residual norm as an objective error.
# ======================================================================================
def canonical_qualify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    verify_canonical_hessian(H, t)                      # §3 — the registered 2/t objective
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    ck = jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)
    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)

    cert = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)   # raises on a defective construction
    if not cert.qualifies:
        if cert.certified_gap < 0.0:
            bad.append("certified_gap_negative")
        elif cert.certified_gap > CERTIFIED_GAP_MAX:
            bad.append("certified_gap_exceeds_1e-10")
        else:
            bad.append("interval_width_too_wide")
    return (not bad), bad, ck, cert


def _lam_of(fn_raw):
    """Wrap a raw (z, lam) solver into the canonical qualification."""
    def run(t, A_ub, b_ub, A_eq, b_eq, upper):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            z, lam = fn_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
        if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
            raise RuntimeError("non-finite primal or dual")
        return z, lam
    return run


def _quadprog_variant(fn_checks):
    """The quadprog wrappers return (z, checks); recover lam via the same construction."""
    def run(t, A_ub, b_ub, A_eq, b_eq, upper):
        import quadprog
        n = len(t)
        C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
        meq = A_eq.shape[0]
        if fn_checks is solve_sqrt:
            s = np.sqrt(t)
            S = np.diag(s)
            C_v, b_v = jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out = quadprog.solve_qp(2.0 * np.eye(n), 2.0 * s, C_v, b_v, meq)
            v = np.asarray(out[0], float)
            lam_v = np.asarray(out[4], float)
            z = S @ v
            nr = meq + A_ub.shape[0]
            lam = lam_v.copy()
            lam[nr:nr + n] /= s
            lam[nr + n:] /= s
            return z, lam
        if fn_checks is solve_raw:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out = quadprog.solve_qp(np.diag(2.0 / t), 2.0 * np.ones(n), C, b, meq)
            return np.asarray(out[0], float), np.asarray(out[4], float)
        T = np.diag(t)
        C_u, b_u = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, np.ones(n), n)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = quadprog.solve_qp(2.0 * np.diag(t), 2.0 * t, C_u, b_u, meq)
        u = np.asarray(out[0], float)
        lam_u = np.asarray(out[4], float)
        z = T @ u
        nr = meq + A_ub.shape[0]
        lam = lam_u.copy()
        lam[nr:nr + n] /= t
        lam[nr + n:] /= t
        return z, lam
    return run


SOLVERS = {
    "QUADPROG_SQRT": _quadprog_variant(solve_sqrt),          # PRIMARY
    "PIQP_P2": _lam_of(lambda *a: _piqp_raw(True, *a)),      # FALLBACK (adjudicated)
    "PIQP_P1": _lam_of(lambda *a: _piqp_raw(False, *a)),
    "QUADPROG_RAW": _quadprog_variant(solve_raw),
    "QUADPROG_TSCALED": _quadprog_variant(solve_tscaled),
    "CLARABEL": _lam_of(_clarabel_raw),                      # offline verifier
    "HIGHS_QPASM": _lam_of(_highs_raw),                      # offline verifier
}
PRIMARY, FALLBACK = "QUADPROG_SQRT", "PIQP_P2"


# ======================================================================================
# §10 — fixture identity is the CONTENT HASH of the canonical original problem
# ======================================================================================
def fixture_hash(inst: dict) -> str:
    h = hashlib.sha256()
    h.update(b"MR002|stage3|canonical-original-problem|v1")
    for key in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"):
        a = np.ascontiguousarray(np.asarray(inst[key], dtype=np.float64))
        h.update(key.encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    h.update(b"|acceptance-policy|")
    h.update(json.dumps(LIMITS, sort_keys=True).encode())
    h.update(f"|certified_gap<={CERTIFIED_GAP_MAX}|width<={MAX_INTERVAL_WIDTH}".encode())
    return h.hexdigest()


def _src_hash(*objs) -> str:
    h = hashlib.sha256()
    for o in objs:
        h.update(inspect.getsource(o).encode())
    return h.hexdigest()


# ======================================================================================
def capture(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    t = np.asarray(targets, float)
    CORPUS.append({
        "t": t.copy(), "A_ub": A_ub.copy(), "b_ub": b_ub.copy(),
        "A_eq": A_eq.copy(), "b_eq": b_eq.copy(),
        "upper": np.asarray(upper, float).copy(),
        "hash": _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper),
    })
    for fn in (solve_raw, solve_sqrt, solve_tscaled):
        try:
            z, ck = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
            if not [k for k, lim in LIMITS.items() if ck[k] > lim]:
                return z, dict(ck, stage3_formulation="CAPTURE",
                               hessian_condition_number=1.0, qp_iterations=[0, 0])
        except ValueError:
            continue
    from scipy.optimize import linprog
    n = len(t)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                options=jp.LP_OPTIONS)
    if not f.success:
        raise jp.InvalidRun("capture: infeasible")
    z = np.asarray(f.x, float)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], H, a, C, b,
                        A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def try_solve(name, rec):
    try:
        z, lam = SOLVERS[name](*(x.copy() for x in rec))
        ok, bad, _ck, cert = canonical_qualify(z, lam, *rec)
        return ok, ("+".join(bad) if bad else ""), z, lam, cert
    except CertificateDefect:
        raise                       # a broken CERTIFICATE is not a solver failure — STOP
    except Exception as e:  # noqa: BLE001 — a raise IS a nonqualification
        return False, f"{type(e).__name__}: {str(e)[:70]}", None, None, None


def main() -> int:  # noqa: PLR0915
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    n_inst = len(CORPUS)
    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {n_inst}  hash {ch}")
    if ch != REGISTERED_CORPUS_HASH:
        print("ABORT: corpus hash mismatch", file=sys.stderr)
        return 1
    print("[ok] corpus reproduced EXACTLY\n")

    print("CANONICAL PREDICATE = registered LIMITS + CERTIFIED dual-lower-bound gap in "
          "[0, 1e-10]   (§7/§9)\n")

    matrix: dict[str, dict[int, str]] = {k: {} for k in SOLVERS}
    fails: dict[str, set[int]] = {k: set() for k in SOLVERS}
    zs: dict[str, dict[int, np.ndarray]] = {k: {} for k in SOLVERS}
    certs: dict[str, dict[int, object]] = {k: {} for k in SOLVERS}
    clip_log: list[dict] = []
    neg_log: list[dict] = []
    worst_width = 0.0

    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        for name in SOLVERS:
            ok, why, z, _lam, cert = try_solve(name, rec)
            matrix[name][i] = "QUALIFIES" if ok else why
            if cert is not None:
                worst_width = max(worst_width, cert.primal_interval_width,
                                  cert.dual_interval_width)
                if cert.n_multipliers_clipped:                     # §2 — recorded, not laundered
                    clip_log.append({"instance": i, "solver": name,
                                     "n_clipped": cert.n_multipliers_clipped,
                                     "max_clip": cert.max_multiplier_clip,
                                     "clipped": [list(c) for c in cert.clipped[:12]]})
                if cert.certified_gap < 0.0:
                    # A gap a few ulps below zero is a submitted point that is feasible only to
                    # within rounding — NOT a broken certificate (that would violate the
                    # Lagrangian floor and raise). It still NONQUALIFIES, per the ruling. Record
                    # every one, with its derived floor and whether the NEGATIVE GAP WAS THE ONLY
                    # thing wrong with it, so the disposition is decided on evidence.
                    neg_log.append({"instance": i, "solver": name,
                                    "G": cert.certified_gap,
                                    "lagrangian_floor": cert.lagrangian_slack,
                                    "sole_failure_reason": (why == "certified_gap_negative")})
            if ok:
                zs[name][i] = z
                certs[name][i] = cert
            else:
                fails[name].add(i)
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{n_inst}", flush=True)

    print("\n--- per-solver nonqualifications (FULL canonical predicate) ---")
    for name in SOLVERS:
        print(f"  {name:18} {len(fails[name]):4} / {n_inst}")

    # ---- THE CASCADE ------------------------------------------------------------------
    unresolved = sorted(fails[PRIMARY] & fails[FALLBACK])
    primary_fail = sorted(fails[PRIMARY])
    print(f"\n=== PRODUCTION CASCADE  {PRIMARY} -> {FALLBACK} ===")
    print(f"  primary nonqualifications : {len(primary_fail)}  -> {primary_fail}")
    print(f"  UNRESOLVED                : {len(unresolved)}  -> {unresolved}")

    # ---- §10 fixture identity ---------------------------------------------------------
    fixtures = []
    for i in primary_fail:
        inst = CORPUS[i]
        fixtures.append({
            "label_index_only": i,
            "content_hash": fixture_hash(inst),
            "instance_hash": inst["hash"],
            "primary_outcome": matrix[PRIMARY][i],
            "fallback_outcome": matrix[FALLBACK][i],
            "certified_by": sorted(k for k in SOLVERS if i not in fails[k]),
        })
    print("\n--- §10 fixtures (identity = CONTENT HASH; index is a label only) ---")
    for f in fixtures:
        print(f"  [{f['label_index_only']:>4}] {f['content_hash'][:16]}…  "
              f"primary={f['primary_outcome'][:34]:<34} fallback={f['fallback_outcome']}")

    # ---- §15 same-image determinism ----------------------------------------------------
    det_ok = True
    for i in primary_fail:
        rec = tuple(CORPUS[i][k] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        a_ok, _, za, _, _ = try_solve(FALLBACK, rec)
        b_ok, _, zb, _, _ = try_solve(FALLBACK, rec)
        if not (a_ok and b_ok and np.array_equal(za, zb)):
            det_ok = False
    print(f"\n--- §15 same-image determinism on the fixtures: "
          f"{'PASS' if det_ok else 'FAIL'}")

    # ---- §10 shuffle invariance --------------------------------------------------------
    rng = np.random.default_rng(0)
    shuf_ok, worst_shuf = True, 0.0
    for i in primary_fail:
        inst = CORPUS[i]
        t, A_ub, b_ub, A_eq, b_eq, upper = (
            inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        ok0, _, z0, _, _ = try_solve(FALLBACK, (t, A_ub, b_ub, A_eq, b_eq, upper))
        p = rng.permutation(len(t))                       # variable shuffle
        r = rng.permutation(A_ub.shape[0])                # row shuffle
        ok1, _, z1, _, _ = try_solve(
            FALLBACK, (t[p], A_ub[np.ix_(r, p)], b_ub[r], A_eq[:, p], b_eq, upper[p]))
        if not (ok0 and ok1):
            shuf_ok = False
            continue
        d = float(np.max(np.abs(z0[p] - z1)))
        worst_shuf = max(worst_shuf, d)
        if d > 1e-8:
            shuf_ok = False
    print(f"--- §10 shuffle invariance: {'PASS' if shuf_ok else 'FAIL'} "
          f"(worst |Δallocation| = {worst_shuf:.3e})")

    # ---- §8 agreement, under the CERTIFIED radius (no KKT inflation term) ---------------
    agree_ok, obj_ok = True, True
    worst_ratio = worst_obj_ratio = worst_dz_abs = 0.0
    both = sorted(set(zs[PRIMARY]) & set(zs[FALLBACK]))
    viol, obj_viol = [], []
    for i in both:
        c1, c2 = certs[PRIMARY][i], certs[FALLBACK][i]
        ok_a, dz, bound = agreement(c1, c2, zs[PRIMARY][i], zs[FALLBACK][i])
        ok_o, df, obound = objective_agreement(c1, c2)
        worst_dz_abs = max(worst_dz_abs, dz)
        worst_ratio = max(worst_ratio, dz / bound if bound > 0 else 0.0)
        worst_obj_ratio = max(worst_obj_ratio, df / obound if obound > 0 else 0.0)
        if not ok_a:
            agree_ok = False
            viol.append({"i": i, "dz": dz, "bound": bound, "ratio": dz / bound,
                         "G_primary": c1.certified_gap, "G_fallback": c2.certified_gap,
                         "r_primary": c1.radius, "r_fallback": c2.radius})
        if not ok_o:
            obj_ok = False
            obj_viol.append({"i": i, "df": df, "bound": obound})
    viol.sort(key=lambda v: -v["ratio"])
    print(f"\n--- §8 certified-radius agreement over {len(both)} overlap instances: "
          f"{'PASS' if agree_ok else 'FAIL'}   worst dz/bound = {worst_ratio:.3e}")
    print(f"    violations: {len(viol)}   worst ABSOLUTE |z1-z2| = {worst_dz_abs:.3e}")
    for v in viol[:5]:
        print(f"      i={v['i']:>4}  dz={v['dz']:.3e}  bound={v['bound']:.3e}  "
              f"G=({v['G_primary']:.2e}, {v['G_fallback']:.2e})")
    print(f"--- §8 objective agreement: {'PASS' if obj_ok else 'FAIL'}   "
          f"worst |f1-f2|/bound = {worst_obj_ratio:.3e}   violations: {len(obj_viol)}")
    print(f"--- §7 worst interval width across every certificate: {worst_width:.3e} "
          f"(limit {MAX_INTERVAL_WIDTH:.0e})")
    print(f"--- §2 certificates needing a multiplier clip: {len(clip_log)}")

    sole = [r for r in neg_log if r["sole_failure_reason"]]
    worst_neg = min((r["G"] for r in neg_log), default=0.0)
    print(f"--- §7 NEGATIVE certified gaps: {len(neg_log)}  (worst {worst_neg:.3e})   "
          f"of which the negative gap was the SOLE failure: {len(sole)}")
    if sole:
        by_solver: dict[str, int] = {}
        for r in sole:
            by_solver[r["solver"]] = by_solver.get(r["solver"], 0) + 1
        print(f"    solvers disqualified ONLY by a negative gap: {by_solver}")
        print("    ⚠ these are points feasible only to within rounding, not broken certificates "
              "(every one clears its Lagrangian floor). Disposition is the owner's.")

    # ---- §9 module + wrapper hashes ----------------------------------------------------
    hashes = {
        "canonical_acceptance_module": _src_hash(jp._acceptance, canonical_qualify),
        "certificate_module": _src_hash(certify, bound_intervals, project_dual, agreement,
                                        objective_agreement, verify_canonical_hessian),
        "LIMITS_object": hashlib.sha256(
            json.dumps(LIMITS, sort_keys=True).encode()).hexdigest(),
        "quadprog_sqrt_wrapper_and_dual_mapping": _src_hash(_quadprog_variant),
        "piqp_wrapper_and_dual_mapping": _src_hash(_piqp_raw),
        "coverage_driver": _src_hash(main),
    }

    ok_gate = (len(unresolved) == 0) and det_ok and shuf_ok and agree_ok and obj_ok
    print("\n" + "=" * 74)
    print("  §13 COMPLEMENTARY-COVERAGE GATE: " + ("PASS" if ok_gate else "FAIL"))
    print("=" * 74)

    out = {
        "cascade": [PRIMARY, FALLBACK],
        "supersedes": {
            "artifact": "MR002_ComplementaryCoverage.json",
            "sha256": "790002c05c45e685a5126b6a2a5707689460486ad16800c7ea3be960f9c7a1c7",
            "disposition": ("CASCADE COVERAGE PASSED / AGREEMENT GATE FAILED / SIGNED-GAP "
                            "AGREEMENT SPECIFICATION INVALIDATED / NOT COUNTERSIGNED — retained "
                            "immutable"),
        },
        "canonical_predicate": {
            "LIMITS": LIMITS,
            "certified_gap_max": CERTIFIED_GAP_MAX,
            "max_interval_width": MAX_INTERVAL_WIDTH,
            "definition": ("G = upper(f(z)) - lower(d_cert), weak duality, folded C/b/lambda, "
                           "outward-rounded intervals at >= 100 decimal digits, exact "
                           "as_integer_ratio conversion. NO cushion, NO max(G,0), NO KKT term."),
        },
        "instances": n_inst,
        "corpus_hash": ch,
        "corpus_verified": True,
        "nonqualifications": {k: sorted(v) for k, v in fails.items()},
        "qualification_matrix": {k: {str(i): v for i, v in m.items()}
                                 for k, m in matrix.items()},
        "primary_nonqualifications": primary_fail,
        "cascade_unresolved": unresolved,
        "fixtures_by_content_hash": fixtures,
        "same_image_determinism": det_ok,
        "shuffle_invariance": {"pass": shuf_ok, "worst_delta": worst_shuf},
        "certified_radius_agreement": {"pass": agree_ok, "overlap_instances": len(both),
                                       "worst_ratio": worst_ratio,
                                       "violations": len(viol),
                                       "worst_absolute_dz": worst_dz_abs,
                                       "top_violations": viol[:20]},
        "objective_agreement": {"pass": obj_ok, "worst_ratio": worst_obj_ratio,
                                "violations": len(obj_viol), "top_violations": obj_viol[:20]},
        "interval_arithmetic": {"worst_width": worst_width, "limit": MAX_INTERVAL_WIDTH},
        "multiplier_clipping": {"certificates_with_clips": len(clip_log),
                                "records": clip_log[:200]},
        "negative_certified_gaps": {
            "count": len(neg_log),
            "worst": worst_neg,
            "sole_failure_reason_count": len(sole),
            "note": ("A gap a few ulps below zero is a submitted point that is feasible only to "
                     "within rounding, not a broken certificate: every one clears its derived "
                     "Lagrangian floor G >= lam'(C'z - b), which a sign/conversion defect could "
                     "not. Per the ruling G >= 0 is required to qualify, so they NONQUALIFY here. "
                     "Where that is the SOLE failure reason the disposition is the owner's."),
            "records": neg_log[:200],
        },
        "implementation_hashes": hashes,
        "correction_2765": (
            "WITHDRAWN: the prior statement that instance 2765 is certified only by HiGHS is "
            "FALSE. Both frozen PIQP profiles certify it under the canonical predicate. No "
            "captured instance uniquely requires HiGHS."
        ),
        "complementarity_is_empirical_not_structural": (
            "Zero unresolved is empirical complementary coverage on ONE ladder-conditioned "
            "corpus. Zero double failures among a small number of primary nonqualifications "
            "leaves a wide one-sided upper bound on the unknown overlap rate; any probability "
            "derived from unconditional failure rates assumes unproven independence and "
            "stationarity and is DIAGNOSTIC ONLY. The prospective preflight is a real gate."
        ),
        "no_performance_computed": True,
        "gate_pass": ok_gate,
    }
    # A NEW artifact. The prior one is immutable and keeps its failed-agreement disposition (§10).
    with open("/out/MR002_ComplementaryCoverage_Certified.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("wrote /out/MR002_ComplementaryCoverage_Certified.json")
    return 0 if ok_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
