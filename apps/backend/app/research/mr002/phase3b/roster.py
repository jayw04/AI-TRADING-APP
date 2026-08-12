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


def current_roster() -> dict[str, dict[str, str]]:
    return {"layer": enumerate_layer(), "producer": enumerate_producer()}


def verify(bound: dict[str, dict[str, str]]) -> dict[str, object]:
    """Fail closed on drift, on a missing module, and on an extra module.

    Returns the verification detail on success so a caller can publish it as evidence; raises
    otherwise. There is no partial-pass branch.
    """
    actual = current_roster()
    problems: list[str] = []
    for group in ("layer", "producer"):
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
    if not actual["layer"] or not actual["producer"]:
        problems.append("empty enumeration - a roster that binds nothing proves nothing")
    if problems:
        raise RosterRefused("; ".join(problems))
    return {
        "layer_modules": len(actual["layer"]),
        "producer_modules": len(actual["producer"]),
        "drift": 0,
        "missing": 0,
        "extra": 0,
        "roster": actual,
    }
