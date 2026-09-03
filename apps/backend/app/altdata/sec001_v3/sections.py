"""A gate harness that cannot report PASS for checks it never ran.

The control this module implements comes from a failure on 2026-08-24: an arrival gate
printed PASS while an entire section had silently not executed. Nothing was wrong with the
checks in that section — they simply never ran, because an edit that was supposed to insert
them failed to match, and a gate that only accumulates failures has no way to notice
absence. Zero failures out of zero checks is indistinguishable from zero failures out of
twelve.

The fix is to make the expected work a *declaration* that lives apart from the code that
performs it, and to compare the two at the end:

  - every declared section must be entered and completed;
  - each section must contribute exactly the number of checks it declared;
  - the totals must agree.

Any mismatch is a gate FAILURE, reported with the same weight as a substantive check
failing — because operationally it is worse. A failed check tells you something is wrong;
a skipped section tells you that you do not know.

Declaring counts up front does mean the registry has to be updated whenever a section
gains or loses a check. That friction is the point: it converts "I forgot to run it" into
"I have to say so".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.altdata.sec001_v3.forbidden import assert_dataclass_clean


class GateIncomplete(RuntimeError):
    """Raised when a gate's executed work does not match its declared work."""


@dataclass(frozen=True)
class SectionSpec:
    """A declared section and the exact number of checks it must contribute."""

    name: str
    expected_checks: int
    description: str = ""


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    section: str = ""


assert_dataclass_clean(CheckResult)


@dataclass
class GateRun:
    """Executes a declared set of sections and refuses to pass on absence.

    Usage::

        gate = GateRun(REQUIRED_SECTIONS)
        with gate.section("blob identity"):
            gate.check("sic_history blob", got == expected, got[:12])
        report = gate.finish()
    """

    registry: tuple[SectionSpec, ...]
    results: list[CheckResult] = field(default_factory=list)
    entered: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    structural_failures: list[str] = field(default_factory=list)
    _current: str | None = None

    def __post_init__(self) -> None:
        names = [s.name for s in self.registry]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise GateIncomplete(f"duplicate section names in registry: {sorted(duplicates)}")
        if not self.registry:
            raise GateIncomplete("a gate with an empty registry can only ever be vacuously green")

    # -- execution ---------------------------------------------------------------------

    @contextmanager
    def section(self, name: str) -> Iterator[GateRun]:
        spec = self.spec(name)
        if spec is None:
            raise GateIncomplete(
                f"section {name!r} is not in the declared registry; "
                f"add it to the registry rather than running undeclared work"
            )
        if name in self.entered:
            raise GateIncomplete(f"section {name!r} entered twice")
        self.entered.append(name)
        previous, self._current = self._current, name
        try:
            yield self
        finally:
            self._current = previous
            # Completion is recorded only on a clean exit, so a section that raised
            # halfway through is visible as entered-but-not-completed.
            self.completed.append(name)

    def check(self, name: str, condition: object, detail: str = "") -> bool:
        passed = bool(condition)
        self.results.append(
            CheckResult(name=name, passed=passed, detail=detail, section=self._current or "")
        )
        return passed

    def spec(self, name: str) -> SectionSpec | None:
        for s in self.registry:
            if s.name == name:
                return s
        return None

    # -- the completeness assertion ----------------------------------------------------

    def _verify_completeness(self) -> list[str]:
        problems: list[str] = []
        declared = {s.name for s in self.registry}

        missing = [n for n in (s.name for s in self.registry) if n not in self.entered]
        for name in missing:
            problems.append(f"section never executed: {name!r}")

        incomplete = [n for n in self.entered if n not in self.completed]
        for name in incomplete:
            problems.append(f"section entered but did not complete: {name!r}")

        undeclared = sorted({r.section for r in self.results} - declared - {""})
        for name in undeclared:
            problems.append(f"checks recorded under undeclared section: {name!r}")

        orphaned = [r.name for r in self.results if not r.section]
        if orphaned:
            problems.append(f"checks recorded outside any section: {orphaned}")

        for spec in self.registry:
            actual = sum(1 for r in self.results if r.section == spec.name)
            if actual != spec.expected_checks:
                problems.append(
                    f"section {spec.name!r} ran {actual} checks, declared "
                    f"{spec.expected_checks}"
                )

        expected_total = sum(s.expected_checks for s in self.registry)
        if len(self.results) != expected_total:
            problems.append(
                f"total checks {len(self.results)} != declared total {expected_total}"
            )
        return problems

    # -- reporting ---------------------------------------------------------------------

    def finish(self) -> dict[str, object]:
        """Return the gate report. ``passed`` is true only if nothing failed *and*
        every declared check demonstrably ran."""
        self.structural_failures = self._verify_completeness()
        failed = [r.name for r in self.results if not r.passed]
        expected_total = sum(s.expected_checks for s in self.registry)
        return {
            "sections_declared": len(self.registry),
            "sections_completed": len(self.completed),
            "checks_declared": expected_total,
            "checks_executed": len(self.results),
            "checks_passed": sum(1 for r in self.results if r.passed),
            "failed_checks": failed,
            "structural_failures": self.structural_failures,
            "passed": not failed and not self.structural_failures,
        }

    def render(self, report: dict[str, object]) -> str:
        lines: list[str] = []
        for spec in self.registry:
            rows = [r for r in self.results if r.section == spec.name]
            status = "ran" if spec.name in self.completed else "NOT RUN"
            lines.append(f"=== {spec.name} ({len(rows)}/{spec.expected_checks}, {status}) ===")
            for r in rows:
                lines.append(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name:<44} {r.detail}")
        for problem in self.structural_failures:
            lines.append(f"  [FAIL] STRUCTURAL: {problem}")
        lines.append("")
        lines.append(
            f"checks {report['checks_executed']}/{report['checks_declared']} executed, "
            f"{report['checks_passed']} passed"
        )
        lines.append("GATE: " + ("PASS" if report["passed"] else "FAIL"))
        return "\n".join(lines)
