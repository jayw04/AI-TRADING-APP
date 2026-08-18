"""Route `joint_portfolio` Stage-3 through the countersigned successor cascade.

The Stage-3 path bound inside `joint_portfolio._solve_qp` is the OLD cascade: RAW primary, with a
rescue keyed to one exact `quadprog` ValueError. It has no rescue path for a *certificate*
nonqualification, which is the corrupted-duals defect recorded at commit 2a31044 -- a correct
primal with corrupted duals, stationarity 5.03 against a 1e-8 limit. That defect halts the
development replay for configs A and B.

`app.research.mr002.stage3_cascade` is the countersigned successor: primary `QUADPROG_SQRT`,
falling back ONCE to `PIQP_P2`, with a single registered certifier deciding acceptance. It
classifies a certificate nonqualification as fallback-eligible, which is exactly the class the old
path could not handle.

This module is the seam and nothing more. It does NOT:
  - edit `joint_portfolio` bytes (its identity stays bound as the governing construction),
  - change any numerical parameter, tolerance, epsilon, or profile,
  - add a third attempt, jitter, per-instance routing, or eligibility by analogy,
  - broaden the old exception allowlist.

It replaces one function object at runtime, records the closed disposition of every Stage-3
invocation, and RAISES on a stop disposition so a run can never continue past an unresolved
numerical failure.

⚠ Running this against any corpus requires the execution countersignature that
`stage3_cascade`'s own header demands. `install()` refuses unless the caller passes the
countersignature identity it expects, so the seam cannot be used casually.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np

from app.research.mr002 import joint_portfolio as jp
from app.research.mr002 import stage3_cascade as sc

# The execution countersignature this seam is bound to. `install` refuses without it.
EXECUTION_COUNTERSIGNATURE_ID = "MR002_Stage3ExecutionCountersignature_v1.0"


class Stage3Stop(RuntimeError):
    """A terminal stop disposition from the successor cascade.

    UNRESOLVED_NUMERICAL_FAILURE or INVALID_RUN. Per the owner stop rule this ends the run; it is
    never converted into a no-trade day, retried, or routed to a third solver.
    """

    def __init__(self, outcome: sc.Outcome) -> None:
        super().__init__(f"{outcome.disposition}: {outcome.detail}")
        self.outcome = outcome
        self.disposition = outcome.disposition


@contextmanager
def routed(census: list, *, countersignature: str):
    """Route Stage-3 through the successor cascade for the duration of the block.

    `census` receives one summary dict per Stage-3 invocation, so every invocation reconciles.
    """
    if countersignature != EXECUTION_COUNTERSIGNATURE_ID:
        raise RuntimeError(
            "Stage-3 routing requires the execution countersignature "
            f"{EXECUTION_COUNTERSIGNATURE_ID!r}; got {countersignature!r}. The design "
            "countersignature alone does not authorize execution."
        )

    original = jp._solve_qp

    def _routed_solve_qp(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
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
        outcome = sc.resolve_instance(rec)
        summary = outcome.summary()
        summary["hessian_condition_number"] = kappa
        summary["n"] = n
        summary["min_target"] = float(t.min()) if n else None
        census.append(summary)

        if outcome.stop:
            raise Stage3Stop(outcome)

        z = outcome.accepted_z
        if z is None:
            raise Stage3Stop(outcome)
        z = np.asarray(z, dtype=float)

        # `info` keeps the shape the frozen caller and the development census already read, with
        # the cascade's closed disposition carried alongside rather than in place of it.
        info = {
            "stage3_formulation": outcome.accepted_by,
            "stage3_disposition": outcome.disposition,
            "stage3_cascade": summary,
            "raw_exception_class": outcome.primary.code if not outcome.primary.is_qualified else None,
            "raw_exception_message": None,
            "feasibility_probe_status": None,
            "scaled_solver_status": outcome.fallback.enum if outcome.fallback else None,
            "raw_coordinate_objective": float(np.sum((z - t) ** 2 / t)) if n else 0.0,
            "hessian_condition_number": kappa,
        }
        return z, info

    jp._solve_qp = _routed_solve_qp
    try:
        yield census
    finally:
        jp._solve_qp = original


def census_summary(census: list) -> dict:
    """Reconcile every Stage-3 invocation to a registered disposition."""
    by_disposition: dict[str, int] = {}
    by_accepted_by: dict[str, int] = {}
    for row in census:
        by_disposition[row["disposition"]] = by_disposition.get(row["disposition"], 0) + 1
        key = str(row.get("accepted_by"))
        by_accepted_by[key] = by_accepted_by.get(key, 0) + 1
    total = len(census)
    known = sum(by_disposition.get(d, 0) for d in (
        sc.PRIMARY_QUALIFIED, sc.FALLBACK_QUALIFIED,
        sc.UNRESOLVED_NUMERICAL_FAILURE, sc.INVALID_RUN))
    return {
        "invocations": total,
        "by_disposition": by_disposition,
        "by_accepted_by": by_accepted_by,
        "fallback_invoked": sum(1 for r in census if r["fallback_invoked"]),
        "all_reconcile_to_a_registered_disposition": known == total,
        "unrecognized_outcomes": total - known,
        "stop_dispositions": (by_disposition.get(sc.UNRESOLVED_NUMERICAL_FAILURE, 0)
                              + by_disposition.get(sc.INVALID_RUN, 0)),
    }
