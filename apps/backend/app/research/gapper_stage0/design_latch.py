"""Startup design latch — the approval identity anchor (scoping memo §6.1).

The approved GAPPER Research Design v2.1.1 DOCX is gitignored (ADR 0050,
S3-resident), so it carries no Git object identity: **the SHA-256 is the
approval**. Any harness entry point must call :func:`latch_design` before doing
anything else and refuse to proceed unless the artifact on disk hashes to the
frozen approved constant. The superseded round-2 hash is hard-rejected with a
distinct error so a stale artifact can never be mistaken for a missing one, and
a missing artifact (the normal state on CI/dev machines without the DOCX) is a
third, clearly-worded error.

The constants are module-level and frozen by review — deliberately NOT
configuration. Changing them requires a new owner approval record.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Approval record v1.0 (2026-08-11): SHA-256 of the approved v2.1.1 DOCX.
APPROVED_DESIGN_SHA256 = "2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d"
# Round-2 artifact — SUPERSEDED, never approved. Hard-rejected, never accepted.
SUPERSEDED_SHA256 = "84913de09363bb52786d6ca93917920239533d889e4651c90f8004c07d08e993"

# Repo-relative default location of the approved artifact (gitignored; absent in CI).
DEFAULT_DESIGN_DOCX_PATH = "docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx"

_CHUNK = 1 << 20


class DesignLatchError(RuntimeError):
    """Base class: the design latch refused to open."""


class DesignArtifactMissingError(DesignLatchError):
    """The design artifact is not present on disk (expected on CI/dev machines)."""


class SupersededDesignError(DesignLatchError):
    """The artifact hashes to the superseded round-2 design — never approved."""


class DesignHashMismatchError(DesignLatchError):
    """The artifact hashes to neither the approved nor the superseded constant."""


def sha256_of_file(path: str | Path) -> str:
    """Streaming SHA-256 of ``path`` (hex digest)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def latch_design(docx_path: str | Path = DEFAULT_DESIGN_DOCX_PATH) -> str:
    """Verify the design artifact at ``docx_path`` and return its SHA-256.

    Raises:
        DesignArtifactMissingError: file absent — "design artifact not present".
        SupersededDesignError: hash equals :data:`SUPERSEDED_SHA256`.
        DesignHashMismatchError: any other hash.
    """
    path = Path(docx_path)
    if not path.is_file():
        raise DesignArtifactMissingError(
            f"design artifact not present: {path} — the approved v2.1.1 DOCX is "
            "gitignored/S3-resident (ADR 0050) and must be fetched before the "
            "harness can latch. This is NOT a hash mismatch."
        )
    digest = sha256_of_file(path)
    if digest == SUPERSEDED_SHA256:
        raise SupersededDesignError(
            f"design artifact at {path} is the SUPERSEDED round-2 design "
            f"({digest[:12]}…) — never approved; do not pin, cite, or run against it."
        )
    if digest != APPROVED_DESIGN_SHA256:
        raise DesignHashMismatchError(
            f"design artifact at {path} hashes to {digest[:12]}…, not the approved "
            f"{APPROVED_DESIGN_SHA256[:12]}… — any edit invalidates the approval "
            "(approval record v1.0)."
        )
    return digest
