"""Audit-pack header: binds a pack file to the run and spec it came from (round 4, N2c).

Minimal format. The FIRST line of an audit-pack file (terminated by ``\\n``) is the canonical
JSON (sorted keys, compact separators) of exactly::

    {"format":"range002-audit-pack","run_id":"<run id>","spec_sha256":"<64-hex>","version":1}

Everything after the first newline is the pack body and is not interpreted here. The guard
parses the header of a predecessor's pack at ``authorize`` time and requires the embedded
``run_id`` / ``spec_sha256`` to equal the predecessor's registry row, so a pack produced for
one run cannot be presented as another run's evidence.

Level 1 only (accidental misuse / casual bypass): the header is unauthenticated text. Someone
who can write a pack file can write any header; nothing here signs it. Signed run results are
Level 2, design-only.
"""

from __future__ import annotations

import json
import re

from app.research.range002.governance.errors import PredecessorEvidenceBindingError
from app.research.range002.spec.hashing import CanonicalisationError, loads_strict

AUDIT_PACK_FORMAT = "range002-audit-pack"
AUDIT_PACK_VERSION = 1
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_KEYS = frozenset({"format", "run_id", "spec_sha256", "version"})


def audit_pack_header(run_id: str, spec_sha256: str) -> bytes:
    """The canonical header line (with its trailing newline) for a pack of ``run_id``."""
    if not isinstance(run_id, str) or not run_id:
        raise PredecessorEvidenceBindingError("audit pack header needs a non-empty run_id")
    if not isinstance(spec_sha256, str) or not _HEX64.fullmatch(spec_sha256):
        raise PredecessorEvidenceBindingError("audit pack header needs a 64-hex spec_sha256")
    body = {
        "format": AUDIT_PACK_FORMAT,
        "run_id": run_id,
        "spec_sha256": spec_sha256,
        "version": AUDIT_PACK_VERSION,
    }
    return (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def parse_audit_pack_header(raw: bytes) -> tuple[str, str]:
    """``(run_id, spec_sha256)`` from a pack's first line, or a named refusal."""
    line, newline, _body = raw.partition(b"\n")
    if not newline:
        raise PredecessorEvidenceBindingError("audit pack has no header line (no newline)")
    try:
        header = loads_strict(line.decode("utf-8"))
    except (UnicodeDecodeError, CanonicalisationError) as exc:
        raise PredecessorEvidenceBindingError(
            f"audit pack header is not strict JSON: {exc}"
        ) from exc
    if not isinstance(header, dict) or set(header) != _KEYS:
        raise PredecessorEvidenceBindingError(
            f"audit pack header must be an object with exactly the keys {sorted(_KEYS)}"
        )
    run_id, spec_sha = header["run_id"], header["spec_sha256"]
    if (
        header["format"] != AUDIT_PACK_FORMAT
        or header["version"] != AUDIT_PACK_VERSION
        or type(header["version"]) is not int
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(spec_sha, str)
        or not _HEX64.fullmatch(spec_sha)
    ):
        raise PredecessorEvidenceBindingError("audit pack header has a wrong format/version/field")
    if audit_pack_header(run_id, spec_sha) != line + b"\n":
        raise PredecessorEvidenceBindingError("audit pack header is not in canonical form")
    return run_id, spec_sha
