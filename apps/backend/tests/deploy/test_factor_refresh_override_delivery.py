"""Whatever ``factor_refresh.py`` imports as a sibling must actually reach the container.

``scripts/`` is baked into the backend image and is NOT bind-mounted into the long-running
backend. The deployed image predates both files, so ``docker-compose.factor-refresh.yml``
is the *only* delivery mechanism for the one-off refresh container — and it maps individual
files, deliberately, rather than shadowing the whole directory.

That design is right, and it has a sharp edge: adding a sibling import to
``factor_refresh.py`` without adding a mount line produces `ModuleNotFoundError` inside a
throwaway container, which surfaces as the refresh aborting before it reads a single row.
Confirmed on the box on 2026-08-11 — the deployed image carried neither file.

Nothing else in the test suite could catch this. Every other test imports the module from
the source tree, where its siblings are simply present.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "apps" / "backend" / "scripts"
REFRESH = SCRIPTS / "factor_refresh.py"
OVERRIDE = REPO_ROOT / "deploy" / "aws" / "docker-compose.factor-refresh.yml"


def _sibling_imports() -> set[str]:
    """Top-level module names ``factor_refresh.py`` imports that live beside it.

    Parsed with ``ast`` rather than grepped: the module's own docstring and comments name
    sibling files in prose, and matching those would make this test pass for the wrong
    reason — the same trap the planner-v3 provenance docstring set for a grep-based check.
    """
    tree = ast.parse(REFRESH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return {n for n in names if (SCRIPTS / f"{n}.py").exists()}


def _mounted_files() -> set[str]:
    text = OVERRIDE.read_text(encoding="utf-8")
    return {Path(m).name for m in re.findall(r"\./apps/backend/scripts/([A-Za-z0-9_]+\.py):", text)}


def test_the_override_delivers_every_sibling_module_factor_refresh_imports():
    siblings = _sibling_imports()
    assert siblings, "expected factor_refresh.py to import at least one sibling module"
    mounted = _mounted_files()
    missing = {f"{name}.py" for name in siblings} - mounted
    assert not missing, (
        f"{sorted(missing)} imported by factor_refresh.py but not mounted by "
        f"{OVERRIDE.name}. The deployed image does not contain these files, so the "
        f"one-off refresh container would raise ModuleNotFoundError and abort the refresh."
    )


def test_the_override_still_maps_individual_files_not_the_directory():
    """Mounting ``scripts/`` wholesale would shadow every image-baked script the next time
    the long-running backend is recreated — a latent application-runtime change well
    outside a data job. The file's own header says so; this pins it."""
    # Comments only, stripped out — the file's header explains at length WHY a directory
    # mount would be wrong, and matching that prose would fail the test for quoting the
    # rule it enforces. Exactly the trap this file's own header sets.
    code = [
        ln
        for ln in OVERRIDE.read_text(encoding="utf-8").splitlines()
        if not ln.strip().startswith("#")
    ]
    assert "./apps/backend/scripts:/app/scripts" not in "\n".join(code)
    for line in code:
        stripped = line.strip()
        if stripped.startswith("- ./apps/backend/scripts"):
            assert re.fullmatch(
                r"- \./apps/backend/scripts/[A-Za-z0-9_]+\.py:"
                r"/app/scripts/[A-Za-z0-9_]+\.py:ro",
                stripped,
            ), f"expected a read-only single-file mount, got: {stripped}"


def test_the_mounted_files_exist_in_the_tree():
    """A mount whose source is absent is created by Docker as an empty DIRECTORY, which
    shadows the image's file with something unimportable rather than failing loudly."""
    for name in _mounted_files():
        assert (SCRIPTS / name).exists(), f"{name} is mounted but absent from {SCRIPTS}"
