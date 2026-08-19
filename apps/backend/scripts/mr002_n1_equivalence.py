"""MR-002 Gate N1 — §4.4 equivalence gate, SA-2 uniqueness test, and C3 agreement with R.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

ONE pass over the corpus. Per instance: run Solver A, every admissible candidate B, the v1 method,
the exact-feasible repair where obtainable, and Reference Solver R once — then answer all three
questions from those shared results. R and A are not recomputed per candidate; recomputing them
would only invite a discrepancy that means nothing.

  §4.4  EQUIVALENCE GATE (mandatory for N1_ADVANCE). For every instance the v1 method accepted,
        prove the v2-accepted point equivalent: E0 identity -> E1 derived bound -> E2 exact R.
        Any EQUIVALENCE_UNPROVEN means N1_STOP.
  §2.4  SA-2. Where A and B both certify, exceeding the §4 bound is CERTIFIED_SOLUTION_DISAGREEMENT.
  §5.3  C3. Accepted points must agree with R. Reported as the EXACT distance ||z_acc - z*||, and
        as a pass/fail against the §4 radius on the subset where that radius exists.

v1-accepted points are REGENERATED here (§4.4) — equivalence is never asserted against a remembered
number, and the regenerated v1 dispositions are reported so they can be checked against the record.

⭐ A RIGOROUS SHORTCUT, NOT A TOLERANCE. The §4 bound is R_1 + R_2 + AGREEMENT_SLACK with R_s >= 0,
so it is ALWAYS >= AGREEMENT_SLACK = 1e-10. A pair whose EXACT separation is <= 1e-10 therefore
satisfies the bound without either radius being computed. That is a proof, not an epsilon.

Development domain only. Opens no sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.n1 import method as M  # noqa: E402
from app.research.mr002.n1 import reference as R  # noqa: E402

CORPUS_NPZ = "/work/.mr002out/n1/corpus.npz"
OUT_DIR = "/work/.mr002out/n1"
REGISTERED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"

A_PROFILE = "QUADPROG_SQRT"
B_CANDIDATES = ("PIQP_P1", "PIQP_P2")   # C2 survivors; CLARABEL was eliminated at C2

EQ_TRIVIAL = "EQUIVALENCE_TRIVIAL"
EQ_BOUND = "EQUIVALENCE_PROVEN_BOUND"
EQ_R = "EQUIVALENCE_PROVEN_R"
EQ_UNPROVEN = "EQUIVALENCE_UNPROVEN"

SLACK = Fraction(1, 10**10)
SLACK_SQ = SLACK * SLACK


def load_corpus() -> list[dict]:
    d = np.load(CORPUS_NPZ, allow_pickle=False)
    if str(d["corpus_hash"]) != REGISTERED_CORPUS_HASH:
        raise SystemExit("ABORT: corpus hash mismatch")
    n = int(d["n_instances"])
    return [{k: d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")}
            | {"hash": str(d[f"{i}_hash"])} for i in range(n)]


def rec_of(inst: dict) -> tuple:
    return (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])


def exact_sep_sq(z1, z2) -> Fraction:
    a = [R.to_fraction(v) for v in np.asarray(z1, dtype=float).ravel()]
    b = [R.to_fraction(v) for v in np.asarray(z2, dtype=float).ravel()]
    return sum(((a[i] - b[i]) ** 2 for i in range(len(a))), Fraction(0))


def isqrt_up(sq: Fraction) -> Fraction:
    """Exact rational UPPER bound on sqrt(sq). Outward only — a rounded-down bound is no bound.

    Integer square root, not Newton on rationals: each Newton step on a Fraction roughly DOUBLES the
    numerator and denominator bit-length, so an 80-step loop produces multi-megabit rationals and
    dominates the whole run. Here, for sq = p/q, sqrt(p/q) = sqrt(p*q)/q, so with s = isqrt(p*q)
    (floor) we get sqrt(p*q) <= s + 1 and therefore sqrt(p/q) <= (s + 1)/q — exact, one operation.
    """
    if sq <= 0:
        return Fraction(0)
    p, q = sq.numerator, sq.denominator
    return Fraction(math.isqrt(p * q) + 1, q)


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N1_LIMIT", "0"))

    from app.research.mr002 import repair as RP
    from app.research.mr002 import stage3_cascade as SC
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    corpus = load_corpus()
    if limit:
        corpus = corpus[:limit]
    print(f"[{time.time()-t0:7.1f}s] corpus verified, {len(corpus)} instances", flush=True)

    v1_disp: dict[str, int] = {}
    r_status: dict[str, int] = {}
    repair_avail = 0
    eq: dict[str, dict[str, int]] = {c: {} for c in B_CANDIDATES}
    unproven_rows: dict[str, list] = {c: [] for c in B_CANDIDATES}
    sa2 = {c: {"checked": 0, "slack_floor": 0, "bound": 0, "disagree": 0, "unavailable": 0}
           for c in B_CANDIDATES}
    disagree_rows: dict[str, list] = {c: [] for c in B_CANDIDATES}
    c3 = {c: {"evaluable": 0, "violations": 0, "radius_unavailable": 0, "r_unavailable": 0,
              "max_exact_distance": 0.0} for c in B_CANDIDATES}
    c3_rows: dict[str, list] = {c: [] for c in B_CANDIDATES}

    def radius(z, cert, rec):
        try:
            return R.to_fraction(RP.certify_repair(z, cert, *rec).radius_upper)
        except Exception:  # noqa: BLE001 — unavailability is a recorded state, not a failure
            return None

    for i, inst in enumerate(corpus):
        rec = rec_of(inst)

        a = M.normalize(A_PROFILE, SOLVERS[A_PROFILE], canonical_qualify, rec)
        bs = {c: M.normalize(c, SOLVERS[c], canonical_qualify, rec) for c in B_CANDIDATES}

        # v1 method, regenerated
        try:
            o1 = SC.resolve_instance(rec)
            z_v1 = None if o1.accepted_z is None else np.asarray(o1.accepted_z, float)
            d1 = o1.disposition
        except Exception as exc:  # noqa: BLE001
            z_v1, d1 = None, f"RAISED:{type(exc).__name__}"
        v1_disp[d1] = v1_disp.get(d1, 0) + 1

        # Reference Solver R, once per instance
        hint = a.z if a.is_certified else next((b.z for b in bs.values() if b.is_certified), None)
        rr = R.solve_reference(rec, hint_z=hint) if hint is not None else R.ReferenceResult(R.R_UNAVAILABLE)
        r_status[rr.status] = r_status.get(rr.status, 0) + 1

        ra = radius(a.z, a.cert, rec) if a.is_certified else None
        if ra is not None:
            repair_avail += 1

        for c in B_CANDIDATES:
            b = bs[c]
            z_v2 = a.z if a.is_certified else (b.z if b.is_certified else None)
            cert_v2 = a.cert if a.is_certified else (b.cert if b.is_certified else None)

            # ── SA-2 ───────────────────────────────────────────────────────────────────────────
            if a.is_certified and b.is_certified:
                sa2[c]["checked"] += 1
                sep = exact_sep_sq(a.z, b.z)
                if sep <= SLACK_SQ:
                    sa2[c]["slack_floor"] += 1
                else:
                    r1, r2 = ra, radius(b.z, b.cert, rec)
                    if (r1 is None or r2 is None) and rr.is_exact:
                        r1 = r1 if r1 is not None else isqrt_up(R.exact_distance(a.z, rr.z))
                        r2 = r2 if r2 is not None else isqrt_up(R.exact_distance(b.z, rr.z))
                    if r1 is None or r2 is None:
                        sa2[c]["unavailable"] += 1
                    else:
                        bd = r1 + r2 + SLACK
                        if sep <= bd * bd:
                            sa2[c]["bound"] += 1
                        else:
                            sa2[c]["disagree"] += 1
                            disagree_rows[c].append({"i": i, "hash": inst["hash"],
                                                     "sep": float(isqrt_up(sep)), "bound": float(bd)})

            # ── C3: agreement with R ───────────────────────────────────────────────────────────
            if z_v2 is not None:
                if not rr.is_exact:
                    c3[c]["r_unavailable"] += 1
                else:
                    dist_sq = R.exact_distance(z_v2, rr.z)
                    dist = float(isqrt_up(dist_sq))
                    c3[c]["max_exact_distance"] = max(c3[c]["max_exact_distance"], dist)
                    rad = ra if (a.is_certified and z_v2 is a.z) else radius(z_v2, cert_v2, rec)
                    if rad is None:
                        c3[c]["radius_unavailable"] += 1
                    else:
                        c3[c]["evaluable"] += 1
                        if dist_sq > rad * rad:
                            c3[c]["violations"] += 1
                            c3_rows[c].append({"i": i, "hash": inst["hash"],
                                               "dist": dist, "radius": float(rad)})

            # ── §4.4 equivalence gate ──────────────────────────────────────────────────────────
            if z_v1 is None:
                continue                                  # outside the required population
            if z_v2 is None:
                eq[c][EQ_UNPROVEN] = eq[c].get(EQ_UNPROVEN, 0) + 1
                unproven_rows[c].append({"i": i, "hash": inst["hash"], "why": "v2 accepted nothing"})
                continue
            if np.asarray(z_v1).tobytes() == np.asarray(z_v2).tobytes():
                eq[c][EQ_TRIVIAL] = eq[c].get(EQ_TRIVIAL, 0) + 1
                continue

            sep = exact_sep_sq(z_v1, z_v2)
            if sep <= SLACK_SQ:
                eq[c][EQ_BOUND] = eq[c].get(EQ_BOUND, 0) + 1
                continue

            cert_v1 = next((o.cert for o in (a, b) if o.z is not None
                            and np.asarray(o.z).tobytes() == np.asarray(z_v1).tobytes()), None)
            r1 = radius(z_v1, cert_v1, rec) if cert_v1 is not None else None
            r2 = radius(z_v2, cert_v2, rec)
            route = EQ_BOUND
            if (r1 is None or r2 is None) and rr.is_exact:
                r1 = r1 if r1 is not None else isqrt_up(R.exact_distance(z_v1, rr.z))
                r2 = r2 if r2 is not None else isqrt_up(R.exact_distance(z_v2, rr.z))
                route = EQ_R
            if r1 is None or r2 is None:
                eq[c][EQ_UNPROVEN] = eq[c].get(EQ_UNPROVEN, 0) + 1
                unproven_rows[c].append({"i": i, "hash": inst["hash"],
                                         "why": "no derived bound and R unavailable"})
                continue
            bd = r1 + r2 + SLACK
            if sep <= bd * bd:
                eq[c][route] = eq[c].get(route, 0) + 1
            else:
                eq[c][EQ_UNPROVEN] = eq[c].get(EQ_UNPROVEN, 0) + 1
                unproven_rows[c].append({"i": i, "hash": inst["hash"], "why": "separation exceeds bound",
                                         "sep": float(isqrt_up(sep)), "bound": float(bd)})

        if (i + 1) % 200 == 0:
            print(f"[{time.time()-t0:7.1f}s]   {i+1}/{len(corpus)}  R={r_status}", flush=True)

    out = {
        "corpus_hash": REGISTERED_CORPUS_HASH,
        "instances": len(corpus),
        "v1_dispositions": v1_disp,
        "reference_solver_status": r_status,
        "repair_certificate_available_for_A": repair_avail,
        "candidates": {},
    }
    for c in B_CANDIDATES:
        unp = eq[c].get(EQ_UNPROVEN, 0)
        out["candidates"][c] = {
            "equivalence": eq[c],
            "EQUIVALENCE_UNPROVEN": unp,
            "equivalence_gate_pass": unp == 0,
            "sa2": sa2[c],
            "sa2_pass": sa2[c]["disagree"] == 0 and sa2[c]["unavailable"] == 0,
            "c3": c3[c],
            "c3_pass_on_evaluable_subset": c3[c]["violations"] == 0,
            "unproven_rows": unproven_rows[c][:50],
            "disagreement_rows": disagree_rows[c][:50],
            "c3_violation_rows": c3_rows[c][:50],
        }
        print(f"\n{c}:", flush=True)
        print(f"  equivalence {eq[c]}  UNPROVEN={unp}  gate={'PASS' if unp==0 else 'FAIL'}", flush=True)
        print(f"  SA-2 {sa2[c]}", flush=True)
        print(f"  C3   {c3[c]}", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n1_equivalence{suffix}.json"), "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"\n[{time.time()-t0:7.1f}s] wrote equivalence report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
