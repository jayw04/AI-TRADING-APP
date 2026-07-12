"""MR-002 v1.1 — the 27 REGISTERED FIXTURES.

Registered by Pre-Registration v1.1 rev 3 §10 (countersigned 2026-07-12, artifact
sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5). All 27 must
pass, inside the frozen Linux/amd64 mr002-research image, BEFORE the 124-session
structural slice.

NOTE ON THE 8 "INHERITED" FIXTURES. They were written against v1.0's whole-candidate
removal cascade, which v1.1 RETIRES. A cascade cannot be re-tested once it no longer
exists, so each is re-asserted here as the PROPERTY it was protecting, now against the
joint construction. The original cascade tests remain in test_mr002_constraints.py as
permanent evidence that the v1.0 engine executed its registered rules faithfully -- which
is what makes the v1.0 invalidation a design finding rather than a bug.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from scipy.optimize import linprog

from app.research.mr002 import joint_portfolio as jp
from app.research.mr002.joint_portfolio import (
    BELOW_NUMERICAL_INCLUSION_FLOOR,
    BETA_CAP,
    DRIFT_BAND,
    EXECUTION_CONSTRAINED_INFEASIBLE,
    NEW_ENTRY_CAP,
    NO_EXECUTABLE_OPEN,
    SECTOR_GROSS_CAP,
    SECTOR_NET_CAP,
    VALID_ZERO_ENTRY_OUTCOME,
    Holding,
    InvalidRun,
    JointResult,
    NewCandidate,
    build_joint,
)

SECTORS = ["XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLE", "XLB", "XLU"]
TOL = 1e-9


def hold(pt, d, c, sector, beta=1.0, tradable=True, entry=0.015):
    return Holding(pt, d, c, sector, beta, entry, tradable)


def cand(pt, d, w, sector, beta=1.0):
    return NewCandidate(pt, d, w, sector, beta)


def book(res: JointResult, holdings, cands):
    """Independently rebuild the post-trade book from the RESULT -- never from the
    solver's own diagnostics."""
    rows = []
    for h in holdings:
        w = res.y.get(h.permaticker)
        if w is None:                      # fixed: cannot trade, exposure unchanged
            w = h.c if h.permaticker not in res.y else 0.0
        rows.append((h.sector, w, h.d, h.beta))
    for c in cands:
        rows.append((c.sector, res.x.get(c.permaticker, 0.0), c.d, c.beta))
    return [r for r in rows if r[1] > 0]


def assert_constraints(res, holdings, cands):
    rows = book(res, holdings, cands)
    G = sum(w for _s, w, _d, _b in rows)
    if G <= 0:
        return 0.0
    sg, sn = {}, {}
    for s, w, d, _b in rows:
        sg[s] = sg.get(s, 0.0) + w
        sn[s] = sn.get(s, 0.0) + d * w
    for s in sg:
        assert sg[s] <= SECTOR_GROSS_CAP * G + TOL, f"sector gross {s}: {sg[s] / G:.4f}"
        assert abs(sn[s]) <= SECTOR_NET_CAP * G + TOL, f"sector net {s}: {sn[s] / G:.4f}"
    beta = sum(d * b * w for _s, w, d, b in rows)
    assert abs(beta) <= BETA_CAP * G + TOL, f"beta {beta / G:.4f}"
    net = sum(d * w for _s, w, d, _b in rows)
    assert abs(net) <= DRIFT_BAND * G + TOL, f"net drift {net / G:.4f}"
    assert G <= 1.0 + TOL
    return G


def diversified(n_sectors=6, w=0.015, start=100, offset=0):
    """A balanced long/short candidate set across n sectors, beginning at SECTORS[offset].

    `offset` exists so a fixture can guarantee the new candidates occupy sectors DISJOINT
    from the existing book. Without it a shared sector couples the two, and a reduction
    driven by the sector-gross cap is indistinguishable from one driven by the entry cap
    -- which is precisely the distinction fixture 25 has to isolate.
    """
    out, pt = [], start
    for s in SECTORS[offset:offset + n_sectors]:
        out.append(cand(pt, 1, w, s))
        pt += 1
        out.append(cand(pt, -1, w, s))
        pt += 1
    return out


# ======================================================================================
# THE 8 INHERITED PROPERTIES (re-asserted against the joint construction)
# ======================================================================================
def test_01_bootstrap_succeeds_with_diversified_batch():
    """Zero-position book + broad L/S batch -> NONZERO orders satisfying every ratio.
    This is the property v1.0 could not deliver: it produced zero orders forever."""
    cs = diversified(9)
    res = build_joint([], cs)
    assert res.x, "bootstrap produced no orders -- the v1.0 pathology has returned"
    assert sum(res.x.values()) > 0
    G = assert_constraints(res, [], cs)
    assert G > 0


def test_02_single_sector_concentration_yields_no_positive_book():
    """20% sector-gross cap => a single-sector book is impossible. Q* = 0, and that is a
    VALID outcome, not an error."""
    cs = [cand(i, 1 if i % 2 == 0 else -1, 0.015, "XLK") for i in range(1, 21)]
    res = build_joint([], cs)
    assert res.outcome == VALID_ZERO_ENTRY_OUTCOME
    assert all(v <= TOL for v in res.x.values())


def test_03_batch_order_invariance_under_shuffle():
    cs = diversified(7)
    base = build_joint([], list(cs))
    for seed in range(5):
        sh = list(cs)
        np.random.default_rng(seed).shuffle(sh)
        r = build_joint([], sh)
        assert r.diagnostics["determinism_hash"] == base.diagnostics["determinism_hash"]


def test_04_denominator_is_actual_combined_gross_never_nav():
    """Constraints are evaluated against ACTUAL gross of the complete post-trade book --
    never 100% of NAV (the denominator the owner rejected)."""
    hs = [hold(1, 1, 0.010, "XLK")]
    cs = diversified(6)
    res = build_joint(hs, cs)
    G = assert_constraints(res, hs, cs)
    assert 0 < G < 1.0, "gross must not be assumed to be 100% of NAV"
    assert abs(G - res.diagnostics["total_gross"]) < TOL


def test_05_two_sector_batch_cannot_form_a_positive_book():
    """v1.0's 'cascading breach' property, restated: with only 2 sectors each would be
    ~50% of gross, so no positive portfolio exists. The joint solver returns Q*=0 rather
    than cascading."""
    cs = diversified(2)
    res = build_joint([], cs)
    assert res.outcome == VALID_ZERO_ENTRY_OUTCOME
    assert sum(res.x.values()) <= TOL


def test_06_zero_gross_no_division_and_no_precheck_failure():
    """The homogeneous form is well-defined at G = 0. No ZeroDivisionError, no spurious
    infeasibility."""
    res = build_joint([], [])
    assert res.outcome == VALID_ZERO_ENTRY_OUTCOME
    assert res.y == {} and res.x == {}
    res2 = build_joint([], diversified(6))
    assert res2.diagnostics["total_gross"] > 0


def test_07_low_gross_existing_book_uses_combined_gross():
    hs = [hold(1, 1, 0.015, "XLK"), hold(2, -1, 0.015, "XLF")]
    cs = diversified(6, start=200)
    res = build_joint(hs, cs)
    G = assert_constraints(res, hs, cs)
    assert G < 1.0
    assert G > sum(h.c for h in hs), "diversifying orders must raise gross"


def test_08_entry_cap_and_adv_clip_preserved():
    """1.5% NAV cap applies to NEW ENTRIES. A candidate above it is a FATAL defect (the
    ADV clip and the cap are embedded in w upstream)."""
    cs = diversified(6)
    res = build_joint([], cs)
    for pt, w in res.x.items():
        assert w <= NEW_ENTRY_CAP + TOL
    with pytest.raises(InvalidRun, match="1.5% entry cap"):
        build_joint([], [cand(1, 1, 0.02, "XLK")])


# ======================================================================================
# THE 16 JOINT-SOLVE FIXTURES
# ======================================================================================
def test_09_two_position_counterexample_joint_retains_what_sequential_liquidates():
    """THE fixture. A 2-sector existing book is 50%/50% of its own gross at ANY scale, so
    sequential repair (requiring the existing book to be independently feasible) drives it
    to zero. The JOINT solve retains it, because diversifying new orders make the COMBINED
    book compliant."""
    hs = [hold(1, 1, 0.00833, "XLK"), hold(2, -1, 0.00833, "XLF")]

    # sequential repair == solve the existing book with NO new candidates
    sequential = build_joint(hs, [])
    assert sum(sequential.y.values()) <= TOL, "the 2-sector book should be independently infeasible"

    cs = diversified(5, start=300)          # 5 OTHER sectors
    joint = build_joint(hs, cs)
    retained = sum(joint.y.values())
    assert retained > TOL, "the joint solve must retain what sequential repair liquidates"
    assert joint.x, "and must still deploy new orders"
    assert_constraints(joint, hs, cs)


def test_10_full_retention_when_new_candidates_make_the_book_feasible():
    hs = [hold(1, 1, 0.00833, "XLK"), hold(2, -1, 0.00833, "XLF")]
    cs = diversified(5, start=300)
    res = build_joint(hs, cs)
    for h in hs:
        assert res.y[h.permaticker] == pytest.approx(h.c, abs=1e-7), "should retain in full"


def test_11_minimum_forced_liquidation_when_full_retention_impossible():
    """A 5% sector-net position cannot be fully retained against a 0.05*G cap. The solver
    must reduce it as LITTLE as the constraints allow -- not liquidate it."""
    hs = [hold(1, 1, 0.05, "XLK")]
    cs = diversified(5, start=300)
    res = build_joint(hs, cs)
    y = res.y[1]
    assert 0 < y < 0.05, "must reduce, but not to zero"
    G = assert_constraints(res, hs, cs)
    # binding: the sector-net cap on XLK
    assert y == pytest.approx(SECTOR_NET_CAP * G, rel=1e-6), "reduction must be exactly binding"


def test_12_empty_existing_book_reduces_to_the_new_order_problem():
    cs = diversified(6)
    res = build_joint([], cs)
    assert res.y == {}
    assert res.diagnostics["R_star"] == 0.0
    assert res.diagnostics["Q_star"] > 0
    assert_constraints(res, [], cs)


def test_13_no_candidates_causes_only_necessary_existing_reductions():
    feasible = [
        hold(pt, 1 if i % 2 == 0 else -1, 0.015, SECTORS[i // 2])
        for i, pt in enumerate(range(1, 13))
    ]
    res = build_joint(feasible, [])
    for h in feasible:
        assert res.y[h.permaticker] == pytest.approx(h.c, abs=1e-7), "no gratuitous reduction"
    assert_constraints(res, feasible, [])


def test_14_genuine_joint_R0_Q0_is_accepted_without_error():
    hs = [hold(1, 1, 0.015, "XLK"), hold(2, 1, 0.015, "XLK")]
    res = build_joint(hs, [])
    assert res.outcome == VALID_ZERO_ENTRY_OUTCOME
    assert res.diagnostics["R_star"] == pytest.approx(0.0, abs=1e-9)
    assert res.diagnostics["Q_star"] == pytest.approx(0.0, abs=1e-9)


def test_15_degenerate_lp_optima_produce_the_same_unique_stage3_allocation():
    """Identical candidates give the LP many optimal vertices. Stage 3 is strictly convex,
    so the ALLOCATION is unique regardless of which vertex HiGHS lands on."""
    cs = []
    pt = 1
    for s in SECTORS[:6]:
        for _ in range(3):                  # three IDENTICAL candidates per side/sector
            cs.append(cand(pt, 1, 0.010, s))
            pt += 1
            cs.append(cand(pt, -1, 0.010, s))
            pt += 1
    runs = [build_joint([], list(cs)) for _ in range(3)]
    for r in runs[1:]:
        assert r.diagnostics["determinism_hash"] == runs[0].diagnostics["determinism_hash"]
    # identical candidates must receive identical weight -- no arbitrary vertex tie-break
    first = runs[0]
    for s in SECTORS[:6]:
        ws = [round(w, 12) for pt_, w in first.x.items()
              if next(c for c in cs if c.permaticker == pt_).sector == s
              and next(c for c in cs if c.permaticker == pt_).d == 1]
        assert len(set(ws)) == 1, f"identical candidates in {s} got different weights: {ws}"


def test_16_stage3_output_independent_of_the_vertex_highs_returns():
    cs = diversified(6)
    fwd = build_joint([], list(cs))
    rev = build_joint([], list(reversed(cs)))
    assert fwd.x == rev.x
    assert fwd.diagnostics["determinism_hash"] == rev.diagnostics["determinism_hash"]


def test_17_candidate_and_existing_shuffle_produce_byte_identical_orders():
    hs = [hold(1, 1, 0.010, "XLK"), hold(2, -1, 0.010, "XLF"), hold(3, 1, 0.008, "XLV")]
    cs = diversified(6, start=300)
    base = build_joint(list(hs), list(cs))
    for seed in range(5):
        rng = np.random.default_rng(seed)
        h2, c2 = list(hs), list(cs)
        rng.shuffle(h2)
        rng.shuffle(c2)
        r = build_joint(h2, c2)
        assert r.diagnostics["determinism_hash"] == base.diagnostics["determinism_hash"]
        assert r.y == base.y and r.x == base.x


def test_18_no_existing_position_increases():
    hs = [hold(1, 1, 0.004, "XLK"), hold(2, -1, 0.004, "XLF")]
    cs = diversified(6, start=300)
    res = build_joint(hs, cs)
    for h in hs:
        assert res.y[h.permaticker] <= h.c + TOL, "downward-only violated"


def test_19_no_new_candidate_exceeds_its_registered_starting_weight():
    cs = diversified(6)
    res = build_joint([], cs)
    by = {c.permaticker: c.w for c in cs}
    for pt, w in res.x.items():
        assert w <= by[pt] + TOL
        assert w <= NEW_ENTRY_CAP + TOL


def test_20_new_entries_remain_exactly_side_matched():
    hs = [hold(1, 1, 0.012, "XLK")]
    cs = diversified(6, start=300)
    res = build_joint(hs, cs)
    by = {c.permaticker: c for c in cs}
    lo = sum(w for pt, w in res.x.items() if by[pt].d == 1)
    sh = sum(w for pt, w in res.x.items() if by[pt].d == -1)
    assert lo == pytest.approx(sh, abs=1e-9), "new entries must be dollar-neutral"


def test_21_combined_drift_band_on_the_complete_post_trade_portfolio():
    """The band applies to the COMPLETE book. The solver may retain an existing imbalance
    when new orders bring the combined book inside the band."""
    hs = [hold(1, 1, 0.010, "XLK"), hold(2, 1, 0.010, "XLV")]   # long-only: imbalanced
    cs = diversified(6, start=300)
    res = build_joint(hs, cs)
    rows = book(res, hs, cs)
    G = sum(w for _s, w, _d, _b in rows)
    net = sum(d * w for _s, w, d, _b in rows)
    assert abs(net) <= DRIFT_BAND * G + TOL


def test_22_fixed_nontradable_position_creates_execution_constrained_infeasible():
    """A FIXED coupling breach -- not a solver failure and not an ordinary Q*=0."""
    hs = [hold(1, 1, 0.02, "XLK", tradable=False)]
    res = build_joint(hs, diversified(6, start=300))
    assert res.outcome == EXECUTION_CONSTRAINED_INFEASIBLE
    assert res.x == {} and res.y == {}
    assert res.diagnostics["unavoidable_coupling_breaches"]
    assert res.diagnostics["fixed_reasons"][1] == NO_EXECUTABLE_OPEN


def test_23_solver_failure_stops_the_run_and_never_becomes_cash(monkeypatch):
    class Bad:
        success = False
        status = 4                       # numerical difficulties
        message = "simulated numerical failure"
        x = None
        fun = None

    monkeypatch.setattr(jp, "linprog", lambda *a, **k: Bad())
    with pytest.raises(InvalidRun, match="LP status 4"):
        build_joint([], diversified(6))


def test_24_residuals_pass_and_iterative_scaling_stays_rejected():
    hs = [hold(1, 1, 0.012, "XLK"), hold(2, -1, 0.009, "XLF")]
    cs = diversified(6, start=300)
    res = build_joint(hs, cs)
    s3 = res.diagnostics["stage3"]
    assert s3["primal_residual"] <= jp.PRIMAL_RESIDUAL_MAX
    assert s3["dual_residual"] <= jp.DUAL_RESIDUAL_MAX
    assert s3["stationarity_residual"] <= jp.STATIONARITY_RESIDUAL_MAX
    assert s3["complementarity_residual"] <= jp.COMPLEMENTARITY_RESIDUAL_MAX
    assert s3["kkt_residual"] <= jp.KKT_RESIDUAL_MAX
    assert s3["hessian_condition_number"] <= jp.HESSIAN_CONDITION_MAX
    # REGRESSION LOCK: the construction is a single simultaneous solve, never an
    # iterative per-sector down-scaling loop (which provably does not converge).
    src = __import__("inspect").getsource(jp)
    assert "while" not in src, "an iterative scaling loop must never reappear"


# ======================================================================================
# THE 3 rev-3 FIXTURES (D1, D2, D3)
# ======================================================================================
def test_25_existing_position_over_entry_cap_is_a_diagnostic_and_never_halts(caplog):
    """[D1] The 1.5% limit is a NEW-ENTRY sizing cap. An existing holding above it is
    fully in the accounting and coupling constraints, is never increased, is REPORTED,
    and does not by itself halt the optimization -- nor is it trimmed merely for being
    above the cap."""
    # The book is sector-neutral within XLK (long 2% + short 2%), and the new candidates
    # occupy six DISJOINT sectors -- so no coupling constraint binds on XLK. Anything that
    # trimmed these holdings could only be the entry cap, which must not.
    hs = [hold(1, 1, 0.020, "XLK", entry=0.015), hold(2, -1, 0.020, "XLK", entry=0.015)]
    cs = diversified(6, start=300, offset=1)
    res = build_joint(hs, cs)

    assert res.outcome != EXECUTION_CONSTRAINED_INFEASIBLE, "the entry cap must never halt a day"
    assert res.x, "the rest of the book must still trade"

    recs = {r["permaticker"]: r for r in res.diagnostics["existing_position_over_entry_cap"]}
    assert set(recs) == {1, 2}
    for pt in (1, 2):
        assert recs[pt]["current_weight"] == 0.020
        assert recs[pt]["entry_weight"] == 0.015
        assert recs[pt]["amount_above_1_5pct"] == pytest.approx(0.005)
        assert recs[pt]["tradable_at_open"] is True

    # NOT trimmed to 1.5% -- retained in full, because no coupling constraint requires
    # a reduction. This is the whole point of the D1 ruling.
    assert res.y[1] == pytest.approx(0.020, abs=1e-7)
    assert res.y[2] == pytest.approx(0.020, abs=1e-7)
    for pt in (1, 2):
        assert recs[pt]["reduction_due_to_other_constraints"] == pytest.approx(0.0, abs=1e-7)

    # and it contributes fully to the constraints
    assert_constraints(res, hs, cs)
    assert res.diagnostics["sector_gross"]["XLK"] >= 0.04 - TOL


def test_25b_over_cap_position_IS_reduced_when_coupling_requires_it():
    """The converse half: reduction happens for a COUPLING reason, never for the cap."""
    hs = [hold(1, 1, 0.020, "XLK", entry=0.015)]        # unhedged -> sector-net binds
    cs = diversified(6, start=300, offset=1)            # disjoint sectors: only net binds
    res = build_joint(hs, cs)
    recs = {r["permaticker"]: r for r in res.diagnostics["existing_position_over_entry_cap"]}
    assert recs[1]["reduction_due_to_other_constraints"] > 0
    assert res.outcome != EXECUTION_CONSTRAINED_INFEASIBLE
    assert_constraints(res, hs, cs)


def test_26_below_floor_tolerance_warns_and_stops_and_1e10_is_verified_honored():
    """[D2] BOTH halves are required.

    (a) A below-floor tolerance (<1e-10) emits a warning and, under the frozen policy,
        STOPS the run -- it must never silently revert to the 1e-7 default while still
        reporting success=True.
    (b) The accepted runtime VERIFIES 1e-10 was honored rather than merely requesting it.
    """
    lp = dict(c=[-1.0, -1.0], A_ub=[[1.0, 1.0]], b_ub=[1.0],
              bounds=[(0.0, 1.0), (0.0, 1.0)], method="highs-ds")

    # (a) below the floor -> warns -> fatal under the frozen policy
    bad = dict(jp.LP_OPTIONS)
    bad["primal_feasibility_tolerance"] = 1e-11
    bad["dual_feasibility_tolerance"] = 1e-11
    with pytest.raises(Warning):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            linprog(**lp, options=bad)

    # ...and the silent-fallback it would otherwise permit is real: success DESPITE
    # the option being rejected. This is what the fatal policy exists to catch.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res_bad = linprog(**lp, options=bad)
    assert res_bad.success and res_bad.status == 0
    assert caught, "the silent-fallback detector is inoperative"

    # (b) the registered value is accepted SILENTLY -> proof it reached HiGHS
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res_ok = linprog(**lp, options=jp.LP_OPTIONS)
    assert res_ok.success and res_ok.status == 0
    assert not caught, "1e-10 must be accepted without warning, or it was NOT honored"
    assert jp.LP_OPTIONS["primal_feasibility_tolerance"] == 1e-10
    assert jp.LP_OPTIONS["dual_feasibility_tolerance"] == 1e-10


def test_27_inclusion_floor_carries_below_floor_exposure_as_fixed_never_deleted():
    """[D3] A below-floor existing exposure stays FIXED and fully accounted; it never
    enters the Hessian and can never increase. A below-floor candidate is omitted."""
    tiny = 1e-12
    hs = [
        hold(1, 1, tiny, "XLK"),                       # below the floor
        hold(2, 1, 0.010, "XLV"),
        hold(3, -1, 0.010, "XLF"),
    ]
    cs = diversified(6, start=300) + [cand(999, 1, tiny, "XLE")]
    res = build_joint(hs, cs)

    assert res.diagnostics["fixed_reasons"][1] == BELOW_NUMERICAL_INCLUSION_FLOOR
    assert 1 not in res.y, "a below-floor position must not be a decision variable"
    assert 999 not in res.x, "a below-floor candidate must create no order"

    em = res.diagnostics["excluded_mass"]
    assert em["below_floor_existing_count"] == 1
    assert em["below_floor_existing_total_weight"] == pytest.approx(tiny)
    assert em["below_floor_candidate_count"] == 1
    assert em["below_floor_candidate_total_weight"] == pytest.approx(tiny)

    # NEVER deleted from the accounting: it is still in gross and in its sector.
    assert res.diagnostics["sector_gross"].get("XLK", 0.0) >= tiny
    assert res.diagnostics["total_gross"] >= tiny

    # the Hessian never sees it -> conditioning stays sane
    assert res.diagnostics["stage3"]["hessian_condition_number"] <= jp.HESSIAN_CONDITION_MAX


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
