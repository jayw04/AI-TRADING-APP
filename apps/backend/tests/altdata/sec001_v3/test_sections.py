"""A gate may not report PASS unless every declared check demonstrably ran.

The control added after 2026-08-24, when an arrival gate printed PASS while a whole section
had silently not executed. The checks in that section were fine; they simply never ran, and
a gate that only accumulates failures cannot tell "nothing failed" from "nothing happened".
"""

from __future__ import annotations

import pytest

from app.altdata.sec001_v3.sections import GateIncomplete, GateRun, SectionSpec

REGISTRY = (
    SectionSpec("blob identity", 2, "frozen source blobs match Git objects"),
    SectionSpec("module origin", 1, "modules loaded from the frozen root"),
)


def test_complete_run_passes() -> None:
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("sic_history", True, "48779ada")
        gate.check("crosswalk", True, "f3b58008")
    with gate.section("module origin"):
        gate.check("origin under frozen root", True)

    report = gate.finish()
    assert report["passed"] is True
    assert report["checks_executed"] == report["checks_declared"] == 3
    assert report["structural_failures"] == []


def test_skipped_section_fails_even_though_no_check_failed() -> None:
    """The exact 2026-08-24 failure mode. Every check that ran, passed."""
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("sic_history", True)
        gate.check("crosswalk", True)
    # "module origin" is never entered — e.g. an edit that failed to match.

    report = gate.finish()
    assert report["failed_checks"] == []          # nothing failed...
    assert report["passed"] is False              # ...and it still must not pass
    assert any("never executed" in p and "module origin" in p
               for p in report["structural_failures"])
    assert "GATE: FAIL" in gate.render(report)


def test_section_with_too_few_checks_fails() -> None:
    """Partial execution is caught as precisely as total absence."""
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("sic_history", True)          # declared 2, ran 1
    with gate.section("module origin"):
        gate.check("origin", True)

    report = gate.finish()
    assert report["passed"] is False
    assert any("ran 1 checks, declared 2" in p for p in report["structural_failures"])


def test_section_with_too_many_checks_also_fails() -> None:
    """Drift in either direction means the registry no longer describes the gate."""
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("a", True)
        gate.check("b", True)
        gate.check("c", True)
    with gate.section("module origin"):
        gate.check("origin", True)

    report = gate.finish()
    assert report["passed"] is False
    assert any("ran 3 checks, declared 2" in p for p in report["structural_failures"])


def test_section_that_raises_is_reported_as_incomplete() -> None:
    gate = GateRun(REGISTRY)
    with pytest.raises(ValueError), gate.section("blob identity"):
        gate.check("sic_history", True)
        raise ValueError("frozen file missing")

    report = gate.finish()
    assert report["passed"] is False
    assert any("ran 1 checks, declared 2" in p for p in report["structural_failures"])


def test_undeclared_section_is_rejected_at_entry() -> None:
    gate = GateRun(REGISTRY)
    with pytest.raises(GateIncomplete, match="not in the declared registry"), \
            gate.section("improvised extra section"):
        pass


def test_duplicate_entry_is_rejected() -> None:
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("a", True)
        gate.check("b", True)
    with pytest.raises(GateIncomplete, match="entered twice"), gate.section("blob identity"):
        pass


def test_checks_outside_a_section_are_structural_failures() -> None:
    gate = GateRun(REGISTRY)
    gate.check("orphan", True)
    with gate.section("blob identity"):
        gate.check("a", True)
        gate.check("b", True)
    with gate.section("module origin"):
        gate.check("origin", True)

    report = gate.finish()
    assert report["passed"] is False
    assert any("outside any section" in p for p in report["structural_failures"])


def test_empty_registry_is_rejected() -> None:
    """A gate with nothing declared can only ever be vacuously green — trap #5."""
    with pytest.raises(GateIncomplete, match="vacuously green"):
        GateRun(())


def test_duplicate_registry_names_rejected() -> None:
    with pytest.raises(GateIncomplete, match="duplicate section names"):
        GateRun((SectionSpec("x", 1), SectionSpec("x", 1)))


def test_a_real_failure_still_fails() -> None:
    """Positive control: the completeness machinery does not mask ordinary failures."""
    gate = GateRun(REGISTRY)
    with gate.section("blob identity"):
        gate.check("sic_history", True)
        gate.check("crosswalk", False, "got 258c570d")
    with gate.section("module origin"):
        gate.check("origin", True)

    report = gate.finish()
    assert report["passed"] is False
    assert report["failed_checks"] == ["crosswalk"]
    assert report["structural_failures"] == []
