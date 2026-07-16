"""MR-002 — DIRECTED-ROUNDING CORRECTION over the COMPLETE affected population (ruling §1–§5).

    "Do not infer absence of impact from representative magnitudes, worst cases from a sample,
     theoretical ulp estimates alone, or large apparent average margins. Every affected comparison
     must be recomputed."

So nothing here is sampled, extrapolated, or argued from scale. Every certificate the corpus can
produce is rebuilt, every serialized endpoint is recomputed under every serializer that has existed
in this program, and every Boolean verdict is compared record by record.

WHY ALL THREE SERIALIZERS
-------------------------
The defective nearest-rounding version was NEVER COMMITTED — it lived only in a working tree. Git
therefore cannot tell us which of the 2026-07-13 artifacts it produced, and I will not guess.

The way out is to stop needing to know. The corpus is frozen and the solvers are deterministic, so
every certificate any past run could have produced is reproducible here. Recompute each under all
three serializers and require ZERO verdict flips under EVERY pairing:

    L  float(x)                     NEAREST — the defect. Not a bound in either direction.
    N  nextafter(float(x), +-inf)   rigorous but a full ulp loose; maps an exact 0 to -5e-324.
    D  correctly directed           the tightest double on the correct side. THE CORRECTION.

If no verdict differs between L, N and D, then the retained Booleans are unaffected regardless of
which serializer wrote them, and the archaeology is moot.

THE AUTHORITY IS THE EXACT RATIONAL. Each gate is ALSO evaluated in exact arithmetic, straight from
the interval endpoints as Fractions, with no binary64 anywhere. That is the ground truth the three
serializers are judged against — not one of them judging another.

Emits:
  MR002_DirectedRounding_Inventory.jsonl.gz   every affected field, one record per line (§2)
  MR002_DirectedRounding_Correction.json      verdict comparison, margins, provenance (§4, §5, §7)

No performance computed. Validation and sealed OOS remain SEALED AND UNREAD.
"""

from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import os
import struct
import sys
import time
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002 import certificate as cert_mod  # noqa: E402
from app.research.mr002 import directed  # noqa: E402
from app.research.mr002.certificate import (  # noqa: E402
    MAX_INTERVAL_WIDTH,
    SIGNED_GAP_MAX,
    CertificateDefect,
    gap_intervals,
    project_dual,
    verify_canonical_hessian,
)
from app.research.mr002.directed import (  # noqa: E402
    as_fraction,
    legacy_nearest_dn,
    legacy_nearest_up,
    legacy_nextafter_dn,
    legacy_nextafter_up,
    to_binary64_dn,
    to_binary64_up,
)
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    SOLVERS,
    capture,
    fixture_hash,
)
from scripts.mr002_solver_intersection import (  # noqa: E402
    LIMITS,
    REGISTERED_CORPUS_HASH,
)

GAP_BAND = Fraction(*SIGNED_GAP_MAX.as_integer_ratio())
WIDTH_LIM = Fraction(*MAX_INTERVAL_WIDTH.as_integer_ratio())

# Every serialized endpoint the certificate writes. `direction` is the side the bound must fall on.
FIELDS = (
    ("gamma_lower", "dn", "signed_gap_band"),
    ("gamma_upper", "up", "signed_gap_band"),
    ("primal_lower", "dn", None),
    ("primal_upper", "up", None),
    ("dual_lower", "dn", "reused_as_input"),      # -> certify_repair's Ghat. A downstream INPUT.
    ("dual_upper", "up", None),
    ("lagrangian_slack", "dn", None),
    ("stationarity_energy", "dn", None),
    ("primal_interval_width", "up", "interval_width_limit"),
    ("dual_interval_width", "up", "interval_width_limit"),
)


# §7 — everything whose bytes can change a serialized endpoint or a verdict. Hashed from INSIDE the
# container, from the files `import` actually resolved.
SOURCE_TREE = (
    "app/research/mr002/directed.py",             # the serializer
    "app/research/mr002/certificate.py",          # its only evidentiary caller
    "app/research/mr002/joint_portfolio.py",      # the canonical C/b construction
    "scripts/mr002_directed_rounding_correction.py",   # the inventory generator + flip analysis
    "scripts/mr002_coverage_signed_gap.py",       # the solver set and the corpus capture
    "scripts/mr002_solver_intersection.py",       # LIMITS + the registered corpus hash
    "tests/research/test_mr002_directed_rounding.py",  # the fixture suite
)


def source_hashes() -> dict:
    """Line-ending-normalised, because `git archive` on a Windows host injects CRLF on the way into
    the image. Provenance asks whether this is the same SOURCE, not whether it crossed the same
    filesystem."""
    root = "/work/apps/backend"
    out = {}
    for rel in SOURCE_TREE:
        with open(f"{root}/{rel}", "rb") as fh:
            out[rel] = hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()
    return out


def _mono(x: float) -> int:
    """A double's IEEE-754 bits mapped to a MONOTONIC integer, so consecutive doubles differ by 1.

    Adjacent doubles are adjacent bit patterns within a sign, but the negatives run backwards. This
    folds them so the whole line is ordered, which is what makes an ulp COUNT exact.
    """
    (i,) = struct.unpack("<q", struct.pack("<d", x))
    return i if i >= 0 else (1 << 63) - i


def ulps_between(a: float, b: float) -> int:
    """Signed ulp distance. Counted on the bit pattern — NEVER as (a - b) / ulp, which is itself a
    floating-point calculation and rounds exactly where we are trying to measure rounding."""
    return _mono(a) - _mono(b)


def endpoints(f_iv, d_iv, slag_iv, energy_iv):
    """The authoritative EXACT rational for every serialized field, plus the interval it came from."""
    gamma = f_iv - d_iv
    return {
        "gamma_lower": gamma.a, "gamma_upper": gamma.b,
        "primal_lower": f_iv.a, "primal_upper": f_iv.b,
        "dual_lower": d_iv.a, "dual_upper": d_iv.b,
        "lagrangian_slack": slag_iv.a, "stationarity_energy": energy_iv.a,
        "primal_interval_width": f_iv.delta, "dual_interval_width": d_iv.delta,
    }


def serialize(v, direction, how):
    if how == "D":
        return to_binary64_up(v) if direction == "up" else to_binary64_dn(v)
    if how == "N":
        return legacy_nextafter_up(v) if direction == "up" else legacy_nextafter_dn(v)
    return legacy_nearest_up(v) if direction == "up" else legacy_nearest_dn(v)


def gate(vals: dict, exact: bool) -> bool:
    """The registered signed-gap predicate. `exact=True` evaluates it in pure rational arithmetic —
    no binary64 anywhere — which is the authority the three serializers are judged against."""
    if exact:
        g = max(abs(vals["gamma_lower"]), abs(vals["gamma_upper"]))
        return (g <= GAP_BAND
                and vals["primal_interval_width"] <= WIDTH_LIM
                and vals["dual_interval_width"] <= WIDTH_LIM)
    g = max(abs(vals["gamma_lower"]), abs(vals["gamma_upper"]))
    return (g <= SIGNED_GAP_MAX
            and vals["primal_interval_width"] <= MAX_INTERVAL_WIDTH
            and vals["dual_interval_width"] <= MAX_INTERVAL_WIDTH)


def main() -> int:  # noqa: PLR0915
    out_dir = os.environ.get("MR002_OUT", "/out")
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {len(CORPUS)}  hash {ch}")
    if ch != REGISTERED_CORPUS_HASH:
        print("ABORT: corpus hash mismatch — this is not the registered population", file=sys.stderr)
        return 1
    print("[ok] corpus reproduced EXACTLY\n")

    # SMOKE ONLY. The evidentiary run sets no limit, and the artifact records the population it
    # actually covered — so a truncated run cannot be mistaken for a complete one: `population.
    # complete` compares the certificates built against instances x solvers, and a smoke run is
    # stamped `smoke_truncated`, which fails the §9 completeness condition by construction.
    smoke = int(os.environ.get("MR002_SMOKE_N", "0"))
    population = CORPUS[:smoke] if smoke else CORPUS
    n_inst = len(population)
    if smoke:
        print(f"⚠ SMOKE RUN — {n_inst} of {len(CORPUS)} instances. NOT EVIDENCE.\n")

    inv_path = f"{out_dir}/MR002_DirectedRounding_Inventory.jsonl.gz"

    n_cert = n_records = 0
    n_solver_exc = 0
    n_kkt_fail = 0
    gap_only: dict[str, dict[int, bool]] = {s: {} for s in SOLVERS}
    unclassified = 0
    non_finite = 0
    flips = {"L_vs_D": [], "N_vs_D": [], "D_vs_EXACT": []}
    verdicts: dict[str, dict[str, dict[int, bool]]] = {
        h: {s: {} for s in SOLVERS} for h in ("L", "N", "D", "EXACT")
    }
    # margin statistics, per gate type
    stats: dict[str, dict] = {
        g: {"max_inward_error_ulps": 0, "min_authoritative_margin": None,
            "min_corrected_margin": None, "within_1_ulp": 0, "within_10_ulps": 0,
            "capable_of_flipping": 0, "records": 0}
        for g in ("signed_gap_band", "interval_width_limit", "reused_as_input")
    }

    with gzip.open(inv_path, "wt", encoding="utf-8", compresslevel=6) as inv:
        t0 = time.perf_counter()
        for i, inst in enumerate(population):
            rec = (inst["t"], inst["A_ub"], inst["b_ub"],
                   inst["A_eq"], inst["b_eq"], inst["upper"])
            chash = fixture_hash(inst)
            for sname, solver in SOLVERS.items():
                try:
                    z, lam = solver(*(x.copy() for x in rec))
                    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
                        raise RuntimeError("non-finite primal or dual")
                except CertificateDefect:
                    raise
                except Exception:  # noqa: BLE001
                    # The solver never produced a point, so NO value was ever serialized for it and the
                    # nonqualification cannot depend on rounding. Classified, not unclassified.
                    n_solver_exc += 1
                    for h in ("L", "N", "D", "EXACT"):
                        verdicts[h][sname][i] = False
                    continue

                meq = rec[3].shape[0]
                lam_bar, _clip, _cl = project_dual(lam, meq)
                verify_canonical_hessian(np.diag(2.0 / rec[0]), rec[0])

                # THE REGISTERED VERDICT is canonical_qualify = (no KKT limit violated) AND (the
                # signed-gap gate passes). Evaluating only the signed-gap half would be reporting a
                # SUB-COMPONENT of the verdict and calling it the verdict — and the counts would not
                # reconcile against what the predecessor artifacts actually recorded (measured: 454
                # vs 592 for HIGHS_QPASM). The KKT half never touches the serializer, so it cannot
                # flip under rounding; it is carried here so that what is compared is the REGISTERED
                # Boolean, not a piece of it.
                n = len(rec[0])
                C, b = jp._qp_matrices(rec[1], rec[2], rec[3], rec[4], rec[5], n)
                ck = jp._acceptance(z, lam, meq, np.diag(2.0 / rec[0]), 2.0 * np.ones(n),
                                    C, b, *rec[1:])
                kkt_bad = sorted(k for k, lim in LIMITS.items() if ck[k] > lim)

                f_iv, d_iv, slag_iv, energy_iv = gap_intervals(z, lam_bar, *rec)
                eps = endpoints(f_iv, d_iv, slag_iv, energy_iv)
                n_cert += 1
                if kkt_bad:
                    n_kkt_fail += 1

                exact_vals, ser = {}, {"L": {}, "N": {}, "D": {}}
                bad_field = False
                for fname, direction, gate_type in FIELDS:
                    v = eps[fname]
                    try:
                        ex = as_fraction(v)
                    except directed.SerializationDefect:
                        non_finite += 1
                        bad_field = True
                        break
                    exact_vals[fname] = ex
                    for h in ("L", "N", "D"):
                        ser[h][fname] = serialize(v, direction, h)

                    d_val = ser["D"][fname]
                    l_val, n_val = ser["L"][fname], ser["N"][fname]
                    # INWARD error of the defective serializer: how far L fell on the WRONG side.
                    fl = Fraction(*l_val.as_integer_ratio())
                    inward = (ex - fl) if direction == "up" else (fl - ex)   # > 0 => L is NOT a bound
                    rowrec = {
                        "i": i, "ch": chash, "solver": sname, "field": fname, "dir": direction,
                        "gate": gate_type,
                        "auth": f"{ex.numerator}/{ex.denominator}",
                        "L": repr(l_val), "N": repr(n_val), "D": repr(d_val),
                        "L_ulps_from_D": ulps_between(l_val, d_val),
                        "N_ulps_from_D": ulps_between(n_val, d_val),
                        "L_inward_error": float(inward),
                        "L_is_a_bound": inward <= 0,
                    }
                    inv.write(json.dumps(rowrec, separators=(",", ":")) + "\n")
                    n_records += 1

                    if gate_type:
                        st = stats[gate_type]
                        st["records"] += 1
                        st["max_inward_error_ulps"] = max(
                            st["max_inward_error_ulps"], abs(ulps_between(l_val, d_val)))
                        if gate_type == "signed_gap_band":
                            m_auth = GAP_BAND - abs(ex)
                            m_corr = SIGNED_GAP_MAX - abs(d_val)
                        elif gate_type == "interval_width_limit":
                            m_auth = WIDTH_LIM - ex
                            m_corr = MAX_INTERVAL_WIDTH - d_val
                        else:
                            m_auth = m_corr = None
                        if m_auth is not None:
                            if (st["min_authoritative_margin"] is None
                                    or m_auth < st["min_authoritative_margin"]):
                                st["min_authoritative_margin"] = m_auth
                            if (st["min_corrected_margin"] is None
                                    or m_corr < st["min_corrected_margin"]):
                                st["min_corrected_margin"] = m_corr

                            # "within k ulps of the gate" — counted on the BIT PATTERN, so it is the
                            # real question ("how many representable steps from the threshold is this
                            # value?") rather than a ratio that would itself have to be rounded.
                            lim = (SIGNED_GAP_MAX if gate_type == "signed_gap_band"
                                   else MAX_INTERVAL_WIDTH)
                            near = abs(ulps_between(abs(d_val), lim))
                            if near <= 1:
                                st["within_1_ulp"] += 1
                            if near <= 10:
                                st["within_10_ulps"] += 1
                            # CAPABLE OF FLIPPING: the authoritative margin and the corrected binary64
                            # margin fall on OPPOSITE sides of the threshold, i.e. serialization alone
                            # decides this verdict. This is the count that must be reconciled against
                            # the observed flips — not an average, not a typical scale.
                            if (m_auth <= 0) != (m_corr <= 0):
                                st["capable_of_flipping"] += 1

                if bad_field:
                    for h in ("L", "N", "D", "EXACT"):
                        verdicts[h][sname][i] = False
                    continue

                # The REGISTERED verdict: both halves. `kkt_bad` is identical across serializers by
                # construction, so any flip that appears below is attributable to rounding ALONE.
                ok_kkt = not kkt_bad
                v_exact = ok_kkt and gate(exact_vals, exact=True)
                v_l, v_n, v_d = (ok_kkt and gate(ser[h], exact=False) for h in ("L", "N", "D"))
                for h, v in (("L", v_l), ("N", v_n), ("D", v_d), ("EXACT", v_exact)):
                    verdicts[h][sname][i] = v
                gap_only[sname][i] = gate(ser["D"], exact=False)

                if v_l != v_d:
                    flips["L_vs_D"].append({"i": i, "ch": chash, "solver": sname,
                                            "previous": v_l, "corrected": v_d})
                if v_n != v_d:
                    flips["N_vs_D"].append({"i": i, "ch": chash, "solver": sname,
                                            "previous": v_n, "corrected": v_d})
                if v_d != v_exact:
                    flips["D_vs_EXACT"].append({"i": i, "ch": chash, "solver": sname,
                                                "corrected": v_d, "authoritative": v_exact})

            if (i + 1) % 250 == 0:
                print(f"  {i+1}/{n_inst}  ({time.perf_counter()-t0:.0f}s, {n_records} field records)",
                      flush=True)
    secs = time.perf_counter() - t0

    # ---- expected population: every (instance, solver) pair must be classified -----------------
    expected = n_inst * len(SOLVERS)
    for h in ("L", "N", "D", "EXACT"):
        for s in SOLVERS:
            unclassified += n_inst - len(verdicts[h][s])
    unclassified //= 4

    nonqual = {h: {s: sorted(i for i, v in verdicts[h][s].items() if not v) for s in SOLVERS}
               for h in ("L", "N", "D", "EXACT")}
    cascade = {h: sorted(set(nonqual[h]["QUADPROG_SQRT"]) & set(nonqual[h]["PIQP_P2"]))
               for h in ("L", "N", "D", "EXACT")}

    with open(inv_path, "rb") as fh:
        inv_sha = hashlib.sha256(fh.read()).hexdigest()

    print("\n=== population ===")
    print(f"  instances                  : {n_inst}")
    print(f"  solvers                    : {len(SOLVERS)}")
    print(f"  (instance, solver) pairs   : {expected}")
    print(f"  certificates rebuilt       : {n_cert}")
    print(f"  solver exceptions          : {n_solver_exc}  (no value serialized; rounding cannot "
          f"affect the outcome)")
    print(f"  serialized field records   : {n_records}")
    print(f"  certificates failing a KKT limit : {n_kkt_fail}  (rounding-independent; the KKT half "
          f"of the registered verdict never touches the serializer)")
    print(f"  unclassified               : {unclassified}")
    print(f"  non-finite corrections     : {non_finite}")

    print("\n=== verdict comparison (§4) ===")
    for k, v in flips.items():
        print(f"  {k:12} flips: {len(v)}")
    print("\n  primary (QUADPROG_SQRT) nonqualifications:")
    for h in ("L", "N", "D", "EXACT"):
        print(f"    {h:6} {len(nonqual[h]['QUADPROG_SQRT']):5}   cascade unresolved: "
              f"{len(cascade[h])}")

    print("\n=== margins (§5) — explanatory; the record-level recomputation above is the proof ===")
    for g, st in stats.items():
        if not st["records"]:
            continue
        ma = st["min_authoritative_margin"]
        mc = st["min_corrected_margin"]
        print(f"  {g}")
        print(f"    records                       : {st['records']}")
        print(f"    max |L - D| (ulps)            : {st['max_inward_error_ulps']}")
        if ma is not None:
            print(f"    min authoritative margin      : {float(ma):.6e}")
            print(f"    min corrected binary64 margin : {float(mc):.6e}")
        print(f"    within 1 ulp of the gate      : {st['within_1_ulp']}")
        print(f"    within 10 ulps of the gate    : {st['within_10_ulps']}")
        print(f"    verdicts capable of flipping  : {st['capable_of_flipping']}")

    zero_flips = all(len(v) == 0 for v in flips.values())
    complete = (unclassified == 0 and non_finite == 0
                and n_cert + n_solver_exc == expected
                and not smoke)          # a truncated run is NOT the complete affected population
    ok = zero_flips and complete

    print("\n" + "=" * 74)
    print("  DIRECTED-ROUNDING CORRECTION: " + ("PASS" if ok else "STOP FOR ADJUDICATION"))
    print("=" * 74)

    doc = {
        "schema": "MR002_DirectedRoundingCorrection/v1",
        "authorization": "owner ruling 2026-07-14, directed-rounding correction §1-§9",
        "standard": ("complete affected population; no sampling, no extrapolation, no ulp argument "
                     "substituted for a record-level recomputation"),
        "why_three_serializers": (
            "the defective nearest-rounding serializer was NEVER COMMITTED, so git cannot establish "
            "which retained artifact it produced. Rather than guess, every certificate is recomputed "
            "under L (nearest, the defect), N (nextafter, rigorous but loose) and D (correctly "
            "directed), and zero flips are required under EVERY pairing — which makes the question "
            "moot."),
        "serializers": {
            "L": "float(x) — NEAREST. the defect. not a bound in either direction.",
            "N": "nextafter(float(x), +-inf) — rigorous, 1-2 ulps loose, maps exact 0 to -5e-324.",
            "D": "correctly directed — the tightest double on the correct side. THE CORRECTION.",
            "EXACT": "pure rational arithmetic, no binary64. THE AUTHORITY.",
        },
        "population": {
            "instances": n_inst,
            "corpus_hash": ch,
            "corpus_verified": True,
            "solvers": sorted(SOLVERS),
            "instance_solver_pairs": expected,
            "certificates_rebuilt": n_cert,
            "solver_exceptions": n_solver_exc,
            "serialized_field_records": n_records,
            "unclassified_records": unclassified,
            "non_finite_corrections": non_finite,
            "certificates_failing_a_kkt_limit": n_kkt_fail,
            "complete": complete,
            "smoke_truncated": bool(smoke),
        },
        "verdict_changes": {k: {"count": len(v), "records": v[:50]} for k, v in flips.items()},
        "nonqualifications": {h: {s: nonqual[h][s] for s in SOLVERS}
                              for h in ("L", "N", "D", "EXACT")},
        "cascade_unresolved": {h: cascade[h] for h in ("L", "N", "D", "EXACT")},
        "signed_gap_gate_only_nonqualifications": {
            s: sorted(i for i, v in gap_only[s].items() if not v) for s in SOLVERS},
        "verdict_definition": (
            "the REGISTERED verdict is canonical_qualify = (no KKT limit violated) AND (the "
            "signed-gap interval lies wholly in the band AND the interval widths are within limit). "
            "`nonqualifications` is that verdict. `signed_gap_gate_only_nonqualifications` is the "
            "signed-gap half ALONE, recorded separately so the two can never be confused: reporting "
            "the half as if it were the whole is what made an earlier pass of this correction fail "
            "to reconcile with the predecessor artifacts."),
        "margins": {
            g: {
                "records": st["records"],
                "max_inward_rounding_error_ulps": st["max_inward_error_ulps"],
                "min_authoritative_margin": (float(st["min_authoritative_margin"])
                                             if st["min_authoritative_margin"] is not None else None),
                "min_corrected_binary64_margin": (float(st["min_corrected_margin"])
                                                  if st["min_corrected_margin"] is not None
                                                  else None),
                "within_1_ulp_of_gate": st["within_1_ulp"],
                "within_10_ulps_of_gate": st["within_10_ulps"],
                "verdicts_capable_of_flipping": st["capable_of_flipping"],
            } for g, st in stats.items() if st["records"]
        },
        "gates": {
            "signed_gap_band": [-SIGNED_GAP_MAX, SIGNED_GAP_MAX],
            "max_interval_width": MAX_INTERVAL_WIDTH,
            "LIMITS": LIMITS,
        },
        "inventory": {
            "path": "MR002_DirectedRounding_Inventory.jsonl.gz",
            "sha256": inv_sha,
            "records": n_records,
            "fields_per_certificate": [f[0] for f in FIELDS],
        },
        "provenance": {
            "image": os.environ.get("MR002_IMAGE_DIGEST"),
            "commit": os.environ.get("MR002_COMMIT_SHA"),
            # §7 — the MOUNTED SOURCE TREE, hashed from inside the container. A host-side hash proves
            # what is in the repository; only this proves which bytes the interpreter actually read.
            "mounted_source_sha256": source_hashes(),
            "directed_module_sha256": hashlib.sha256(
                inspect.getsource(directed).encode()).hexdigest(),
            "certificate_module_sha256": hashlib.sha256(
                inspect.getsource(cert_mod).encode()).hexdigest(),
            "correction_driver_sha256": hashlib.sha256(
                inspect.getsource(sys.modules[__name__]).encode()).hexdigest(),
        },
        "wall_clock_seconds": secs,
        "correction_pass": ok,
        "no_performance_computed": True,
        "validation_and_sealed_oos": "SEALED AND UNREAD",
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{out_dir}/MR002_DirectedRounding_Correction.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\ninventory  sha256 {inv_sha}  ({n_records} records)")
    print(f"correction sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"wall-clock {secs:.0f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
