"""Machine-readable exposure ledger -- loader, validator and overlap queries (WP0.6).

The file is strict JSON (no PyYAML: it is not a declared dependency and adding one needs an
ADR), parsed and hashed with the same rules as the frozen spec: duplicate keys and NaN are
refused, and ``sha256`` is the digest of the *canonical* JSON, so re-indenting the file does not
change it. This module is only the *mechanism*. The real ``exposure_ledger.json`` contents
(RNG-001 window, the entry study, AI-session contact audit) are authored by the
owner audit and signed under D01; nothing here fabricates or defaults them.

File schema (every key required, unknown keys rejected, nothing defaulted; dates are
ISO strings)::

    {"schema_version": 1,
     "signoff": null | {"signed_by": <str>, "signed_on": "YYYY-MM-DD"},
     "entries": [{"id": <unique str>,
                  "start": "YYYY-MM-DD",       # inclusive
                  "end": "YYYY-MM-DD",         # inclusive
                  "description": <str>,
                  "source": <str>,             # what exposed the data
                  "observed_by": <str>}]}      # who / which agent session saw it

A ledger with ``signoff: null`` loads (so a draft can be inspected) but
``require_signed()`` -- which the results guard calls -- refuses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, final

from app.research.range002.governance.errors import (
    ExposureLedgerError,
    ExposureLedgerNotSignedError,
)
from app.research.range002.governance.model import DateRange
from app.research.range002.spec.hashing import CanonicalisationError, content_sha256, loads_strict

SCHEMA_VERSION = 1
_TOP_KEYS = frozenset({"schema_version", "signoff", "entries"})
_ENTRY_KEYS = frozenset({"id", "start", "end", "description", "source", "observed_by"})
_SIGNOFF_KEYS = frozenset({"signed_by", "signed_on"})


@dataclass(frozen=True)
class ExposureEntry:
    id: str
    window: DateRange
    description: str
    source: str
    observed_by: str


def _as_date(value: object, where: str) -> date:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ExposureLedgerError(f"{where}: {value!r} is not an ISO date") from exc
    raise ExposureLedgerError(f"{where}: expected an ISO date, got {type(value).__name__}")


def _req_str(mapping: Mapping[str, Any], key: str, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExposureLedgerError(f"{where}: '{key}' must be a non-empty string")
    return value


def _check_keys(mapping: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    missing = sorted(allowed - set(mapping))
    if unknown:
        raise ExposureLedgerError(f"{where}: unknown keys {unknown}")
    if missing:
        raise ExposureLedgerError(f"{where}: missing keys {missing}")


_CONSTRUCT = object()  # module-private: only the from_* classmethods hold it


@final
class ExposureLedger:
    """Validated, immutable view of one exposure ledger file.

    Constructible only through :meth:`from_bytes` / :meth:`from_text` / :meth:`from_file`
    (the constructor demands a module-private token), so a ledger object always carries a
    ``sha256`` computed from the content it was parsed from; a hand-made "signed" ledger
    with a copied sha cannot be built through the public API. "Signed" means only that the
    ``signoff`` block is present and well-formed -- nothing here verifies who signed it.
    Reaching the token (a module-private name) is code execution, outside the threat model.
    """

    __slots__ = ("_entries", "_sha256", "_signoff")

    _entries: tuple[ExposureEntry, ...]
    _signoff: dict[str, str] | None
    _sha256: str

    def __init__(
        self,
        token: object,
        entries: tuple[ExposureEntry, ...],
        signoff: Mapping[str, str] | None,
        sha256: str,
    ) -> None:
        if token is not _CONSTRUCT:
            raise ExposureLedgerError(
                "ExposureLedger can only be built with ExposureLedger.from_bytes / from_text / "
                "from_file"
            )
        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_signoff", dict(signoff) if signoff is not None else None)
        object.__setattr__(self, "_sha256", sha256)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ExposureLedger is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ExposureLedger is immutable")

    @classmethod
    def from_file(cls, path: Path) -> ExposureLedger:
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            raise ExposureLedgerError(f"cannot read exposure ledger {path}: {exc}") from exc
        return cls.from_bytes(raw)

    @classmethod
    def from_text(cls, text: str) -> ExposureLedger:
        return cls.from_bytes(text.encode("utf-8"))

    @classmethod
    def from_bytes(cls, raw: bytes) -> ExposureLedger:
        try:
            doc = loads_strict(raw)
        except CanonicalisationError as exc:
            raise ExposureLedgerError(f"exposure ledger is not valid strict JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise ExposureLedgerError("exposure ledger must be a mapping")
        _check_keys(doc, _TOP_KEYS, "ledger")
        if doc["schema_version"] != SCHEMA_VERSION:
            raise ExposureLedgerError(
                f"schema_version {doc['schema_version']!r} unsupported; expected {SCHEMA_VERSION}"
            )

        signoff: dict[str, str] | None = None
        raw_signoff = doc["signoff"]
        if raw_signoff is not None:
            if not isinstance(raw_signoff, dict):
                raise ExposureLedgerError("signoff must be null or a mapping")
            _check_keys(raw_signoff, _SIGNOFF_KEYS, "signoff")
            signoff = {
                "signed_by": _req_str(raw_signoff, "signed_by", "signoff"),
                "signed_on": _as_date(raw_signoff["signed_on"], "signoff.signed_on").isoformat(),
            }

        raw_entries = doc["entries"]
        if not isinstance(raw_entries, list):
            raise ExposureLedgerError("entries must be a list")
        entries: list[ExposureEntry] = []
        seen: set[str] = set()
        for i, item in enumerate(raw_entries):
            where = f"entries[{i}]"
            if not isinstance(item, dict):
                raise ExposureLedgerError(f"{where} must be a mapping")
            _check_keys(item, _ENTRY_KEYS, where)
            entry_id = _req_str(item, "id", where)
            if entry_id in seen:
                raise ExposureLedgerError(f"{where}: duplicate id {entry_id!r}")
            seen.add(entry_id)
            start, end = (
                _as_date(item["start"], f"{where}.start"),
                _as_date(item["end"], f"{where}.end"),
            )
            if start > end:
                raise ExposureLedgerError(f"{where}: start {start} is after end {end}")
            entries.append(
                ExposureEntry(
                    id=entry_id,
                    window=DateRange(start, end),
                    description=_req_str(item, "description", where),
                    source=_req_str(item, "source", where),
                    observed_by=_req_str(item, "observed_by", where),
                )
            )
        return cls(_CONSTRUCT, tuple(entries), signoff, content_sha256(doc))

    # --- queries ------------------------------------------------------------

    @property
    def entries(self) -> tuple[ExposureEntry, ...]:
        return self._entries

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def is_signed(self) -> bool:
        return self._signoff is not None

    def require_signed(self) -> None:
        if not self.is_signed:
            raise ExposureLedgerNotSignedError(
                "exposure ledger has no sign-off (WP0.6 audit / D01); the results guard "
                "will not consume an unsigned ledger"
            )

    def overlaps(self, window: DateRange) -> tuple[ExposureEntry, ...]:
        """Entries whose window intersects ``window`` (inclusive on both ends)."""
        return tuple(e for e in self._entries if e.window.overlaps(window))
