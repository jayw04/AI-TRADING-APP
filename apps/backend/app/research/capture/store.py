"""Immutable time-partitioned raw-data store for MDQ-001 captures.

Layout (registration §7 control 2):

    <root>/<feed>/<YYYY-MM-DD>/quotes/samples.jsonl
    <root>/<feed>/<YYYY-MM-DD>/bars/bars_1min.parquet
    <root>/<feed>/<YYYY-MM-DD>/trades/...            (future capture mode)
    <root>/<feed>/<YYYY-MM-DD>/manifest.json         (presence == FROZEN)

The collector appends to today's partition; freezing writes the provenance
manifest with per-file SHA-256 (control 3) after which the store refuses every
write (control 4). MDQ-001 analysis reads frozen partitions only. All writes
are temp-file + atomic replace — never open(path, "w") on a file that matters.

This store is deliberately separate from the live bar cache (plan §16.2); its
single designated writer is the collector (ADR 0051 decision 6).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

COLLECTOR_VERSION = "mdq-collector/0.1.0"
MANIFEST_SCHEMA = "mdq-capture-manifest/1"
FEEDS = ("sip", "iex")
KINDS = ("quotes", "trades", "bars")


class FrozenPartitionError(RuntimeError):
    """Write attempted against a partition that already has a manifest."""


@dataclass(frozen=True)
class PartitionRef:
    feed: str
    session: date

    def __post_init__(self) -> None:
        if self.feed not in FEEDS:
            raise ValueError(f"feed must be one of {FEEDS}, got {self.feed!r}")


class CaptureStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- paths ---------------------------------------------------------------

    def partition_dir(self, ref: PartitionRef) -> Path:
        return self.root / ref.feed / ref.session.isoformat()

    def manifest_path(self, ref: PartitionRef) -> Path:
        return self.partition_dir(ref) / "manifest.json"

    def is_frozen(self, ref: PartitionRef) -> bool:
        return self.manifest_path(ref).exists()

    def _writable_dir(self, ref: PartitionRef, kind: str) -> Path:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        if self.is_frozen(ref):
            raise FrozenPartitionError(
                f"partition {ref.feed}/{ref.session} is frozen; captures are immutable"
            )
        d = self.partition_dir(ref) / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- writes (collector only) ---------------------------------------------

    def append_jsonl(self, ref: PartitionRef, kind: str, records: list[dict[str, Any]]) -> Path:
        """Append records to <kind>/samples.jsonl (append is the one non-atomic
        operation; a torn final line is detected at freeze/verify by hash and
        tolerated by readers as a truncated tail)."""
        path = self._writable_dir(ref, kind) / "samples.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
        return path

    def write_parquet(self, ref: PartitionRef, kind: str, name: str, df: Any) -> Path:
        """Atomically write a DataFrame as <kind>/<name>.parquet."""
        target = self._writable_dir(ref, kind) / f"{name}.parquet"
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        os.close(fd)
        try:
            df.to_parquet(tmp, index=False)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return target

    # --- freeze / verify ------------------------------------------------------

    def freeze(self, ref: PartitionRef, *, provenance: dict[str, Any]) -> Path:
        """Hash every captured file and atomically write the manifest.

        ``provenance`` supplies the registration §7 control-3 fields (feed
        literal, credential fingerprint, account number, collector version,
        universe + universe_sha256, capture modes, endpoint/schema versions).
        """
        if self.is_frozen(ref):
            raise FrozenPartitionError(f"partition {ref.feed}/{ref.session} is already frozen")
        pdir = self.partition_dir(ref)
        files = sorted(p for p in pdir.rglob("*") if p.is_file() and p.suffix != ".tmp")
        if not files:
            raise FileNotFoundError(f"nothing captured under {pdir}; refusing empty freeze")
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "feed": ref.feed,
            "session": ref.session.isoformat(),
            "collector_version": COLLECTOR_VERSION,
            "frozen_at": datetime.now(UTC).isoformat(),
            **provenance,
            "files": [
                {
                    "path": p.relative_to(pdir).as_posix(),
                    "sha256": _sha256(p),
                    "bytes": p.stat().st_size,
                }
                for p in files
            ],
        }
        mpath = self.manifest_path(ref)
        fd, tmp = tempfile.mkstemp(dir=str(pdir), suffix=".tmp")
        os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            os.replace(tmp, mpath)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        logger.info(
            "mdq_partition_frozen",
            feed=ref.feed,
            session=str(ref.session),
            files=len(files),
        )
        return mpath

    def verify(self, ref: PartitionRef) -> list[str]:
        """Re-hash a frozen partition against its manifest. Returns mismatch
        descriptions (empty == verified)."""
        mpath = self.manifest_path(ref)
        if not mpath.exists():
            return [f"no manifest for {ref.feed}/{ref.session}"]
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        pdir = self.partition_dir(ref)
        problems: list[str] = []
        listed = {f["path"] for f in manifest["files"]}
        for entry in manifest["files"]:
            p = pdir / entry["path"]
            if not p.exists():
                problems.append(f"missing file: {entry['path']}")
            elif _sha256(p) != entry["sha256"]:
                problems.append(f"hash mismatch: {entry['path']}")
        for p in pdir.rglob("*"):
            if (
                p.is_file()
                and p != mpath
                and p.suffix != ".tmp"
                and p.relative_to(pdir).as_posix() not in listed
            ):
                problems.append(f"unmanifested file: {p.relative_to(pdir).as_posix()}")
        return problems


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
