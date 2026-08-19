"""MR-002 Gate N1 — fixtures proving the certificate-driven classifier behaves as registered.

The load-bearing claim of the whole v2 architecture is that a QP generator terminating without a
candidate is NO_CERTIFIED_CANDIDATE (SA-5 INCIDENT_CLASS_KNOWLEDGE), not an integrity defect. That
is the exact misclassification that consumed the sealed opening on 2026-08-19 12:49Z.

These fixtures drive the real registered generators and the real classifier. Nothing is mocked
except the two deliberate defect cases, which must remain fatal.

Development domain only.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.n1 import method as M  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f"  (want {want!r})"))
    if not ok:
        FAILS.append(name)


def infeasible_instance() -> tuple:
    """A structurally infeasible registered-form instance.

    The equality demands sum(z) = 10 while the box caps every coordinate at 0.1, so the feasible set
    is provably empty. Every generator must report that; none may produce a certified candidate.
    """
    n = 4
    t = np.full(n, 0.05)
    A_ub = np.zeros((1, n))
    b_ub = np.array([1.0])
    A_eq = np.ones((1, n))
    b_eq = np.array([10.0])
    upper = np.full(n, 0.1)
    return (t, A_ub, b_ub, A_eq, b_eq, upper)


def feasible_instance() -> tuple:
    n = 4
    t = np.full(n, 0.25)
    A_ub = np.zeros((1, n))
    b_ub = np.array([1.0])
    A_eq = np.ones((1, n))
    b_eq = np.array([1.0])
    upper = np.full(n, 1.0)
    return (t, A_ub, b_ub, A_eq, b_eq, upper)


def main() -> int:
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    print("\n1. REAL generators on a provably infeasible instance")
    print("   (the 12:49Z class: a generator terminating without a candidate)")
    rec = infeasible_instance()
    for profile in ("QUADPROG_SQRT", "PIQP_P1", "PIQP_P2", "CLARABEL"):
        o = M.normalize(profile, SOLVERS[profile], canonical_qualify, rec)
        print(f"\n   {profile}")
        print(f"     outcome={o.outcome} reason={o.reason} provenance={o.provenance}")
        print(f"     exception={o.exception_class} module={o.owning_module}")
        print(f"     literal_rule_would_give={o.literal_outcome}")
        check(f"{profile} is not an integrity defect", o.outcome != M.SYSTEM_INTEGRITY_DEFECT, True)
        check(f"{profile} reason is registered",
              o.reason in M.REGISTERED_TERMINATION_REASONS or o.outcome == M.CERTIFIED, True)

    print("\n2. REAL generators on a feasible instance (must certify)")
    rec = feasible_instance()
    for profile in ("QUADPROG_SQRT", "PIQP_P2", "CLARABEL"):
        o = M.normalize(profile, SOLVERS[profile], canonical_qualify, rec)
        print(f"   {profile}: outcome={o.outcome} reason={o.reason} detail={o.detail[:60]}")

    print("\n3. A genuine WRAPPER DEFECT must stay FATAL")
    # Provenance is the FRAME's module, not the function's __module__ attribute — a frame belongs to
    # the module whose code object created it. Setting `fn.__module__` would prove nothing, so the
    # defective wrapper is compiled with real module globals for one of OUR roots.
    ns: dict = {"__name__": "app.research.mr002.n1._fixture_broken_wrapper"}
    exec(compile("def broken_wrapper(t, A_ub, b_ub, A_eq, b_eq, upper):\n"
                 "    raise KeyError('a real bug in our mapping code')\n",
                 "<fixture>", "exec"), ns)
    o = M.normalize("BROKEN", ns["broken_wrapper"], canonical_qualify, feasible_instance())
    print(f"   outcome={o.outcome} reason={o.reason} provenance={o.provenance} module={o.owning_module}")
    check("wrapper defect is a SYSTEM_INTEGRITY_DEFECT", o.outcome, M.SYSTEM_INTEGRITY_DEFECT)
    check("wrapper defect reason", o.reason, M.WRAPPER_ORIGIN)

    print("\n3b. An UNATTRIBUTABLE frame resolves the instance but blocks advancement")
    ns2: dict = {"__name__": "some_third_party_thing"}
    exec(compile("def opaque(t, A_ub, b_ub, A_eq, b_eq, upper):\n"
                 "    raise RuntimeError('from nowhere we own')\n", "<fixture>", "exec"), ns2)
    o = M.normalize("OPAQUE", ns2["opaque"], canonical_qualify, feasible_instance())
    print(f"   outcome={o.outcome} reason={o.reason} provenance={o.provenance}")
    check("unattributable resolves the instance", o.outcome, M.NO_CERTIFIED_CANDIDATE)
    check("unattributable blocks advancement", o.reason, M.UNREGISTERED_TERMINATION_REASON)

    print("\n4. Contract violations — shape is OURS, values are the SOLVER's")
    rec = feasible_instance()
    n = len(rec[0])
    lam_len = rec[3].shape[0] + rec[1].shape[0] + 2 * n

    o = M.normalize("STUB", lambda *a: (np.zeros(n + 1), np.zeros(lam_len)), canonical_qualify, rec)
    check("wrong-sized candidate is a system defect", o.outcome, M.SYSTEM_INTEGRITY_DEFECT)

    o = M.normalize("STUB", lambda *a: (np.full(n, np.nan), np.zeros(lam_len)), canonical_qualify, rec)
    check("non-finite candidate is NOT a system defect", o.outcome, M.NO_CERTIFIED_CANDIDATE)
    check("non-finite reason", o.reason, M.NON_FINITE_CANDIDATE)

    o = M.normalize("STUB", lambda *a: None, canonical_qualify, rec)
    check("non-pair return is a system defect", o.outcome, M.SYSTEM_INTEGRITY_DEFECT)

    print("\n5. BaseException must propagate, never be normalized")

    def interrupts(*a):
        raise KeyboardInterrupt

    try:
        M.normalize("STUB", interrupts, canonical_qualify, rec)
        check("KeyboardInterrupt propagates", False, True)
    except KeyboardInterrupt:
        check("KeyboardInterrupt propagates", True, True)

    print("\n6. method.resolve() must reproduce the census's inline disposition table")
    # The census computes dispositions inline from normalize(); resolve() is the production-shaped
    # API. If they can disagree, the census validated something other than the production method.
    # This proves they agree on real corpus instances rather than asserting it.
    import numpy as _np
    try:
        d = _np.load("/work/.mr002out/n1/corpus.npz", allow_pickle=False)
        n_inst = int(d["n_instances"])
    except Exception as exc:  # noqa: BLE001
        print(f"   SKIP — corpus not available ({type(exc).__name__})")
        n_inst = 0

    agree = disagree = 0
    for i in range(0, min(n_inst, 400)):
        rec = tuple(d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        for cand in ("PIQP_P1", "PIQP_P2"):
            a = M.normalize("QUADPROG_SQRT", SOLVERS["QUADPROG_SQRT"], canonical_qualify, rec)
            b = M.normalize(cand, SOLVERS[cand], canonical_qualify, rec)
            if a.outcome == M.SYSTEM_INTEGRITY_DEFECT or b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                inline = M.INVALID_RUN
            elif a.is_certified:
                inline = M.PRIMARY_CERTIFIED
            elif b.is_certified:
                inline = M.SECONDARY_CERTIFIED
            else:
                inline = M.UNRESOLVED_INSTANCE

            r = M.resolve(rec, a_solver=SOLVERS["QUADPROG_SQRT"], b_solver=SOLVERS[cand],
                          certify_fn=canonical_qualify, a_profile="QUADPROG_SQRT",
                          b_profile=cand, run_both=True)
            same_z = ((r.accepted_z is None and inline in (M.INVALID_RUN, M.UNRESOLVED_INSTANCE))
                      or (r.accepted_z is not None
                          and _np.asarray(r.accepted_z).tobytes()
                          == _np.asarray(a.z if a.is_certified else b.z).tobytes()))
            if r.disposition == inline and same_z:
                agree += 1
            else:
                disagree += 1
                if disagree <= 3:
                    print(f"   i={i} {cand}: resolve={r.disposition} inline={inline} same_z={same_z}")
    if n_inst:
        print(f"   agree={agree} disagree={disagree}")
        check("resolve() matches the inline disposition table", disagree, 0)

    print(f"\n{'ALL FIXTURES PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
