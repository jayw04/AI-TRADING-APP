"""The crawler must be structurally incapable of emitting a coverage quantity.

CoverageFreeze v1.0 is an anti-peek control: the evaluation-period decision is only
defensible while nobody has seen which start dates survive. A coverage number produced
during acquisition — before the one-shot adjudication artifact spends ``5b26ffa2…`` —
destroys that ordering whether or not anyone looks at it.

So this is not a style test. It asserts that serialization *fails* for all ten frozen
names, at every depth, through every writer the package exposes, and that the package's own
emitted record types declare none of them.

Each test carries a positive control. Trap #5 of 2026-08-24 was a check that passed because
it was structurally incapable of failing; a suite that only asserts "this raises" can drift
into asserting nothing if the guard starts rejecting everything.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import pkgutil
from dataclasses import dataclass

import pytest

import app.altdata.sec001_v3 as pkg
from app.altdata.sec001_v3.forbidden import (
    FORBIDDEN_COVERAGE_FIELDS,
    ForbiddenCoverageField,
    append_jsonl,
    assert_dataclass_clean,
    assert_no_forbidden_fields,
    dump_json,
    dumps,
)

EXPECTED_FORBIDDEN = {
    "name_coverage_pct",
    "slot_coverage_pct",
    "window_coverage_pct",
    "qualifying_slot_count",
    "failing_slot_count",
    "earliest_qualifying_start",
    "final_evaluation_start",
    "theta_name_pass",
    "theta_window_pass",
    "coverage_gate_result",
}


def test_registry_is_exactly_the_frozen_ten() -> None:
    """Drift in either direction is a governance change, not a refactor."""
    assert FORBIDDEN_COVERAGE_FIELDS == EXPECTED_FORBIDDEN
    assert len(FORBIDDEN_COVERAGE_FIELDS) == 10


@pytest.mark.parametrize("field", sorted(EXPECTED_FORBIDDEN))
def test_top_level_field_cannot_serialize(field: str) -> None:
    with pytest.raises(ForbiddenCoverageField) as exc:
        dumps({field: 0.95})
    assert exc.value.field == field


@pytest.mark.parametrize("field", sorted(EXPECTED_FORBIDDEN))
def test_nested_field_cannot_serialize(field: str) -> None:
    """Depth is not an escape hatch — nor is hiding inside a list."""
    payload = {"crawl": {"units": [{"cik": 320193, "stats": {field: 1}}]}}
    with pytest.raises(ForbiddenCoverageField) as exc:
        dumps(payload)
    assert exc.value.field == field
    assert "units" in exc.value.path


@pytest.mark.parametrize("field", sorted(EXPECTED_FORBIDDEN))
def test_dataclass_field_cannot_serialize(field: str) -> None:
    """A dataclass is asdict-ed before the walk, so it gets no free pass."""
    record = dataclasses.make_dataclass("Sneaky", [("cik", int), (field, float)])
    with pytest.raises(ForbiddenCoverageField):
        dumps(record(320193, 0.95))


@pytest.mark.parametrize("field", sorted(EXPECTED_FORBIDDEN))
def test_declaring_the_field_fails_at_import_time(field: str) -> None:
    """``assert_dataclass_clean`` is what makes the failure land on the developer's
    machine at import rather than on the host at the crawl's last write."""
    record = dataclasses.make_dataclass("Sneaky", [("cik", int), (field, float)])
    with pytest.raises(ForbiddenCoverageField):
        assert_dataclass_clean(record)


@pytest.mark.parametrize("field", sorted(EXPECTED_FORBIDDEN))
def test_file_writers_refuse_and_leave_no_file(field: str, tmp_path) -> None:
    """The guard runs before any byte is written, so a refused write leaves nothing."""
    target = tmp_path / "out.json"
    with pytest.raises(ForbiddenCoverageField):
        dump_json({field: 1}, target)
    assert not target.exists()

    line_target = tmp_path / "out.jsonl"
    with pytest.raises(ForbiddenCoverageField):
        append_jsonl({field: 1}, line_target)
    assert not line_target.exists()


def test_case_sensitivity_is_deliberate() -> None:
    """The ban is on the exact frozen vocabulary.

    A differently-cased name is a *different* field, and silently banning it would make the
    guard's scope unpredictable. Recorded so the behaviour is a decision, not an accident.
    """
    assert dumps({"Name_Coverage_Pct": 1})


def test_clean_records_still_serialize(tmp_path) -> None:
    """Positive control — the guard rejects the ten names, not serialization at large."""
    payload = {"cik": 320193, "ticker": "AAPL", "observations": 41, "segments": 2}
    assert json.loads(dumps(payload)) == payload

    target = tmp_path / "clean.json"
    dump_json(payload, target)
    assert json.loads(target.read_text(encoding="utf-8")) == payload

    lines = tmp_path / "clean.jsonl"
    append_jsonl(payload, lines)
    append_jsonl(payload, lines)
    assert len(lines.read_text(encoding="utf-8").strip().splitlines()) == 2

    assert_no_forbidden_fields(payload)  # does not raise


def test_no_package_dataclass_declares_a_forbidden_field() -> None:
    """Sweeps the whole package, so a new module cannot opt out by not being imported."""
    checked = 0
    for info in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(f"{pkg.__name__}.{info.name}")
        for obj in vars(module).values():
            if isinstance(obj, type) and dataclasses.is_dataclass(obj):
                assert_dataclass_clean(obj)
                checked += 1
    # Guards the sweep itself: if the package stopped exporting dataclasses, this test
    # would otherwise pass by iterating over nothing.
    assert checked >= 5, f"expected the package to expose dataclasses, found {checked}"


def test_guard_survives_recursive_and_exotic_containers() -> None:
    """Sets, tuples and nested lists are all walked; strings are not walked element-wise."""

    @dataclass
    class Inner:
        theta_name_pass: bool

    with pytest.raises(ForbiddenCoverageField):
        dumps({"a": [({"b": {"c": [Inner(True)]}},)]})
    # A string that merely *contains* a forbidden name is data, not a field.
    assert dumps({"note": "coverage_gate_result is computed elsewhere"})
