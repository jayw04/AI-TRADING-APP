"""Mutation check: prove the producer-equivalence suite detects semantic reconstruction drift.

An equivalence suite that passed on the first attempt is exactly the kind that might be comparing
something trivial. This injects the specific drifts that would change the study's numbers and
requires the suite to FAIL for each one:

  1. the signal series read from the split-adjusted close instead of the total-return close;
  2. YOUNG collapsed into UNEXPLAINED_HOLE, destroying the distinction the window rules key off;
  3. ADV taking the adjusted close instead of the raw close;
  4. duplicate rows resolved last-wins instead of refused.

Each is a plausible mistake, and each would be invisible to a suite that only checked shapes.

Run directly:  python tests/research/phase3b/mutation_check_assembly.py
"""

from __future__ import annotations

import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
ASSEMBLY = os.path.join(_BACKEND, "app", "research", "mr002", "phase3b", "assembly.py")
SUITE = "tests/research/phase3b/test_phase3b_producer_equivalence.py"

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "signal series reads the split-adjusted close",
        'fields = {name: _column(prices, name) for name in ("closeadj", "closeunadj", "volume")}',
        'fields = {"closeadj": _column(prices, "close"), '
        '"closeunadj": _column(prices, "closeunadj"), "volume": _column(prices, "volume")}',
    ),
    (
        "YOUNG collapsed into UNEXPLAINED_HOLE",
        "else (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)",
        "else CellStatus.UNEXPLAINED_HOLE",
    ),
    (
        "ADV raw close replaced by the adjusted close",
        'raw_close=arrays["closeunadj"],',
        'raw_close=arrays["closeadj"],',
    ),
    (
        "duplicate rows resolved last-wins instead of refused",
        'raise AssemblyRefused(f"duplicate price row for {symbol} {session}")',
        "pass",
    ),
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path: str, text: str) -> None:
    """Build first, then write once: never truncate a file you cannot reproduce."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _run() -> tuple[int, list[str]]:
    """Return the exit code AND which tests failed.

    Reporting the detecting test matters: a mutation can be "detected" by an unrelated assertion
    while the comparison it was meant to exercise stays blind to it. That is a false pass wearing
    a green tick.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
    )
    failed = [
        ln.split("::", 1)[-1].split(" ")[0]
        for ln in (proc.stdout or "").splitlines()
        if ln.startswith("FAILED")
    ]
    return proc.returncode, failed


def main() -> int:
    original = _read(ASSEMBLY)
    missing = [label for label, old, _new in MUTATIONS if old not in original]
    if missing:
        raise SystemExit(f"REFUSED: mutation targets not found, cannot prove anything: {missing}")

    if _run()[0] != 0:
        raise SystemExit("REFUSED: the equivalence suite does not pass before mutation")
    print("baseline equivalence suite: PASS")

    survivors = []
    for label, old, new in MUTATIONS:
        try:
            _write(ASSEMBLY, original.replace(old, new, 1))
            rc, failed = _run()
        finally:
            _write(ASSEMBLY, original)
        verdict = "DETECTED" if rc != 0 else "SURVIVED"
        by = ", ".join(failed[:3]) if failed else "-"
        print(f"  {label:52s} -> {verdict:9s} by: {by}")
        if rc == 0:
            survivors.append(label)

    if _run()[0] != 0:
        raise SystemExit("MUTATION CHECK FAILED: assembly.py was not restored cleanly")
    if survivors:
        raise SystemExit(f"MUTATION CHECK FAILED: drift the suite cannot detect: {survivors}")
    print("MUTATION CHECK PASSED: the equivalence suite detects every injected drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
