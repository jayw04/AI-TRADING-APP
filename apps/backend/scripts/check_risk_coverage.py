"""Fail CI if branch coverage on app/risk/engine.py drops below the threshold.

Risk Engine is the safety-critical path that gates every order before it
reaches the broker (ADR 0002). Every branch is meaningful — a flag that
silently stops catching SHORT_NOT_ALLOWED or GROSS_EXPOSURE is a real bug
that won't surface in normal use.

Reads coverage.xml (produced by ``pytest --cov-report=xml``), finds the
entry for app/risk/engine.py, and exits non-zero if its branch-rate falls
below ``THRESHOLD``. Ratchet up as we close the remaining branches; never
ratchet down without a written reason.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Ratcheted back to 0.85 after the backfill PR
# (tests/risk/test_engine_extras.py) covered the previously-uncovered
# STOP/STOP_LIMIT shape checks, denied/allowed symbol lists, partial
# short-cover SHORT_NOT_ALLOWED, gross-exposure rejection, and rate
# limit. Current branch-rate is 0.905 with line-rate at 1.000; the
# floor lives just below current state so a real regression trips it.
THRESHOLD = 0.85
TARGET_FILE = "app/risk/engine.py"


def main() -> int:
    coverage_xml = Path("coverage.xml")
    if not coverage_xml.exists():
        print(
            f"ERROR: {coverage_xml} not found. "
            f"Run pytest --cov-report=xml first.",
            file=sys.stderr,
        )
        return 2

    tree = ET.parse(coverage_xml)
    root = tree.getroot()

    # coverage.xml emits paths relative to the package source root ([tool.coverage.run]
    # source = ["app"]) — so the filename for app/risk/engine.py shows up as
    # "risk/engine.py". Match against both the absolute-from-repo form and the
    # source-relative form, with both forward and backslash separators.
    candidates = (
        TARGET_FILE,
        TARGET_FILE.removeprefix("app/"),
    )

    for cls in root.iter("class"):
        filename = (cls.get("filename") or "").replace("\\", "/")
        if any(filename.endswith(c) for c in candidates):
            branch_rate = float(cls.get("branch-rate", "0"))
            line_rate = float(cls.get("line-rate", "0"))
            print(
                f"{filename}: branch-rate={branch_rate:.3f} "
                f"line-rate={line_rate:.3f}"
            )
            if branch_rate < THRESHOLD:
                print(
                    f"FAIL: branch coverage on {TARGET_FILE} is "
                    f"{branch_rate:.3f}, below required {THRESHOLD}",
                    file=sys.stderr,
                )
                return 1
            return 0

    print(
        f"ERROR: {TARGET_FILE} not found in coverage.xml — "
        f"is the file in [tool.coverage.run] omit?",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
