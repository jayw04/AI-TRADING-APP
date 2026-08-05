"""Regression test for the dependency-lock re-resolution gate (GITHUB-OPS-001).

The nightly `Fresh resolution proof (uncached)` job compares a fresh `uv pip compile` against
the committed `constraints/*.txt`. `uv` is invoked with --no-header and so emits only the
resolved body, while the generator commits `header(...) + body`. Comparing the bare body
against the committed file is unsatisfiable by construction, so the gate failed on every run
from the day it landed (2026-07-29) until it was repaired — burning a full Tier 3 nightly each
time and reporting a red result that no longer distinguished real drift from the defect.

A second fault made it unsatisfiable *over time*: the resolver ran against a live index, so a
re-resolution could never be required to equal a file committed earlier. Measured 2026-08-04, a
freshly regenerated set drifted again within six hours. Both scripts now constrain the candidate
set with the same governed `--exclude-newer` cutoff.

These pin the properties that make the gate meaningful: what `recompile_one` writes is exactly
what the generator would commit, both invoke the resolver with the same cutoff, and the cutoff is
recorded in the artifact. Offline — the `uv` invocation is stubbed, because the properties under
test are the command and the output format, not the network.
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
        "GOVERNED_EXCLUDE_NEWER",
        "PROJECTS",
    ):
        assert getattr(gate, attr) == getattr(generator, attr), (
            f"{attr} drifted between the scripts"
        )


def test_both_scripts_pass_the_governed_cutoff_to_the_resolver(
    gate, generator, tmp_path, monkeypatch
):
    """Without --exclude-newer the resolver sees a moving index and parity is unsatisfiable.

    This is fault C: a freshly regenerated set drifted again within six hours (2026-08-04),
    because upstream publishes continuously. Both the generator and the gate must constrain
    the candidate set to the same instant, or the nightly goes red on someone else's release.
    """
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        Path(cmd[cmd.index("--output-file") + 1]).write_text("x==1\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate.recompile_one("backend", "apps/backend", tmp_path / "g.txt")

    monkeypatch.setattr(generator.subprocess, "run", fake_run)
    generator.compile_one("backend", "apps/backend", tmp_path / "r.txt", False)

    assert len(seen) == 2
    for cmd in seen:
        assert "--exclude-newer" in cmd, f"resolver invoked without a cutoff: {cmd}"
        assert cmd[cmd.index("--exclude-newer") + 1] == generator.GOVERNED_EXCLUDE_NEWER


def test_committed_headers_record_the_cutoff(generator):
    """The cutoff must be discoverable from the artifact, not only from the script."""
    for project in generator.PROJECTS:
        text = (REPO_ROOT / "constraints" / f"{project}-py312.txt").read_text(encoding="utf-8")
        assert generator.GOVERNED_EXCLUDE_NEWER in text, (
            f"{project}: committed file does not record the governed exclude-newer cutoff"
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
