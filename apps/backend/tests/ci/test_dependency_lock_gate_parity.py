"""Regression test for the dependency-lock re-resolution gate (GITHUB-OPS-001).

The nightly `Fresh resolution proof (uncached)` job compares a fresh `uv pip compile` against
the committed `constraints/*.txt`. `uv` is invoked with --no-header and so emits only the
resolved body, while the generator commits `header(...) + body`. Comparing the bare body
against the committed file is unsatisfiable by construction, so the gate failed on every run
from the day it landed (2026-07-29) until it was repaired — burning a full Tier 3 nightly each
time and reporting a red result that no longer distinguished real drift from the defect.

This pins the property that makes the gate meaningful: what `recompile_one` writes is exactly
what the generator would commit, so a clean tree can actually pass. Offline — the `uv`
invocation is stubbed, because the property under test is the output format, not the network.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load {name}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate():
    return _load("check_dependency_locks")


@pytest.fixture(scope="module")
def generator():
    return _load("regenerate_dependency_locks")


def test_recompile_output_matches_what_the_generator_commits(
    gate, generator, tmp_path, monkeypatch
):
    """recompile_one() must reproduce header + body, or the parity check can never pass."""
    body = "aiosqlite==0.22.1 \\\n    --hash=sha256:" + ("0" * 64) + "\n"

    def fake_run(cmd, **kwargs):
        out = Path(cmd[cmd.index("--output-file") + 1])
        out.write_text(body, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    dest = tmp_path / "backend.txt"
    ok, why = gate.recompile_one("backend", "apps/backend", dest)
    assert ok, why

    expected = generator.header("backend", "apps/backend") + body
    assert dest.read_text(encoding="utf-8") == expected, (
        "recompile_one() output differs from what the generator commits; the nightly "
        "re-resolution parity comparison is unsatisfiable again"
    )


def test_gate_and_generator_agree_on_the_governed_tuple(gate, generator):
    """The two scripts duplicate the resolution tuple by design — assert they stay in sync."""
    for attr in (
        "GOVERNED_PYTHON",
        "GOVERNED_PYTHON_FULL",
        "GOVERNED_PLATFORM",
        "GOVERNED_UV_VERSION",
        "GOVERNED_EXTRAS",
        "PROJECTS",
    ):
        assert getattr(gate, attr) == getattr(generator, attr), (
            f"{attr} drifted between the scripts"
        )


def test_committed_files_carry_the_generator_header(gate, generator):
    """Every committed constraints file must start with the exact governed header."""
    for project, directory in generator.PROJECTS.items():
        path = REPO_ROOT / "constraints" / f"{project}-py312.txt"
        assert path.is_file(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert text.startswith(generator.header(project, directory)), (
            f"{path.name} does not begin with the governed header; regenerate with "
            f"scripts/regenerate_dependency_locks.py"
        )
