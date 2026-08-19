"""MR-002 Gate N1 — the v2 Stage-3 seam, for the governed development replay.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af,
as adjudicated by MR002_N1_AdjudicationAddendum_v1.0.

The counterpart of `app.research.mr002.stage3_route` for the certificate-driven v2 method. It routes
`joint_portfolio._solve_qp` through `n1.method.resolve` in PRODUCTION shape — B is invoked only when
A produces no certified candidate — so the replay exercises the method as it would actually run.

It is the seam and nothing more. It does NOT edit `joint_portfolio` bytes, change any numerical
parameter, tolerance, epsilon or profile, add a third attempt, jitter, or per-instance routing.

⚠ The emitted `info` dict mirrors `stage3_route`'s shape EXACTLY, including which keys it omits.
`mr002_development_run` reads `kkt_residual` and `hessian_condition_number` off it with `.get(...)`
defaults, so adding keys the v1 seam does not emit would make `max_kkt` differ between the two
replays and show up in the differential as an economic difference that is really a reporting
difference. The differential must reflect Stage-3 behaviour, not seam bookkeeping.
"""
from __future__ import annotations

from contextlib import contextmanager

import numpy as np

from app.research.mr002 import joint_portfolio as jp
from app.research.mr002.n1 import method as M

A_PROFILE = "QUADPROG_SQRT"


class Stage3StopV2(RuntimeError):
    """A terminal v2 disposition. Per the frozen stop rule this ends the run; it is never converted
    into a no-trade day, retried, or routed to a third generator."""

    def __init__(self, resolution: M.Resolution) -> None:
        super().__init__(f"{resolution.disposition}: {resolution.detail}")
        self.resolution = resolution
        self.disposition = resolution.disposition


@contextmanager
def routed_v2(census: list, *, candidate: str, solvers, certify_fn):
    """Route Stage-3 through the v2 certificate-driven method for the duration of the block.

    `census` receives one summary dict per Stage-3 invocation, so every invocation reconciles.
    """
    original = jp._solve_qp

    def _routed(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
        # Preserve the registered pre-solve integrity gate exactly as the frozen path applies it.
        jp._assert_registered_solver()
        t = np.asarray(targets, dtype=float)
        n = len(t)
        kappa = float(np.linalg.cond(np.diag(H_diag))) if n else 1.0
        if kappa > jp.HESSIAN_CONDITION_MAX:
            raise jp.InvalidRun(
                f"hessian_condition_number kappa(H)={kappa:.3e} > {jp.HESSIAN_CONDITION_MAX:.0e}"
            )

        rec = (t, A_ub, b_ub, A_eq, b_eq, upper)
        res = M.resolve(rec, a_solver=solvers[A_PROFILE], b_solver=solvers[candidate],
                        certify_fn=certify_fn, a_profile=A_PROFILE, b_profile=candidate,
                        run_both=False)

        census.append({
            "disposition": res.disposition,
            "accepted_by": res.accepted_by,
            "A_outcome": res.a.outcome,
            "A_reason": res.a.reason,
            "A_provenance": res.a.provenance,
            "B_outcome": None if res.b is None else res.b.outcome,
            "B_reason": None if res.b is None else res.b.reason,
            "B_provenance": None if res.b is None else res.b.provenance,
            "fallback_invoked": res.b is not None,
            "hessian_condition_number": kappa,
            "n": n,
        })

        if res.accepted_z is None:
            raise Stage3StopV2(res)

        z = np.asarray(res.accepted_z, dtype=float)
        info = {
            "stage3_formulation": res.accepted_by,
            "stage3_disposition": res.disposition,
            "stage3_cascade": census[-1],
            "raw_exception_class": res.a.exception_class,
            "raw_exception_message": None,
            "feasibility_probe_status": None,
            "scaled_solver_status": None if res.b is None else res.b.reason,
            "raw_coordinate_objective": float(np.sum((z - t) ** 2 / t)) if n else 0.0,
            "hessian_condition_number": kappa,
        }
        return z, info

    jp._solve_qp = _routed
    try:
        yield census
    finally:
        jp._solve_qp = original


def census_summary(census: list) -> dict:
    """Reconcile every Stage-3 invocation to a registered v2 disposition."""
    by: dict[str, int] = {}
    by_accept: dict[str, int] = {}
    for row in census:
        by[row["disposition"]] = by.get(row["disposition"], 0) + 1
        by_accept[str(row.get("accepted_by"))] = by_accept.get(str(row.get("accepted_by")), 0) + 1
    total = len(census)
    known = sum(by.get(d, 0) for d in (M.PRIMARY_CERTIFIED, M.SECONDARY_CERTIFIED,
                                       M.UNRESOLVED_INSTANCE, M.INVALID_RUN))
    return {
        "invocations": total,
        "by_disposition": by,
        "by_accepted_by": by_accept,
        "fallback_invoked": sum(1 for r in census if r["fallback_invoked"]),
        "all_reconcile_to_a_registered_disposition": known == total,
        "unrecognized_outcomes": total - known,
        "stop_dispositions": (by.get(M.UNRESOLVED_INSTANCE, 0) + by.get(M.INVALID_RUN, 0)),
        "unregistered_termination_reasons": sum(
            1 for r in census
            if M.UNREGISTERED_TERMINATION_REASON in (r.get("A_reason"), r.get("B_reason"))),
    }
