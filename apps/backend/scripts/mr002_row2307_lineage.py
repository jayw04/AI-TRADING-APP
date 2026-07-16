"""MR-002 row 2307 — near-cancellation LINEAGE analysis. DIAGNOSTIC ONLY.

Authorised by the owner (2026-07-16) AFTER disposition A. Explains HOW an exactly infeasible derived
model arose. It CANNOT alter row 2307's registered disposition, and it does NOT rebuild the corpus
from rearranged arithmetic — it reads the frozen corpus and reports.

Method: the Farkas certificate's SUPPORT is the minimal contradiction. Only rows with y_i != 0
participate, so we trace those rather than all 45. For each, we recover the upstream operands from
the matrices themselves (the model's algebraic form is known, see joint_portfolio._build_model):

    all inequalities are   const + coef . z <= 0   ->   coef . z <= -const
      sector_gross[k] : coef = ind_k - 0.20*ones      const = F_gross_k - 0.20*F_gross
      sector_net+-[k] : coef = +-(ind_k*v_d) - 0.05*ones
      beta+-          : coef = +-(v_d*v_beta) - 0.10*ones
      net_drift+-     : coef = +-v_d - 0.05*ones      const = +-F_net - 0.05*F_gross
      gross<=1        : coef = ones                   const = F_gross - 1.00
    equality          : sum_{cands} d_i * x_i = 0     (coefficients +-1.0, RHS 0.0 — both EXACT)
    bounds            : w_i <= upper_i
"""
from __future__ import annotations

import json
import struct
import sys
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")
sys.path.insert(0, "/work/apps/backend/scripts")

from mr002_row2307_adjudication import indep_original, indep_phase1, verify_farkas  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    REGISTERED_CORPUS_HASH,
    capture,
    fixture_hash,
)

ROW = 2307
CONTENT_HASH = "cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f"
OUT = "/out/MR002_Row2307_Lineage.json"

SECTOR_GROSS_CAP, SECTOR_NET_CAP, BETA_CAP, DRIFT_BAND, MAX_GROSS_NAV = 0.20, 0.05, 0.10, 0.05, 1.00


def hx(x: float) -> str:
    """The exact binary64 payload — never a rounded decimal rendering."""
    return "0x" + struct.pack(">d", float(x)).hex()


def exact(x: float) -> str:
    f = Fraction(*float(x).as_integer_ratio())
    return f"{f.numerator}/{f.denominator}"


def ulps(a: float, b: float) -> int:
    """Distance in ULPs — how many representable doubles separate a and b."""
    ia = struct.unpack(">q", struct.pack(">d", float(a)))[0]
    ib = struct.unpack(">q", struct.pack(">d", float(b)))[0]
    if ia < 0: ia = -(1 << 63) - ia
    if ib < 0: ib = -(1 << 63) - ib
    return abs(ia - ib)


def classify_row(coef, n) -> str:
    """Infer the constraint label from its algebraic signature."""
    c = np.asarray(coef, dtype=float)
    if np.all(c == 1.0):
        return "gross<=1"
    vals = set(np.round(c, 12))
    # sector_gross: entries are (1 - 0.20) or (0 - 0.20)
    if vals <= {round(1 - SECTOR_GROSS_CAP, 12), round(-SECTOR_GROSS_CAP, 12)}:
        return "sector_gross[k]"
    # net_drift: +-1 - 0.05
    if vals <= {round(1 - DRIFT_BAND, 12), round(-1 - DRIFT_BAND, 12)}:
        return "net_drift+"
    if vals <= {round(1 - DRIFT_BAND, 12), round(-1 - DRIFT_BAND, 12), round(-DRIFT_BAND, 12)}:
        return "net_drift+/-"
    # sector_net: +-1 - 0.05 or -0.05
    if vals <= {round(1 - SECTOR_NET_CAP, 12), round(-1 - SECTOR_NET_CAP, 12),
                round(-SECTOR_NET_CAP, 12)}:
        return "sector_net+-[k]"
    return "beta+- (or sector_net with beta-weighted coef)"


def main() -> int:
    ev: dict = {"analysis": "MR002 row 2307 near-cancellation lineage",
                "status": "DIAGNOSTIC ONLY — cannot alter the registered disposition A",
                "row": ROW}

    import app.research.mr002.joint_portfolio as jp
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])
    import hashlib
    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    if ch != REGISTERED_CORPUS_HASH:
        raise SystemExit(f"STOP: corpus hash mismatch {ch}")
    inst = CORPUS[ROW]
    if fixture_hash(inst) != CONTENT_HASH:
        raise SystemExit("STOP: content hash mismatch")
    print("[ok] corpus + row 2307 identity bound\n")

    A_ub = np.asarray(inst["A_ub"], dtype=np.float64)
    b_ub = np.asarray(inst["b_ub"], dtype=np.float64).ravel()
    A_eq = np.asarray(inst["A_eq"], dtype=np.float64)
    b_eq = np.asarray(inst["b_eq"], dtype=np.float64).ravel()
    upper = np.asarray(inst["upper"], dtype=np.float64).ravel()
    n, mub, meq = A_eq.shape[1], A_ub.shape[0], A_eq.shape[0]
    ev["shape"] = {"n": n, "m_ub": mub, "m_eq": meq}
    print(f"n={n}  m_ub={mub}  m_eq={meq}")

    # ---- the Farkas certificate: the MINIMAL contradiction -----------------------------------
    M, h, _ = indep_original(A_ub, b_ub, A_eq, b_eq, upper)
    r = indep_phase1(M, h)
    if r["feasible"]:
        raise SystemExit("STOP: row 2307 is feasible here — contradicts the adjudication")
    y = r["y"]
    v = verify_farkas(M, h, y)
    ev["farkas_verified"] = v
    print(f"[ok] Farkas verified: {v['holds']}  h'y = {v['hTy']}\n")

    support = [(i, y[i]) for i in range(len(y)) if y[i] != 0]
    ev["certificate_support_size"] = len(support)
    print(f"=== certificate support: {len(support)} of {len(M)} rows carry NONZERO y ===")
    print("    (only these participate in the contradiction)\n")

    rows_out = []
    for i, yi in support:
        if i < meq:
            origin, label, coef, rhs = f"A_eq[{i}]", "dollar_neutral_new_entries", A_eq[i], b_eq[i]
        elif i < meq + mub:
            rr = i - meq
            origin, label, coef, rhs = f"A_ub[{rr}]", classify_row(A_ub[rr], n), A_ub[rr], b_ub[rr]
        else:
            bi = i - meq - mub
            origin, label = f"bound[{bi}]", "w_i <= upper_i"
            coef, rhs = np.eye(n)[bi], upper[bi]
        d = {
            "M_row": i, "origin": origin, "inferred_label": label,
            "y": f"{yi.numerator}/{yi.denominator}", "y_float": float(yi),
            "rhs_float": float(rhs), "rhs_hex": hx(rhs), "rhs_exact": exact(rhs),
            "coef_hex": [hx(c) for c in np.asarray(coef, dtype=float)],
            "coef_float": [float(c) for c in np.asarray(coef, dtype=float)],
        }
        rows_out.append(d)
        print(f"  {origin:12} y={float(yi):+.6e}  {label}")
        print(f"      rhs = {float(rhs):+.17e}  hex {hx(rhs)}")
    ev["support_rows"] = rows_out

    # ---- recover the upstream operands from the matrices --------------------------------------
    print("\n=== recovered upstream operands (the model's algebraic form is known) ===")
    lin = {}
    gross_row = next((rr for rr in range(mub) if np.all(A_ub[rr] == 1.0)), None)
    if gross_row is not None:
        F_gross = MAX_GROSS_NAV - float(b_ub[gross_row])   # rhs = -(F_gross - 1.00)
        lin["gross_row_index"] = gross_row
        lin["F_gross"] = {"float": F_gross, "hex": hx(F_gross), "exact": exact(F_gross)}
        print(f"  F_gross = 1.00 - b_ub[{gross_row}] = {F_gross:.17e}   hex {hx(F_gross)}")

    # net_drift+ : coef = v_d - 0.05*ones  ->  v_d = coef + 0.05
    nd = None
    for rr in range(mub):
        vals = set(np.round(A_ub[rr], 12))
        if vals <= {round(1 - DRIFT_BAND, 12), round(-1 - DRIFT_BAND, 12)} and len(vals) > 0:
            nd = rr
            break
    if nd is not None:
        v_d = np.round(A_ub[nd] + DRIFT_BAND)
        lin["net_drift_row_index"] = nd
        lin["v_d_recovered"] = [int(x) for x in v_d]
        print(f"  v_d (from A_ub[{nd}] + 0.05) = {[int(x) for x in v_d]}")
    ev["recovered_operands"] = lin

    # ---- the cancellation diagnostic -----------------------------------------------------------
    print("\n=== cancellation diagnostic ===")
    caps = {"SECTOR_GROSS_CAP": SECTOR_GROSS_CAP, "SECTOR_NET_CAP": SECTOR_NET_CAP,
            "BETA_CAP": BETA_CAP, "DRIFT_BAND": DRIFT_BAND, "MAX_GROSS_NAV": MAX_GROSS_NAV}
    cap_rep = {}
    for k, val in caps.items():
        f = Fraction(*float(val).as_integer_ratio())
        target = Fraction(int(round(val * 100)), 100)
        exact_rep = f == target
        cap_rep[k] = {"float": val, "hex": hx(val), "exact_rational": exact(val),
                      "is_exactly_representable": exact_rep,
                      "error_vs_decimal": float(f - target)}
        print(f"  {k:18} {val:<6} hex {hx(val)}  exactly representable: {exact_rep}")
    ev["cap_representation"] = cap_rep

    # magnitude of the contradiction vs the scale of the data in the support
    scales = [abs(d["rhs_float"]) for d in rows_out if d["rhs_float"] != 0]
    ev["contradiction"] = {
        "phase_i_optimum_exact": r["objective"],
        "phase_i_optimum_float": float(Fraction(r["objective"])),
        "support_rhs_magnitudes": scales,
        "min_nonzero_rhs_magnitude": min(scales) if scales else None,
    }
    print(f"\n  exact Phase-I optimum : {r['objective']}")
    print(f"                        = {float(Fraction(r['objective'])):.6e}")
    if scales:
        print(f"  support |rhs| range   : {min(scales):.6e} .. {max(scales):.6e}")

    body = json.dumps(ev, indent=2, sort_keys=True, default=str)
    with open(OUT, "w") as f:
        f.write(body)
    import hashlib as _h
    print(f"\nevidence -> {OUT}  sha256 {_h.sha256(body.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
