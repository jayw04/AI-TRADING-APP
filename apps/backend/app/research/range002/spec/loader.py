"""Spec loading and the read-only :class:`SpecView` the results guard consumes (WP0.2 / WP0.3).

Files are JSON (a strict subset of YAML 1.2, so a ``.yaml`` name is honest). PyYAML is not a
declared dependency of this repository and adding one needs an ADR, so the freeze path does not
use it. Duplicate keys are rejected so a hand edit cannot hide a value behind a repeat.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from app.research.range002.spec.hashing import content_sha256, loads_strict
from app.research.range002.spec.immutable import deep_freeze
from app.research.range002.spec.schema import (
    DraftSpec,
    FrozenSpec,
    _non_distinct_signoff_roles,
    _signoff_invisible_char_roles,
)


class SpecSchemaError(ValueError):
    """The file does not satisfy the schema. ``problems`` names every offending field."""

    def __init__(self, problems: list[str]) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("spec schema errors: " + "; ".join(problems))


class SpecHashMismatchError(ValueError):
    """The content no longer hashes to the recorded ``signoff.spec_sha256``. Loader refuses."""

    def __init__(self, recorded: str, computed: str) -> None:
        self.recorded = recorded
        self.computed = computed
        super().__init__(
            f"frozen spec was modified after freezing: recorded {recorded}, content hashes to "
            f"{computed}"
        )


class SpecViewNotCopyableError(TypeError):
    """A minted ``SpecView`` was copied, deep-copied or pickled: refused (the copy would carry
    the loader's mint)."""


def _read_json(path: Path) -> Any:
    try:
        return loads_strict(path.read_bytes())
    except (ValueError, OSError) as exc:  # CanonicalisationError is a ValueError
        raise SpecSchemaError([f"{path}: {exc}"]) from exc


def parse_draft(payload: Any) -> DraftSpec:
    """Validate a decoded payload. Unknown keys, missing P0 keys and bad shapes all raise
    :class:`SpecSchemaError` with dotted field names."""
    try:
        # Strict JSON-mode validation: no lax coercion ("300", 1 for bool); ISO date strings
        # and arrays are the only accepted encodings for dates and tuples.
        return DraftSpec.model_validate_json(json.dumps(payload), strict=True)
    except ValidationError as exc:
        problems = sorted(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise SpecSchemaError(problems) from exc
    except (TypeError, ValueError) as exc:
        raise SpecSchemaError([f"payload is not strict JSON: {exc}"]) from exc


def load_draft(path: Path) -> DraftSpec:
    return parse_draft(_read_json(Path(path)))


def spec_sha256(spec: DraftSpec) -> str:
    """Stable hash of the spec content (everything except the ``signoff`` block)."""
    return content_sha256(spec.hashable_payload())


@dataclass(frozen=True)
class SpecView:
    """Read-only view of a loaded frozen spec. This is the contract the results guard builds on.

    Attributes
    ----------
    spec_sha256        recomputed content hash (never the recorded one).
    is_signed          True only if every sign-off field is present AND the recorded hash equals
                       ``spec_sha256``. An unsigned spec is unusable for any guarded run.
    partitions         name -> (start, end) for ``development_selection``,
                       ``development_confirmation`` and ``holdout``; inclusive dates.
    exposed_windows    exposure windows (inclusive) that no decisive run may touch.
    p3_criteria        the D17 block, or None.
    exits_candidates   tuple of :class:`ExitCandidate`, or None.
    exits_selection    :class:`ExitSelection`, or None.
    unusable_reasons   why ``is_signed`` is False (empty when signed).
    exposure_signed    ``governance.exposure_signed`` (D01 record, shape open), or None.
    registry_genesis_id  ``governance.registry_genesis_id`` (P0), or None while unset.
    max_p3a_attempts / max_p3b_attempts  ``p3.max_p3a_attempts`` / ``p3.max_p3b_attempts`` (P0).

    Immutability (round 4): ``p3_criteria``, ``exits_candidates``, ``exits_selection`` and
    ``exposure_signed`` are DEEP-FROZEN COPIES (:func:`spec.immutable.deep_freeze`: mappings are
    ``MappingProxyType``, sequences are tuples, models become frozen mappings), so mutating the
    original loaded dicts cannot change what a view exposes and the view's values cannot be
    item-assigned. The dataclass is frozen, so its attributes cannot be rebound. This is NOT
    protection against code execution in this process (Level 2, design-only).

    Provenance (Level 1: accidental misuse and casual bypass): only :func:`load_frozen` stamps a
    view with a private mint, and ``spec_adapter.to_guard_view`` accepts only stamped views, so
    a hand-built ``SpecView(is_signed=True, ...)`` or ``dataclasses.replace(view, ...)`` (the
    mint is a non-init field and is not carried over) is refused. A minted view also REFUSES
    ``copy.copy`` / ``copy.deepcopy`` / pickling (:class:`SpecViewNotCopyableError`), because a
    plain copy would carry the mint. That is the whole guarantee: a minted view cannot be
    duplicated through the standard copy protocols; code that reads the module-private mint or
    writes ``_minted`` directly is outside the threat model. "Signed" means the sign-off fields
    are non-empty and the recorded hash equals the recomputed hash; it is not an authenticated
    signature (Level 2, design pending).
    """

    spec_sha256: str
    is_signed: bool
    partitions: Mapping[str, tuple[date, date]]
    exposed_windows: tuple[tuple[date, date], ...]
    p3_criteria: Any | None
    exits_candidates: tuple[Mapping[str, Any], ...] | None
    exits_selection: Mapping[str, Any] | None
    unusable_reasons: tuple[str, ...] = ()
    exposure_signed: Any | None = None
    registry_genesis_id: str | None = None
    max_p3a_attempts: int | None = None
    max_p3b_attempts: int | None = None
    _minted: object = field(default=None, init=False, repr=False, compare=False)

    def __copy__(self) -> SpecView:
        raise SpecViewNotCopyableError("a SpecView cannot be copied (it would carry the mint)")

    def __deepcopy__(self, memo: Any) -> SpecView:
        raise SpecViewNotCopyableError("a SpecView cannot be copied (it would carry the mint)")

    def __reduce__(self) -> Any:
        raise SpecViewNotCopyableError("a SpecView cannot be pickled or copied")


_MINT = object()  # module-private: only load_frozen() stamps a view with it


def is_loader_minted(view: object) -> bool:
    """True only for a ``SpecView`` produced by :func:`load_frozen` (not copied or rebuilt)."""
    return type(view) is SpecView and view._minted is _MINT


def _build_view(
    spec: DraftSpec, *, spec_sha256: str, unusable_reasons: tuple[str, ...]
) -> SpecView:
    p = spec.partitions
    return SpecView(
        spec_sha256=spec_sha256,
        is_signed=not unusable_reasons,
        partitions=MappingProxyType(
            {
                "development_selection": p.development_selection,
                "development_confirmation": p.development_confirmation,
                "holdout": p.holdout,
            }
        ),
        exposed_windows=tuple(p.exposed),
        p3_criteria=deep_freeze(spec.p3.criteria),
        exits_candidates=deep_freeze(spec.exits.candidates),
        exits_selection=deep_freeze(spec.exits.selection),
        unusable_reasons=unusable_reasons,
        exposure_signed=deep_freeze(spec.governance.exposure_signed),
        registry_genesis_id=spec.governance.registry_genesis_id,
        max_p3a_attempts=spec.p3.max_p3a_attempts,
        max_p3b_attempts=spec.p3.max_p3b_attempts,
    )


def load_frozen(path: Path) -> SpecView:
    """Load a frozen spec file.

    Raises :class:`SpecSchemaError` for schema problems, :class:`UnsetP0FieldsError` if any P0
    field is unset, and :class:`SpecHashMismatchError` if the content was edited after freezing.
    A spec with missing/empty sign-off is returned with ``is_signed=False`` rather than raised,
    so callers can report *why* it is unusable.
    """
    spec = load_draft(Path(path))
    FrozenSpec.from_draft(spec)  # raises UnsetP0FieldsError naming every unset field
    computed = spec_sha256(spec)
    recorded = spec.signoff.spec_sha256
    if recorded is not None and recorded != computed:
        raise SpecHashMismatchError(recorded, computed)
    reasons = [f"{name} missing" for name in spec.missing_signoff_fields()]
    reasons.extend(
        f"signoff.{role} contains invisible or control characters ({', '.join(codes)})"
        for role, codes in _signoff_invisible_char_roles(spec.signoff)
    )
    reasons.extend(
        "sign-off roles not distinct: " + " == ".join(f"signoff.{r}" for r in group)
        for group in _non_distinct_signoff_roles(spec.signoff)
    )
    if recorded is None:
        reasons.append("signoff.spec_sha256 missing")
    view = _build_view(spec, spec_sha256=computed, unusable_reasons=tuple(reasons))
    object.__setattr__(view, "_minted", _MINT)  # only this function mints a trusted view
    return view


# Spec handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = (
    "parse_draft",
    "load_draft",
    "spec_sha256",
    "is_loader_minted",
    "load_frozen",
    "SpecView.__copy__",
    "SpecView.__deepcopy__",
    "SpecView.__reduce__",
)
