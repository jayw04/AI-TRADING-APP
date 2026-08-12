"""EB-1/EB-2: the execution layer is independently enumerated and hash-bound before any access.

The mounted Phase 3B package must be enumerable in full and reproduce every bound digest. An extra
module is as much a failure as a missing one: an unenumerated file that executes is exactly the gap
this binding exists to close.

Three groups are bound together, because all three affect the produced records:

  * the mounted layer itself (this package);
  * `spq1/models.py`, the frozen decision-record seam, bound by the Phase 3A run specification;
  * the 15 core SPQ-1 producer modules, bound to their Phase 2B development-run identities so the
    validation window is produced by byte-identical economic code (R-PROD).
"""

from __future__ import annotations

import hashlib
import os

from . import closure as _CLOSURE

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPQ1 = os.path.abspath(os.path.join(_HERE, "..", "spq1"))

# R-PROD: byte-identical to Phase 2B commit 1cc98f5 (MR002_Phase3B_ProducerIdentityContinuity_v1.0).
PRODUCER_MODULES = (
    "calendar.py",
    "constants.py",
    "eligibility.py",
    "identities.py",
    "liquidity.py",
    "models.py",
    "normalization.py",
    "producer.py",
    "refusals.py",
    "residuals.py",
    "returns.py",
    "sector_factor.py",
    "sector_pit.py",
    "security_identity.py",
    "stock_regression.py",
)

LAYER_MODULES = ("__init__.py", "enrichment.py", "gap.py", "guard.py", "roster.py", "states.py")


class RosterRefused(Exception):
    """The execution roster does not reproduce its bound identity. The run must not proceed."""


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def enumerate_layer() -> dict[str, str]:
    """Mechanically enumerate the mounted package. Nothing is implicit and nothing is skipped."""
    found = sorted(f for f in os.listdir(_HERE) if f.endswith(".py"))
    return {name: _sha256(os.path.join(_HERE, name)) for name in found}


def enumerate_producer() -> dict[str, str]:
    return {name: _sha256(os.path.join(_SPQ1, name)) for name in sorted(PRODUCER_MODULES)}


def enumerate_closure() -> dict[str, str]:
    """The whole executing import closure, derived mechanically.

    `enumerate_layer` and `enumerate_producer` above are hand-maintained lists, and a hand-
    maintained list is how `spq1/__init__.py` -- which supplies four constants that reach
    GOVERNING_IDENTITIES and therefore every emitted record -- stayed unbound while this roster
    still passed. This group binds every file Python actually executes, package initializers
    included, so nothing can execute unbound.
    """
    root = _CLOSURE.package_root(_HERE)
    return {
        os.path.relpath(p, root).replace(os.sep, "/"): h
        for p, h in _CLOSURE.static_closure(_HERE).items()
    }


def current_roster() -> dict[str, dict[str, str]]:
    return {
        "layer": enumerate_layer(),
        "producer": enumerate_producer(),
        "closure": enumerate_closure(),
    }


def audit_runtime_against(bound_closure: dict[str, str]) -> dict[str, object]:
    """Post-import audit: prove nothing executed that the static binding did not predict.

    Static binding happens before any access (EB-2). This is the check that the static prediction
    was actually complete -- conditional imports, importlib and re-exports cannot be seen by an AST
    walk, so the binding is only trustworthy if runtime agrees with it.
    """
    root = _CLOSURE.package_root(_HERE)
    runtime = _CLOSURE.runtime_closure(root)
    bound_abs = {os.path.abspath(os.path.join(root, rel)): h for rel, h in bound_closure.items()}
    unpredicted = sorted(
        os.path.relpath(p, root).replace(os.sep, "/") for p in set(runtime) - set(bound_abs)
    )
    if unpredicted:
        raise RosterRefused(
            f"executed but NOT bound: {unpredicted}. The static closure was incomplete; the run "
            "must not proceed on an identity that does not cover what ran."
        )
    drift = sorted(
        os.path.relpath(p, root).replace(os.sep, "/")
        for p, h in runtime.items()
        if bound_abs.get(p) not in (None, h)
    )
    if drift:
        raise RosterRefused(f"a module changed identity between binding and execution: {drift}")
    return {"runtime_modules_observed": len(runtime), "unpredicted": 0, "drift": 0}


def verify(bound: dict[str, dict[str, str]]) -> dict[str, object]:
    """Fail closed on drift, on a missing module, and on an extra module.

    Returns the verification detail on success so a caller can publish it as evidence; raises
    otherwise. There is no partial-pass branch.
    """
    actual = current_roster()
    problems: list[str] = []
    for group in ("layer", "producer", "closure"):
        want, have = bound.get(group, {}), actual[group]
        missing = sorted(set(want) - set(have))
        extra = sorted(set(have) - set(want))
        drift = sorted(m for m in set(want) & set(have) if want[m] != have[m])
        if missing:
            problems.append(f"{group}: missing {missing}")
        if extra:
            problems.append(f"{group}: unbound module present {extra}")
        if drift:
            problems.append(f"{group}: digest drift {drift}")
    if not actual["layer"] or not actual["producer"] or not actual["closure"]:
        problems.append("empty enumeration - a roster that binds nothing proves nothing")
    if problems:
        raise RosterRefused("; ".join(problems))
    return {
        "layer_modules": len(actual["layer"]),
        "producer_modules": len(actual["producer"]),
        "closure_files": len(actual["closure"]),
        "drift": 0,
        "missing": 0,
        "extra": 0,
        "roster": actual,
    }
