"""ADR 0002 — single order entry point.

This file used to carry its own copy of the static check plus a fourteen-entry
whole-file allowlist. The allowlist was the problem: exempting a file to keep
the check green disables the check for that file forever, and the comment
telling readers not to do that sat directly above fourteen instances of it. It
had also drifted red against an untracked strategy that was using the perfectly
legitimate ``self.ctx.submit_order(...)`` context path.

The check now lives in ``scripts/check_adr0002.sh`` so it runs on every pull
request alongside the twelve sibling invariant checks — ``pytest`` in this repo
is FULL-runs-only, so a pytest-only ADR 0002 check was invisible on PRs. This
module is the script's test harness: it proves the script actually catches a
bypass rather than merely passing.

A check nobody has watched fail is not a check.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_ROOT / "scripts" / "check_adr0002.sh"

# The tripwire methods, written so this file's own source does not trip the
# check it is testing (this file is allowlisted, but relying on that would be
# exactly the whole-file exemption habit being removed here).
MUTATORS = ("submit" + "_order", "cancel" + "_order", "replace" + "_order")
TOKEN_NAME = "ROUTER" + "_TOKEN"


def _resolve_bash() -> str | None:
    """Find a bash that can actually execute a script.

    On Windows, plain ``bash`` on PATH is often WSL's launcher, which fails with
    ``execvpe(/bin/bash)`` when no distribution is installed. Resolve to an
    absolute interpreter and prove it runs before trusting it.
    """
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

pytestmark = pytest.mark.skipif(
    BASH is None,
    reason="check_adr0002.sh needs bash; CI runs ubuntu-latest and Windows has Git Bash",
)


def _run(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    env = {**os.environ, "ADR0002_ROOT": root.as_posix()}
    return subprocess.run(
        [BASH, SCRIPT.as_posix()],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal well-formed backend tree the check should pass."""
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "app" / "orders").mkdir(parents=True)
    (tmp_path / "strategies_user").mkdir(parents=True)
    (tmp_path / "app" / "services" / "quiet.py").write_text("X = 1\n", encoding="utf-8")
    return tmp_path


def test_script_exists_and_is_the_named_invariant() -> None:
    """CLAUDE.md, the risk-engine skill, ADR 0020 and ADR 0021 all cite this path."""
    assert SCRIPT.is_file(), f"{SCRIPT} is missing — ADR 0002 has no PR-visible check"


def test_the_real_repository_satisfies_adr_0002() -> None:
    result = _run(BACKEND_ROOT)
    assert result.returncode == 0, f"ADR 0002 violated in this tree:\n{result.stdout}"


@pytest.mark.parametrize("mutator", MUTATORS)
def test_direct_adapter_call_is_caught(tmp_path: pathlib.Path, mutator: str) -> None:
    """The bypass ADR 0002 exists to prevent: reaching the broker adapter directly.

    This skips the risk engine, the pre-call Order row, and the audit entry —
    all three of which only exist on the OrderRouter path.
    """
    root = _tree(tmp_path)
    offender = root / "app" / "services" / "emergency_tool.py"
    offender.write_text(
        f"def liquidate(adapter):\n    return adapter.{mutator}(symbol='AAPL', qty=1)\n",
        encoding="utf-8",
    )

    result = _run(root)

    assert result.returncode == 1, f"bypass NOT caught:\n{result.stdout}"
    assert "app/services/emergency_tool.py" in result.stdout
    assert "direct broker order call" in result.stdout


def test_router_token_leak_is_caught(tmp_path: pathlib.Path) -> None:
    """The runtime tripwire assumes only the router knows the token.

    Nothing verified that before this check. A module that imports the token can
    satisfy the adapter's guard and place an order with the router none the wiser.
    """
    root = _tree(tmp_path)
    (root / "app" / "services" / "sneaky.py").write_text(
        f"from app.orders import {TOKEN_NAME}\n", encoding="utf-8"
    )

    result = _run(root)

    assert result.returncode == 1, f"token leak NOT caught:\n{result.stdout}"
    assert "router-token leak" in result.stdout


def test_context_pass_through_is_not_flagged(tmp_path: pathlib.Path) -> None:
    """``self.ctx.submit_order(...)`` IS the sanctioned path — it is bound to
    ``OrderRouter.submit``. Flagging it is what forced the old whole-file
    exemptions, which is how the check lost its teeth.
    """
    root = _tree(tmp_path)
    (root / "strategies_user" / "template.py").write_text(
        "class S:\n"
        "    async def rebalance(self):\n"
        f"        await self.ctx.{MUTATORS[0]}(req)\n"
        f"        await self.ctx.{MUTATORS[1]}(oid)\n",
        encoding="utf-8",
    )
    (root / "app" / "services" / "nested.py").write_text(
        f"async def go(running):\n    await running.instance.ctx.{MUTATORS[0]}(req)\n",
        encoding="utf-8",
    )

    result = _run(root)

    assert result.returncode == 0, f"sanctioned context path flagged:\n{result.stdout}"


def test_method_definitions_are_not_flagged(tmp_path: pathlib.Path) -> None:
    """``BrokerAdapter`` Protocol and ``StrategyContext`` declare these names."""
    root = _tree(tmp_path)
    (root / "app" / "services" / "iface.py").write_text(
        "class Thing:\n"
        f"    async def {MUTATORS[0]}(self, req): ...\n"
        f"    def {MUTATORS[1]}(self, oid): ...\n",
        encoding="utf-8",
    )

    result = _run(root)

    assert result.returncode == 0, f"definitions flagged as calls:\n{result.stdout}"


def test_clean_tree_passes(tmp_path: pathlib.Path) -> None:
    assert _run(_tree(tmp_path)).returncode == 0
