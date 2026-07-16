"""MR-002 v1.1 — COMPLEMENTARY COVERAGE under the TWO-SIDED SIGNED LAGRANGIAN GAP (ruling §17).

Cascade under adjudication:  QUADPROG_SQRT -> PIQP_P2   (no third attempt)
Offline verifiers only:      Clarabel, HiGHS

Supersedes `MR002_ComplementaryCoverage_Certified.json` (sha256 47215cd2...), which is IMMUTABLE
and keeps its disposition: NONNEGATIVE SIGNED-GAP RULE INVALIDATED / CASCADE UNRESOLVED = 35 UNDER
SUPERSEDED GATE / DETERMINISM+SHUFFLE FIELDS DEFECTIVE / NOT COUNTERSIGNED.

THE PREDICATE (one implementation, imported — `app.research.mr002.certificate`):

    primal / dual-sign / stationarity / complementarity / aggregate-KKT  <= registered LIMITS
    signed Lagrangian gap interval  [Gamma_L, Gamma_U]  ENTIRELY within +/- 1e-10
    interval widths of f and d                                          <= 1e-30
    exact identity  Gamma == S_lag + 1/2 e'H^-1 e                        (violation => INVALID_RUN)

THE AGREEMENT GATES (imported — `app.research.mr002.repair`) are built on an EXACTLY FEASIBLE
rational repair, never on max(Gamma, 0) and never on a KKT-to-objective conversion:

    ||z1 - z2||  <= R1 + R2 + 1e-10          R_s = delta_s + sqrt(2*Ghat_s/m)
    |f(z1)-f(z2)| <= U1 + U2 + 1e-12         U_s = |f(z_s) - f(zhat_s)| + Ghat_s

⚠ THE DETERMINISM AND SHUFFLE LOOPS ARE CORRECTED AT SOURCE. The superseded script conflated "the
fallback NONQUALIFIES here" with "the fallback is not repeatable", which guaranteed a false FAIL
once the primary had 2,054 nonqualifications instead of 5. Qualification and repeatability are now
separate predicates, and the SKIPPED count is reported alongside the checked population so a
vacuously-empty check cannot pass by default.

DIAGNOSTIC ONLY. No performance computed, printed or persisted. Preflight and the development run
remain STOPPED. Validation and sealed OOS remain sealed and unread.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import time
import warnings
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

# ---- IMPORTED, never re-derived. A hand-rolled Clarabel dual mapping produced a false
# ---- "structural, close v1.1" verdict earlier in this program.
from app.research.mr002.certificate import (  # noqa: E402
    MAX_INTERVAL_WIDTH,
    SIGNED_GAP_MAX,
    CertificateDefect,
    certify,
    classify,
    gap_intervals,
    project_dual,
    verify_canonical_hessian,
)
from app.research.mr002.repair import (  # noqa: E402
    PROPOSAL_PROFILE,
    RepairUnavailable,
    agreement,
    certify_repair,
    exact_repair_from_proposal,
    objective_agreement,
)
from app.research.mr002.repair import manifest as repair_manifest  # noqa: E402
from scripts.mr002_characterize_native_qp import solve_clarabel as _clarabel_raw  # noqa: E402
from scripts.mr002_characterize_native_qp import solve_highs as _highs_raw
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

# §13 — the ANTI-OVERFITTING characterization sequence. R2 was designed AFTER observing the
# 50-overlap failure sample, so a pass on that same sample proves only that the diagnosed mechanism
# is corrected — not that R2 generalizes. Two distinct samples run before the full pass, both with
# selection rules frozen here, which no result may influence:
#
#   A  REGRESSION   the first 50 qualifying overlaps in canonical corpus order — the SAME overlaps
#                   that failed under R1, kept for direct comparability with the stopped report.
#
#   B  PROSPECTIVE  100 qualifying overlaps NOT in A, ordered by CONTENT HASH ascending. That order
#                   is independent of every result, of corpus position, and of R1's failures, so
#                   membership cannot be contaminated by what was learned from A.
#
# A mathematical failure in either sample is SUBSTANTIVE and stops the run. It is not excusable as
# "only a sample".
SAMPLE = os.environ.get("MR002_SAMPLE", "").upper()          # "A" | "B" | "" (full)
REGRESSION_N = 50
PROSPECTIVE_N = 100


def canonical_qualify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper):
    """THE canonical predicate. KKT gates and the signed-gap gate are SEPARATE hard conditions:
    the gap does not replace KKT verification, and the KKT tolerance does not inflate the gap."""
    n = len(t)
    H = np.diag(2.0 / t)
    verify_canonical_hessian(H, t)                    # the registered 2/t objective, not a scaled one
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    ck = jp._acceptance(z, lam, meq, H, 2.0 * np.ones(n), C, b, A_ub, b_ub, A_eq, b_eq, upper)
    bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)

    cert = certify(z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)   # raises on an identity violation
    if not cert.qualifies:
        bad.append(classify(cert))
    return (not bad), bad, cert


def _lam_of(fn_raw):
    def run(t, A_ub, b_ub, A_eq, b_eq, upper):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            z, lam = fn_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
        if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
            raise RuntimeError("non-finite primal or dual")
        return z, lam
    return run


def _quadprog_variant(fn_checks):
    """The quadprog wrappers return (z, checks); recover lam via the same registered construction."""
    def run(t, A_ub, b_ub, A_eq, b_eq, upper):
        import quadprog
        n = len(t)
        C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
        meq = A_eq.shape[0]
        nr = meq + A_ub.shape[0]
        if fn_checks is solve_sqrt:
            s = np.sqrt(t)
            S = np.diag(s)
            C_v, b_v = jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out = quadprog.solve_qp(2.0 * np.eye(n), 2.0 * s, C_v, b_v, meq)
            lam = np.asarray(out[4], float).copy()
            lam[nr:nr + n] /= s
            lam[nr + n:] /= s
            return S @ np.asarray(out[0], float), lam
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
        lam = np.asarray(out[4], float).copy()
        lam[nr:nr + n] /= t
        lam[nr + n:] /= t
        return T @ np.asarray(out[0], float), lam
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


def fixture_hash(inst: dict) -> str:
    """Fixture identity is the CONTENT HASH of the canonical problem, never the corpus index — the
    production corpus will differ, and index 2765 in a new corpus is a different problem."""
    h = hashlib.sha256()
    h.update(b"MR002|stage3|canonical-original-problem|v1")
    for key in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"):
        a = np.ascontiguousarray(np.asarray(inst[key], dtype=np.float64))
        h.update(key.encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    h.update(b"|acceptance-policy|")
    h.update(json.dumps(LIMITS, sort_keys=True).encode())
    h.update(f"|signed_gap<=+/-{SIGNED_GAP_MAX}|width<={MAX_INTERVAL_WIDTH}".encode())
    return h.hexdigest()


def _src_hash(*objs) -> str:
    h = hashlib.sha256()
    for o in objs:
        h.update(inspect.getsource(o).encode())
    return h.hexdigest()


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
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], np.diag(2.0 / t),
                        2.0 * np.ones(n), C, b, A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def try_solve(name, rec):
    try:
        z, lam = SOLVERS[name](*(x.copy() for x in rec))
        ok, bad, cert = canonical_qualify(z, lam, *rec)
        return ok, ("+".join(bad) if bad else ""), z, lam, cert
    except CertificateDefect:
        raise                          # a broken CERTIFICATE is not a solver failure — STOP
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
    print("PREDICATE = registered LIMITS + TWO-SIDED signed Lagrangian gap interval in "
          "[-1e-10, +1e-10]\n")

    matrix: dict[str, dict[int, str]] = {k: {} for k in SOLVERS}
    fails: dict[str, set[int]] = {k: set() for k in SOLVERS}
    zs: dict[str, dict[int, np.ndarray]] = {k: {} for k in SOLVERS}
    certs: dict[str, dict[int, object]] = {k: {} for k in SOLVERS}
    clip_log: list[dict] = []
    neg_gap = {k: 0 for k in SOLVERS}
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
                if cert.gamma_upper < 0.0:
                    neg_gap[name] += 1
                if cert.n_multipliers_clipped:
                    clip_log.append({"instance": i, "solver": name,
                                     "n_clipped": cert.n_multipliers_clipped,
                                     "max_clip": cert.max_multiplier_clip,
                                     "clipped": [list(c) for c in cert.clipped[:12]]})
            if ok:
                zs[name][i] = z
                certs[name][i] = cert
            else:
                fails[name].add(i)
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{n_inst}", flush=True)

    print("\n--- per-solver nonqualifications (two-sided signed-gap predicate) ---")
    for name in SOLVERS:
        print(f"  {name:18} {len(fails[name]):5} / {n_inst}   "
              f"(negative-gap certificates: {neg_gap[name]})")

    unresolved = sorted(fails[PRIMARY] & fails[FALLBACK])
    primary_fail = sorted(fails[PRIMARY])
    print(f"\n=== PRODUCTION CASCADE  {PRIMARY} -> {FALLBACK} ===")
    print(f"  primary nonqualifications : {len(primary_fail)}  -> {primary_fail}")
    print(f"  UNRESOLVED                : {len(unresolved)}  -> {unresolved}")

    fixtures = [{
        "label_index_only": i,
        "content_hash": fixture_hash(CORPUS[i]),
        "instance_hash": CORPUS[i]["hash"],
        "primary_outcome": matrix[PRIMARY][i],
        "fallback_outcome": matrix[FALLBACK][i],
        "certified_by": sorted(k for k in SOLVERS if i not in fails[k]),
    } for i in primary_fail]
    print("\n--- fixtures (identity = CONTENT HASH; the index is a label only) ---")
    for f in fixtures:
        print(f"  [{f['label_index_only']:>4}] {f['content_hash'][:16]}…  "
              f"primary={f['primary_outcome'][:36]:<36} fallback={f['fallback_outcome'][:24]}")

    # ---- determinism / shuffle: qualification and repeatability are SEPARATE predicates --------
    rng = np.random.default_rng(0)
    det_checked = det_diff = det_skipped = 0
    shuf_checked = shuf_bad = shuf_skipped = 0
    worst_shuf = 0.0
    for i in primary_fail:
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        a_ok, _, za, _, _ = try_solve(FALLBACK, rec)
        b_ok, _, zb, _, _ = try_solve(FALLBACK, rec)
        if not (a_ok and b_ok):
            det_skipped += 1          # NONQUALIFIES — says nothing about repeatability
            shuf_skipped += 1
            continue
        det_checked += 1
        if not np.array_equal(za, zb):
            det_diff += 1
        t, A_ub, b_ub, A_eq, b_eq, upper = rec
        p = rng.permutation(len(t))
        r = rng.permutation(A_ub.shape[0])
        ok1, _, z1, _, _ = try_solve(
            FALLBACK, (t[p], A_ub[np.ix_(r, p)], b_ub[r], A_eq[:, p], b_eq, upper[p]))
        if not ok1:
            shuf_skipped += 1
            continue
        shuf_checked += 1
        d = float(np.max(np.abs(za[p] - z1)))
        worst_shuf = max(worst_shuf, d)
        if d > 1e-8:
            shuf_bad += 1
    det_ok = (det_diff == 0) and det_checked > 0
    shuf_ok = (shuf_bad == 0) and shuf_checked > 0
    print(f"\n--- determinism : {'PASS' if det_ok else 'FAIL'}  "
          f"{det_checked} checked, {det_diff} differed, {det_skipped} skipped (nonqualifying)")
    print(f"--- shuffle     : {'PASS' if shuf_ok else 'FAIL'}  "
          f"{shuf_checked} checked, {shuf_bad} violations, {shuf_skipped} skipped  "
          f"(worst |Δ| = {worst_shuf:.3e})")

    # ---- EXACT-RATIONAL REPAIR + agreement on every qualifying overlap ------------------------
    qualifying = sorted(set(zs[PRIMARY]) & set(zs[FALLBACK]))
    regression = qualifying[:REGRESSION_N]
    rest = [i for i in qualifying if i not in set(regression)]
    prospective = sorted(rest, key=lambda i: fixture_hash(CORPUS[i]))[:PROSPECTIVE_N]
    if set(prospective) & set(regression):
        print("ABORT: sample B is not disjoint from sample A", file=sys.stderr)
        return 1

    if SAMPLE == "A":
        both, label = regression, f"REGRESSION sample A ({len(regression)} overlaps)"
    elif SAMPLE == "B":
        both, label = prospective, f"DISJOINT PROSPECTIVE sample B ({len(prospective)} overlaps)"
    else:
        both, label = qualifying, f"FULL overlap run ({len(qualifying)} overlaps)"

    rm = repair_manifest()
    print(f"\n--- R2 exact-rational feasible repair: {label} ---")
    print(f"    proposal profile (frozen) : {PROPOSAL_PROFILE}")
    print(f"    eta                       : {rm['eta_exact_rational']} = {rm['eta_ieee754_hex']}")
    print(f"    untightened fallback      : {rm['untightened_fallback_reachable']}")
    if SAMPLE:
        print("    selection rule frozen before execution; no result influences membership.")

    agree_ok = obj_ok = True
    worst_ratio = worst_obj_ratio = worst_dz = 0.0
    worst_delta = worst_ghat = 0.0
    viol, obj_viol, unavailable = [], [], []
    n_feas_hist: dict[int, int] = {}
    n_empty_rows = 0
    t0 = time.perf_counter()
    for idx, i in enumerate(both):
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        try:
            r1 = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
            r2 = certify_repair(zs[FALLBACK][i], certs[FALLBACK][i], *rec)
        except RepairUnavailable as e:
            # NOT a solver invalidation. The registered one-coordinate constructor produced no
            # certificate; that is a statement about the constructor. Stop for adjudication.
            unavailable.append({"instance": i, "reason": str(e)[:120]})
            continue
        for r in (r1, r2):
            n_feas_hist[r.n_feasible_candidates] = n_feas_hist.get(r.n_feasible_candidates, 0) + 1
            n_empty_rows += len(r.empty_rows)
            worst_delta = max(worst_delta, r.delta_upper)
            worst_ghat = max(worst_ghat, r.ghat_upper)

        ok_a, dz, bound = agreement(r1, r2, zs[PRIMARY][i], zs[FALLBACK][i])
        ok_o, df, obound = objective_agreement(r1, r2, certs[PRIMARY][i], certs[FALLBACK][i])
        worst_dz = max(worst_dz, dz)
        worst_ratio = max(worst_ratio, dz / bound if bound > 0 else 0.0)
        worst_obj_ratio = max(worst_obj_ratio, df / obound if obound > 0 else 0.0)
        if not ok_a:
            agree_ok = False
            viol.append({"i": i, "dz": dz, "bound": bound,
                         "R_primary": r1.radius_upper, "R_fallback": r2.radius_upper,
                         "delta_primary": r1.delta_upper, "ghat_primary": r1.ghat_upper})
        if not ok_o:
            obj_ok = False
            obj_viol.append({"i": i, "df": df, "bound": obound})
        if (idx + 1) % 250 == 0:
            print(f"    {idx+1}/{len(both)}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    repair_secs = time.perf_counter() - t0

    repair_ok = not unavailable
    print(f"\n--- repair certificates : {'PASS' if repair_ok else 'STOP'}   "
          f"{len(both)-len(unavailable)}/{len(both)} obtained, "
          f"{len(unavailable)} REPAIR_CERTIFICATE_UNAVAILABLE")
    print(f"    feasible absorbers/pt  : {dict(sorted(n_feas_hist.items()))}")
    print(f"    worst repair distance  : {worst_delta:.3e}    worst repaired gap: {worst_ghat:.3e}")
    print(f"    structurally empty rows encountered: {n_empty_rows}")
    for u in unavailable[:5]:
        print(f"      UNAVAILABLE i={u['instance']}: {u['reason'][:90]}")
    print(f"    wall-clock             : {repair_secs:.1f}s "
          f"({repair_secs/max(len(both),1)*1000:.0f} ms per overlap, 2 repairs each)")
    print(f"--- radius agreement    : {'PASS' if agree_ok else 'FAIL'}   "
          f"{len(viol)} violations, worst dz/bound = {worst_ratio:.3e}, worst |z1-z2| = "
          f"{worst_dz:.3e}")
    print(f"--- objective agreement : {'PASS' if obj_ok else 'FAIL'}   "
          f"{len(obj_viol)} violations, worst ratio = {worst_obj_ratio:.3e}")
    for v in viol[:5]:
        print(f"      i={v['i']:>4} dz={v['dz']:.3e} bound={v['bound']:.3e} "
              f"R=({v['R_primary']:.2e}, {v['R_fallback']:.2e})")
    print(f"--- worst interval width across every certificate: {worst_width:.3e} "
          f"(limit {MAX_INTERVAL_WIDTH:.0e})")
    print(f"--- certificates needing a multiplier clip: {len(clip_log)}")

    ok_gate = (len(unresolved) == 0 and det_ok and shuf_ok
               and repair_ok and agree_ok and obj_ok)
    print("\n" + "=" * 74)
    print("  COMPLEMENTARY-COVERAGE GATE: " + ("PASS" if ok_gate else "FAIL / INCOMPLETE"))
    print("=" * 74)

    out = {
        "cascade": [PRIMARY, FALLBACK],
        "supersedes": {
            "artifact": "MR002_ComplementaryCoverage_Certified.json",
            "sha256": "47215cd2aa65124ba0ffe4d2e41ae2539030a449fddd614b28e7f2078d00fda6",
            "disposition": ("CERTIFICATE MODULE INTEGRITY PASSED / NONNEGATIVE SIGNED-GAP RULE "
                            "INVALIDATED / CASCADE UNRESOLVED = 35 UNDER SUPERSEDED GATE / "
                            "DETERMINISM+SHUFFLE FIELDS DEFECTIVE / NOT COUNTERSIGNED — "
                            "retained immutable"),
        },
        "sample_only": bool(SAMPLE),
        "predicate": {
            "LIMITS": LIMITS,
            "signed_gap_band": [-SIGNED_GAP_MAX, SIGNED_GAP_MAX],
            "max_interval_width": MAX_INTERVAL_WIDTH,
            "definition": ("Gamma_int = [f_L - d_U, f_U - d_L] must lie ENTIRELY within the band. "
                           "Exact as_integer_ratio inputs, outward-rounded intervals at >= 100 "
                           "decimal digits. Integrity: Gamma == S_lag + 1/2 e'H^-1 e. "
                           "NO max(Gamma,0), NO cushion, NO KKT-to-objective conversion."),
        },
        "agreement": {
            "definition": ("Radius from an EXACTLY FEASIBLE rational repair: "
                           "R_s = delta_s + sqrt(2*Ghat_s/m), Ghat_s = f(zhat_s) - d_s >= 0. "
                           "The tightened proposal is NON-EVIDENTIARY: exact verification against "
                           "the ORIGINAL untightened constraints is the sole feasibility "
                           "authority, and nothing passes 'by construction'."),
            "repair_manifest": repair_manifest(),
        },
        "sample": {
            "which": SAMPLE or "FULL",
            "selection_rule": ("A = the first 50 qualifying overlaps in canonical corpus order. "
                               "B = 100 qualifying overlaps NOT in A, ordered by CONTENT HASH "
                               "ascending — independent of every result and of R1's failures."),
            "regression_A": regression,
            "prospective_B": prospective,
            "prospective_B_content_hashes": [fixture_hash(CORPUS[i]) for i in prospective],
            "samples_disjoint": True,
        },
        "instances": n_inst,
        "corpus_hash": ch,
        "corpus_verified": True,
        "nonqualifications": {k: sorted(v) for k, v in fails.items()},
        "negative_gap_certificates": neg_gap,
        "qualification_matrix": {k: {str(i): v for i, v in m.items()} for k, m in matrix.items()},
        "primary_nonqualifications": primary_fail,
        "cascade_unresolved": unresolved,
        "fixtures_by_content_hash": fixtures,
        "determinism": {"pass": det_ok, "checked": det_checked, "differed": det_diff,
                        "skipped_nonqualifying": det_skipped},
        "shuffle_invariance": {"pass": shuf_ok, "checked": shuf_checked, "violations": shuf_bad,
                               "skipped_nonqualifying": shuf_skipped, "worst_delta": worst_shuf},
        "repair_certificates": {"pass": repair_ok, "overlaps": len(both),
                                "unavailable": unavailable,
                                "feasible_absorbers_histogram": {str(k): v for k, v
                                                                 in sorted(n_feas_hist.items())},
                                "worst_repair_distance": worst_delta,
                                "worst_repaired_gap": worst_ghat,
                                "structurally_empty_rows_seen": n_empty_rows,
                                "wall_clock_seconds": repair_secs},
        "radius_agreement": {"pass": agree_ok, "overlaps": len(both), "violations": len(viol),
                             "worst_ratio": worst_ratio, "worst_absolute_dz": worst_dz,
                             "top_violations": viol[:20]},
        "objective_agreement": {"pass": obj_ok, "violations": len(obj_viol),
                                "worst_ratio": worst_obj_ratio, "top_violations": obj_viol[:20]},
        "interval_arithmetic": {"worst_width": worst_width, "limit": MAX_INTERVAL_WIDTH},
        "multiplier_clipping": {"certificates_with_clips": len(clip_log),
                                "records": clip_log[:200]},
        "implementation_hashes": {
            "canonical_acceptance": _src_hash(jp._acceptance, canonical_qualify),
            "signed_gap_module": _src_hash(certify, gap_intervals, project_dual, classify,
                                           verify_canonical_hessian),
            "repair_module": _src_hash(certify_repair, exact_repair_from_proposal,
                                       agreement, objective_agreement),
            "LIMITS_object": hashlib.sha256(
                json.dumps(LIMITS, sort_keys=True).encode()).hexdigest(),
            "quadprog_sqrt_wrapper": _src_hash(_quadprog_variant),
            "piqp_wrapper": _src_hash(_piqp_raw),
            "coverage_driver": _src_hash(main),
        },
        "no_performance_computed": True,
        "gate_pass": ok_gate,
    }
    name = {"A": "MR002_R2_RegressionSampleA.json",
            "B": "MR002_R2_ProspectiveSampleB.json"}.get(
        SAMPLE, "MR002_ComplementaryCoverage_SignedGap_R2.json")
    with open(f"/out/{name}", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote /out/{name}")
    return 0 if ok_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
