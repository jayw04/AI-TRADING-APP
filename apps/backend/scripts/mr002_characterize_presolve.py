"""MR-002 v1.1 — EXACT CONSTRAINT-PRESOLVE CHARACTERIZATION.

Authorized 2026-07-12. OFFLINE CHARACTERIZATION ONLY. No performance is computed. The
preflight and development run remain stopped.

Row removal is permitted ONLY under a machine-verifiable certificate:

  A  EXACT_DUPLICATE          bitwise-identical coefficients, direction and RHS
  B  SAME_LHS_WEAKER_BOUND    bitwise-identical coefficients; keep the smaller RHS
  C  ZERO_ROW                 all variable coefficients exactly zero:
                                satisfied constant -> remove;  violated -> INFEASIBLE (stop)
  D  SECTOR_SIGN_DOMINANCE    symbolic, from the position-direction sets

PROOF of certificate D. In sector k, all weights are ABSOLUTE and NON-NEGATIVE and
G = sum of all weights >= 0. If EVERY exposure in sector k (fixed, tradable and new) has the
same direction d, then net_k = d * gross_k with gross_k >= 0, and the three rows

    (1)  gross_k - 0.20 G <= 0
    (2)   net_k  - 0.05 G <= 0
    (3)  -net_k  - 0.05 G <= 0

reduce as follows.
  d = +1:  (2) is gross_k - 0.05G <= 0, which IMPLIES (1) because 0.05G <= 0.20G for G >= 0.
           (3) is -gross_k - 0.05G <= 0, which is ALWAYS true (both terms non-negative).
           => KEEP (2); REMOVE (1) and (3).
  d = -1:  symmetric. KEEP (3); REMOVE (1) and (2).

ZERO-MULTIPLIER VALIDITY. Under dominance the removed rows are STRICTLY slack at any optimum
with G > 0 (e.g. gross_k - 0.20G = 0.05G - 0.20G = -0.15G < 0 when (2) is active), so a zero
multiplier is exactly correct. At G = 0 the slack is 0 and lambda = 0, so complementarity
(lambda * slack) is still exactly 0.

NO approximate matching, rank, QR, SVD, correlation or tolerance-based removal is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import warnings
from collections import Counter
from datetime import date

import pathlib

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.joint_portfolio import InvalidRun  # noqa: E402

FALSE_INCONSISTENCY = "constraints are inconsistent, no solution"
LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
AGREE = 1e-8

CORPUS: list[dict] = []
CAPTURE_PATH: Counter = Counter()
CTX: dict = {}
CURRENT: dict = {"config": None}

_real_build = jp._build


def build_spy(fixed, tradable, cands):
    """Record the SYMBOLIC context the certificates need -- sector membership and the
    position-direction sets. The matrices alone are insufficient for certificate D."""
    out = _real_build(fixed, tradable, cands)
    dirs: dict[str, set] = {}
    sup: dict[str, dict] = {}
    for p in fixed:                              # FIXED exposures count toward the support
        dirs.setdefault(p.sector, set()).add(int(p.d))
        sup.setdefault(p.sector, {"fixed": [], "vars": []})["fixed"].append(int(p.permaticker))
    for h in tradable:                           # existing y variables
        dirs.setdefault(h.sector, set()).add(int(h.d))
        sup.setdefault(h.sector, {"fixed": [], "vars": []})["vars"].append(int(h.permaticker))
    for c in cands:                              # new x variables
        dirs.setdefault(c.sector, set()).add(int(c.d))
        sup.setdefault(c.sector, {"fixed": [], "vars": []})["vars"].append(int(c.permaticker))
    CTX["sector_directions"] = {k: sorted(v) for k, v in dirs.items()}
    CTX["sector_support"] = sup
    CTX["variables"] = (
        [{"id": int(h.permaticker), "type": "existing_y", "sector": h.sector,
          "direction": int(h.d)} for h in tradable]
        + [{"id": int(c.permaticker), "type": "candidate_x", "sector": c.sector,
            "direction": int(c.d)} for c in cands])
    CTX["fixed"] = [{"id": int(p.permaticker), "type": "fixed_f", "sector": p.sector,
                     "direction": int(p.d), "reason": p.fixed_reason} for p in fixed]
    CTX["labels"] = out[5]
    return out


jp._build = build_spy


def _qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


# ======================================================================================
# EXACT CONSTRAINT PRESOLVE
# ======================================================================================
def presolve(A_ub, b_ub, labels, sector_directions, support=None):
    """Return (keep_mask, audit). Purely structural and deterministic.

    NOTE: build_joint appends TWO rows to A_ub after _build -- the lexicographic bands
    R >= R*-eps and Q >= Q*-eps -- which carry no label. They are padded here. They are
    never sector rows, so certificate D cannot touch them; but row_Q is an EXACT ZERO ROW
    whenever there are no new candidates (n_x == 0), and a constraint with a zero-norm
    normal vector is a classic Goldfarb-Idnani failure mode. Certificate C removes it.
    """
    m = A_ub.shape[0]
    labels = list(labels)
    while len(labels) < m:
        labels.append("lex_band_R" if len(labels) == m - 2 else "lex_band_Q")
    keep = np.ones(m, dtype=bool)
    audit: list[dict] = []

    def rec(i, cert, retained=None, evidence=""):
        audit.append({
            "original_row_id": int(i),
            "original_row_label": labels[i],
            "retained_row_id": None if retained is None else int(retained),
            "redundancy_certificate": cert,
            "symbolic_evidence": evidence,
            "original_coefficients_sha256": hashlib.sha256(
                np.ascontiguousarray(A_ub[i], dtype=np.float64).tobytes()).hexdigest(),
            "original_rhs_ieee754_hex": float(b_ub[i]).hex(),
        })

    # ---- D: sector-sign dominance (symbolic; the workhorse) ---------------------------
    by_label = {lab: i for i, lab in enumerate(labels)}
    for sec, ds in sector_directions.items():
        if len(ds) != 1:
            continue                                  # mixed directions -> no dominance
        d = ds[0]
        i_g = by_label.get(f"sector_gross[{sec}]")
        i_p = by_label.get(f"sector_net+[{sec}]")
        i_m = by_label.get(f"sector_net-[{sec}]")
        if i_g is None or i_p is None or i_m is None:
            continue
        sup = (support or {}).get(sec, {"fixed": [], "vars": []})
        dominating = i_p if d > 0 else i_m
        auto_sat = i_m if d > 0 else i_p
        for row, dom, why in (
            (i_g, dominating,
             f"all exposures in {sec} have direction {d:+d} -> sector_gross = |sector_net|; "
             f"the 5%-of-gross net row implies the 20%-of-gross gross row for G >= 0"),
            (auto_sat, None,
             f"all exposures in {sec} have direction {d:+d} -> the opposite-sign net row is "
             f"-gross_k - 0.05G <= 0, always true (both terms non-negative)"),
        ):
            keep[row] = False
            audit.append({
                "removed_row_id": int(row),
                "removed_row_label": labels[row],
                "dominating_row_id": None if dom is None else int(dom),
                "sector_id": sec,
                "common_direction": int(d),
                "fixed_support_ids": sup["fixed"],
                "variable_support_ids": sup["vars"],
                "symbolic_certificate": "SAME_DIRECTION_SECTOR_DOMINANCE",
                "redundancy_certificate": "SAME_DIRECTION_SECTOR_DOMINANCE",
                "symbolic_evidence": why,
                "original_coefficients_sha256": hashlib.sha256(
                    np.ascontiguousarray(A_ub[row], dtype=np.float64).tobytes()).hexdigest(),
                "original_rhs_ieee754_hex": float(b_ub[row]).hex(),
            })

    # ---- C: zero rows (exact) ----------------------------------------------------------
    for i in range(m):
        if not keep[i]:
            continue
        if np.all(A_ub[i] == 0.0):
            if b_ub[i] < 0.0:
                raise InvalidRun(
                    f"presolve: zero row {labels[i]} with rhs {b_ub[i]!r} < 0 proves "
                    "INFEASIBILITY -- must stop, never be silently discarded")
            keep[i] = False
            rec(i, "ZERO_ROW", None, "all variable coefficients exactly 0; constant satisfied")

    # ---- A / B: bitwise-identical coefficient vectors ----------------------------------
    seen: dict[bytes, int] = {}
    for i in range(m):
        if not keep[i]:
            continue
        key = np.ascontiguousarray(A_ub[i], dtype=np.float64).tobytes()
        j = seen.get(key)
        if j is None:
            seen[key] = i
            continue
        if b_ub[i] == b_ub[j]:
            keep[i] = False
            rec(i, "EXACT_DUPLICATE", j, "bitwise-identical coefficients and RHS")
        elif b_ub[i] > b_ub[j]:
            keep[i] = False
            rec(i, "SAME_LHS_WEAKER_BOUND", j, "bitwise-identical coefficients; larger RHS")
        else:
            keep[j] = False
            rec(j, "SAME_LHS_WEAKER_BOUND", i, "bitwise-identical coefficients; larger RHS")
            seen[key] = i

    return keep, audit


# ======================================================================================
# solvers
# ======================================================================================
def _accept_full(z, lam_red, keep, meq, t, A_ub, b_ub, A_eq, b_eq, upper):
    """Map back to the FULL original system: removed rows get ZERO multipliers, and EVERY
    original row -- including removed ones -- is re-evaluated directly."""
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C_full, b_full = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    m_full = A_ub.shape[0]

    lam_full = np.zeros(meq + m_full + 2 * n)
    lam_full[:meq] = lam_red[:meq]
    idx_keep = np.where(keep)[0]
    lam_full[meq + idx_keep] = lam_red[meq:meq + len(idx_keep)]      # retained rows
    lam_full[meq + m_full:] = lam_red[meq + len(idx_keep):]          # bound multipliers

    ck = jp._acceptance(z, lam_full, meq, H, a, C_full, b_full,
                        A_ub, b_ub, A_eq, b_eq, upper)
    # direct re-evaluation of EVERY original row, removed ones included
    ck["max_original_row_violation"] = float(np.max(A_ub @ z - b_ub)) if m_full else 0.0
    return ck


def _solve_presolved(t, A_ub, b_ub, A_eq, b_eq, upper, keep, sqrt_scaled: bool):
    n = len(t)
    Ar, br = A_ub[keep], b_ub[keep]
    meq = A_eq.shape[0]

    if sqrt_scaled:
        s = np.sqrt(t)
        if not (np.all(np.isfinite(s)) and np.all(s > 0)):
            raise InvalidRun("presolve+sqrt: non-finite or non-positive sqrt(t)")
        S = np.diag(s)
        H_v = 2.0 * np.eye(n)                    # EXACTLY 2I
        a_v = 2.0 * s
        C_v, b_v = jp._qp_matrices(Ar @ S, br, A_eq @ S, b_eq, s, n)
        out = _qp(H_v, a_v, C_v, b_v, meq)
        v = np.asarray(out[0], float)
        z = S @ v
        lam = np.asarray(out[4], float).copy()
        nr = meq + Ar.shape[0]
        lam[nr:nr + n] /= s                      # mu_z = mu_v / sqrt(t)
        lam[nr + n:] /= s
    else:
        H = np.diag(2.0 / t)
        a = 2.0 * np.ones(n)
        C_r, b_r = jp._qp_matrices(Ar, br, A_eq, b_eq, upper, n)
        out = _qp(H, a, C_r, b_r, meq)
        z = np.asarray(out[0], float)
        lam = np.asarray(out[4], float)

    return z, _accept_full(z, lam, keep, meq, t, A_ub, b_ub, A_eq, b_eq, upper)


def solve_raw(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    out = _qp(H, a, C, b, meq)
    z = np.asarray(out[0], float)
    return z, jp._acceptance(z, np.asarray(out[4], float), meq, H, a, C, b,
                             A_ub, b_ub, A_eq, b_eq, upper)


def solve_sqrt(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    s = np.sqrt(t)
    S = np.diag(s)
    C_v, b_v = jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)
    out = _qp(2.0 * np.eye(n), 2.0 * s, C_v, b_v, meq)
    v = np.asarray(out[0], float)
    z = S @ v
    lam = np.asarray(out[4], float).copy()
    nr = meq + A_ub.shape[0]
    lam[nr:nr + n] /= s
    lam[nr + n:] /= s
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_tscaled(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    T = np.diag(t)
    meq = A_eq.shape[0]
    C_s, b_s = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, upper / t, n)
    out = _qp(np.diag(2.0 * t), 2.0 * t, C_s, b_s, meq)
    u = np.asarray(out[0], float)
    z = T @ u
    lam = np.asarray(out[4], float).copy()
    nr = meq + A_ub.shape[0]
    lam[nr:nr + n] /= t
    lam[nr + n:] /= t
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def failures(ck) -> list[str]:
    return sorted(k for k, lim in LIMITS.items() if ck[k] > lim)


def objective(z, t) -> float:
    return float(np.sum((z - t) ** 2 / t))


# ======================================================================================
# PHASE 1 — capture (identical deterministic ladder; corpus hash must MATCH 1d231930…)
# ======================================================================================
def capture_solver(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    t = np.asarray(targets, float)
    CORPUS.append({
        "t": t.copy(), "A_ub": A_ub.copy(), "b_ub": b_ub.copy(),
        "A_eq": A_eq.copy(), "b_eq": b_eq.copy(), "upper": np.asarray(upper, float).copy(),
        "sector_directions": dict(CTX["sector_directions"]),
        "sector_support": dict(CTX["sector_support"]),
        "variables": list(CTX["variables"]),
        "fixed": list(CTX["fixed"]),
        "config": CURRENT["config"],
        "labels": list(CTX["labels"]),
        "hash": _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper),
    })
    for nm, fn in (("RAW", solve_raw), ("SQRT", solve_sqrt), ("TSCALED", solve_tscaled)):
        try:
            z, ck = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
            if not failures(ck):
                CAPTURE_PATH[nm] += 1
                return z, dict(ck, stage3_formulation=nm,
                               hessian_condition_number=1.0, qp_iterations=[0, 0])
        except ValueError:
            continue
    from scipy.optimize import linprog
    n = len(t)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                options=jp.LP_OPTIONS)
    CAPTURE_PATH["DIAGNOSTIC_FALLBACK"] += 1
    if not f.success:
        raise InvalidRun("capture: infeasible")
    z = np.asarray(f.x, float)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], H, a, C, b,
                        A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def main() -> int:
    jp._solve_qp = capture_solver
    from app.research.mr002.dataset import FrozenDataset  # noqa: E402
    from app.research.mr002.runner import CONFIGS  # noqa: E402
    from scripts.mr002_development_run import run_config  # noqa: E402

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    print("PHASE 1 — re-capture WITH symbolic metadata (certificate D needs it)")
    for name in ("A", "B", "C"):
        print(f"  {name} ...", flush=True)
        CURRENT["config"] = name
        run_config(days, CONFIGS[name])

    # ---- VERIFY against the PERSISTED immutable corpus. The original matrices-only npz
    # ---- is NEVER modified; the symbolic data goes to a separate hashed sidecar.
    corpus_hash = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    with open("/out/MR002_Stage3_Corpus_Hashes.json", encoding="utf-8") as fh:
        prior = json.load(fh)
    prior_hashes = prior["instance_hashes"]
    now_hashes = [i["hash"] for i in CORPUS]

    count_ok = len(now_hashes) == len(prior_hashes) == 3895
    global_ok = corpus_hash == prior["corpus_hash"]
    first_div = next((k for k, (a_, b_) in enumerate(zip(now_hashes, prior_hashes))
                      if a_ != b_), None)
    per_ok = first_div is None and count_ok
    print(f"  instances: {len(CORPUS)} (expected 3895: {count_ok})")
    print(f"  corpus hash : {corpus_hash[:16]}  | matches persisted: {global_ok}")
    print(f"  per-instance: all {len(now_hashes)} match: {per_ok}")

    if not (count_ok and global_ok and per_ok):
        d = {"verdict": "CORPUS_DIVERGENCE",
             "expected_instances": 3895, "got_instances": len(now_hashes),
             "expected_corpus_hash": prior["corpus_hash"], "got_corpus_hash": corpus_hash,
             "first_divergent_instance_index": first_div}
        if first_div is not None:
            inst = CORPUS[first_div]
            d["first_divergent_instance"] = {
                "config": inst["config"], "expected_hash": prior_hashes[first_div],
                "got_hash": inst["hash"], "n_vars": int(len(inst["t"])),
                "n_rows": int(inst["A_ub"].shape[0])}
        print(json.dumps(d, indent=2), file=sys.stderr)
        with open("/out/MR002_Corpus_Divergence.json", "w", encoding="utf-8",
                  newline="\n") as fh:
            json.dump(d, fh, indent=2)
        print("CORPUS DIVERGENCE — the recapture is NOT the same corpus. The presolve "
              "characterization is NOT authorized against it.", file=sys.stderr)
        return 1

    # ---- symbolic SIDECAR (separate artifact; the original corpus is untouched) --------
    with open("/out/MR002_Stage3_Corpus_Symbolic.jsonl", "w", encoding="utf-8",
              newline="\n") as fh:
        for k, inst in enumerate(CORPUS):
            fh.write(json.dumps({
                "instance_index": k,
                "instance_hash": inst["hash"],          # keyed by the IMMUTABLE matrix hash
                "config": inst["config"],
                "variables": inst["variables"],
                "fixed": inst["fixed"],
                "sector_directions": inst["sector_directions"],
                "sector_support": inst["sector_support"],
                "row_labels": inst["labels"],
                "n_rows_A_ub": int(inst["A_ub"].shape[0]),
            }, default=str) + "\n")
    side = hashlib.sha256(
        pathlib.Path("/out/MR002_Stage3_Corpus_Symbolic.jsonl").read_bytes()).hexdigest()
    with open("/out/MR002_Stage3_Corpus_EnrichmentManifest.json", "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump({
            "record_type": "MR002_STAGE3_CORPUS_ENRICHMENT_MANIFEST",
            "matrix_corpus_hash": prior["corpus_hash"],
            "matrix_corpus_unmodified": True,
            "symbolic_sidecar_sha256": side,
            "instances": len(CORPUS),
            "per_instance_matrix_hash_match": True,
            "linkage": "each symbolic record is keyed by the immutable matrix instance hash",
            "capture_image": os.environ.get("MR002_IMAGE_TAG", "mr002-research:v1.1f"),
            "verification_verdict": "IDENTICAL — the symbolic capture was observational "
                                    "only and did not alter the numerical path",
        }, fh, indent=2)
    print(f"  symbolic sidecar sha256: {side[:16]}  (matrix corpus UNMODIFIED)")

    # ---- PHASE 2: offline, immutable copies -------------------------------------------
    print("\nPHASE 2 — offline evaluation on immutable copies")
    R = {
        "instances": len(CORPUS), "corpus_hash": corpus_hash,
        "corpus_hash_matches_persisted": True,
        "per_instance_matrix_hash_match": True,
        "symbolic_sidecar_sha256": side,
        "matrix_corpus_unmodified": True,
        "rows_total": 0, "rows_removed": 0,
        "certificates": Counter(),
        "raw_presolve_failed": 0, "sqrt_presolve_failed": 0,
        "raw_presolve_failure_kinds": Counter(), "sqrt_presolve_failure_kinds": Counter(),
        "raw_failed": 0, "sqrt_failed": 0,
        "max_orig_row_violation": 0.0,
        "worst_sqrt_presolve_stationarity": 0.0,
        "max_z_disagreement_vs_raw_clean": 0.0,
        "max_obj_disagreement_vs_raw_clean": 0.0,
        "removed_by_numerical_threshold": 0,          # REQUIRED 0 -- none is possible
    }
    audit_sample: list = []

    for inst in CORPUS:
        t = inst["t"].copy()
        A_ub, b_ub = inst["A_ub"].copy(), inst["b_ub"].copy()
        A_eq, b_eq = inst["A_eq"].copy(), inst["b_eq"].copy()
        upper = inst["upper"].copy()

        keep, audit = presolve(A_ub, b_ub, inst["labels"], inst["sector_directions"],
                               inst["sector_support"])
        R["rows_total"] += A_ub.shape[0]
        R["rows_removed"] += int((~keep).sum())
        for a_ in audit:
            R["certificates"][a_["redundancy_certificate"]] += 1
        if audit and len(audit_sample) < 3:
            audit_sample.append(audit[:4])

        # baselines
        raw_clean, raw_z = False, None
        try:
            raw_z, ck = solve_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
            raw_clean = not failures(ck)
        except ValueError:
            pass
        if not raw_clean:
            R["raw_failed"] += 1
        try:
            _z, ck = solve_sqrt(t, A_ub, b_ub, A_eq, b_eq, upper)
            if failures(ck):
                R["sqrt_failed"] += 1
        except ValueError:
            R["sqrt_failed"] += 1

        # RAW + PRESOLVE
        try:
            _z, ck = _solve_presolved(t, A_ub, b_ub, A_eq, b_eq, upper, keep, False)
            bad = failures(ck)
            if bad:
                R["raw_presolve_failed"] += 1
                R["raw_presolve_failure_kinds"]["+".join(bad)] += 1
        except ValueError as e:
            R["raw_presolve_failed"] += 1
            R["raw_presolve_failure_kinds"][f"RAISED:{e}"] += 1

        # SQRT + PRESOLVE  <-- THE CANDIDATE
        try:
            z, ck = _solve_presolved(t, A_ub, b_ub, A_eq, b_eq, upper, keep, True)
            bad = failures(ck)
            R["worst_sqrt_presolve_stationarity"] = max(
                R["worst_sqrt_presolve_stationarity"], ck["stationarity_residual"])
            R["max_orig_row_violation"] = max(
                R["max_orig_row_violation"], ck["max_original_row_violation"])
            if bad:
                R["sqrt_presolve_failed"] += 1
                R["sqrt_presolve_failure_kinds"]["+".join(bad)] += 1
            elif raw_clean:
                R["max_z_disagreement_vs_raw_clean"] = max(
                    R["max_z_disagreement_vs_raw_clean"], float(np.max(np.abs(z - raw_z))))
                R["max_obj_disagreement_vs_raw_clean"] = max(
                    R["max_obj_disagreement_vs_raw_clean"],
                    abs(objective(z, t) - objective(raw_z, t)))
        except ValueError as e:
            R["sqrt_presolve_failed"] += 1
            R["sqrt_presolve_failure_kinds"][f"RAISED:{e}"] += 1

    gates = {
        "sqrt_presolve_solves_all_instances": R["sqrt_presolve_failed"] == 0,
        "every_original_row_passes_direct_reevaluation":
            R["max_orig_row_violation"] <= LIMITS["primal_residual"],
        "z_agreement_vs_raw_clean_within_1e-8":
            R["max_z_disagreement_vs_raw_clean"] <= AGREE,
        "objective_agreement_within_1e-8":
            R["max_obj_disagreement_vs_raw_clean"] <= AGREE,
        "zero_rows_removed_by_numerical_threshold":
            R["removed_by_numerical_threshold"] == 0,
    }
    R["certificates"] = dict(R["certificates"])
    R["raw_presolve_failure_kinds"] = dict(R["raw_presolve_failure_kinds"])
    R["sqrt_presolve_failure_kinds"] = dict(R["sqrt_presolve_failure_kinds"])
    R["audit_sample"] = audit_sample
    R["gates"] = gates
    R["VERDICT"] = "PASS" if all(gates.values()) else "FAIL"

    dst = "/out/MR002_ConstraintPresolve_Characterization.json"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(R, fh, indent=2, default=str)
        fh.write("\n")

    print(json.dumps({k: R[k] for k in (
        "instances", "corpus_hash_matches_persisted", "rows_total", "rows_removed",
        "certificates", "raw_failed", "sqrt_failed",
        "raw_presolve_failed", "sqrt_presolve_failed",
        "sqrt_presolve_failure_kinds", "max_orig_row_violation",
        "worst_sqrt_presolve_stationarity", "max_z_disagreement_vs_raw_clean",
        "max_obj_disagreement_vs_raw_clean", "gates", "VERDICT")}, indent=2, default=str))
    print(f"\nreport: {dst}")
    return 0 if R["VERDICT"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
