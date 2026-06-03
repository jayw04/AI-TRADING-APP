"""Fail CI if branch coverage on any P3 module drops below its floor.

Reads coverage.xml (produced by ``pytest --cov-branch --cov-report=xml``),
checks each P3 module against its threshold, and exits non-zero if any
drops below.

Thresholds are starting floors calibrated to the state at the close of P3
Session 6. Same principle as ``check_p2_coverage.py`` and
``check_risk_coverage.py``:

  - **Ratchet up, never down.** If a PR adds tests that push a module
    higher, raise the threshold here in the same PR so the new floor is
    locked in. Never lower a threshold without a written reason in the
    PR description.
  - The two lowest floors (``anthropic_client.py``, ``api/v1/agent.py``)
    intentionally accept low branch rates. Those modules are dominated
    by error-path branches whose only meaningful test is "does the right
    HTTP status come back," which is exercised at higher integration
    levels rather than per-branch.

The script also functions as a contract: anyone touching a listed module
sees the floor next to it and knows what the codebase is willing to
defend.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# (path suffix, minimum branch-rate)
# NOTE: the LLM helper modules moved app/agent/ → app/llm/ in P6 cleanup-1;
# suffixes match coverage.xml filenames (llm/*.py). api/v1/agent.py (the P3
# chat router) was NOT renamed.
P3_MODULES: list[tuple[str, float]] = [
    ("llm/pricing.py", 0.95),
    ("llm/system_prompt.py", 0.85),
    # State-machine module — branch coverage on a session-lifecycle ×
    # cap-state × tool-loop matrix tops out around 0.55 with reasonable
    # unit-test investment. Higher coverage requires injecting failures
    # at every Anthropic call site, which is rapidly diminishing returns.
    ("llm/runtime.py", 0.50),
    # Mostly SDK shape-matching code. The interesting paths (Anthropic
    # API errors, MCP-connector edge cases) are exercised at the runtime
    # layer or in the e2e integration test.
    ("llm/anthropic_client.py", 0.30),
    # Endpoint module — branches are dominated by HTTPException raises
    # the doc explicitly excludes from per-branch testing. Matches the
    # ``api/v1/strategies.py = 0.10`` precedent in check_p2_coverage.py.
    ("api/v1/agent.py", 0.10),
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
        for suffix, _threshold in P3_MODULES:
            if filename.endswith(suffix):
                actual[suffix] = float(cls.get("branch-rate", "0"))

    failures: list[str] = []
    print("P3 module branch coverage:")
    for suffix, threshold in P3_MODULES:
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
        print("\nP3 coverage FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nP3 coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
