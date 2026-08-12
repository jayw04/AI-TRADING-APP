"""Mutation check: prove the qualification suite actually enforces the registered gap formula.

A suite that carries the right formula in documentation but would pass with the wrong one is worth
nothing. This deliberately reintroduces the A1-F2 defect - the legacy SPQ-1 behaviour
`open / distribution_adjusted_close - 1`, which drops the distribution from the numerator - and
asserts that the suite FAILS. Then it restores the file and asserts the suite passes again.

Run directly:  python tests/research/phase3b/mutation_check_a1f2.py
"""

from __future__ import annotations

import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
GAP = os.path.join(_BACKEND, "app", "research", "mr002", "phase3b", "gap.py")
SUITE = "tests/research/phase3b"  # both suites, so the check covers the whole layer

REGISTERED = "    return (open_t_plus_1 + known_cash_distribution_t_plus_1) / close_t - 1.0"
LEGACY = "    return open_t_plus_1 / close_t - 1.0  # A1-F2 DEFECT, injected by the mutation check"


def _run() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "-x"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path: str, text: str) -> None:
    """Never truncate-then-fail: build the text first, then write it in one guarded call."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> int:
    original = _read(GAP)
    if REGISTERED not in original:
        raise SystemExit(
            "REFUSED: the registered formula line was not found; the mutation check "
            "cannot prove anything about a file it does not recognise"
        )

    clean_rc, clean_out = _run()
    if clean_rc != 0:
        print(clean_out[-2000:])
        raise SystemExit("REFUSED: the suite does not pass before mutation; fix that first")
    print(f"baseline suite: PASS ({clean_out.strip().splitlines()[-1]})")

    try:
        _write(GAP, original.replace(REGISTERED, LEGACY, 1))
        mut_rc, mut_out = _run()
    finally:
        _write(GAP, original)

    restored_rc, _ = _run()
    failing = [ln for ln in mut_out.splitlines() if ln.startswith("FAILED")]

    print(f"mutated suite : {'FAIL' if mut_rc != 0 else 'PASS'}")
    for ln in failing[:6]:
        print(f"  {ln}")
    print(f"restored suite: {'PASS' if restored_rc == 0 else 'FAIL'}")

    if mut_rc == 0:
        raise SystemExit(
            "MUTATION CHECK FAILED: the suite passes with the A1-F2 defect "
            "reintroduced, so it does not enforce the registered formula"
        )
    if restored_rc != 0:
        raise SystemExit("MUTATION CHECK FAILED: the file was not restored cleanly")
    print("MUTATION CHECK PASSED: the suite enforces the registered economic-gap formula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
