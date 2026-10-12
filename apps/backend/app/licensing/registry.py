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
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.licensing.scopes import LicenseScope, combine_scopes

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_PATH = Path(__file__).with_name("data_license_registry.json")
# Canonical (sorted-key, compact) SHA-256 of the parsed registry document. Insensitive to
# whitespace / line endings so a CRLF checkout cannot spuriously fail the pin.
REGISTRY_SHA256 = "d6bfa0ed993b77bd961d7ead77ae6ad89426e51981c8a143c1ff0b51e0c80679"


# The one Alpaca market-data source id. Every feed (sip, iex, delayed_sip, ...) maps to it.
ALPACA_MARKET_DATA = "alpaca_market_data"
# The owner's own account / order / operational records (no vendor market data).
OWNER_GENERATED_RECORDS = "owner_generated_records"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LicenseRegistryError(RuntimeError):
    """The licence registry is unreadable, malformed or does not match its pinned hash."""


@dataclass(frozen=True)
class LicenseDocument:
    """A licence document the classification rests on. ``sha256`` is ``None`` only while pending
    (never for a ``COMMERCIAL_OK`` entry)."""

    name: str
    sha256: str | None
    sha256_status: str | None


@dataclass(frozen=True)
class LicenseEntry:
    source_id: str
    license_scope: LicenseScope
    basis_document: str
    basis_date: str | None
    owner_ruling_ref: str
    covers: tuple[str, ...]
    documents: tuple[LicenseDocument, ...] = ()
    reading: str | None = None
    recheck_triggers: tuple[str, ...] = ()


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


def _parse_documents(raw: Any, scope: LicenseScope, where: str) -> tuple[LicenseDocument, ...]:
    """Validate ``basis.documents``. A null hash is accepted only for PERSONAL / UNKNOWN entries
    and only with a stated pending status; a COMMERCIAL_OK entry needs a real SHA-256 on EVERY
    document."""
    if not isinstance(raw, list):
        raise LicenseRegistryError(f"{where}: 'documents' must be a list")
    out: list[LicenseDocument] = []
    for j, d in enumerate(raw):
        w = f"{where}.documents[{j}]"
        if not isinstance(d, dict):
            raise LicenseRegistryError(f"{w}: not an object")
        name = _require_str(d, "name", w)
        digest = d.get("sha256")
        status = d.get("sha256_status")
        if digest is None:
            if scope is LicenseScope.COMMERCIAL_OK:
                raise LicenseRegistryError(
                    f"{w}: a COMMERCIAL_OK entry requires a sha256 for every licence document"
                )
            if not isinstance(status, str) or not status.strip():
                raise LicenseRegistryError(f"{w}: a null sha256 needs a non-empty 'sha256_status'")
        elif not isinstance(digest, str) or not _SHA256_RE.match(digest):
            raise LicenseRegistryError(f"{w}: 'sha256' must be 64 lowercase hex characters or null")
        out.append(LicenseDocument(name, digest, status if isinstance(status, str) else None))
    return tuple(out)


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
        date = basis.get("date")
        if date is not None and (not isinstance(date, str) or not date.strip()):
            raise LicenseRegistryError(f"{where}.basis: 'date' must be a string or null")
        documents = _parse_documents(basis.get("documents", []), scope, f"{where}.basis")
        doc_text = basis.get("document")
        if doc_text is None:
            if not documents:
                raise LicenseRegistryError(
                    f"{where}.basis: needs a 'document' string or a non-empty 'documents' list"
                )
            doc_text = "; ".join(d.name for d in documents)
        elif not isinstance(doc_text, str) or not doc_text.strip():
            raise LicenseRegistryError(f"{where}.basis: 'document' must be a non-empty string")
        ruling = _require_str(item, "owner_ruling_ref", where)
        reading = basis.get("reading")
        if reading is not None and (not isinstance(reading, str) or not reading.strip()):
            raise LicenseRegistryError(f"{where}.basis: 'reading' must be a non-empty string")
        triggers = basis.get("recheck_triggers", [])
        if not isinstance(triggers, list) or not all(
            isinstance(t, str) and t.strip() for t in triggers
        ):
            raise LicenseRegistryError(
                f"{where}.basis: 'recheck_triggers' must be a list of strings"
            )
        if scope is LicenseScope.COMMERCIAL_OK:
            if date is None:
                raise LicenseRegistryError(
                    f"{where}: a COMMERCIAL_OK entry must cite the dated vendor permission or basis"
                )
            no_vendor = basis.get("no_vendor_documents")
            if not documents and not (isinstance(no_vendor, str) and no_vendor.strip()):
                raise LicenseRegistryError(
                    f"{where}: a COMMERCIAL_OK entry must list its hashed licence documents, or "
                    "state in 'no_vendor_documents' why no vendor licence applies"
                )
        covers = item.get("covers", [])
        if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
            raise LicenseRegistryError(f"{where}: 'covers' must be a list of strings")
        entries[sid] = LicenseEntry(
            sid, scope, doc_text, date, ruling, tuple(covers), documents, reading, tuple(triggers)
        )
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


def alpaca_feed_source_id(feed: str | None = None) -> str:
    """Registry source id for ANY Alpaca market-data pull (bars, trades, quotes; sip, iex,
    delayed_sip or any other feed value, including missing): always ``alpaca_market_data``.

    Deliberately total: no feed value can map to an unregistered id, so an IEX or delayed-SIP
    pull is neither UNKNOWN-by-accident nor let through under a different reason.
    """
    del feed  # every feed is the same licensed source
    return ALPACA_MARKET_DATA
