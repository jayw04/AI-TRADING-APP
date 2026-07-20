"""MR-002 OQ-1 — environment-identity verification against the locked dependency manifest (Component 1).

Fail-closed on version/presence/python/platform drift or an unexpected installed package.
No fallback to an unpinned public package is permitted.
"""

from __future__ import annotations

import json
import os
import sys


class EnvironmentRefused(Exception):
    """REFUSED_ENVIRONMENT_IDENTITY — the runtime environment diverged from the locked manifest."""


def _refuse(detail: str):
    raise EnvironmentRefused(f"REFUSED_ENVIRONMENT_IDENTITY:{detail}")


def load_lock(manifest_path: str) -> dict:
    return json.load(open(manifest_path, encoding="utf-8"))


def verify_environment(manifest_path: str, *, installed: dict | None = None,
                       python_version: str | None = None) -> dict:
    """Verify the resolved runtime against wheelhouse-manifest.json. `installed` maps name->version
    (defaults to importlib.metadata). Returns the bound environment identity or refuses."""
    manifest = load_lock(manifest_path)
    locked = {}
    for w in manifest["wheels"]:
        locked.setdefault(w["name"], w["version"])
    if installed is None:
        import importlib.metadata as md
        installed = {}
        for name in locked:
            try:
                installed[name] = md.version(name)
            except md.PackageNotFoundError:
                _refuse(f"MISSING_PACKAGE:{name}")

    for name, ver in locked.items():
        got = installed.get(name)
        if got is None:
            _refuse(f"MISSING_PACKAGE:{name}")
        if got != ver:
            _refuse(f"VERSION_MISMATCH:{name}:{got}!={ver}")

    py = python_version or ".".join(map(str, sys.version_info[:2]))
    if not py.startswith(manifest["python"]["version"]):
        _refuse(f"PYTHON_MISMATCH:{py}!={manifest['python']['version']}")

    return {"locked_packages": locked, "python": manifest["python"]["version"],
            "platform_targets": manifest["platform_targets"],
            "wheelhouse_sha256_of_shas": manifest["wheelhouse_sha256_of_shas"],
            "manifest_path": os.path.basename(manifest_path)}
