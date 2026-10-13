"""PU-1 writers. ``export_for_external_use`` / ``export_file_for_external_use`` are THE seam for
anything leaving the owner's private working set (decks, PDFs, HTML, charts, share/outbound
folders). They gate before any byte is written and take no override argument.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.licensing.envelope import atomic_write, scope_of_file, sidecar_path, write_sidecar
from app.licensing.gate import PersonalScopeBlocked, assert_presentable
from app.licensing.render import Fmt, stamp


def write_internal_report(
    path: Path, text: str, *, sources: Iterable[str], fmt: Fmt = "markdown"
) -> Path:
    """Write an INTERNAL research report: PU-1 footer when not COMMERCIAL_OK, plus a scope sidecar."""
    srcs = tuple(sources)
    atomic_write(path, stamp(text, sources=srcs, fmt=fmt).encode("utf-8"))
    write_sidecar(path, srcs)
    return path


def write_internal_json(path: Path, obj: Any, *, sources: Iterable[str]) -> Path:
    """Write an INTERNAL machine-readable report (JSON) byte-for-byte as ``json.dumps(indent=2,
    default=str)`` would, plus its scope sidecar. No footer is injected (it would corrupt the JSON);
    the sidecar binds the file's SHA-256 to its declared sources, and scope is recomputed from the
    registry, so a missing/invalid sidecar is UNKNOWN."""
    atomic_write(path, json.dumps(obj, indent=2, default=str).encode("utf-8"))
    write_sidecar(path, tuple(sources))
    return path


def export_for_external_use(
    path: Path,
    content: str | bytes,
    *,
    sources: Iterable[str],
    destination: str = "external",
) -> Path:
    """Write ``content`` for external use. Raises ``PersonalScopeBlocked`` (reason
    ``PU1_PERSONAL_SCOPE_BLOCKED``) before touching the filesystem unless every source is
    ``COMMERCIAL_OK``."""
    srcs = tuple(sources)
    assert_presentable(sources=srcs, destination=destination)
    data = content.encode("utf-8") if isinstance(content, str) else content
    atomic_write(path, data)
    write_sidecar(path, srcs)
    return path


def export_file_for_external_use(src: Path, dest: Path, *, destination: str = "external") -> Path:
    """Copy an existing artifact to an external location, gated on its sidecar scope. A file with
    no valid sidecar is ``UNKNOWN`` and is refused."""
    scope = scope_of_file(src)
    if scope.blocks_presentation:
        raise PersonalScopeBlocked(
            scope=scope,
            sources=(str(src),),
            destination=destination,
            detail="artifact scope taken from its sidecar (missing/invalid sidecar is UNKNOWN)",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    shutil.copyfile(sidecar_path(src), sidecar_path(dest))
    return dest
