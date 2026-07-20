"""Fail CI if branch coverage on any ADR 0043 loss-control module drops below 0.95.

Reads a branch-coverage XML (produced by ``pytest --cov=app.risk.loss_control --cov-branch
--cov-report=xml:<file>``; default ``coverage-adr0043.xml``) and checks each required module
against its floor.

This gate is DELIBERATELY STRICTER than ``check_p2_coverage.py`` in one way the owner required:
**a required module that is absent from the coverage report is a FAILURE, not a skip.** A missing
file means the tests that were supposed to exercise it did not run (or it was renamed/removed) —
silently passing that is exactly how a safety-critical module loses its coverage floor unnoticed.
Absent ⇒ fail, never treat-as-zero-and-skip.

Scope is the NEW loss-control code only (not averaged with unrelated well-covered modules), so the
0.95 floor is enforceable on its own terms. The list grows one line per ADR-0043 increment.

  - Ratchet up, never down. If a PR pushes a module higher, raise its floor here in the same PR.
  - Lowering a floor requires a written reason in the PR description.

Usage:  python scripts/check_adr0043_coverage.py [coverage_xml_path]
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_XML = "coverage-adr0043.xml"

# (path suffix, minimum branch-rate). Matched against the trailing portion of coverage.xml's
# ``filename`` attribute (under [tool.coverage.run] source=["app"] these report relative to app/).
ADR0043_MODULES: list[tuple[str, float]] = [
    ("risk/loss_control/constants.py", 0.95),
    ("risk/loss_control/state_machine.py", 0.95),
    ("risk/loss_control/service.py", 0.95),
]


def main(argv: list[str]) -> int:
    xml_path = Path(argv[1]) if len(argv) > 1 else Path(DEFAULT_XML)
    if not xml_path.exists():
        print(
            f"ERROR: {xml_path} not found. Run "
            f"pytest --cov=app.risk.loss_control --cov-branch "
            f"--cov-report=xml:{xml_path} first.",
            file=sys.stderr,
        )
        return 2

    root = ET.parse(xml_path).getroot()
    actual: dict[str, float] = {}
    for cls in root.iter("class"):
        filename = (cls.get("filename") or "").replace("\\", "/")
        for suffix, _threshold in ADR0043_MODULES:
            if filename.endswith(suffix):
                actual[suffix] = float(cls.get("branch-rate", "0"))

    failures: list[str] = []
    print("ADR 0043 loss-control branch coverage:")
    for suffix, threshold in ADR0043_MODULES:
        rate = actual.get(suffix)
        if rate is None:
            # STRICT: a required module missing from the report is a failure, not a skip.
            print(f"  {suffix:44s} MISSING from coverage report  FAIL", file=sys.stderr)
            failures.append(f"{suffix}: absent from coverage report (tests did not exercise it?)")
            continue
        status = "OK" if rate >= threshold else "FAIL"
        print(f"  {suffix:44s} branch-rate={rate:.3f} threshold={threshold:.2f}  {status}")
        if rate < threshold:
            failures.append(f"{suffix}: {rate:.3f} < {threshold:.2f}")

    if failures:
        print("\nADR 0043 coverage FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nADR 0043 coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
