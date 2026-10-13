"""Planned-run vs prior-exposure ledger entries (owner decision 2026-10-13).

Synthetic dates and ids only. A ``planned_run`` entry records, before execution, the access one
run is about to make; it authorises exactly that phase / partition / range and is not prior
contamination. The actual exposure afterwards is a ``prior_exposure`` entry and blocks like every
pre-existing entry. Nothing is omitted from a ledger to satisfy the guard.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from app.research.range002.governance.errors import ExposureLedgerError, ExposureOverlapError
from app.research.range002.governance.exposure_ledger import (
    KIND_PLANNED_RUN,
    KIND_PRIOR_EXPOSURE,
    ExposureLedger,
)
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.run_registry import RunRegistry

from .conftest import DECIDED_LEDGER, LEDGER_DECISION_JSON, new_registry, spec_for
from .test_results_guard import go

Q1 = DateRange(date(2016, 1, 1), date(2016, 3, 31))


def _entry(entry_id: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": entry_id,
        "start": start,
        "end": end,
        "description": "synthetic",
        "source": "synthetic",
        "observed_by": "synthetic",
        **extra,
    }


def _ledger(*entries: dict[str, Any]) -> ExposureLedger:
    doc = {
        "schema_version": 1,
        "decision": json.loads(LEDGER_DECISION_JSON),
        "entries": list(entries),
    }
    return ExposureLedger.from_text(json.dumps(doc))


def _planned(entry_id: str = "plan-q1", start: str = "2016-01-01", end: str = "2016-03-31",
             phase: str = "P3A", partition: str = "DEVELOPMENT_SELECTION") -> dict[str, Any]:  # fmt: skip
    return _entry(
        entry_id, start, end, kind="planned_run", phase=phase, partition=partition,
        planned_label="screen-q1-planned",
    )  # fmt: skip


@pytest.fixture
def registry(tmp_path: Any) -> RunRegistry:
    return new_registry(tmp_path / "runs.jsonl")


def test_planned_entry_lets_its_own_run_through(registry: RunRegistry) -> None:
    led = _ledger(_planned())
    cap = go(spec_for(led), registry, led, requested_range=Q1)
    assert cap.date_range == Q1
    assert cap.exposure_ledger_sha256 == led.sha256  # the sha binding mechanism is unchanged


def test_planned_entry_authorises_a_sub_range_of_itself(registry: RunRegistry) -> None:
    led = _ledger(_planned())
    sub = DateRange(date(2016, 2, 1), date(2016, 2, 29))
    assert go(spec_for(led), registry, led, requested_range=sub).date_range == sub


def test_request_broader_than_the_planned_range_is_refused(registry: RunRegistry) -> None:
    led = _ledger(_planned())
    wider = DateRange(date(2016, 1, 1), date(2016, 6, 30))
    with pytest.raises(ExposureOverlapError, match="plan-q1"):
        go(spec_for(led), registry, led, requested_range=wider)


def test_planned_entry_does_not_let_a_different_partition_through(registry: RunRegistry) -> None:
    # The planned entry names DEVELOPMENT_SELECTION; a CONFIRMATION request that overlaps it is
    # blocked like a prior exposure (the entry authorises only its own phase/partition).
    led = _ledger(_planned(start="2020-01-01", end="2020-03-31"))
    with pytest.raises(ExposureOverlapError, match="plan-q1"):
        go(
            spec_for(led), registry, led, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION,
            requested_range=DateRange(date(2020, 1, 1), date(2020, 3, 31)),
        )  # fmt: skip


def test_blocking_overlaps_matches_phase_partition_and_coverage() -> None:
    led = _ledger(_planned())
    ok = led.blocking_overlaps(Q1, phase=Phase.P3A, partition=Partition.DEVELOPMENT_SELECTION)
    assert ok == ()
    other_phase = led.blocking_overlaps(Q1, phase=Phase.P2, partition=Partition.REPLAY_RNG001)
    assert [e.id for e in other_phase] == ["plan-q1"]
    assert len(led.overlaps(Q1)) == 1  # the plain overlap query is unchanged


def test_prior_exposure_after_the_run_blocks_later_overlap(registry: RunRegistry) -> None:
    successor = _ledger(_entry("actual-q1", "2016-01-01", "2016-03-31", kind="prior_exposure"))
    # a later request covering Q1 is blocked and must be explicit as exploratory prior exposure
    covering = DateRange(date(2016, 1, 1), date(2016, 12, 31))
    with pytest.raises(ExposureOverlapError, match="actual-q1"):
        go(spec_for(successor), registry, successor, requested_range=covering)
    with pytest.raises(ExposureOverlapError, match="actual-q1"):
        go(spec_for(successor), registry, successor, requested_range=Q1)
    # a later range not touching Q1 passes
    later = DateRange(date(2016, 4, 1), date(2016, 6, 30))
    assert go(spec_for(successor), registry, successor, requested_range=later).date_range == later


def test_a_prior_exposure_is_not_cancelled_by_a_planned_entry(registry: RunRegistry) -> None:
    led = _ledger(_planned(), _entry("actual-q1", "2016-01-01", "2016-03-31"))
    with pytest.raises(ExposureOverlapError, match="actual-q1"):
        go(spec_for(led), registry, led, requested_range=Q1)


def test_entries_without_kind_default_to_prior_exposure() -> None:
    led = ExposureLedger.from_text(DECIDED_LEDGER)
    assert {e.kind for e in led.entries} == {KIND_PRIOR_EXPOSURE}
    assert all(e.phase is None and e.partition is None for e in led.entries)
    planned = _ledger(_planned()).entries[0]
    assert planned.kind == KIND_PLANNED_RUN and planned.planned_label == "screen-q1-planned"


@pytest.mark.parametrize(
    "bad",
    [
        _entry("e", "2016-01-01", "2016-01-31", kind="planned"),  # unknown kind
        _entry("e", "2016-01-01", "2016-01-31", kind=None),  # not a string
        _entry("e", "2016-01-01", "2016-01-31", kind="prior_exposure", phase="P3A"),  # stray field
        _entry("e", "2016-01-01", "2016-01-31", kind="planned_run"),  # no phase/partition/label
        _entry("e", "2016-01-01", "2016-01-31", kind="planned_run", phase="P3A",
               partition="HOLDOUT", planned_label="x"),  # partition not of the phase
        _entry("e", "2016-01-01", "2016-01-31", kind="planned_run", phase="P9",
               partition="HOLDOUT", planned_label="x"),  # unknown phase
        _entry("e", "2016-01-01", "2016-01-31", kind="planned_run", phase="P3A",
               partition="DEVELOPMENT_SELECTION", planned_label="x", extra="y"),  # unknown key
    ],
)  # fmt: skip
def test_malformed_kind_fields_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ExposureLedgerError):
        _ledger(bad)
