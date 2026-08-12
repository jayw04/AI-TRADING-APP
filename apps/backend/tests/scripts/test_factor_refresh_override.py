"""The refresh-only compose override must reach the one-off container and nothing else.

The corrected ``scripts/factor_refresh.py`` is baked into the backend image
(``COPY scripts ./scripts``) and is not bind-mounted, so a deployed image built
before the file existed cannot run it. Rebuilding the image to fix a data job
would carry 182 commits — including the risk engine, the broker layer and three
Alembic migrations — into the live trading runtime, so the corrected file is
delivered by a **single-file** read-only mount into the throwaway refresh
container instead.

Each test below names the production failure it prevents.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SH = _REPO_ROOT / "deploy" / "aws" / "factor-refresh.sh"
_OVERRIDE = _REPO_ROOT / "deploy" / "aws" / "docker-compose.factor-refresh.yml"

pytestmark = pytest.mark.skipif(not _SH.exists(), reason="factor-refresh.sh absent")

_SCRIPTS = _REPO_ROOT / "apps" / "backend" / "scripts"

#: The reviewed set. factor_refresh.py imports factor_adjudication as a SIBLING, so
#: delivering one without the other raises ModuleNotFoundError inside the throwaway
#: container and the refresh aborts before reading a row — confirmed against the live
#: image on 2026-08-11, which carried NEITHER file.
MOUNTS = [
    "./apps/backend/scripts/factor_refresh.py:/app/scripts/factor_refresh.py:ro",
    "./apps/backend/scripts/factor_adjudication.py:/app/scripts/factor_adjudication.py:ro",
]


@pytest.fixture(scope="module")
def sh() -> str:
    return _SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def override() -> str:
    return _OVERRIDE.read_text(encoding="utf-8")


def _code(text: str) -> list[str]:
    """Non-comment, non-blank lines — comments legitimately discuss what is banned."""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


# ------------------------------------------------------------------ override


def test_override_exists_and_is_parseable(override):
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(override)
    assert set(doc) == {"services"}
    assert set(doc["services"]) == {"backend"}, "only the backend service may be overridden"


def test_override_maps_only_reviewed_single_file_mounts(override):
    """A directory mount would shadow EVERY image-baked script the moment the
    long-running backend is next recreated — a latent application-runtime change
    outside the narrow recovery. Each entry must remain a named, reviewed FILE."""
    yaml = pytest.importorskip("yaml")
    vols = yaml.safe_load(override)["services"]["backend"]["volumes"]
    assert vols == MOUNTS, f"expected exactly the reviewed single-file mounts, got {vols}"


def test_override_delivers_every_sibling_module_factor_refresh_imports(override):
    """The list above is a REVIEWED set; this is the drift guard behind it.

    Adding a sibling import to factor_refresh.py without a mount line ships a refresh
    that dies on ModuleNotFoundError in a throwaway container — and nothing else in the
    suite can catch it, because every other test imports the module from the source tree
    where its siblings are simply present.

    Parsed with ``ast``, not grepped: the module names its siblings in prose, and matching
    that would pass for the wrong reason (the trap that made a grep check on the planner-v3
    provenance docstring return a false positive)."""
    tree = ast.parse((_SCRIPTS / "factor_refresh.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
    siblings = {n for n in imported if (_SCRIPTS / f"{n}.py").exists()}
    assert siblings, "expected factor_refresh.py to import at least one sibling module"

    mounted = {m.split(":")[0].rsplit("/", 1)[-1] for m in MOUNTS}
    missing = {f"{n}.py" for n in siblings} - mounted
    assert not missing, (
        f"{sorted(missing)} imported by factor_refresh.py but not mounted. The deployed "
        "image does not contain these files, so the one-off refresh container would raise "
        "ModuleNotFoundError and abort the refresh."
    )


def test_override_does_not_mount_the_scripts_directory(override):
    """The rejected shape. Guard it by name so it cannot come back.

    Checked against non-comment lines only — the file's rationale comment names
    the banned pattern in order to explain why it is banned."""
    body = "\n".join(_code(override))
    for banned in (
        "./apps/backend/scripts:/app/scripts",
        "./apps/backend/scripts:/app/scripts:ro",
        "./apps/backend:/app",
    ):
        assert banned not in body, f"directory-level shadowing is prohibited: {banned}"


def test_override_mount_is_read_only(override):
    yaml = pytest.importorskip("yaml")
    vols = yaml.safe_load(override)["services"]["backend"]["volumes"]
    assert all(v.endswith(":ro") for v in vols), "the refresh mount must be read-only"


def test_override_declares_no_other_service_or_key(override):
    """Scope creep guard: no ports, env, command, image or extra services."""
    yaml = pytest.importorskip("yaml")
    backend = yaml.safe_load(override)["services"]["backend"]
    assert set(backend) == {"volumes"}, f"override must only add volumes, got {sorted(backend)}"


def test_mounted_source_files_exist_in_the_repo(override):
    """Every mount source must be a real file, or the container silently gets a
    directory created by the daemon and the import fails at runtime."""
    for mount in MOUNTS:
        src = mount.split(":")[0].lstrip("./")
        assert (_REPO_ROOT / src).is_file(), f"{src} must exist as a file"


# ------------------------------------------------------------- shell wiring


def test_refresh_compose_includes_the_override(sh):
    assert "COMPOSE_REFRESH=" in sh
    m = re.search(r'^COMPOSE_REFRESH="([^"]+)"', sh, re.M)
    assert m, "COMPOSE_REFRESH must be defined"
    assert "deploy/aws/docker-compose.factor-refresh.yml" in m.group(1)
    assert "$COMPOSE " in m.group(1), "it must extend COMPOSE, not redefine the base files"


def test_factor_refresh_invocations_use_the_override(sh):
    """Both `factor_refresh.py` calls run in the throwaway container and need the
    corrected file; without the override they execute the image's copy — which,
    on the currently deployed image, does not exist at all."""
    calls = [ln for ln in _code(sh) if "scripts/factor_refresh.py" in ln]
    assert len(calls) == 2, f"expected the universe and verify calls, got {calls}"
    for ln in calls:
        assert "$COMPOSE_REFRESH run" in ln, f"must use the override: {ln}"


def test_running_backend_operations_never_use_the_override(sh):
    """stop/start/exec act on the LONG-RUNNING backend. If the override reached
    them, a later recreation would silently mount host scripts over the image."""
    for ln in _code(sh):
        if re.search(r"\$COMPOSE(_REFRESH)?\s+(stop|start|exec|up|down|restart)\b", ln):
            assert "$COMPOSE_REFRESH" not in ln, f"override must not touch the live backend: {ln}"


def test_ingest_does_not_use_the_override(sh):
    """ingest_sharadar.py already ships in the image; mounting over it would be
    an unnecessary and unreviewed substitution."""
    for ln in _code(sh):
        if "ingest_sharadar.py" in ln or "-e WORKBENCH_FACTOR_DATA_DB_PATH" in ln:
            assert "$COMPOSE_REFRESH" not in ln, f"ingest must use the plain image: {ln}"


def test_base_compose_files_are_unchanged(sh):
    """The recovery must not edit the committed production compose files."""
    m = re.search(r'^COMPOSE="([^"]+)"', sh, re.M)
    assert m
    assert m.group(1) == "docker compose -f docker-compose.yml -f docker-compose.prod.yml"


def test_no_image_rebuild_or_migration_is_triggered(sh):
    """A narrow data recovery must not become a 182-commit production release."""
    body = "\n".join(_code(sh))
    for banned in ("docker build", "compose build", "alembic", "seed_dev_data"):
        assert banned not in body, f"factor-refresh.sh must not invoke {banned}"
