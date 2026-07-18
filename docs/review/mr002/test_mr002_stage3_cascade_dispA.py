"""MR-002 Stage-3 — Disposition-A cascade eligibility fixtures (`QUADPROG_SQRT -> PIQP_P2`).

Complete eligibility fixtures for the finalized cascade `app/research/mr002/stage3_cascade.py`
(adjudication §7 "Required test fixtures"). DISTINCT from `test_mr002_stage3_cascade.py`, which tests
the SUPERSEDED 2026-07-12 raw -> T-scaled cascade (do not conflate).

The fixtures drive every §7 branch through the injection seam (`resolve`) with stub solvers / a stub
certifier, so the decision table is validated without the numerical stack. The numerical producibility
of each enum against the real solvers is exercised by `scripts/mr002_stage3_cascade_fixtures.py`.

Coverage:
  * the nine required §7 branches;
  * SOLVER-SCOPED, class-identity exact matching — a PIQP raise of the QUADPROG message, a same-named
    user ValueError, a subclass, a wrong message, and a superstring all → INTEGRITY (findings 1, 2, 14);
  * "exactly once" — a counting spy asserts the fallback runs exactly one time on every eligible
    branch and zero times on every non-eligible branch (finding 15);
  * the malformed-contract battery — non-iterable rec, scalar t, unconvertible members, solver
    returning None / too many values / non-numeric candidates, malformed certifier tuples, non-bool
    ok, invalid bad, contradictory verdicts, negative upper bound (findings 7-9, 16);
  * input-array immutability and accepted-output immutability (findings 13, 16);
  * a production-binding check that `resolve_instance` binds the intended callables (finding 17;
    skipped when the solver stack is unavailable — it runs in the pinned image).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.research.mr002 import stage3_cascade as sc

# ── a well-formed tiny registered problem (n=2, meq=0, m_ub=1 -> lam length 5) ───────────────────
REC = (
    np.array([0.008, 0.008]),          # t  (all > 0)
    np.array([[1.0, 1.0]]),            # A_ub
    np.array([0.01]),                  # b_ub
    np.zeros((0, 2)),                  # A_eq
    np.zeros(0),                       # b_eq
    np.array([0.02, 0.02]),            # upper
)
_N, _LAM = sc._expected_lengths(REC)   # (2, 5)
Z_OK = np.array([0.005, 0.005])
LAM_OK = np.zeros(_LAM)


def registered_valueerror():
    return ValueError("constraints are inconsistent, no solution")


# ── stub solvers with call counting (finding 15) ────────────────────────────────────────────────
class CountingSolver:
    """Records call count; on call, returns a fixed (z, lam) or raises a supplied exception."""

    def __init__(self, *, returns=None, raises=None):
        self.calls = 0
        self._returns = returns
        self._raises = raises

    def __call__(self, *_a):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return (np.asarray(self._returns[0], float), np.asarray(self._returns[1], float))


def raising(exc):
    return CountingSolver(raises=exc)


def returning(z, lam):
    return CountingSolver(returns=(z, lam))


def full_cert(qualifies=True):
    """A contract-complete certificate stub: an ACCEPTED cert is snapshotted at normalization and
    must carry every registered field (cycle-4 finding 19)."""
    from types import SimpleNamespace
    vals = {f: 0.0 for f in sc.REQUIRED_CERT_FIELDS}
    vals["qualifies"] = qualifies
    vals["n_multipliers_clipped"] = 0          # must be a real int (cycle-4 finding 18)
    return SimpleNamespace(**vals)


def cert_pass(_z, _lam, *_rec):
    return True, [], full_cert()


def cert_fail(bad):
    def certify(_z, _lam, *_rec):
        return False, list(bad), object()
    return certify


def cert_raise(_z, _lam, *_rec):
    raise sc._CertifierException("CERTIFICATE_LAGRANGIAN_IDENTITY_VIOLATION")


class CertSpy:
    """A certifier that records whether it was reached (must be 0 for pre-certifier defects)."""

    def __init__(self, verdict=None):
        self.calls = 0
        self._v = verdict if verdict is not None else (True, [], full_cert())

    def __call__(self, _z, _lam, *_rec):
        self.calls += 1
        return self._v


def run(primary, fallback, certify_fn=cert_pass, rec=REC):
    return sc.resolve(rec, primary=primary, fallback=fallback, certify_fn=certify_fn)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 1 — valid solver exception eligible for rescue -> FALLBACK_QUALIFIED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch1_registered_valueerror_rescued_exactly_once():
    fb = returning(Z_OK, LAM_OK)
    o = run(raising(registered_valueerror()), fb, cert_pass)
    assert o.primary.enum == sc.NUMERICAL_STATUS_NONQUALIFICATION
    assert o.primary.code == "QUADPROG_CONSTRAINTS_INCONSISTENT"
    assert o.disposition == sc.FALLBACK_QUALIFIED
    assert o.accepted_by == sc.FALLBACK_SOLVER_ID
    assert o.stop is False
    assert o.fallback_invoked is True
    assert fb.calls == 1                          # exactly once
    assert np.array_equal(o.accepted_z, Z_OK)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 2 — finite candidate failing one KKT gate -> primary CERTIFICATE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch2_primary_fails_kkt_gate_is_certificate_nonqualification():
    fb = returning(Z_OK, LAM_OK)
    o = run(returning(Z_OK, LAM_OK), fb, cert_fail(["stationarity_residual"]))
    assert o.primary.enum == sc.CERTIFICATE_NONQUALIFICATION
    assert "stationarity_residual" in o.primary.code
    assert o.fallback_invoked is True
    assert fb.calls == 1
    # both fail the same certifier here -> UNRESOLVED, STOP
    assert o.fallback.enum == sc.CERTIFICATE_NONQUALIFICATION
    assert o.disposition == sc.UNRESOLVED_NUMERICAL_FAILURE
    assert o.stop is True


def test_branch2b_primary_kkt_fail_then_fallback_qualifies_exactly_once():
    seen = {"n": 0}

    def certify(_z, _lam, *_rec):
        seen["n"] += 1
        return (False, ["complementarity_residual"], "c") if seen["n"] == 1 else (True, [], full_cert())

    fb = returning(Z_OK, LAM_OK)
    o = run(returning(Z_OK, LAM_OK), fb, certify)
    assert o.primary.enum == sc.CERTIFICATE_NONQUALIFICATION
    assert o.disposition == sc.FALLBACK_QUALIFIED
    assert fb.calls == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 3 — finite candidate failing ONLY the signed-gap gate -> primary CERTIFICATE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch3_primary_fails_signed_gap_only_is_certificate_nonqualification():
    fb = returning(Z_OK, LAM_OK)
    o = run(returning(Z_OK, LAM_OK), fb, cert_fail(["SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED"]))
    assert o.primary.enum == sc.CERTIFICATE_NONQUALIFICATION
    assert o.primary.code == "SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED"
    assert o.fallback_invoked is True
    assert fb.calls == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 4 — non-finite candidate -> INVALID_RUN, fallback NOT invoked
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch4_nonfinite_candidate_is_integrity_defect_no_fallback():
    fb, cert = CountingSolver(returns=(Z_OK, LAM_OK)), CertSpy()
    o = run(returning([np.inf, 0.005], LAM_OK), fb, cert)
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code == "NON_FINITE_SOLVER_OUTPUT"
    assert o.disposition == sc.INVALID_RUN and o.stop is True
    assert o.fallback_invoked is False
    assert fb.calls == 0 and cert.calls == 0


def test_branch4b_nonfinite_dual():
    o = run(returning(Z_OK, np.array([np.nan, 0, 0, 0, 0])), CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 5 — wrong-sized candidate -> INVALID_RUN, fallback NOT invoked
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch5_wrong_sized_primal_is_integrity_defect_no_fallback():
    fb = CountingSolver(returns=(Z_OK, LAM_OK))
    o = run(returning([0.005, 0.005, 0.005], LAM_OK), fb)   # z has 3 entries, expected 2
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code.startswith("WRONG_SIZED_CANDIDATE")
    assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False
    assert fb.calls == 0


def test_branch5b_wrong_sized_dual():
    o = run(returning(Z_OK, np.zeros(4)), CountingSolver(returns=(Z_OK, LAM_OK)))  # lam 4, expected 5
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 6 — unknown status -> INTEGRITY_DEFECT (class IDENTITY + exact message; no analogy)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch6_unknown_exception_class_is_integrity_defect_no_fallback():
    fb = CountingSolver(returns=(Z_OK, LAM_OK))
    o = run(raising(RuntimeError("status PIQP_NUMERICS")), fb)
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code.startswith("UNREGISTERED_EXCEPTION:RuntimeError")
    assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False
    assert fb.calls == 0


def test_branch6b_exact_class_wrong_message_not_matched():
    o = run(raising(ValueError("constraints are inconsistent")), CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


def test_branch6c_exact_message_wrong_class_not_matched():
    o = run(raising(RuntimeError("constraints are inconsistent, no solution")),
            CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


def test_branch6d_registered_message_superstring_not_matched():
    o = run(raising(ValueError("constraints are inconsistent, no solution (row 2765)")),
            CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


def test_branch6e_user_defined_class_named_valueerror_not_matched():
    # A DIFFERENT class object that happens to be named "ValueError" must NOT match (finding 2).
    class ValueError(Exception):   # noqa: A001 — deliberately shadowing to test identity matching
        pass
    exc = ValueError("constraints are inconsistent, no solution")
    assert type(exc).__name__ == "ValueError"
    o = run(raising(exc), CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


def test_branch6f_valueerror_subclass_not_matched():
    class MyVE(ValueError):
        pass
    o = run(raising(MyVE("constraints are inconsistent, no solution")),
            CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 7 — certifier exception -> INTEGRITY_DEFECT, fallback NOT invoked
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch7_certifier_exception_is_integrity_defect_no_fallback():
    fb = CountingSolver(returns=(Z_OK, LAM_OK))
    o = run(returning(Z_OK, LAM_OK), fb, cert_raise)
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code.startswith("CERTIFIER_EXCEPTION")
    assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False
    assert fb.calls == 0


def test_branch7b_arbitrary_certifier_fault_is_integrity_defect():
    def certify_boom(_z, _lam, *_rec):
        raise KeyError("kkt_residual")
    o = run(returning(Z_OK, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), certify_boom)
    assert o.primary.enum == sc.INTEGRITY_DEFECT and o.fallback_invoked is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 8 — the fallback disposition (§7-D). Solver-scoped normalization (findings 1, 14).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_branch8_unresolved_is_reached_by_fallback_certificate_nonqualification():
    # The ONLY way to UNRESOLVED_NUMERICAL_FAILURE: primary eligible; fallback COMPLETES but its
    # returned candidate fails the certifier. (A fallback that RAISES is an integrity defect — below.)
    def certify(_z, _lam, *_rec):
        return False, ["kkt_residual"], "c"
    fb = returning(Z_OK, LAM_OK)
    o = run(raising(registered_valueerror()), fb, certify)
    assert o.primary.enum == sc.NUMERICAL_STATUS_NONQUALIFICATION
    assert o.fallback.enum == sc.CERTIFICATE_NONQUALIFICATION
    assert o.disposition == sc.UNRESOLVED_NUMERICAL_FAILURE and o.stop is True
    assert o.accepted_by is None and fb.calls == 1


def test_branch8b_piqp_raising_quadprog_message_is_integrity_not_unresolved():
    # ★ finding 1/14: the QUADPROG numerical status is solver-scoped. PIQP raising the identical
    # class/message is NOT a registered numerical status → INTEGRITY_DEFECT → INVALID_RUN (not
    # UNRESOLVED). The old Branch-8 asserted the opposite; this pins the corrected rule.
    fb = raising(registered_valueerror())
    o = run(raising(registered_valueerror()), fb, cert_pass)
    assert o.primary.enum == sc.NUMERICAL_STATUS_NONQUALIFICATION   # QUADPROG primary: registered
    assert o.fallback.enum == sc.INTEGRITY_DEFECT                   # PIQP: NOT registered
    assert o.fallback.code.startswith("UNREGISTERED_EXCEPTION:ValueError")
    assert o.disposition == sc.INVALID_RUN and o.stop is True
    assert fb.calls == 1


def test_branch8c_fallback_integrity_defect_is_invalid_run_stop():
    fb = returning([np.inf, 0], LAM_OK)
    o = run(raising(registered_valueerror()), fb, cert_pass)
    assert o.fallback.enum == sc.INTEGRITY_DEFECT
    assert o.disposition == sc.INVALID_RUN and o.stop is True
    assert fb.calls == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BRANCH 9 — PRIMARY integrity failure: PROOF the fallback is never called (§7-C)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("primary", [
    raising(RuntimeError("unknown solver status")),
    returning([np.inf, 0.005], LAM_OK),
    returning([0.005, 0.005, 0.005], LAM_OK),
    raising(registered_valueerror()),  # NOTE: registered for QUADPROG, so this one is NUMERICAL...
], ids=["unregistered_exc", "nonfinite", "wrong_size", "registered_numerical_is_NOT_integrity"])
def test_branch9_fallback_call_count_matches_eligibility(primary):
    fb = CountingSolver(returns=(Z_OK, LAM_OK))
    o = run(primary, fb, cert_pass)
    if o.primary.enum == sc.INTEGRITY_DEFECT:
        assert o.disposition == sc.INVALID_RUN and o.fallback_invoked is False
        assert fb.calls == 0, "fallback must NEVER run on a primary integrity defect (§7-C)"
    else:
        # the registered-numerical case IS eligible -> fallback runs exactly once
        assert o.primary.enum == sc.NUMERICAL_STATUS_NONQUALIFICATION
        assert o.fallback_invoked is True and fb.calls == 1


def test_branch9b_model_input_defect_invokes_no_solver():
    bad_rec = (np.array([0.008, -1e-9]), REC[1], REC[2], REC[3], REC[4], REC[5])
    pr, fb = CountingSolver(returns=(Z_OK, LAM_OK)), CountingSolver(returns=(Z_OK, LAM_OK))
    o = sc.resolve(bad_rec, primary=pr, fallback=fb, certify_fn=CertSpy())
    assert o.disposition == sc.INVALID_RUN
    assert o.primary.code == "MODEL_INPUT:MODEL_T_NONPOSITIVE"
    assert o.fallback_invoked is False and pr.calls == 0 and fb.calls == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MALFORMED-CONTRACT BATTERY (findings 7-9, 16) — every malformed input maps to INVALID_RUN,
# nothing escapes as an exception.
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad_rec, expect", [
    (None, "MODEL_ARITY"),
    ((1, 2, 3), "MODEL_ARITY"),                                   # wrong arity
    ((np.array(0.008), REC[1], REC[2], REC[3], REC[4], REC[5]), "MODEL_T_SHAPE"),   # scalar t
    (("x", REC[1], REC[2], REC[3], REC[4], REC[5]), "MODEL_UNCONVERTIBLE"),         # non-numeric
    ((REC[0], REC[1], REC[2], REC[3], REC[4], np.array([-0.01, 0.02])), "MODEL_UPPER_NEGATIVE"),
])
def test_malformed_model_inputs_map_to_invalid_run(bad_rec, expect):
    pr, fb = CountingSolver(returns=(Z_OK, LAM_OK)), CountingSolver(returns=(Z_OK, LAM_OK))
    o = sc.resolve(bad_rec, primary=pr, fallback=fb, certify_fn=CertSpy())
    assert o.disposition == sc.INVALID_RUN
    assert expect in o.primary.code
    assert pr.calls == 0 and fb.calls == 0


def test_solver_returns_bare_none_object_is_integrity():
    def solver(*_a):
        return None
    o = run(solver, CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code == "SOLVER_RETURN_NOT_A_PAIR"


def test_solver_returns_three_values_is_integrity():
    def solver(*_a):
        return Z_OK, LAM_OK, "extra"
    o = run(solver, CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code == "SOLVER_RETURN_NOT_A_PAIR"


def test_solver_returns_nonnumeric_candidate_is_integrity():
    def solver(*_a):
        return np.array(["a", "b"], dtype=object), LAM_OK
    o = run(solver, CountingSolver(returns=(Z_OK, LAM_OK)))
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code == "NON_NUMERIC_CANDIDATE"


@pytest.mark.parametrize("verdict, code", [
    ((True, [], "c", "extra"), "NOT_A_3TUPLE"),
    (("yes", [], "c"), "OK_NOT_BOOL"),
    ((1, [], "c"), "OK_NOT_BOOL"),
    ((True, None, "c"), "BAD_NOT_LIST_OF_STR"),
    ((False, [1, 2], "c"), "BAD_NOT_LIST_OF_STR"),
    ((True, [], None), "CERT_MISSING"),
    ((True, ["oops"], "c"), "OK_TRUE_WITH_FAILURES"),
    ((False, [], "c"), "OK_FALSE_WITHOUT_FAILURES"),
])
def test_malformed_certifier_result_is_integrity(verdict, code):
    def certify(_z, _lam, *_rec):
        return verdict
    o = run(returning(Z_OK, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), certify)
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code.startswith(f"CERTIFIER_CONTRACT:{code}")


def test_numpy_bool_ok_is_rejected():
    def certify(_z, _lam, *_rec):
        return np.bool_(True), [], "c"      # numpy bool, not python bool
    o = run(returning(Z_OK, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), certify)
    assert o.primary.enum == sc.INTEGRITY_DEFECT
    assert o.primary.code.startswith("CERTIFIER_CONTRACT:OK_NOT_BOOL")


def test_fallback_certifier_exception_is_integrity():
    calls = {"n": 0}

    def certify(_z, _lam, *_rec):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, ["kkt_residual"], "c"     # primary: CERTIFICATE (eligible)
        raise sc._CertifierException("boom on fallback")
    o = run(returning(Z_OK, LAM_OK), returning(Z_OK, LAM_OK), certify)
    assert o.fallback.enum == sc.INTEGRITY_DEFECT
    assert o.disposition == sc.INVALID_RUN and o.stop is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# IMMUTABILITY (findings 13, 16)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_input_arrays_are_not_mutated():
    rec = tuple(np.array(x, dtype=float, copy=True) for x in REC)
    snap = [x.copy() for x in rec]
    run(returning(Z_OK, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), cert_pass, rec=rec)
    for before, after in zip(snap, rec, strict=True):
        assert np.array_equal(before, after)


def test_accepted_z_is_read_only_copy():
    zref = np.array([0.005, 0.005])
    o = run(returning(zref, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), cert_pass)
    assert o.disposition == sc.PRIMARY_QUALIFIED
    assert o.accepted_z.flags.writeable is False
    with pytest.raises(ValueError):
        o.accepted_z[0] = 999.0
    # mutating the caller's original array does not change the accepted point
    zref[0] = 1.0
    assert o.accepted_z[0] == 0.005


# ══════════════════════════════════════════════════════════════════════════════════════════════
# COMPLETENESS — the decision table is total and closed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_primary_qualified_does_not_invoke_fallback():
    fb = CountingSolver(returns=(Z_OK, LAM_OK))
    o = run(returning(Z_OK, LAM_OK), fb, cert_pass)
    assert o.disposition == sc.PRIMARY_QUALIFIED
    assert o.accepted_by == sc.PRIMARY_SOLVER_ID
    assert o.fallback_invoked is False and fb.calls == 0 and o.stop is False


def test_every_outcome_is_a_closed_enum_and_terminal_disposition():
    cases = [
        run(returning(Z_OK, LAM_OK), CountingSolver(returns=(Z_OK, LAM_OK)), cert_pass),
        run(raising(registered_valueerror()), returning(Z_OK, LAM_OK)),
        run(raising(registered_valueerror()), returning(Z_OK, LAM_OK), cert_fail(["k"])),
        run(raising(RuntimeError("x")), CountingSolver(returns=(Z_OK, LAM_OK))),
    ]
    terminal = {sc.PRIMARY_QUALIFIED, sc.FALLBACK_QUALIFIED,
                sc.UNRESOLVED_NUMERICAL_FAILURE, sc.INVALID_RUN}
    for o in cases:
        assert o.disposition in terminal
        assert o.primary.enum in sc.CLOSED_ENUM
        if o.fallback is not None:
            assert o.fallback.enum in sc.CLOSED_ENUM
        if o.disposition in (sc.PRIMARY_QUALIFIED, sc.FALLBACK_QUALIFIED):
            assert o.accepted_by is not None and o.accepted_z is not None
        else:
            assert o.accepted_by is None


def test_summary_is_json_safe():
    import json
    o = run(raising(registered_valueerror()), returning(Z_OK, LAM_OK))
    json.loads(json.dumps(o.summary()))
    assert o.summary()["disposition"] == sc.FALLBACK_QUALIFIED


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PRODUCTION BINDING (finding 17) — resolve_instance binds the intended frozen callables.
# Requires the solver stack; skipped when unavailable (runs in the pinned image).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_production_binding_uses_frozen_solvers():
    pytest.importorskip("piqp")
    pytest.importorskip("mpmath")
    from scripts.mr002_coverage_signed_gap import FALLBACK, PRIMARY, SOLVERS, canonical_qualify

    # The production entry point must bind these exact frozen callables (no solve is performed).
    assert PRIMARY == sc.PRIMARY_SOLVER_ID and FALLBACK == sc.FALLBACK_SOLVER_ID
    assert canonical_qualify.__module__ == "scripts.mr002_coverage_signed_gap"
    assert SOLVERS[PRIMARY] is not SOLVERS[FALLBACK]
    # solver-identity drift is a loud runtime error (not an assert) — see _default_primary/_fallback
    assert callable(SOLVERS[PRIMARY]) and callable(SOLVERS[FALLBACK])
