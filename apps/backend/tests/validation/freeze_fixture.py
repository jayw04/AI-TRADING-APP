"""A valid measurement freeze for tests that exercise something OTHER than the freeze itself.

`preflight` now refuses a context with no freeze — correctly, since an unestablished measurement
identity must never be assumed. That would otherwise break every fixture that predates the freeze, so
this helper supplies a real one: a tiny runtime tree plus a manifest whose `validation_tree_sha256` is
computed from it. Nothing here is a stub — `verify_deployment` runs its full check against it.

The freeze names the SAME commit the fixture passes as `code_commit`, so the deployed HEAD *is* the
ratified commit and the ancestry branch is not exercised. Ancestry refusals are covered directly in
`test_measurement_freeze.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.validation.measurement_freeze import (
    MEASURED_PATHS,
    TREE_IDENTITY_ALGORITHM,
    load_measurement_freeze,
    validation_tree_digest,
)

#: The commit a fixture presents as BOTH the ratified and the actual deployed identity.
TEST_DEPLOYED_COMMIT = "d13310a32227c67163250566eca719d5f734dd53"


def test_freeze(tmp_path: Path):
    """Return `(freeze, runtime_root)` — a manifest that genuinely verifies against a real tree."""
    root = tmp_path / "_freeze_runtime"
    pkg = root / MEASURED_PATHS[0]
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "measured.py").write_bytes(b"# measurement content under test\n")
    manifest = tmp_path / "_measurement_freeze.json"
    manifest.write_bytes(json.dumps({
        "manifest_schema_version": "1.0",
        "measurement_commit": TEST_DEPLOYED_COMMIT,
        "validation_tree_sha256": validation_tree_digest(root),
        "supersedes_measurement_commit": "764883b58cb96936f23e49182dd02b70d969501b",
        "ratified_increment_inventory_sha256": "1" * 64,
        "amendment_sha256": "2" * 64,
        "measured_paths": list(MEASURED_PATHS),
        "validation_tree_identity_algorithm": TREE_IDENTITY_ALGORITHM,
        "byte_manifest_sha256": "3" * 64,
    }, sort_keys=True, indent=2).encode())
    return load_measurement_freeze(manifest), root


def freeze_kwargs(tmp_path: Path) -> dict:
    """The two `ForwardRunContext` fields a fixture must now supply. The fixture keeps its own
    `code_commit`, which must equal `TEST_DEPLOYED_COMMIT` for the freeze to verify."""
    freeze, root = test_freeze(tmp_path)
    return {"measurement_freeze": freeze, "runtime_root": root}
