"""PU-1 licence scopes and taint propagation (pure; no I/O, no registry access).

Order of restriction: ``COMMERCIAL_OK`` < ``UNKNOWN`` <= ``PERSONAL``. ``UNKNOWN`` and ``PERSONAL``
both BLOCK presentation; the distinction is only diagnostic ("we know it is personal-use" versus
"nobody has read the contract"). Taint propagates through every derivation: the scope of an output
is the most restrictive scope among its inputs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class LicenseScope(IntEnum):
    """Higher value = more restrictive. ``max`` of a set of scopes is the combined scope."""

    COMMERCIAL_OK = 0
    UNKNOWN = 1
    PERSONAL = 2

    @classmethod
    def parse(cls, value: object) -> LicenseScope:
        """Parse a stored scope. Anything unrecognised is ``UNKNOWN`` (fail closed)."""
        if isinstance(value, LicenseScope):
            return value
        if isinstance(value, str):
            try:
                return cls[value.strip().upper()]
            except KeyError:
                return cls.UNKNOWN
        return cls.UNKNOWN

    @property
    def blocks_presentation(self) -> bool:
        return self is not LicenseScope.COMMERCIAL_OK


def combine_scopes(*scopes: LicenseScope | str | None) -> LicenseScope:
    """Most restrictive of ``scopes``. No inputs => ``UNKNOWN`` (an artifact whose lineage is empty
    has no licence evidence, so it is not presentable)."""
    parsed = [LicenseScope.parse(s) for s in scopes]
    if not parsed:
        return LicenseScope.UNKNOWN
    return max(parsed)


@dataclass(frozen=True)
class Scoped[T]:
    """A value together with the licensed sources it was derived from (its lineage).

    ``derive`` is the only way to build a child: the child's sources are the union of every
    parent's sources, so taint cannot be dropped by a join, resample or backtest step.
    """

    value: T
    sources: frozenset[str]

    @staticmethod
    def of(value: T, sources: Iterable[str]) -> Scoped[T]:
        return Scoped(value, frozenset(_norm(s) for s in sources))


def derive(fn: Callable[..., Any], *parents: Scoped[Any], **kwargs: Any) -> Scoped[Any]:
    """Apply ``fn`` to the parents' values; the result carries the union of the parents' sources."""
    sources: frozenset[str] = frozenset()
    for p in parents:
        sources = sources | p.sources
    return Scoped(fn(*(p.value for p in parents), **kwargs), sources)


def _norm(source_id: str) -> str:
    return str(source_id).strip().lower()
