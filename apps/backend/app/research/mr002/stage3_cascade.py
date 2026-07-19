"""MR-002 Stage-3 — finalized cascade `QUADPROG_SQRT -> PIQP_P2 (once)`.

This module implements the successor Stage-3 numerical cascade **as countersigned (design only)
2026-07-17**:

    docs/implementation/evidence/mr_002/
        MR002_Erratum_Stage3_Cascade_ProspectiveAdjudication_v1.0_DRAFT.md   (design commit 3548a2d)
        MR002_Stage3ProspectiveAdjudication_Countersign_v1.0.json            (countersign  b8e95e1)

It is the operational realization of the §7 **total eligibility decision table** and the §5 fallback
rule. It is NOT a re-adjudication and it introduces no new numerical method: the primary is the frozen
`QUADPROG_SQRT` path, the fallback is the frozen `PIQP_P2` profile (`mr002_piqp.py` BASE,
`preconditioner_scale_cost=true`), and the acceptance authority is the single registered certifier
(`canonical_qualify` = registered KKT LIMITS + two-sided signed Lagrangian gap). The *only* thing this
module adds over the diagnostic scripts is the **decision table**: it runs the primary, normalizes its
raw behavior into the closed enum, and — only on an eligible numerical nonqualification — invokes the
one fixed fallback exactly once.

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║  EXECUTION IS NOT AUTHORIZED BY THE DESIGN COUNTERSIGNATURE.                                    ║
║  A SEPARATE execution countersignature (adjudication §10) must bind this finalized             ║
║  implementation, the eligibility fixtures, the source manifest, the image digest, the runtime  ║
║  configuration, the regenerated-population protocol, and the clean-run stop gates BEFORE any    ║
║  Stage-3 instance is resolved. This module must not be pointed at the registered corpus, the    ║
║  frozen dataset, or any population-selection loop until that countersignature exists.           ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝

Closed eligibility enum (adjudication §7; frozen operationally in
`MR002_Stage3EligibilityStatusMapping_v1.0.json`):

    QUALIFIED
    NUMERICAL_STATUS_NONQUALIFICATION      (§7-B(i): registered ValueError on the exact allowlist)
    CERTIFICATE_NONQUALIFICATION           (§7-B(ii): certifier completes, registered predicate false)
    INTEGRITY_DEFECT                       (§7-C: any provenance/construction/certifier/contract defect)

    default_for_unrecognized = INTEGRITY_DEFECT   (never fallback-eligible, never by analogy)

Terminal dispositions (adjudication §7-A/§7-D; each raw outcome maps to exactly one):

    PRIMARY_QUALIFIED             accept the primary point; the fallback is NOT invoked.
    FALLBACK_QUALIFIED            eligible primary nonqualification, fallback qualifies; accept it.
    UNRESOLVED_NUMERICAL_FAILURE  eligible primary nonqualification, fallback completes but does not
                                  qualify.  STOP.
    INVALID_RUN                   any integrity defect in the model inputs, the primary, or the
                                  fallback.  STOP.  **On a PRIMARY integrity defect the fallback is
                                  never invoked** (§7-C; proved by the fixtures).

Matching discipline (§7-B): the numerical allowlist is SOLVER-SCOPED and keyed on the EXACT exception
class OBJECT (matched by identity, not name) AND the EXACT complete message string. The one registered
numerical status belongs to QUADPROG_SQRT only; PIQP_P2 has none, so an identical class/message from
PIQP is an INTEGRITY_DEFECT, not a rescue. No substring, regex, partial, or cross-solver match — an
unknown class, message, or solver maps to INTEGRITY_DEFECT, never to fallback eligibility.

Prohibited (§5.1, countersign): a third attempt, jitter, tolerance change, profile change, per-instance
routing, eligibility by analogy, and reuse of any quarantined artifact/row disposition.

The default primary/fallback/certifier are bound LAZILY (see `_default_*`) to the frozen numerical
paths, which live in the pinned research image. The pure decision-table logic below has no dependency
on quadprog / piqp / mpmath, so it — and the eligibility fixtures — run without the solver stack; the
fixtures drive every branch through the injection seam (`resolve`), and an in-image realism harness
(`scripts/mr002_stage3_cascade_fixtures.py`) exercises the same branches against the real numerics.
"""

from __future__ import annotations

import builtins
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np


class Stage3IntegrityError(RuntimeError):
    """A production integrity precondition (e.g. solver identity) that must fail loudly.

    Used for defense-in-depth checks that `assert` would silence under `python -O`. When raised
    inside `normalize`, it is caught and classified INTEGRITY_DEFECT (→ INVALID_RUN, STOP).
    """

# ── closed eligibility enum (§7) ─────────────────────────────────────────────────────────────────
QUALIFIED = "QUALIFIED"
NUMERICAL_STATUS_NONQUALIFICATION = "NUMERICAL_STATUS_NONQUALIFICATION"
CERTIFICATE_NONQUALIFICATION = "CERTIFICATE_NONQUALIFICATION"
INTEGRITY_DEFECT = "INTEGRITY_DEFECT"
CLOSED_ENUM = (
    QUALIFIED,
    NUMERICAL_STATUS_NONQUALIFICATION,
    CERTIFICATE_NONQUALIFICATION,
    INTEGRITY_DEFECT,
)
DEFAULT_FOR_UNRECOGNIZED = INTEGRITY_DEFECT

# the two fallback-eligible categories (§7-B) — invoke the one fixed fallback exactly once
_FALLBACK_ELIGIBLE = frozenset(
    {NUMERICAL_STATUS_NONQUALIFICATION, CERTIFICATE_NONQUALIFICATION}
)

# ── terminal dispositions (§7-A / §7-D) ──────────────────────────────────────────────────────────
PRIMARY_QUALIFIED = "PRIMARY_QUALIFIED"
FALLBACK_QUALIFIED = "FALLBACK_QUALIFIED"
UNRESOLVED_NUMERICAL_FAILURE = "UNRESOLVED_NUMERICAL_FAILURE"
INVALID_RUN = "INVALID_RUN"
_STOP_DISPOSITIONS = frozenset({UNRESOLVED_NUMERICAL_FAILURE, INVALID_RUN})

PRIMARY_SOLVER_ID = "QUADPROG_SQRT"
FALLBACK_SOLVER_ID = "PIQP_P2"

# ── frozen numerical-nonqualification allowlist (§7-B(i)) ────────────────────────────────────────
# SOLVER-SCOPED. Keyed on (solver_id, EXACT exception class OBJECT, EXACT complete message). The one
# registered numerical status was registered for QUADPROG_SQRT ONLY (eligibility-status mapping:
# scripts/mr002_solver_intersection.py:240-246, quadprog family). PIQP_P2 has NO registered numerical
# status: an identical class/message raised by PIQP is NOT this status — it is an INTEGRITY_DEFECT.
# Matching is by class IDENTITY (`type(exc) is cls`), not by class name — a user-defined class also
# named "ValueError" does not match, and neither does a subclass.
NUMERICAL_ALLOWLIST: dict[tuple[str, type, str], str] = {
    (PRIMARY_SOLVER_ID, builtins.ValueError, "constraints are inconsistent, no solution"):
        "QUADPROG_CONSTRAINTS_INCONSISTENT",
}


def match_registered_numerical(solver_id: str, exc: BaseException) -> str | None:
    """Exact, solver-scoped lookup. `type(exc)` is the class OBJECT, so subclasses and same-named
    user classes do not match; the message must be byte-equal; and the mapping is scoped to the solver
    it was registered for."""
    return NUMERICAL_ALLOWLIST.get((solver_id, type(exc), str(exc)))


# rec = (t, A_ub, b_ub, A_eq, b_eq, upper) — the canonical registered problem, original coordinates.
Rec = tuple


@dataclass(frozen=True)
class Attempt:
    """The normalized outcome of ONE solver on the registered problem."""

    solver_id: str
    enum: str  # one of CLOSED_ENUM
    code: str  # normalized reason code / detail (never used for routing — enum routes)
    z: np.ndarray | None = None
    lam: np.ndarray | None = None
    cert: object = None

    @property
    def is_qualified(self) -> bool:
        return self.enum == QUALIFIED

    @property
    def is_fallback_eligible(self) -> bool:
        return self.enum in _FALLBACK_ELIGIBLE

    @property
    def is_integrity_defect(self) -> bool:
        return self.enum == INTEGRITY_DEFECT


@dataclass(frozen=True)
class Outcome:
    """The terminal §7 disposition of the cascade on one registered problem."""

    disposition: str  # one of the four terminal dispositions
    primary: Attempt
    fallback: Attempt | None = None
    fallback_invoked: bool = False
    accepted_by: str | None = None  # PRIMARY_SOLVER_ID | FALLBACK_SOLVER_ID | None
    detail: str = ""
    _accepted_z: np.ndarray | None = field(default=None, repr=False)

    @property
    def stop(self) -> bool:
        return self.disposition in _STOP_DISPOSITIONS

    @property
    def accepted_z(self) -> np.ndarray | None:
        return self._accepted_z

    def summary(self) -> dict:
        """JSON-safe record (no arrays); the shape used in the evidence stream."""
        return {
            "disposition": self.disposition,
            "stop": self.stop,
            "primary_solver": self.primary.solver_id,
            "primary_enum": self.primary.enum,
            "primary_code": self.primary.code,
            "fallback_invoked": self.fallback_invoked,
            "fallback_solver": self.fallback.solver_id if self.fallback else None,
            "fallback_enum": self.fallback.enum if self.fallback else None,
            "fallback_code": self.fallback.code if self.fallback else None,
            "accepted_by": self.accepted_by,
            "detail": self.detail,
        }


# Type of an injectable solver: (t, A_ub, b_ub, A_eq, b_eq, upper) -> (z, lam), or raises.
SolverFn = Callable[..., tuple]
# Type of an injectable certifier: (z, lam, t, A_ub, b_ub, A_eq, b_eq, upper)
#                                   -> (ok: bool, bad: list[str], cert), or raises.
CertifyFn = Callable[..., tuple]


class _CertifierException(Exception):
    """Internal marker so a certifier fault is always classified INTEGRITY_DEFECT (§7-C)."""


# ── the FORMAL model-input contract (cycle-5 finding 4) ──────────────────────────────────────────
# Derived clause-by-clause from the frozen consumers: `_qp_matrices` (C = vstack[A_eq,-A_ub,I,-I]ᵀ,
# b = concat[b_eq,-b_ub,0,-upper] — requires 2-D matrices with n columns, matching 1-D rhs, 1-D
# upper of length n), the SQRT transformation (S = diag(√t) — requires t strictly positive), the
# dual reconstruction (lam layout meq+m_ub+2n and the /s scaling — same positivity), the PIQP setup
# (P = diag(2/t), bounds [0, upper] — requires finite inputs and upper ≥ 0), and the certifier
# indexing (lam[meq:], slack[meq:] — same layout). Every clause names the validate_model_inputs
# defect code that enforces it; the conformance test proves each clause rejects its boundary fixture.
INPUT_CONTRACT: dict = {
    "record_type": "MR002_STAGE3_QP_MATRICES_INPUT_CONTRACT",
    "version": "1.0",
    "derived_from": ["joint_portfolio._qp_matrices", "solver_intersection.solve_sqrt (S=diag(sqrt(t)))",
                     "dual unscaling lam[nr:nr+n]/=s", "mr002_piqp.solve_piqp (P=diag(2/t), 0<=z<=upper)",
                     "certificate/canonical_qualify lam layout meq+m_ub+2n"],
    "clauses": [
        {"id": "ARITY6", "requires": "rec is a 6-tuple/list (t, A_ub, b_ub, A_eq, b_eq, upper)", "enforced_by": "MODEL_ARITY"},
        {"id": "CONVERTIBLE", "requires": "every component converts to float64 (no ragged/object/str)", "enforced_by": "MODEL_UNCONVERTIBLE"},
        {"id": "T_1D_NONEMPTY", "requires": "t is 1-D with n >= 1", "enforced_by": "MODEL_T_SHAPE"},
        {"id": "AUB_2D_NCOLS", "requires": "A_ub is 2-D with exactly n columns (m_ub >= 0 rows allowed)", "enforced_by": "MODEL_A_UB_SHAPE"},
        {"id": "AEQ_2D_NCOLS", "requires": "A_eq is 2-D with exactly n columns (meq >= 0 rows allowed)", "enforced_by": "MODEL_A_EQ_SHAPE"},
        {"id": "BUB_MATCH", "requires": "b_ub is 1-D of length m_ub", "enforced_by": "MODEL_B_UB_SHAPE"},
        {"id": "BEQ_MATCH", "requires": "b_eq is 1-D of length meq", "enforced_by": "MODEL_B_EQ_SHAPE"},
        {"id": "UPPER_1D_N", "requires": "upper is 1-D of length n", "enforced_by": "MODEL_UPPER_SHAPE"},
        {"id": "ALL_FINITE", "requires": "every entry of every component is finite", "enforced_by": "NON_FINITE_MODEL_INPUT"},
        {"id": "T_POSITIVE", "requires": "t > 0 strictly (H=2/t, S=sqrt(t), dual /s scaling)", "enforced_by": "MODEL_T_NONPOSITIVE"},
        {"id": "UPPER_NONNEG", "requires": "upper >= 0 (bounds are 0 <= z <= upper)", "enforced_by": "MODEL_UPPER_NEGATIVE"},
    ],
    "derived_properties": {
        "lam_layout": "meq + m_ub + 2n (equalities, inequalities, lower bounds, upper bounds)",
        "empty_constraint_convention": "meq == 0 and/or m_ub == 0 are VALID (zero-row 2-D matrices)",
        "dtype": "float64 canonical (canonicalize() coerces + freezes)"
    },
}


# ── model-input integrity gate (§7-C; before ANY solve) ──────────────────────────────────────────
def validate_model_inputs(rec: Rec) -> str | None:
    """Return a defect string if the registered problem is itself malformed, else None.

    These are §7-C INVALID_RUN triggers evaluated *before* the primary runs, so a malformed
    instance never even reaches a solver. `t_i <= 0` is explicitly an integrity defect (never a
    numerical nonqualification): the registered objective Hessian is `2*diag(1/t_i)`, so a
    non-positive `t_i` is a modelling-precondition violation.
    """
    # Defensive boundary (finding 7): rec may be None, wrong-arity, or hold non-convertible/scalar
    # members. Every one of these is a deterministic INVALID_RUN, never an escaping exception.
    if not isinstance(rec, (tuple, list)) or len(rec) != 6:
        return f"MODEL_ARITY:{type(rec).__name__}:{len(rec) if hasattr(rec, '__len__') else 'n/a'}"
    try:
        t, A_ub, b_ub, A_eq, b_eq, upper = (np.asarray(x, dtype=float) for x in rec)
    except (TypeError, ValueError):
        return "MODEL_UNCONVERTIBLE"           # non-numeric / ragged / object members
    # ndim BEFORE any [0] indexing (finding 7: a scalar t must not raise on t.shape[0]).
    if t.ndim != 1 or t.shape[0] == 0:
        return "MODEL_T_SHAPE"
    n = int(t.shape[0])
    if A_ub.ndim != 2 or A_ub.shape[1] != n:
        return "MODEL_A_UB_SHAPE"
    if A_eq.ndim != 2 or A_eq.shape[1] != n:
        return "MODEL_A_EQ_SHAPE"
    if b_ub.ndim != 1 or b_ub.shape[0] != A_ub.shape[0]:
        return "MODEL_B_UB_SHAPE"
    if b_eq.ndim != 1 or b_eq.shape[0] != A_eq.shape[0]:
        return "MODEL_B_EQ_SHAPE"
    if upper.ndim != 1 or upper.shape[0] != n:
        return "MODEL_UPPER_SHAPE"
    for name, arr in (("t", t), ("A_ub", A_ub), ("b_ub", b_ub),
                      ("A_eq", A_eq), ("b_eq", b_eq), ("upper", upper)):
        if not np.all(np.isfinite(arr)):
            return f"NON_FINITE_MODEL_INPUT:{name}"
    # Registered-model invariants assumed by the frozen constructors (finding 12):
    if not np.all(t > 0.0):
        return "MODEL_T_NONPOSITIVE"           # H = 2*diag(1/t) — §7-C, never fallback-eligible
    if not np.all(upper >= 0.0):
        return "MODEL_UPPER_NEGATIVE"          # bounds are 0 <= z <= upper; upper < 0 is infeasible-by-construction
    return None


def _expected_lengths(rec: Rec) -> tuple[int, int]:
    """(n, lam_len) for the canonical `_qp_matrices` layout: lam has meq + m_ub + 2n entries."""
    t, A_ub, _b_ub, A_eq, _b_eq, _upper = rec
    n = int(np.asarray(t).shape[0])
    meq = int(np.asarray(A_eq).shape[0])
    m_ub = int(np.asarray(A_ub).shape[0])
    return n, meq + m_ub + 2 * n


def _frozen_copy(z: np.ndarray | None) -> np.ndarray | None:
    """A read-only float64 copy (findings 13, 21): downstream cannot mutate accepted evidence."""
    if z is None:
        return None
    c = np.array(z, dtype=float, copy=True)
    c.flags.writeable = False
    return c


def canonicalize(rec: Rec) -> tuple:
    """Normalize a validated rec into ONE canonical, copied, read-only tuple used for validation,
    the primary, the fallback, the certifier, and record hashing (finding 20).

    A mutable/stateful input object could otherwise present one value at validation and another at
    solve time (a time-of-check/time-of-use gap). After this, every consumer reads identical bytes.
    """
    return tuple(_frozen_copy(np.asarray(x, dtype=float)) for x in rec)


# ── §7-B / §7-A normalization of ONE solver's raw behavior into the closed enum ──────────────────
def normalize(solver_id: str, solver: SolverFn, certify_fn: CertifyFn, rec: Rec) -> Attempt:
    """Run one solver and map its raw behavior to exactly one closed-enum category.

    This is pure §7 normalization — it contains no cascade/fallback logic. The exact-match allowlist
    and the certifier verdict are the ONLY inputs to the enum; the reason code is descriptive and is
    never consulted for routing.
    """
    n, lam_len = _expected_lengths(rec)

    # (1) raw solver behavior -------------------------------------------------------------------
    # Catch Exception, NOT BaseException (finding 10): KeyboardInterrupt / SystemExit / GeneratorExit
    # must propagate, never be normalized as a solver status.
    try:
        returned = solver(*(np.array(x, dtype=float, copy=True) for x in rec))
    except Exception as exc:  # noqa: BLE001 — a raise IS a candidate nonqualification/defect
        code = match_registered_numerical(solver_id, exc)
        if code is not None:
            # §7-B(i): the exact, solver-scoped registered numerical nonqualification.
            return Attempt(solver_id, NUMERICAL_STATUS_NONQUALIFICATION, code)
        # Unknown class OR unknown message OR wrong solver → §7-C integrity. Never by analogy.
        return Attempt(solver_id, INTEGRITY_DEFECT,
                       f"UNREGISTERED_EXCEPTION:{type(exc).__name__}:{str(exc)[:120]}")

    # (2) contract checks on the returned candidate (§7-C) --------------------------------------
    # The solver's return is untrusted: it may not be a 2-tuple, and the members may be non-numeric
    # (findings 8, 16). Convert defensively; any failure is an integrity defect, never an escape.
    try:
        z_raw, lam_raw = returned            # arity: None / too-many-values → TypeError/ValueError
    except (TypeError, ValueError):
        return Attempt(solver_id, INTEGRITY_DEFECT, "SOLVER_RETURN_NOT_A_PAIR")
    try:
        z = np.asarray(z_raw, dtype=float)
        lam = np.asarray(lam_raw, dtype=float)
    except (TypeError, ValueError):
        return Attempt(solver_id, INTEGRITY_DEFECT, "NON_NUMERIC_CANDIDATE")
    if z.shape != (n,) or lam.shape != (lam_len,):
        return Attempt(solver_id, INTEGRITY_DEFECT,
                       f"WRONG_SIZED_CANDIDATE:z{z.shape}!=({n},) lam{lam.shape}!=({lam_len},)")
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        return Attempt(solver_id, INTEGRITY_DEFECT, "NON_FINITE_SOLVER_OUTPUT")

    # (3) the single registered certifier is the acceptance authority (§5.4, §7) ----------------
    try:
        result = certify_fn(z, lam, *rec)
    except _CertifierException as exc:
        return Attempt(solver_id, INTEGRITY_DEFECT, f"CERTIFIER_EXCEPTION:{str(exc)[:120]}")
    except Exception as exc:  # noqa: BLE001 — a certifier fault is INVALID_RUN, never a rescue
        return Attempt(solver_id, INTEGRITY_DEFECT,
                       f"CERTIFIER_EXCEPTION:{type(exc).__name__}:{str(exc)[:100]}")

    # A completed certifier CALL is not a valid certifier RESULT (finding 9): validate the contract.
    contract = _validate_certifier_result(result)
    if contract is not None:
        return Attempt(solver_id, INTEGRITY_DEFECT, f"CERTIFIER_CONTRACT:{contract}")
    ok, bad, cert = result

    # Freeze the evidence (findings 21, cycle-4 19): arrays are read-only copies, and an ACCEPTED
    # certificate is snapshotted into an immutable CertSnapshot at normalization time — a caller
    # cannot mutate certificate fields between certification, validation, and serialization. A cert
    # missing any registered field cannot be accepted evidence.
    if ok:
        snap = _snapshot_certificate(cert)
        if snap is None:
            return Attempt(solver_id, INTEGRITY_DEFECT,
                           "CERTIFIER_CONTRACT:CERT_FIELDS_MISSING_ON_ACCEPT")
        return Attempt(solver_id, QUALIFIED, "PASS",
                       z=_frozen_copy(z), lam=_frozen_copy(lam), cert=snap)
    # §7-B(ii): finite, correctly mapped candidate; certifier completed; registered predicate false.
    return Attempt(solver_id, CERTIFICATE_NONQUALIFICATION,
                   "+".join(bad), z=_frozen_copy(z), lam=_frozen_copy(lam), cert=cert)


def _validate_certifier_result(result: object) -> str | None:
    """Return a defect string if the certifier's return violates the registered (ok, bad, cert)
    contract, else None (finding 9).

    Enforced invariants: exactly a 3-tuple; `ok` is a real bool (not 1 / "yes" / an array); `bad` is a
    list of strings; `cert` is present; and `ok` is consistent with an empty `bad` (a True verdict with
    a nonempty failure list, or a False verdict with an empty one, is a contradiction → INTEGRITY).
    """
    if not (isinstance(result, tuple) and len(result) == 3):
        return "NOT_A_3TUPLE"
    ok, bad, cert = result
    if type(ok) is not bool:                 # numpy bool / int / str / array all rejected
        return f"OK_NOT_BOOL:{type(ok).__name__}"
    if not isinstance(bad, list) or not all(isinstance(x, str) for x in bad):
        return "BAD_NOT_LIST_OF_STR"
    if cert is None:
        return "CERT_MISSING"
    if ok and bad:
        return "OK_TRUE_WITH_FAILURES"
    if (not ok) and not bad:
        return "OK_FALSE_WITHOUT_FAILURES"
    return None


# ── the cascade (§7 total decision table) ────────────────────────────────────────────────────────
def resolve(
    rec: Rec,
    *,
    primary: SolverFn,
    fallback: SolverFn,
    certify_fn: CertifyFn,
) -> Outcome:
    """Resolve one registered problem through `QUADPROG_SQRT -> PIQP_P2 (once)`.

    Every path returns exactly one of the four terminal dispositions. The fallback is reachable ONLY
    from the two fallback-eligible primary categories; a primary INTEGRITY_DEFECT returns INVALID_RUN
    without ever constructing the `fallback` call — the §7-C guarantee the fixtures prove.

    All three numerical dependencies are injected so the decision table is testable in isolation;
    `resolve_instance` binds the frozen production implementations.
    """
    # §7-C model-input gate — before any solver touches the instance.
    bad_input = validate_model_inputs(rec)
    if bad_input is not None:
        stub = Attempt(PRIMARY_SOLVER_ID, INTEGRITY_DEFECT, f"MODEL_INPUT:{bad_input}")
        return Outcome(INVALID_RUN, primary=stub, fallback_invoked=False, detail=bad_input)

    # Canonicalize ONCE (finding 20): validation, primary, fallback, certifier, and record hashing
    # all read these identical read-only bytes — no time-of-check/time-of-use gap.
    canon = canonicalize(rec)

    # ── primary ────────────────────────────────────────────────────────────────────────────────
    p = normalize(PRIMARY_SOLVER_ID, primary, certify_fn, canon)

    if p.enum == QUALIFIED:
        # §7-A — accept the primary; do NOT invoke the fallback.
        return Outcome(PRIMARY_QUALIFIED, primary=p, fallback_invoked=False,
                       accepted_by=PRIMARY_SOLVER_ID, _accepted_z=_frozen_copy(p.z))

    if p.enum == INTEGRITY_DEFECT:
        # §7-C — INVALID_RUN. The fallback is NEVER invoked on a primary integrity defect.
        return Outcome(INVALID_RUN, primary=p, fallback_invoked=False,
                       detail=f"primary integrity defect: {p.code}")

    # p.enum is fallback-eligible (NUMERICAL_STATUS_NONQUALIFICATION or CERTIFICATE_NONQUALIFICATION).
    # A runtime check (not an assert — finding 11), so an unexpected enum STOPs rather than falling
    # through silently under `python -O`.
    if not p.is_fallback_eligible:
        return Outcome(INVALID_RUN, primary=p, fallback_invoked=False,
                       detail=f"unexpected primary enum {p.enum!r} outside the closed decision table")

    # §5.1 — invoke the one fixed fallback EXACTLY ONCE, on the identical registered problem.
    f = normalize(FALLBACK_SOLVER_ID, fallback, certify_fn, canon)

    if f.enum == QUALIFIED:
        # §7-D — fallback qualifies under the common certifier; accept the fallback point.
        return Outcome(FALLBACK_QUALIFIED, primary=p, fallback=f, fallback_invoked=True,
                       accepted_by=FALLBACK_SOLVER_ID, _accepted_z=_frozen_copy(f.z))

    if f.enum == INTEGRITY_DEFECT:
        # §7-D — fallback has an integrity/provenance/contract defect → INVALID_RUN, STOP.
        return Outcome(INVALID_RUN, primary=p, fallback=f, fallback_invoked=True,
                       detail=f"fallback integrity defect: {f.code}")

    # §7-D — fallback completes but does not qualify (numerical or certificate) → STOP.
    return Outcome(UNRESOLVED_NUMERICAL_FAILURE, primary=p, fallback=f, fallback_invoked=True,
                   detail=f"both solvers nonqualified (primary={p.enum}, fallback={f.enum})")


# The complete registered SignedGapCertificate field set. Evidence serialization and the outcome
# validator both ENFORCE presence of every field (cycle-3 findings 7, 8).
REQUIRED_CERT_FIELDS = (
    "gamma_lower", "gamma_upper", "primal_lower", "primal_upper", "dual_lower", "dual_upper",
    "lagrangian_slack", "stationarity_energy", "primal_interval_width", "dual_interval_width",
    "max_multiplier_clip", "n_multipliers_clipped", "qualifies",
)


@dataclass(frozen=True)
class CertSnapshot:
    """Immutable snapshot of an ACCEPTED certificate, taken at normalization time (cycle-4 finding
    19): fields cannot be mutated between certification, outcome validation, and serialization."""

    source_type: str
    gamma_lower: float
    gamma_upper: float
    primal_lower: float
    primal_upper: float
    dual_lower: float
    dual_upper: float
    lagrangian_slack: float
    stationarity_energy: float
    primal_interval_width: float
    dual_interval_width: float
    max_multiplier_clip: float
    n_multipliers_clipped: int
    qualifies: bool


def _snapshot_certificate(cert: object) -> CertSnapshot | None:
    """Freeze a certificate's registered fields; None if any registered field is missing."""
    if any(not hasattr(cert, f) for f in REQUIRED_CERT_FIELDS):
        return None
    return CertSnapshot(source_type=type(cert).__name__,
                        **{f: getattr(cert, f) for f in REQUIRED_CERT_FIELDS})


def validate_outcome(o: object, rec: Rec | None = None) -> str | None:
    """Structural consistency gate for a resolved Outcome (cycle-3 finding 7). Returns a defect
    string, or None. Any inconsistency must be treated by the caller as INVALID_RUN → STOP.

    Enforced for QUALIFIED dispositions: solver identities; enum/accepted_by consistency; the
    accepted point byte-equal to the accepting attempt's z; finiteness; the complete registered
    certificate field set with `qualifies` exactly True; and (when `rec` is supplied) primal/dual
    lengths against the problem. Enforced for STOP dispositions: fallback presence/invocation
    consistency with the disposition, and no accepted evidence.
    """
    if not isinstance(o, Outcome):
        return f"NOT_AN_OUTCOME:{type(o).__name__}"
    if o.disposition not in (PRIMARY_QUALIFIED, FALLBACK_QUALIFIED,
                             UNRESOLVED_NUMERICAL_FAILURE, INVALID_RUN):
        return f"UNKNOWN_DISPOSITION:{o.disposition}"
    if not isinstance(o.primary, Attempt) or o.primary.enum not in CLOSED_ENUM:
        return "PRIMARY_NOT_A_CLOSED_ATTEMPT"
    if o.primary.solver_id != PRIMARY_SOLVER_ID:
        return f"PRIMARY_SOLVER_ID_MISMATCH:{o.primary.solver_id}"
    if o.fallback is not None:
        if not isinstance(o.fallback, Attempt) or o.fallback.enum not in CLOSED_ENUM:
            return "FALLBACK_NOT_A_CLOSED_ATTEMPT"
        if o.fallback.solver_id != FALLBACK_SOLVER_ID:
            return f"FALLBACK_SOLVER_ID_MISMATCH:{o.fallback.solver_id}"
        if not o.fallback_invoked:
            return "FALLBACK_PRESENT_BUT_NOT_INVOKED"

    if o.disposition == PRIMARY_QUALIFIED:
        if o.primary.enum != QUALIFIED:
            return "PRIMARY_QUALIFIED_BUT_PRIMARY_ENUM_NOT_QUALIFIED"
        if o.fallback_invoked or o.fallback is not None:
            return "PRIMARY_QUALIFIED_BUT_FALLBACK_INVOKED"
        if o.accepted_by != PRIMARY_SOLVER_ID:
            return "PRIMARY_QUALIFIED_ACCEPTED_BY_MISMATCH"
        return _accepted_evidence_defect(o, o.primary, rec)

    if o.disposition == FALLBACK_QUALIFIED:
        if not o.primary.is_fallback_eligible:
            return "FALLBACK_QUALIFIED_BUT_PRIMARY_NOT_ELIGIBLE"
        if not (o.fallback_invoked and isinstance(o.fallback, Attempt)):
            return "FALLBACK_QUALIFIED_BUT_NO_FALLBACK"
        if o.fallback.enum != QUALIFIED:
            return "FALLBACK_QUALIFIED_BUT_FALLBACK_ENUM_NOT_QUALIFIED"
        if o.accepted_by != FALLBACK_SOLVER_ID:
            return "FALLBACK_QUALIFIED_ACCEPTED_BY_MISMATCH"
        return _accepted_evidence_defect(o, o.fallback, rec)

    # ── STOP dispositions ──────────────────────────────────────────────────────────────────────
    if o.accepted_by is not None or o.accepted_z is not None:
        return "STOP_DISPOSITION_WITH_ACCEPTED_POINT"
    if o.disposition == UNRESOLVED_NUMERICAL_FAILURE:
        # only reachable via: eligible primary + invoked fallback that completed but nonqualified
        if not (o.primary.is_fallback_eligible and o.fallback_invoked
                and isinstance(o.fallback, Attempt)
                and o.fallback.enum in (NUMERICAL_STATUS_NONQUALIFICATION,
                                        CERTIFICATE_NONQUALIFICATION)):
            return "UNRESOLVED_INCONSISTENT_STATE"
    else:  # INVALID_RUN — either a pre-fallback integrity stop, or a fallback integrity defect
        # cycle-4 finding 2: a pre-fallback INVALID_RUN REQUIRES a primary integrity defect —
        # INVALID_RUN with a QUALIFIED (or merely nonqualified) primary is an impossible state.
        pre_fallback = (not o.fallback_invoked and o.fallback is None
                        and o.primary.enum == INTEGRITY_DEFECT)
        fallback_defect = (o.fallback_invoked and isinstance(o.fallback, Attempt)
                          and o.fallback.enum == INTEGRITY_DEFECT
                          and o.primary.is_fallback_eligible)
        if not (pre_fallback or fallback_defect):
            return "INVALID_RUN_INCONSISTENT_STATE"
    return None


def _accepted_evidence_defect(o: Outcome, acc: Attempt, rec: Rec | None) -> str | None:
    """A qualified acceptance must carry a full, finite, correctly-sized primal + dual + a complete
    registered certificate, with the accepted point byte-equal to the accepting attempt's z."""
    if o.accepted_z is None or acc.z is None or acc.lam is None or acc.cert is None:
        return "QUALIFIED_MISSING_NUMERICAL_EVIDENCE"
    if not (np.all(np.isfinite(acc.z)) and np.all(np.isfinite(acc.lam))
            and np.all(np.isfinite(o.accepted_z))):
        return "QUALIFIED_NONFINITE_EVIDENCE"
    if o.accepted_z.shape != acc.z.shape or not np.array_equal(o.accepted_z, acc.z):
        return "ACCEPTED_Z_NOT_IDENTICAL_TO_ATTEMPT_Z"
    missing = [f for f in REQUIRED_CERT_FIELDS if not hasattr(acc.cert, f)]
    if missing:
        return f"CERTIFICATE_FIELDS_MISSING:{missing}"
    if getattr(acc.cert, "qualifies") is not True:  # noqa: B009 — exact-True check is deliberate
        return "CERTIFICATE_QUALIFIES_NOT_TRUE"
    # cycle-4 finding 18 — value integrity, not just presence: finite numerics, interval ordering,
    # nonnegative integer clip count. Full re-certification remains the separate replay function.
    c = acc.cert
    numeric = [getattr(c, f) for f in REQUIRED_CERT_FIELDS if f not in ("qualifies",
                                                                        "n_multipliers_clipped")]
    try:
        if not all(np.isfinite(float(v)) for v in numeric):
            return "CERTIFICATE_NONFINITE_FIELD"
    except (TypeError, ValueError):
        return "CERTIFICATE_NON_NUMERIC_FIELD"
    if not (c.gamma_lower <= c.gamma_upper and c.primal_lower <= c.primal_upper
            and c.dual_lower <= c.dual_upper):
        return "CERTIFICATE_INTERVAL_REVERSED"
    if not (isinstance(c.n_multipliers_clipped, int) and c.n_multipliers_clipped >= 0):
        return "CERTIFICATE_CLIP_COUNT_INVALID"
    if rec is not None:
        n, lam_len = _expected_lengths(rec)
        if acc.z.shape != (n,):
            return f"ACCEPTED_Z_LENGTH_MISMATCH:{acc.z.shape}!=({n},)"
        if acc.lam.shape != (lam_len,):
            return f"ACCEPTED_LAM_LENGTH_MISMATCH:{acc.lam.shape}!=({lam_len},)"
    return None


# Evidence schema 2.0 (delta v1.8, run-4 governing finding): version is EXPLICIT and CLOSED.
# Schema 1.x encoded floats as as_integer_ratio() pairs under `exact_ratio` fields; that encoding
# cannot represent the sign of negative zero ((-0.0).as_integer_ratio() == (0, 1)), so a canonical
# array containing -0.0 could never replay to its own registered content hash. Schema 2.0 encodes
# every float64 as float.hex() under `*_exact_hex` fields — hex strings are NEVER stored under a
# ratio-named field, and replay refuses missing/unknown versions and any mixed v1/v2 fields.
EVIDENCE_SCHEMA_VERSION = "2.0"


def _exact_hex_list(v: np.ndarray) -> list[str]:
    """Each float64 as float.hex() — lossless textual binary64 (preserves ±0.0, subnormals, and
    every finite value bit-exactly through float.fromhex). Non-finite values REFUSE at publication
    (delta v1.8 canonical encoding rules): they never become durable evidence."""
    a = np.asarray(v, dtype=np.float64).ravel()
    if a.size and not np.all(np.isfinite(a)):
        raise Stage3IntegrityError("EVIDENCE_NON_FINITE_VALUE")
    return [float(x).hex() for x in a]


def rec_content_hash(rec: Rec) -> str:
    """Stable content hash of the canonical registered problem (shape + exact float64 bytes)."""
    h = hashlib.sha256(b"MR002|stage3|registered-problem|v1")
    for key, arr in zip(("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"), rec, strict=True):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(key.encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def numerical_evidence(o: Outcome, rec: Rec) -> dict:
    """Complete, independently re-certifiable per-row numerical evidence (cycle-3 finding 8).

    Preserves the COMPLETE input problem (every component as exact float.hex() encodings + its
    shape, evidence schema 2.0) alongside the input content hash, so a reviewer can re-run the
    certifier from ONE record alone — no separate corpus access needed. For a qualified row it adds
    the accepted primal z and dual lam as exact hex plus the complete certificate field set
    (enforced — a missing registered field raises, it is never silently dropped). Arrays are hashed
    so the evidence is self-verifying, and the hash covers raw float64 bytes including the sign of
    zero — which is why the encoding must be bit-lossless (delta v1.8).
    """
    keys = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")
    ev: dict = {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "input_content_hash": rec_content_hash(rec),
        "input": {k: {"shape": list(np.asarray(v, float).shape),
                      "exact_hex": _exact_hex_list(np.asarray(v, float))}
                  for k, v in zip(keys, rec, strict=True)},
        **o.summary(),
    }
    acc = None
    if o.disposition == PRIMARY_QUALIFIED:
        acc = o.primary
    elif o.disposition == FALLBACK_QUALIFIED:
        acc = o.fallback
    if acc is not None and acc.z is not None and acc.lam is not None:
        z = np.asarray(acc.z, float)
        lam = np.asarray(acc.lam, float)
        ev["accepted"] = {
            "solver": acc.solver_id,
            "z_exact_hex": _exact_hex_list(z),
            "lam_exact_hex": _exact_hex_list(lam),
            "z_sha256": hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest(),
            "lam_sha256": hashlib.sha256(np.ascontiguousarray(lam).tobytes()).hexdigest(),
            "certificate": _certificate_fields(acc.cert),
        }
    return ev


def _certificate_fields(cert: object) -> dict:
    """Serialize the registered certificate's COMPLETE field set. A missing registered field is an
    integrity error (cycle-3 finding 8) — evidence must never silently omit a field."""
    missing = [f for f in REQUIRED_CERT_FIELDS if not hasattr(cert, f)]
    if missing:
        raise Stage3IntegrityError(f"certificate missing registered fields: {missing}")
    out = {"type": getattr(cert, "source_type", type(cert).__name__)}
    for f in REQUIRED_CERT_FIELDS:
        out[f] = getattr(cert, f)
    return out


# ── production entry point: frozen implementations, bound once and sealable ─────────────────────
class _SealableRegistry(dict):
    """A binding registry that can be SEALED once (finding 22; hardened per cycle-3 finding 19):
    after sealing, EVERY mutation path — setitem, delitem, clear, pop, popitem, update, setdefault —
    raises for ALL keys, not just three. This is accidental-mutation protection, not a cryptographic
    integrity boundary: a determined in-process attacker can still mutate callables themselves, which
    is why execution additionally runs in a minimal one-shot container and the callables' source
    fingerprints are verified against the countersigned pins at seal time."""

    _sealed = False

    def seal(self) -> None:
        object.__setattr__(self, "_sealed", True)

    def _guard(self, op: str) -> None:
        if self._sealed:
            raise Stage3IntegrityError(f"attempt to {op} the sealed implementation registry")

    def __setitem__(self, key, value):
        self._guard(f"set {key!r} in")
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self._guard(f"delete {key!r} from")
        super().__delitem__(key)

    def clear(self):
        self._guard("clear")
        super().clear()

    def pop(self, *a, **k):
        self._guard("pop from")
        return super().pop(*a, **k)

    def popitem(self):
        self._guard("popitem from")
        return super().popitem()

    def update(self, *a, **k):
        self._guard("update")
        super().update(*a, **k)

    def setdefault(self, *a, **k):
        self._guard("setdefault on")
        return super().setdefault(*a, **k)


_REAL: _SealableRegistry = _SealableRegistry()


# The CLOSED mandatory fingerprint set (cycle-3 finding 20) — the pins must supply exactly these.
REQUIRED_FINGERPRINT_KEYS = frozenset(
    {"primary_wrapper", "piqp_solve", "canonical_qualify", "certify", "resolve"})


def seal_implementations(expected_fingerprints: dict | None = None) -> dict:
    """Bind the frozen primary/fallback/certifier ONCE, optionally verify their source fingerprints
    against the countersigned pins, then SEAL the registry so nothing can swap them mid-run.

    The fingerprint set is CLOSED (finding 20): when pins are supplied they must cover exactly
    `REQUIRED_FINGERPRINT_KEYS` — a partial or padded set is an integrity error, not a pass.
    Returns the observed fingerprints. Raises Stage3IntegrityError on drift.
    """
    import hashlib
    import inspect

    from app.research.mr002 import certificate as _cert
    from scripts import mr002_coverage_signed_gap as _cov
    from scripts import mr002_piqp as _piqp

    _bind_defaults()
    observed = {
        "primary_wrapper": hashlib.sha256(inspect.getsource(_cov._quadprog_variant).encode()).hexdigest(),
        "piqp_solve": hashlib.sha256(inspect.getsource(_piqp.solve_piqp).encode()).hexdigest(),
        "canonical_qualify": hashlib.sha256(inspect.getsource(_cov.canonical_qualify).encode()).hexdigest(),
        "certify": hashlib.sha256(inspect.getsource(_cert.certify).encode()).hexdigest(),
        "resolve": hashlib.sha256(inspect.getsource(resolve).encode()).hexdigest(),
    }
    if expected_fingerprints is not None:
        if set(expected_fingerprints) != REQUIRED_FINGERPRINT_KEYS:
            raise Stage3IntegrityError(
                f"fingerprint pin set not closed: missing={sorted(REQUIRED_FINGERPRINT_KEYS - set(expected_fingerprints))} "
                f"extra={sorted(set(expected_fingerprints) - REQUIRED_FINGERPRINT_KEYS)}")
        drift = {k: (observed.get(k), v) for k, v in expected_fingerprints.items()
                 if observed.get(k) != v}
        if drift:
            raise Stage3IntegrityError(f"callable fingerprint drift: {list(drift)}")
    _REAL.seal()
    return observed


def _bind_defaults() -> None:
    """Bind primary/fallback/certifier into _REAL with solver-identity checks (idempotent)."""
    from app.research.mr002.certificate import CertificateDefect, SignedGapCertificate
    from scripts.mr002_coverage_signed_gap import FALLBACK, PRIMARY, SOLVERS, canonical_qualify
    if PRIMARY != PRIMARY_SOLVER_ID or FALLBACK != FALLBACK_SOLVER_ID:
        raise Stage3IntegrityError(
            f"solver identity drift: PRIMARY={PRIMARY!r} FALLBACK={FALLBACK!r}")
    if "primary" not in _REAL:
        _REAL["primary"] = SOLVERS[PRIMARY]
    if "fallback" not in _REAL:
        _REAL["fallback"] = SOLVERS[FALLBACK]
    if "certify" not in _REAL:
        _REAL["certify"] = canonical_qualify
        _REAL["certdefect"] = CertificateDefect
        _REAL["certtype"] = SignedGapCertificate


def _default_primary(*args):
    """The frozen QUADPROG_SQRT (z, lam) path used by the immutable characterization corpus."""
    if "primary" not in _REAL:
        _bind_defaults()
    return _REAL["primary"](*args)


def _default_fallback(*args):
    """The frozen PIQP_P2 (z, lam) path (mr002_piqp BASE, preconditioner_scale_cost=true)."""
    if "fallback" not in _REAL:
        _bind_defaults()
    return _REAL["fallback"](*args)


def _default_certifier(z, lam, *rec):
    """The single registered certifier: registered KKT LIMITS + two-sided signed Lagrangian gap.

    A broken certificate (`CertificateDefect`) is re-raised as `_CertifierException` so `normalize`
    classifies it INTEGRITY_DEFECT rather than mistaking it for a solver nonqualification.
    """
    if "certify" not in _REAL:
        _bind_defaults()
    try:
        ok, bad, cert = _REAL["certify"](z, lam, *rec)
    except _REAL["certdefect"] as exc:  # type: ignore[misc]
        raise _CertifierException(str(exc)) from exc
    # Production structural check (finding 9): the acceptance authority must return the registered
    # certificate type, not merely something truthy.
    if not isinstance(cert, _REAL["certtype"]):
        raise _CertifierException(f"certifier returned {type(cert).__name__}, not SignedGapCertificate")
    return ok, bad, cert


def resolve_instance(rec: Rec) -> Outcome:
    """Production cascade for one registered problem, bound to the frozen numerical implementations.

    ⚠ Authorized to EXIST and be tested; NOT authorized to run against the registered corpus/dataset
    until the separate execution countersignature (adjudication §10) is in place.
    """
    return resolve(rec, primary=_default_primary, fallback=_default_fallback,
                   certify_fn=_default_certifier)
