"""Snapshot manifest: what a data export must declare before anything reads it (WP1.3, BUILD).

A snapshot is only as trustworthy as its provenance, so the manifest is parsed strictly and
verified fail-closed: every file is hashed, every required table and column must be declared,
and a snapshot not declared cross-table consistent is refused. Nothing here reads a value.

The required columns are the ones the PIT selection logic actually reads
(``data.store_adapter`` / ``data.pit_universe``), so an export that omits one is refused before
a research run rather than discovered during it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.research.range002.spec.hashing import file_sha256

PURE_FUNCTIONS = ("parse_snapshot_manifest", "verify_snapshot_files")

MANIFEST_SCHEMA = "range002.snapshot_manifest.v1"
#: v2 adds ``consistency_class`` and an ``integrity`` section ALONGSIDE v1 (v1 is unchanged and
#: still parses exactly as before). A v2 manifest declares HOW the tables were acquired:
#: ``single_transaction`` (cross_table_consistent must be true) or
#: ``sequential_pulls_evidence_checked`` (the tables were separate vendor pulls; cross_table_consistent
#: must be false, the evidence is in ``consistency_basis``, and ``integrity.all_passed`` records the
#: builder's referential / interval / coverage checks). Such a snapshot is refused unless the
#: caller passes the explicit ``allow_sequential_pulls`` opt-in AND ``integrity.all_passed`` is
#: true; the opt-in never turns a ``cross_table_consistent=false`` into "consistent".
MANIFEST_SCHEMA_V2 = "range002.snapshot_manifest.v2"
_SCHEMAS = (MANIFEST_SCHEMA, MANIFEST_SCHEMA_V2)
CLASS_SINGLE_TRANSACTION = "single_transaction"
CLASS_SEQUENTIAL_PULLS = "sequential_pulls_evidence_checked"
CLASS_UNDECLARED = "undeclared_v1"
_CLASSES = (CLASS_SINGLE_TRANSACTION, CLASS_SEQUENTIAL_PULLS)
SEQUENTIAL_PULLS_LIMITATION = (
    "LIMITATION: the daily tables (tickers, sep, actions) were acquired as sequential vendor API "
    "pulls, not in one transaction. Vendor revision stamps and referential/coverage checks are "
    "evidence, not proof, that the tables describe one state; a revision, deletion or ACTIONS "
    "change between pulls would not be detected."
)

#: (table, required columns). ``tickers`` must be the RAW vendor TICKERS rows (all of them), not
#: a store table collapsed to one row per ticker: a collapsed table cannot show ticker reuse.
REQUIRED_COLUMNS = (
    (
        "tickers",
        (
            "permaticker",
            "ticker",
            "category",
            "isdelisted",
            "firstpricedate",
            "lastpricedate",
        ),
    ),
    ("sep", ("ticker", "date", "close", "closeunadj", "volume")),
    ("actions", ("date", "action", "ticker", "contraticker")),
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """The manifest is malformed or incomplete; nothing is read from the snapshot."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    sha256: str
    s3_version_id: str | None


@dataclass(frozen=True)
class TableEntry:
    name: str
    rows: int
    min_date: str | None
    max_date: str | None
    columns: tuple[str, ...]
    files: tuple[FileEntry, ...]


@dataclass(frozen=True)
class SnapshotManifest:
    source: str
    extracted_at_utc: str
    method: str
    cross_table_consistent: bool
    consistency_basis: str
    tables: tuple[TableEntry, ...]
    #: v1 documents: ``single_transaction`` when declared consistent, else ``undeclared_v1``
    consistency_class: str = CLASS_UNDECLARED
    #: v2 only: ``integrity.all_passed`` (None when the section is absent or v1)
    integrity_all_passed: bool | None = None
    schema: str = MANIFEST_SCHEMA


@dataclass(frozen=True)
class VerifyReport:
    defects: tuple[str, ...]
    ok: bool


def _need(obj: Mapping[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in obj or not isinstance(obj[key], kind) or obj[key] in ("", None):
        raise ManifestError(f"{where}: '{key}' missing or not a non-empty {kind.__name__}")
    return obj[key]


def parse_snapshot_manifest(text: str) -> SnapshotManifest:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") not in _SCHEMAS:
        raise ManifestError(f"manifest schema must be one of {list(_SCHEMAS)!r}")
    schema = raw["schema"]
    tables: list[TableEntry] = []
    for name, spec in sorted(_need(raw, "tables", dict, "manifest").items()):
        where = f"tables.{name}"
        files = []
        for f in _need(spec, "files", list, where):
            sha = _need(f, "sha256", str, f"{where}.files")
            if not _HEX64.match(sha):
                raise ManifestError(f"{where}.files: sha256 must be 64 lowercase hex")
            files.append(FileEntry(_need(f, "path", str, where), sha, f.get("s3_version_id")))
        rows = spec.get("rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
            raise ManifestError(f"{where}: 'rows' must be a non-negative integer")
        tables.append(
            TableEntry(
                name,
                rows,
                spec.get("min_date"),
                spec.get("max_date"),
                tuple(_need(spec, "columns", list, where)),
                tuple(files),
            )
        )
    consistent = raw.get("cross_table_consistent")
    if not isinstance(consistent, bool):
        raise ManifestError("cross_table_consistent must be declared true or false")
    klass = CLASS_SINGLE_TRANSACTION if consistent else CLASS_UNDECLARED
    all_passed: bool | None = None
    if schema == MANIFEST_SCHEMA_V2:
        klass = _need(raw, "consistency_class", str, "manifest")
        if klass not in _CLASSES:
            raise ManifestError(f"consistency_class must be one of {list(_CLASSES)!r}")
        if (klass == CLASS_SINGLE_TRANSACTION) != consistent:
            raise ManifestError(
                "consistency_class and cross_table_consistent disagree: single_transaction needs "
                "cross_table_consistent true; sequential_pulls_evidence_checked needs false"
            )
        integrity = raw.get("integrity")
        if integrity is not None:
            if not isinstance(integrity, dict) or not isinstance(integrity.get("all_passed"), bool):
                raise ManifestError("integrity must be an object with a boolean 'all_passed'")
            all_passed = integrity["all_passed"]
    return SnapshotManifest(
        _need(raw, "source", str, "manifest"),
        _need(raw, "extracted_at_utc", str, "manifest"),
        _need(raw, "method", str, "manifest"),
        consistent,
        _need(raw, "consistency_basis", str, "manifest"),
        tuple(tables),
        klass,
        all_passed,
        schema,
    )


def verify_snapshot_files(
    manifest: SnapshotManifest, root: Path, *, allow_sequential_pulls: bool = False
) -> VerifyReport:
    """Structural and checksum verification. Returns every defect; empty means verified.

    A snapshot not declared cross-table consistent is refused, as before. The only exception is
    a v2 manifest of class ``sequential_pulls_evidence_checked`` when the caller passes
    ``allow_sequential_pulls=True`` AND the manifest's integrity checks all passed; the caller is
    then responsible for carrying ``SEQUENTIAL_PULLS_LIMITATION`` into its report."""
    defects: list[str] = []
    by_name = {t.name: t for t in manifest.tables}
    if not manifest.cross_table_consistent:
        sequential = manifest.consistency_class == CLASS_SEQUENTIAL_PULLS
        if not (sequential and allow_sequential_pulls):
            defects.append("snapshot is not declared cross-table consistent")
        elif manifest.integrity_all_passed is not True:
            defects.append(
                "sequential-pull snapshot: integrity checks are absent or did not all pass"
            )
    for table, required in REQUIRED_COLUMNS:
        entry = by_name.get(table)
        if entry is None:
            defects.append(f"required table {table!r} is not declared")
            continue
        missing = [c for c in required if c not in entry.columns]
        if missing:
            defects.append(f"table {table!r} lacks required column(s) {missing}")
        if not entry.files:
            defects.append(f"table {table!r} lists no files")
    for entry in manifest.tables:
        for f in entry.files:
            try:
                actual = file_sha256(root / f.path)
            except OSError as exc:
                defects.append(f"{entry.name}: cannot read {f.path}: {type(exc).__name__}")
                continue
            if actual != f.sha256:
                defects.append(f"{entry.name}: checksum mismatch for {f.path}")
    return VerifyReport(tuple(defects), not defects)
