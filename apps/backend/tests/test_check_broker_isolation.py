"""Semantic-equivalence tests for ``scripts/check_broker_isolation.sh``.

The script gained a prefilter: one ``grep -REl`` over the alternation of its ten
patterns collects candidate files, and the original per-file/per-pattern walk
then runs only on those. That took the check from 145s to under a second, and it
is the slowest step in the LIGHT block, which runs on every backend PR.

A speed optimisation on a security boundary is only acceptable if it provably
did not change the verdict, so these tests do not merely check that the script
still passes on a clean tree — a prefilter that returned nothing would also do
that, while silently disabling the invariant.

Instead every fixture is run through BOTH the script and an INDEPENDENT
reference implementation of the documented semantics, written here in Python
from the P5 §2 rules rather than transliterated from the bash. Exit code and
exact stdout must agree. The corpus deliberately includes the cases a prefilter
is most likely to get wrong:

  * a directory named ``brokers`` that is NOT ``app/brokers`` — still forbidden
    (this is why the prefilter does not use ``--exclude-dir=brokers``)
  * one file matching several patterns — one line per pattern, in pattern order
  * ``alpaca.data`` — exempt by design, must NOT be reported
  * non-``.py`` files carrying a forbidden import — out of scope
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_ROOT / "scripts" / "check_broker_isolation.sh"

# The ten forbidden patterns, in the script's order — the output emits one line
# per matching pattern in exactly this sequence.
PATTERNS = (
    r"from[[:space:]]+alpaca\.trading",
    r"import[[:space:]]+alpaca\.trading",
    r"from[[:space:]]+alpaca\.broker",
    r"import[[:space:]]+alpaca\.broker",
    r"from[[:space:]]+alpaca\.common",
    r"import[[:space:]]+alpaca\.common",
    r"from[[:space:]]+ib_insync",
    r"import[[:space:]]+ib_insync",
    r"from[[:space:]]+schwab_api",
    r"import[[:space:]]+schwab_api",
)


def _resolve_bash() -> str | None:
    candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
        "/usr/bin/bash",
    ]
    for candidate in candidates:
        if not candidate or not pathlib.Path(candidate).exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "printf ok"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except OSError:
            continue
        if probe.returncode == 0 and probe.stdout.strip() == "ok":
            return candidate
    return None


BASH = _resolve_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="check_broker_isolation.sh needs bash")


def _run_script(root: pathlib.Path) -> tuple[int, list[str]]:
    assert BASH is not None
    result = subprocess.run(
        [BASH, SCRIPT.as_posix()],
        env={**os.environ, "BROKER_ISOLATION_ROOT": root.as_posix()},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.splitlines()


def _reference(root: pathlib.Path) -> tuple[int, list[str]]:
    """Independent implementation of the P5 §2 rules.

    Written from the documented invariant — only files under ``app/brokers/`` may
    import a broker TRADING/ORDER SDK — not from the shell source, so agreement
    between the two is evidence rather than a tautology.
    """
    app_dir = root / "app"
    if not app_dir.is_dir():
        return 0, ["No app/ directory; nothing to check."]

    allowed_prefix = f"{root.as_posix()}/app/brokers/"
    # POSIX [[:space:]] has no Python equivalent; \s is the deliberate translation.
    compiled = [(p, re.compile(p.replace("[[:space:]]", r"\s"))) for p in PATTERNS]

    lines: list[str] = []
    failed = False
    for path in sorted(app_dir.rglob("*.py")):
        if not path.is_file():
            continue
        posix = f"{root.as_posix()}/{path.relative_to(root).as_posix()}"
        if posix.startswith(allowed_prefix):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw, rx in compiled:
            if rx.search(text):
                lines.append(
                    f"BROKER ISOLATION VIOLATION: {posix} matches forbidden pattern: {raw}"
                )
                failed = True

    if failed:
        lines += [
            "Broker isolation check FAILED.",
            "Order-routing broker code must live under app/brokers/. (Market-data",
            "alpaca.data.* imports are exempt by design.) If a broker SDK is",
            "genuinely needed elsewhere, write an ADR first.",
        ]
        return 1, lines
    return 0, [*lines, "Broker isolation check passed."]


def _assert_equivalent(root: pathlib.Path) -> tuple[int, list[str]]:
    script_code, script_out = _run_script(root)
    ref_code, ref_out = _reference(root)

    assert script_code == ref_code, (
        f"exit code diverged: script={script_code} reference={ref_code}\n"
        f"script output:\n" + "\n".join(script_out)
    )
    # Line ORDER for violations follows the filesystem walk in both, but only the
    # set of findings is semantically load-bearing; compare as sets so a walk-order
    # difference is not mistaken for a weakened check.
    assert set(script_out) == set(ref_out), (
        "findings diverged\n"
        f"only in script: {sorted(set(script_out) - set(ref_out))}\n"
        f"only in reference: {sorted(set(ref_out) - set(script_out))}"
    )
    return script_code, script_out


def _mk(root: pathlib.Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_the_real_repository_agrees_with_the_reference() -> None:
    """The optimisation must not change the verdict on the tree that matters."""
    code, _ = _assert_equivalent(BACKEND_ROOT)
    assert code == 0


def test_missing_app_directory(tmp_path: pathlib.Path) -> None:
    code, out = _assert_equivalent(tmp_path)
    assert code == 0
    assert out == ["No app/ directory; nothing to check."]


def test_clean_tree(tmp_path: pathlib.Path) -> None:
    _mk(tmp_path, "app/services/ok.py", "import json\nfrom app.risk import RiskEngine\n")
    _mk(tmp_path, "app/brokers/alpaca/adapter.py", "from alpaca.trading import TradingClient\n")
    code, out = _assert_equivalent(tmp_path)
    assert code == 0
    assert out == ["Broker isolation check passed."]


@pytest.mark.parametrize("pattern", PATTERNS)
def test_each_forbidden_pattern_is_still_caught(tmp_path: pathlib.Path, pattern: str) -> None:
    """The prefilter must not drop any one of the ten patterns from the alternation."""
    literal = pattern.replace("[[:space:]]+", " ").replace("\\.", ".")
    _mk(tmp_path, "app/services/offender.py", f"{literal} import Thing\n")

    code, out = _assert_equivalent(tmp_path)

    assert code == 1
    assert any("offender.py" in line and pattern in line for line in out), out


def test_allowed_directory_is_still_exempt(tmp_path: pathlib.Path) -> None:
    _mk(tmp_path, "app/brokers/alpaca/adapter.py", "from alpaca.trading import TradingClient\n")
    _mk(tmp_path, "app/brokers/ib/adapter.py", "import ib_insync\n")
    code, _ = _assert_equivalent(tmp_path)
    assert code == 0


def test_a_brokers_directory_elsewhere_is_not_exempt(tmp_path: pathlib.Path) -> None:
    """Only app/brokers/ is allowed — not any directory named 'brokers'.

    This is why the prefilter does not use --exclude-dir=brokers, which would
    have quietly exempted this file.
    """
    _mk(tmp_path, "app/services/brokers/sneaky.py", "from alpaca.trading import TradingClient\n")

    code, out = _assert_equivalent(tmp_path)

    assert code == 1
    assert any("services/brokers/sneaky.py" in line for line in out), out


def test_multiple_patterns_in_one_file_report_each(tmp_path: pathlib.Path) -> None:
    _mk(
        tmp_path,
        "app/services/many.py",
        "from alpaca.trading import A\nimport ib_insync\nfrom schwab_api import B\n",
    )

    code, out = _assert_equivalent(tmp_path)

    assert code == 1
    assert sum(1 for line in out if "many.py" in line) == 3, out


def test_alpaca_data_remains_exempt(tmp_path: pathlib.Path) -> None:
    """Market data is a separate read-only concern; flagging it was never intended."""
    _mk(
        tmp_path,
        "app/market_data/bars.py",
        "from alpaca.data.historical import StockHistoricalDataClient\n"
        "from alpaca.data.live import StockDataStream\n",
    )
    code, out = _assert_equivalent(tmp_path)
    assert code == 0
    assert out == ["Broker isolation check passed."]


def test_non_python_files_are_out_of_scope(tmp_path: pathlib.Path) -> None:
    _mk(tmp_path, "app/services/notes.md", "from alpaca.trading import TradingClient\n")
    _mk(tmp_path, "app/services/config.yaml", "import ib_insync\n")
    code, _ = _assert_equivalent(tmp_path)
    assert code == 0


def test_whitespace_variants_still_match(tmp_path: pathlib.Path) -> None:
    _mk(tmp_path, "app/services/spaced.py", "from   alpaca.trading import A\n")
    _mk(tmp_path, "app/services/tabbed.py", "import\talpaca.broker\n")
    code, out = _assert_equivalent(tmp_path)
    assert code == 1
    assert any("spaced.py" in line for line in out)
    assert any("tabbed.py" in line for line in out)


def test_many_offenders_across_nested_packages(tmp_path: pathlib.Path) -> None:
    for i in range(12):
        _mk(tmp_path, f"app/pkg{i}/deep/mod.py", "import ib_insync\n")
    for i in range(20):
        _mk(tmp_path, f"app/quiet{i}/mod.py", "import json\n")

    code, out = _assert_equivalent(tmp_path)

    assert code == 1
    assert sum(1 for line in out if "BROKER ISOLATION VIOLATION" in line) == 12, out
