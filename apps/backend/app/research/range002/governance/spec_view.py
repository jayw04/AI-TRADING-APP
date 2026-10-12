"""The slice of the frozen spec that governance needs.

The real spec schema (WP0.2) is built separately; governance is coded against
this structural ``Protocol`` so the two can be integrated without either
importing the other. Assumptions recorded for the integrator:

* ``spec_sha256`` is the 64-hex canonical hash of the frozen spec.
* ``has_run_decision`` is True only when the spec's meeting-decision reference is present, its
  decision is exactly ``approved``, its scope includes ``run`` and the recorded spec hash equals
  the recomputed one (content-bound; the minutes file it cites is checked by the guard).
* ``decision`` / ``decision_scope`` / ``decision_partitions`` / ``minutes_path`` /
  ``minutes_sha256`` / ``strategy_version`` / ``baseline_id`` are that reference's fields; the
  guard re-checks decision, scope, partition and the minutes file's hash itself.
* ``partitions.selection/confirmation/holdout`` are inclusive ``DateRange``s.
* ``p3_criteria``, ``exits_candidates``, ``exits_selection`` are ``None`` while
  the corresponding P0 decision (D17 / D19) is unset; any other value (even an
  empty one) counts as set -- governance never inspects their content.
* ``exposed`` is the spec's own list of exposed date ranges.
* ``exposure_signed`` is the spec's ``governance.exposure_signed`` record; the guard requires
  it to carry ``{"exposure_ledger_sha256": <64hex>}`` equal to the ledger in use.

* ``registry_genesis_id`` is ``governance.registry_genesis_id`` (the genesis id of the one registry
  this spec may open runs in); ``max_p3a_attempts`` / ``max_p3b_attempts`` are ``p3.*`` P0 values.
  ``None`` means unset, and the guard then refuses (no default for any of them).

This Protocol documents the shape only: ``authorize`` accepts nothing but the adapter's
factory-built ``GuardSpecView`` (see ``spec_adapter``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from app.research.range002.governance.model import DateRange


@runtime_checkable
class PartitionRangesView(Protocol):
    @property
    def selection(self) -> DateRange: ...

    @property
    def confirmation(self) -> DateRange: ...

    @property
    def holdout(self) -> DateRange: ...


@runtime_checkable
class FrozenSpecView(Protocol):
    @property
    def spec_sha256(self) -> str: ...

    @property
    def has_run_decision(self) -> bool: ...

    @property
    def decision(self) -> str | None: ...

    @property
    def decision_scope(self) -> tuple[str, ...]: ...

    @property
    def decision_partitions(self) -> tuple[str, ...]: ...

    @property
    def minutes_path(self) -> str | None: ...

    @property
    def minutes_sha256(self) -> str | None: ...

    @property
    def strategy_version(self) -> str | None: ...

    @property
    def baseline_id(self) -> str | None: ...

    @property
    def partitions(self) -> PartitionRangesView: ...

    @property
    def p3_criteria(self) -> Any | None: ...

    @property
    def exits_candidates(self) -> Any | None: ...

    @property
    def exits_selection(self) -> Any | None: ...

    @property
    def exposed(self) -> Sequence[DateRange]: ...

    @property
    def exposure_signed(self) -> Any | None: ...

    @property
    def registry_genesis_id(self) -> str | None: ...

    @property
    def max_p3a_attempts(self) -> int | None: ...

    @property
    def max_p3b_attempts(self) -> int | None: ...
