"""Fail CI if branch coverage on any P2 module drops below its floor.

Reads coverage.xml (produced by ``pytest --cov-branch --cov-report=xml``),
checks each P2 module against its threshold, and exits non-zero if any
drops below.

Thresholds are starting floors calibrated to the state at the close of P2
Session 6. Same principle as ``check_risk_coverage.py``:

  - **Ratchet up, never down.** If a PR adds tests that push a module
    higher, raise the threshold here in the same PR so the new floor is
    locked in. Never lower a threshold without a written reason in the
    PR description.
  - If a legitimate addition (e.g. a defensive branch that's costly to
    test) would drop a module below its floor, lower the floor here in
    the same PR with a comment explaining why.

The script also functions as a contract: anyone touching a listed module
sees the floor next to it and knows what the codebase is willing to
defend.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# (path suffix, minimum branch-rate)
#
# Paths match against the trailing portion of coverage.xml's filename
# attribute (which under [tool.coverage.run] source=["app"] reports paths
# relative to ``app/``, so e.g. "indicators/computer.py" matches both
# "indicators/computer.py" and "app/indicators/computer.py").
P2_MODULES: list[tuple[str, float]] = [
    ("indicators/computer.py", 0.65),
    ("market_data/bar_cache.py", 0.75),
    ("strategies/base.py", 0.95),
    ("strategies/context.py", 0.60),
    ("strategies/loader.py", 0.85),
    ("strategies/engine.py", 0.65),
    ("strategies/backtest_context.py", 0.50),
    ("strategies/backtester.py", 0.60),
    ("strategies/backtest_models.py", 0.95),
    ("api/v1/strategies.py", 0.10),
    ("api/v1/signals.py", 0.45),
    ("api/v1/indicators.py", 0.85),
]


def main() -> int:
    coverage_xml = Path("coverage.xml")
    if not coverage_xml.exists():
        print(
            f"ERROR: {coverage_xml} not found. "
            f"Run pytest --cov-branch --cov-report=xml first.",
            file=sys.stderr,
        )
        return 2

    tree = ET.parse(coverage_xml)
    root = tree.getroot()

    actual: dict[str, float] = {}
    for cls in root.iter("class"):
        filename = (cls.get("filename") or "").replace("\\", "/")
        for suffix, _threshold in P2_MODULES:
            if filename.endswith(suffix):
                actual[suffix] = float(cls.get("branch-rate", "0"))

    failures: list[str] = []
    print("P2 module branch coverage:")
    for suffix, threshold in P2_MODULES:
        rate = actual.get(suffix)
        if rate is None:
            print(
                f"  WARN: {suffix} not found in coverage.xml "
                f"(no tests touched it?)",
                file=sys.stderr,
            )
            continue
        status = "OK" if rate >= threshold else "FAIL"
        print(
            f"  {suffix:42s} branch-rate={rate:.3f} "
            f"threshold={threshold:.2f}  {status}"
        )
        if rate < threshold:
            failures.append(
                f"{suffix}: {rate:.3f} < {threshold:.2f}"
            )

    if failures:
        print("\nP2 coverage FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nP2 coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
