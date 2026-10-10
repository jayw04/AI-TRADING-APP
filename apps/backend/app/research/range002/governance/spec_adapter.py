"""Adapter from the loaded frozen spec (PR 2) to the guard's ``FrozenSpecView`` (PR 3).

The two were built independently; this is the single place where they meet. It
carries these semantic obligations, each covered by ``test_spec_integration``:

* ``spec_sha256`` is the loader's recomputed hash, never a recorded one;
* ``is_signed`` is the loader's flag (sign-off fields non-empty AND recorded hash equals the
  recomputed hash), passed through unchanged. That is "frozen, sign-off fields present", NOT
  an authenticated signature: nothing verifies who typed the sign-off (Level 2, design
  pending);
* every window the spec marks exposed reaches the guard as a ``DateRange``;
* ``exposure_signed`` is the spec's D01 record, passed through for the guard's
  exposure-ledger binding check.

* ``registry_genesis_id`` and the two attempt limits are passed through for the guard's
  registry-binding and attempt-limit checks.

``GuardSpecView`` is "unforgeable by convention" (Level 1: accidental misuse and casual
bypass): its constructor demands a module-private token that only :func:`to_guard_view`
holds, ``authorize`` accepts nothing else (``type(spec) is GuardSpecView``), and
:func:`to_guard_view` itself accepts only a ``SpecView`` stamped by ``load_frozen``. A
duck-typed object, a hand-built ``SpecView``, a ``dataclasses.replace`` copy and a
``copy.copy`` / ``copy.deepcopy`` of a minted view are refused. Values handed to the guard are
deep-frozen copies (see ``GuardSpecView``). Reaching the private tokens is code execution,
outside the threat model (Level 2, design-only).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, final

from app.research.range002.governance.errors import SpecViewNotTrustedError
from app.research.range002.governance.model import DateRange
from app.research.range002.spec.immutable import deep_freeze
from app.research.range002.spec.loader import SpecView, is_loader_minted

_ISSUE_VIEW = object()  # module-private: only to_guard_view() holds it


@final
class _Partitions:
    __slots__ = ("confirmation", "holdout", "selection")

    selection: DateRange
    confirmation: DateRange
    holdout: DateRange

    def __init__(self, selection: DateRange, confirmation: DateRange, holdout: DateRange) -> None:
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "confirmation", confirmation)
        object.__setattr__(self, "holdout", holdout)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("_Partitions is immutable")


@final
class GuardSpecView:
    """Spec view built only by :func:`to_guard_view`.

    Guarantee (Level 1: accidental misuse and casual bypass), exactly:

    * attributes cannot be rebound or deleted (``__setattr__`` / ``__delattr__`` raise);
    * ``p3_criteria``, ``exits_candidates``, ``exits_selection`` and ``exposure_signed`` are
      DEEP-FROZEN COPIES taken at construction (mappings are ``MappingProxyType``, sequences are
      tuples), so mutating the original loaded dicts or lists afterwards cannot change what the
      guard sees, and the guard-visible values cannot be item-assigned;
    * ``copy.copy`` / ``copy.deepcopy`` / pickling of a view are refused.

    Not guaranteed (Level 2, design-only): resistance to code execution in this process, e.g.
    ``object.__setattr__`` on the instance, reaching the private issue token, or digging the
    private dict out from behind a ``MappingProxyType``.
    """

    __slots__ = (
        "exits_candidates",
        "exits_selection",
        "exposed",
        "exposure_signed",
        "is_signed",
        "max_p3a_attempts",
        "max_p3b_attempts",
        "p3_criteria",
        "partitions",
        "registry_genesis_id",
        "spec_sha256",
    )

    spec_sha256: str
    is_signed: bool
    partitions: _Partitions
    p3_criteria: Any | None
    exits_candidates: Any | None
    exits_selection: Any | None
    exposed: Sequence[DateRange]
    exposure_signed: Any | None
    registry_genesis_id: str | None
    max_p3a_attempts: int | None
    max_p3b_attempts: int | None

    def __init__(
        self,
        issue_token: object,
        *,
        spec_sha256: str,
        is_signed: bool,
        partitions: _Partitions,
        p3_criteria: Any | None,
        exits_candidates: Any | None,
        exits_selection: Any | None,
        exposed: Sequence[DateRange],
        exposure_signed: Any | None,
        registry_genesis_id: str | None,
        max_p3a_attempts: int | None,
        max_p3b_attempts: int | None,
    ) -> None:
        if issue_token is not _ISSUE_VIEW:
            raise SpecViewNotTrustedError(
                "GuardSpecView can only be built by spec_adapter.to_guard_view()"
            )
        for name, value in (
            ("spec_sha256", spec_sha256),
            ("is_signed", is_signed),
            ("partitions", partitions),
            ("p3_criteria", deep_freeze(p3_criteria)),
            ("exits_candidates", deep_freeze(exits_candidates)),
            ("exits_selection", deep_freeze(exits_selection)),
            ("exposed", tuple(exposed)),
            ("exposure_signed", deep_freeze(exposure_signed)),
            ("registry_genesis_id", registry_genesis_id),
            ("max_p3a_attempts", max_p3a_attempts),
            ("max_p3b_attempts", max_p3b_attempts),
        ):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("GuardSpecView is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("GuardSpecView is immutable")

    def __reduce__(self) -> Any:
        raise SpecViewNotTrustedError("GuardSpecView cannot be pickled or copied")

    def __copy__(self) -> Any:
        raise SpecViewNotTrustedError("GuardSpecView cannot be copied")

    def __deepcopy__(self, memo: Any) -> Any:
        raise SpecViewNotTrustedError("GuardSpecView cannot be copied")


def to_guard_view(view: SpecView) -> GuardSpecView:
    """The module's factory -- the only way to obtain a view ``authorize`` will accept."""

    if not is_loader_minted(view):
        raise SpecViewNotTrustedError(
            "to_guard_view accepts only a SpecView produced by spec.loader.load_frozen(); a "
            "hand-built, copied or dataclasses.replace()d SpecView is refused"
        )

    def rng(key: str) -> DateRange:
        start, end = view.partitions[key]
        return DateRange(start, end)

    return GuardSpecView(
        _ISSUE_VIEW,
        spec_sha256=view.spec_sha256,
        is_signed=view.is_signed,
        partitions=_Partitions(
            selection=rng("development_selection"),
            confirmation=rng("development_confirmation"),
            holdout=rng("holdout"),
        ),
        p3_criteria=view.p3_criteria,
        exits_candidates=view.exits_candidates,
        exits_selection=view.exits_selection,
        exposed=tuple(DateRange(s, e) for s, e in view.exposed_windows),
        exposure_signed=view.exposure_signed,
        registry_genesis_id=view.registry_genesis_id,
        max_p3a_attempts=view.max_p3a_attempts,
        max_p3b_attempts=view.max_p3b_attempts,
    )
