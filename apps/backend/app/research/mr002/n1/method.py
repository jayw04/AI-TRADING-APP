"""MR-002 Gate N1 — the certificate-driven two-generator Stage-3 method (v2).

Implements MR002_N1_ProspectiveRegistration_v1.0, SEALED identity
7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af, §2.

THE PRINCIPLE (§2.1). A candidate is accepted because it carries a certificate, never because of
how the generator behaved. Generator exceptions, statuses and messages are RECORDED; they are never
routing inputs. This inverts v1, whose exact exception-class/message allowlist turned
`PIQP_MAX_ITER_REACHED` -- a generator terminating without a candidate -- into INTEGRITY_DEFECT ->
INVALID_RUN, consuming the sealed opening for an INTEGRITY_FAILURE with no economic verdict.

The acceptance predicate is UNCHANGED (§3.1): the single registered certifier
`mr002_coverage_signed_gap.canonical_qualify` (registered KKT LIMITS + two-sided signed Lagrangian
gap). This module changes the DISPOSITION OF FAILURES, which is what broke; it does not change what
"certified" means, which is what preserves the frozen Stage-3 economic solution.

Every numerical path is IMPORTED from its registered implementation and never re-derived.

────────────────────────────────────────────────────────────────────────────────────────────────
⚠ IMPLEMENTATION DETERMINATION — the sealed provenance rule needs one named refinement to be
   operable, and this module makes that refinement explicit and measurable.

Sealed §2.5.2 assigns provenance by walking the traceback to "the first frame belonging to a
registered ownership domain", where the solver-library domain is a frame whose module resolves
under `piqp` / `clarabel` / `quadprog` / `highspy`.

Every registered generator in this program reaches its solver through a C extension or a thin
Python wrapper of OURS, so **no such frame ever exists**:

    QUADPROG_SQRT  quadprog.solve_qp raises ValueError from the C extension; the deepest PYTHON
                   frame is `run` in scripts.mr002_coverage_signed_gap
    PIQP_P1/P2     scripts.mr002_piqp.solve_piqp raises RuntimeError(f"status {st}")
    CLARABEL       scripts.mr002_characterize_native_qp.solve_clarabel raises RuntimeError(...)

Read literally, therefore, EVERY solver termination resolves to "ours" -> SYSTEM_INTEGRITY_DEFECT
-> INVALID_RUN. No candidate could pass C2, for a reason unrelated to solver quality, and the
12:49Z failure mode would reproduce on every instance where any generator fails.

The refinement is one concept the sealed text implies but does not name: a **registered
library-boundary frame** -- a frame in our code whose sole responsibility is to invoke the library
and surface its status. An exception whose deepest Python frame is a registered boundary is
LIBRARY-owned; anything else of ours is OURS. It preserves every property the owner asked for:
structural not message-based; library termination non-fatal; wrapper defect fatal; ambiguity blocks
advancement. The boundary registry is frozen configuration on the same footing as the solver-root
list (§2.5.2).

⚠ NOTHING IS HIDDEN. Every outcome also records `literal_outcome` -- what the sealed rule would
have produced with no refinement -- so the census reports exactly how many instances the two
readings classify differently, and the owner can confirm or reject the refinement against numbers
rather than against an argument.
────────────────────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import FrameType

import numpy as np

# ── §2.2 per-generator outcome enum (closed, total) ──────────────────────────────────────────────
CERTIFIED = "CERTIFIED"
NO_CERTIFIED_CANDIDATE = "NO_CERTIFIED_CANDIDATE"
SYSTEM_INTEGRITY_DEFECT = "SYSTEM_INTEGRITY_DEFECT"
GENERATOR_OUTCOMES = (CERTIFIED, NO_CERTIFIED_CANDIDATE, SYSTEM_INTEGRITY_DEFECT)

# ── §2.5.1 registered termination reasons ────────────────────────────────────────────────────────
ITERATION_LIMIT_REACHED = "ITERATION_LIMIT_REACHED"
CONSTRAINTS_REPORTED_INCONSISTENT = "CONSTRAINTS_REPORTED_INCONSISTENT"
NUMERICAL_BREAKDOWN = "NUMERICAL_BREAKDOWN"
NON_FINITE_CANDIDATE = "NON_FINITE_CANDIDATE"
CERTIFICATE_PREDICATE_FALSE = "CERTIFICATE_PREDICATE_FALSE"
LIBRARY_RAISED = "LIBRARY_RAISED"
REGISTERED_TERMINATION_REASONS = frozenset({
    ITERATION_LIMIT_REACHED, CONSTRAINTS_REPORTED_INCONSISTENT, NUMERICAL_BREAKDOWN,
    NON_FINITE_CANDIDATE, CERTIFICATE_PREDICATE_FALSE, LIBRARY_RAISED,
})

WRAPPER_ORIGIN = "WRAPPER_ORIGIN"
UNREGISTERED_TERMINATION_REASON = "UNREGISTERED_TERMINATION_REASON"

# ── §2.4 run-level dispositions (closed, total) ──────────────────────────────────────────────────
PRIMARY_CERTIFIED = "PRIMARY_CERTIFIED"
SECONDARY_CERTIFIED = "SECONDARY_CERTIFIED"
UNRESOLVED_INSTANCE = "UNRESOLVED_INSTANCE"
INVALID_RUN = "INVALID_RUN"
CERTIFIED_SOLUTION_DISAGREEMENT = "CERTIFIED_SOLUTION_DISAGREEMENT"
RESOLVED_DISPOSITIONS = frozenset({PRIMARY_CERTIFIED, SECONDARY_CERTIFIED})

# ── §2.5.2 ownership domains (frozen configuration) ──────────────────────────────────────────────
SOLVER_LIBRARY_ROOTS = ("piqp", "clarabel", "quadprog", "highspy")
OUR_ROOTS = ("app.research.mr002", "scripts.mr002_", "app.research")

#: Registered library-boundary frames: (module, code-name). A frame here does nothing but invoke the
#: solver library and surface its status, so an exception surfacing from it is the LIBRARY's, not a
#: defect in our mapping. Adding to this registry after observing a failure is a profile-class
#: change and is prohibited on the same footing as retuning `max_iter` (§1).
LIBRARY_BOUNDARIES: frozenset[tuple[str, str]] = frozenset({
    ("scripts.mr002_coverage_signed_gap", "run"),            # _quadprog_variant / _lam_of boundaries
    ("scripts.mr002_piqp", "solve_piqp"),                    # PIQP status raise site
    ("scripts.mr002_characterize_native_qp", "solve_clarabel"),
    ("scripts.mr002_characterize_native_qp", "solve_highs"),
})

LIBRARY_BOUNDARY = "LIBRARY_BOUNDARY"
OURS = "OURS"
UNATTRIBUTABLE = "UNATTRIBUTABLE"


@dataclass(frozen=True)
class GenOutcome:
    """One generator's normalized outcome on one instance."""

    profile: str
    outcome: str
    reason: str | None = None
    detail: str = ""
    provenance: str = "NA"
    exception_class: str | None = None
    owning_module: str | None = None
    z: np.ndarray | None = None
    lam: np.ndarray | None = None
    cert: object | None = None
    checks: dict = field(default_factory=dict)
    #: What sealed §2.5.2 would have produced with no boundary refinement. Recorded so the census
    #: can quantify the refinement instead of asserting it.
    literal_outcome: str = ""

    @property
    def is_certified(self) -> bool:
        return self.outcome == CERTIFIED


# ── provenance ───────────────────────────────────────────────────────────────────────────────────
def _frames(exc: BaseException) -> list[FrameType]:
    """Traceback frames, shallowest first. The last entry is the deepest Python frame."""
    out: list[FrameType] = []
    tb = exc.__traceback__
    while tb is not None:
        out.append(tb.tb_frame)
        tb = tb.tb_next
    return out


def _domain(module: str | None) -> str:
    if not module:
        return UNATTRIBUTABLE
    root = module.split(".")[0]
    if root in SOLVER_LIBRARY_ROOTS:
        return LIBRARY_BOUNDARY
    if any(module.startswith(r) for r in OUR_ROOTS):
        return OURS
    return UNATTRIBUTABLE


def _literal_domain(exc: BaseException) -> str:
    """Sealed §2.5.2 EXACTLY as written: first frame (deepest outward) in a registered domain.

    Shared numeric libraries (numpy/scipy) are deliberately not domains, so they are transparent.
    """
    for frame in reversed(_frames(exc)):
        d = _domain(frame.f_globals.get("__name__"))
        if d in (LIBRARY_BOUNDARY, OURS):
            return d
    return UNATTRIBUTABLE


def _piqp_reason(status: object) -> str | None:
    """Map a piqp status OBJECT to a registered reason. Structured data, never the message."""
    try:
        import piqp
    except Exception:  # noqa: BLE001 - absence of the library is not a status
        return None
    return {
        piqp.PIQP_MAX_ITER_REACHED: ITERATION_LIMIT_REACHED,
        piqp.PIQP_PRIMAL_INFEASIBLE: CONSTRAINTS_REPORTED_INCONSISTENT,
        piqp.PIQP_DUAL_INFEASIBLE: CONSTRAINTS_REPORTED_INCONSISTENT,
        piqp.PIQP_NUMERICS: NUMERICAL_BREAKDOWN,
    }.get(status)


def _clarabel_reason(status: object) -> str | None:
    """Map a clarabel SolverStatus OBJECT to a registered reason. Structured data, never the message."""
    try:
        from clarabel import SolverStatus as S
    except Exception:  # noqa: BLE001
        return None
    return {
        S.MaxIterations: ITERATION_LIMIT_REACHED,
        S.MaxTime: ITERATION_LIMIT_REACHED,
        S.InsufficientProgress: NUMERICAL_BREAKDOWN,
        S.NumericalError: NUMERICAL_BREAKDOWN,
        S.PrimalInfeasible: CONSTRAINTS_REPORTED_INCONSISTENT,
        S.DualInfeasible: CONSTRAINTS_REPORTED_INCONSISTENT,
        S.AlmostPrimalInfeasible: CONSTRAINTS_REPORTED_INCONSISTENT,
        S.AlmostDualInfeasible: CONSTRAINTS_REPORTED_INCONSISTENT,
    }.get(status)


def _structured_reason(frame: FrameType) -> str | None:
    """Read the solver's terminal status as DATA out of the boundary frame's locals.

    §2.5.2 forbids reading the exception message. The status object itself is structured data and is
    available on the traceback frame, so the mapping is by enum identity, not by text.
    """
    loc = frame.f_locals
    module = frame.f_globals.get("__name__", "")
    if module == "scripts.mr002_piqp" and "st" in loc:
        return _piqp_reason(loc["st"])
    if module == "scripts.mr002_characterize_native_qp":
        sol = loc.get("sol")
        status = getattr(sol, "status", None)
        if status is not None:
            return _clarabel_reason(status)
    return None


def classify_exception(exc: BaseException) -> tuple[str, str, str, str]:
    """(outcome, reason, provenance, owning_module) for an exception escaping a generator.

    Structural only. The message is never consulted.
    """
    frames = _frames(exc)
    if not frames:
        return SYSTEM_INTEGRITY_DEFECT, UNREGISTERED_TERMINATION_REASON, UNATTRIBUTABLE, ""

    deepest = frames[-1]
    module = deepest.f_globals.get("__name__", "") or ""
    name = deepest.f_code.co_name

    # A frame genuinely inside the solver library.
    if _domain(module) == LIBRARY_BOUNDARY:
        return NO_CERTIFIED_CANDIDATE, LIBRARY_RAISED, LIBRARY_BOUNDARY, module

    # A registered thin library-boundary frame of ours.
    if (module, name) in LIBRARY_BOUNDARIES:
        reason = _structured_reason(deepest) or LIBRARY_RAISED
        return NO_CERTIFIED_CANDIDATE, reason, LIBRARY_BOUNDARY, module

    if _domain(module) == OURS:
        return SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN, OURS, module

    return NO_CERTIFIED_CANDIDATE, UNREGISTERED_TERMINATION_REASON, UNATTRIBUTABLE, module


# ── §2.2 normalization of ONE generator on ONE instance ──────────────────────────────────────────
def normalize(profile: str, solver, certify_fn, rec: tuple) -> GenOutcome:
    """Run one generator and map its behaviour to exactly one closed-enum outcome."""
    t, A_ub, b_ub, A_eq, b_eq, upper = rec
    n = len(t)
    lam_len = A_eq.shape[0] + A_ub.shape[0] + 2 * n

    # (1) raw generator behaviour ---------------------------------------------------------------
    try:
        returned = solver(*(np.array(x, dtype=float, copy=True) for x in rec))
    except Exception as exc:  # noqa: BLE001 -- classified structurally below, never by message
        outcome, reason, prov, module = classify_exception(exc)
        lit = _literal_domain(exc)
        return GenOutcome(
            profile, outcome, reason,
            detail=f"{type(exc).__name__}@{module}",
            provenance=prov, exception_class=type(exc).__name__, owning_module=module,
            literal_outcome=(SYSTEM_INTEGRITY_DEFECT if lit == OURS
                             else NO_CERTIFIED_CANDIDATE if lit == LIBRARY_BOUNDARY
                             else NO_CERTIFIED_CANDIDATE),
        )

    # (2) contract on the returned candidate ----------------------------------------------------
    # SHAPE IS OURS, VALUES ARE THE SOLVER'S (§2.2). A wrong-sized or non-numeric return means our
    # mapping code is wrong -- a system defect. Non-finite entries of a correctly shaped return are
    # numerical behaviour -- no certified candidate.
    try:
        z_raw, lam_raw = returned
    except (TypeError, ValueError):
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail="SOLVER_RETURN_NOT_A_PAIR", provenance=OURS,
                          literal_outcome=SYSTEM_INTEGRITY_DEFECT)
    try:
        z = np.asarray(z_raw, dtype=float)
        lam = np.asarray(lam_raw, dtype=float)
    except (TypeError, ValueError):
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail="NON_NUMERIC_CANDIDATE", provenance=OURS,
                          literal_outcome=SYSTEM_INTEGRITY_DEFECT)
    if z.shape != (n,) or lam.shape != (lam_len,):
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail=f"WRONG_SIZED_CANDIDATE:z{z.shape}!=({n},) lam{lam.shape}!=({lam_len},)",
                          provenance=OURS, literal_outcome=SYSTEM_INTEGRITY_DEFECT)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        return GenOutcome(profile, NO_CERTIFIED_CANDIDATE, NON_FINITE_CANDIDATE,
                          detail="non-finite entries in a correctly shaped return",
                          provenance=LIBRARY_BOUNDARY, literal_outcome=NO_CERTIFIED_CANDIDATE)

    # (3) the single registered certifier is the acceptance authority (§3.1) --------------------
    try:
        result = certify_fn(z, lam, *rec)
    except Exception as exc:  # noqa: BLE001 -- a certifier fault is a SYSTEM defect, never a rescue
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail=f"CERTIFIER_EXCEPTION:{type(exc).__name__}", provenance=OURS,
                          exception_class=type(exc).__name__,
                          literal_outcome=SYSTEM_INTEGRITY_DEFECT)

    if not (isinstance(result, tuple) and len(result) == 3):
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail="CERTIFIER_CONTRACT:NOT_A_3TUPLE", provenance=OURS,
                          literal_outcome=SYSTEM_INTEGRITY_DEFECT)
    ok, bad, cert = result
    if type(ok) is not bool or not isinstance(bad, list) or cert is None or bool(ok) == bool(bad):
        return GenOutcome(profile, SYSTEM_INTEGRITY_DEFECT, WRAPPER_ORIGIN,
                          detail="CERTIFIER_CONTRACT:INCONSISTENT", provenance=OURS,
                          literal_outcome=SYSTEM_INTEGRITY_DEFECT)

    if ok:
        return GenOutcome(profile, CERTIFIED, None, detail="PASS", provenance="NA",
                          z=z, lam=lam, cert=cert, literal_outcome=CERTIFIED)

    return GenOutcome(profile, NO_CERTIFIED_CANDIDATE, CERTIFICATE_PREDICATE_FALSE,
                      detail="+".join(map(str, bad)), provenance="NA",
                      z=z, lam=lam, cert=cert, literal_outcome=NO_CERTIFIED_CANDIDATE)


# ── §2.4 the two-generator resolution ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Resolution:
    disposition: str
    a: GenOutcome
    b: GenOutcome | None
    accepted_by: str | None = None
    accepted_z: np.ndarray | None = None
    detail: str = ""


def resolve(rec: tuple, *, a_solver, b_solver, certify_fn,
            a_profile: str, b_profile: str, run_both: bool) -> Resolution:
    """Resolve one instance through the certificate-driven two-generator method.

    `run_both=True` is the N1 development-qualification mode, in which both generators run on every
    instance so the SA-2 uniqueness contradiction can be tested. Production mode invokes B only on
    A's NO_CERTIFIED_CANDIDATE, so both-certified cannot arise there.
    """
    a = normalize(a_profile, a_solver, certify_fn, rec)

    if a.outcome == SYSTEM_INTEGRITY_DEFECT:
        return Resolution(INVALID_RUN, a, None, detail=f"A system integrity defect: {a.detail}")

    b: GenOutcome | None = None
    if run_both or not a.is_certified:
        b = normalize(b_profile, b_solver, certify_fn, rec)
        if b.outcome == SYSTEM_INTEGRITY_DEFECT:
            return Resolution(INVALID_RUN, a, b, detail=f"B system integrity defect: {b.detail}")

    if a.is_certified:
        # Both-certified is checked by the caller against the §4 equivalence bound (SA-2); the
        # disposition itself stays PRIMARY_CERTIFIED and A's point is the accepted one.
        return Resolution(PRIMARY_CERTIFIED, a, b, accepted_by=a_profile, accepted_z=a.z)

    if b is not None and b.is_certified:
        return Resolution(SECONDARY_CERTIFIED, a, b, accepted_by=b_profile, accepted_z=b.z)

    return Resolution(UNRESOLVED_INSTANCE, a, b,
                      detail=f"neither certified (A={a.reason}, B={b.reason if b else 'not run'})")
