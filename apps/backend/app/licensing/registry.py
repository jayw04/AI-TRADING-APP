"""PU-1 governed ``data_license`` registry: version-controlled, hash-pinned, fail-closed.

The registry is the JSON file ``data_license_registry.json`` beside this module. Its canonical
SHA-256 is pinned in ``REGISTRY_SHA256`` below, so a change to any licence classification is a
two-place, reviewable edit (the data file and this constant) and cannot be made by editing a file
on a host. The gate needs nothing but this file: no database is consulted.

Fail closed: an unreadable, malformed, tampered (hash mismatch) or schema-invalid registry raises
``LicenseRegistryError``; every gate treats that as "blocked". A source that is not registered is
``UNKNOWN``. A ``COMMERCIAL_OK`` entry is the ONLY way to make a source presentable, and it must
cite a licence document and a date (the written vendor permission) and an owner ruling.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.licensing.scopes import LicenseScope, combine_scopes

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_PATH = Path(__file__).with_name("data_license_registry.json")
# Canonical (sorted-key, compact) SHA-256 of the parsed registry document. Insensitive to
# whitespace / line endings so a CRLF checkout cannot spuriously fail the pin.
REGISTRY_SHA256 = "8a2d47b00f4b0fef5cd458e061bebdda1d80425b1f220cc613db28519a5a8ba6"


class LicenseRegistryError(RuntimeError):
    """The licence registry is unreadable, malformed or does not match its pinned hash."""


@dataclass(frozen=True)
class LicenseEntry:
    source_id: str
    license_scope: LicenseScope
    basis_document: str
    basis_date: str | None
    owner_ruling_ref: str
    covers: tuple[str, ...]


@dataclass(frozen=True)
class LicenseRegistry:
    entries: Mapping[str, LicenseEntry]
    sha256: str

    def scope_of_source(self, source_id: str) -> LicenseScope:
        """Scope of one source. Unregistered => ``UNKNOWN`` (blocked like ``PERSONAL``)."""
        entry = self.entries.get(normalize_source_id(source_id))
        return entry.license_scope if entry is not None else LicenseScope.UNKNOWN

    def scope_of(self, sources: Iterable[str]) -> LicenseScope:
        """Most restrictive scope across ``sources``; no sources => ``UNKNOWN``."""
        return combine_scopes(*(self.scope_of_source(s) for s in sources))


def normalize_source_id(source_id: str) -> str:
    return str(source_id).strip().lower()


def canonical_sha256(document: Any) -> str:
    body = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _require_str(obj: Mapping[str, Any], key: str, where: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str) or not v.strip():
        raise LicenseRegistryError(f"{where}: {key!r} must be a non-empty string")
    return v


def _parse(document: Any, digest: str) -> LicenseRegistry:
    if not isinstance(document, dict):
        raise LicenseRegistryError("registry document is not an object")
    if document.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise LicenseRegistryError(
            f"registry schema_version {document.get('schema_version')!r} != "
            f"{REGISTRY_SCHEMA_VERSION}"
        )
    raw = document.get("entries")
    if not isinstance(raw, list) or not raw:
        raise LicenseRegistryError("registry 'entries' must be a non-empty list")
    entries: dict[str, LicenseEntry] = {}
    for i, item in enumerate(raw):
        where = f"entries[{i}]"
        if not isinstance(item, dict):
            raise LicenseRegistryError(f"{where}: not an object")
        sid = normalize_source_id(_require_str(item, "source_id", where))
        if sid in entries:
            raise LicenseRegistryError(f"{where}: duplicate source_id {sid!r}")
        scope_name = _require_str(item, "license_scope", where)
        if scope_name not in LicenseScope.__members__:
            raise LicenseRegistryError(f"{where}: unknown license_scope {scope_name!r}")
        scope = LicenseScope[scope_name]
        basis = item.get("basis")
        if not isinstance(basis, dict):
            raise LicenseRegistryError(f"{where}: 'basis' must be an object")
        doc = _require_str(basis, "document", f"{where}.basis")
        date = basis.get("date")
        if date is not None and (not isinstance(date, str) or not date.strip()):
            raise LicenseRegistryError(f"{where}.basis: 'date' must be a string or null")
        ruling = _require_str(item, "owner_ruling_ref", where)
        if scope is LicenseScope.COMMERCIAL_OK and date is None:
            raise LicenseRegistryError(
                f"{where}: a COMMERCIAL_OK entry must cite the dated vendor permission"
            )
        covers = item.get("covers", [])
        if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
            raise LicenseRegistryError(f"{where}: 'covers' must be a list of strings")
        entries[sid] = LicenseEntry(sid, scope, doc, date, ruling, tuple(covers))
    return LicenseRegistry(entries=entries, sha256=digest)


def parse_registry_text(text: str, *, expected_sha256: str | None) -> LicenseRegistry:
    """Parse + validate registry JSON. ``expected_sha256=None`` skips the pin (tests only)."""
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise LicenseRegistryError(f"registry is not valid JSON: {exc}") from exc
    digest = canonical_sha256(document)
    if expected_sha256 is not None and digest != expected_sha256:
        raise LicenseRegistryError(
            f"registry hash {digest} does not match the pinned {expected_sha256}"
        )
    return _parse(document, digest)


def load_registry() -> LicenseRegistry:
    """Load the in-repo registry, verifying the pin. Raises ``LicenseRegistryError``."""
    try:
        text = REGISTRY_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise LicenseRegistryError(f"registry unreadable at {REGISTRY_PATH}: {exc}") from exc
    return parse_registry_text(text, expected_sha256=REGISTRY_SHA256)


def alpaca_feed_source_id(feed: str | None) -> str:
    """Registry source id for an Alpaca market-data pull. ``sip`` is ``alpaca_sip``; every other
    (or missing) feed maps to an id that is not registered and therefore ``UNKNOWN``."""
    f = (feed or "").strip().lower()
    return "alpaca_sip" if f == "sip" else f"alpaca_{f or 'unspecified'}"
