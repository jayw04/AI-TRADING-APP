"""Hash-verified access to the ADOPTED v1.1 development mechanics.

Owner ruling R5A (`MR002_Phase3C_OwnerRulings_v1.2.json` ->
`ruling_R5A_coupling_reduction_adoption`) adopts the already-exercised coupling-reduction mechanics
of `apps/backend/scripts/mr002_development_run.py` as the frozen MR-002 validation semantics:

    "use the exact share and rounding behavior already present in mr002_development_run.py -
     do NOT improve or reinterpret it"

An adoption that lives only in a JSON record is an adoption that silently rots the first time
somebody edits the adopted file. So the binding is enforced here, at import: the whole file AND the
specific mechanics block are re-hashed against the values the ruling froze, and a mismatch is fatal.

Phase 3C reuses this module's helpers rather than re-typing them, because a re-typed copy is
exactly how "the same economics" quietly stops being the same economics.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# Bound by MR002_Phase3C_OwnerRulings_v1.2.json -> ruling_R5A_coupling_reduction_adoption
ADOPTED_RUNNER = "apps/backend/scripts/mr002_development_run.py"
ADOPTED_RUNNER_SHA256 = "b1f990e20550a3a964063b0cf4a0c204125b6e0cfc8df6c10d407c26206791f9"
MECHANICS_BLOCK_FIRST_LINE = 251
MECHANICS_BLOCK_LAST_LINE = 276
MECHANICS_BLOCK_SHA256 = "02d9ea7571046419694ec46782c1fdd0e308bfc279c3ca4715681e487bb347b2"

_MODULE_NAME = "mr002_adopted_development_run"


class AdoptionBindingViolation(RuntimeError):
    """The adopted source no longer matches the bytes the owner ruling froze. FATAL."""


def _repo_root() -> Path:
    # .../apps/backend/app/research/mr002/phase3c/adopted.py -> repo root
    return Path(__file__).resolve().parents[6]


def runner_path() -> Path:
    return _repo_root() / "apps" / "backend" / "scripts" / "mr002_development_run.py"


def verify_binding() -> dict:
    """Re-hash the adopted file and its mechanics block. Raises on any drift."""
    path = runner_path()
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AdoptionBindingViolation(f"adopted runner not readable at {path}: {exc}") from exc

    file_sha = hashlib.sha256(raw).hexdigest()
    if file_sha != ADOPTED_RUNNER_SHA256:
        raise AdoptionBindingViolation(
            f"adopted runner sha256 {file_sha} != bound {ADOPTED_RUNNER_SHA256}. The coupling-"
            "reduction semantics are frozen by owner ruling R5A; changing them requires a new "
            "owner ruling, not a code edit."
        )

    lines = raw.split(b"\n")
    block = b"\n".join(lines[MECHANICS_BLOCK_FIRST_LINE - 1:MECHANICS_BLOCK_LAST_LINE])
    block_sha = hashlib.sha256(block).hexdigest()
    if block_sha != MECHANICS_BLOCK_SHA256:
        raise AdoptionBindingViolation(
            f"mechanics block (lines {MECHANICS_BLOCK_FIRST_LINE}-{MECHANICS_BLOCK_LAST_LINE}) "
            f"sha256 {block_sha} != bound {MECHANICS_BLOCK_SHA256}"
        )

    return {
        "adopted_runner": ADOPTED_RUNNER,
        "runner_sha256": file_sha,
        "runner_bytes": len(raw),
        "mechanics_block_lines": f"{MECHANICS_BLOCK_FIRST_LINE}-{MECHANICS_BLOCK_LAST_LINE}",
        "mechanics_block_sha256": block_sha,
        "mechanics_block_bytes": len(block),
        "bound_by": "MR002_Phase3C_OwnerRulings_v1.2.json / ruling_R5A_coupling_reduction_adoption",
    }


def load() -> ModuleType:
    """Import the adopted runner after verifying its bytes. Cached like a normal import."""
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]

    verify_binding()
    path = runner_path()
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise AdoptionBindingViolation(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[_MODULE_NAME]
        raise
    return module
