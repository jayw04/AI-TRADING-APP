"""Mandatory development-partition guard (Phase 2A).

Runs BEFORE any adapter read. Validates that the requested partition is DEVELOPMENT, the requested
time range lies wholly within the frozen development bounds, and the source object is a registered
development object; anything else fails closed INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS. Every
permitted read is recorded in the opened-object ledger. Validation/OOS ranges and unregistered /
path-traversing objects can never be read.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..refusals import refuse
from . import DEV_END, DEV_START


@dataclass
class OpenedObjectLedger:
    """Mandatory ledger of every real-data read (evidence; excluded from determinism hashes)."""

    entries: list[dict[str, object]] = field(default_factory=list)

    def record(
        self,
        object_identity: str,
        partition: str,
        purpose: str,
        reader: str,
        query_range: str,
        row_count: int,
        retrieval_timestamp: str = "",
    ) -> None:
        self.entries.append(
            {
                "seq": len(self.entries),
                "object_identity": object_identity,
                "partition": partition,
                "purpose": purpose,
                "reader_implementation_identity": reader,
                "query_range": query_range,
                "result_row_count": row_count,
                "retrieval_timestamp": retrieval_timestamp,
            }
        )


@dataclass(frozen=True)
class PartitionGuard:
    """Development-only access boundary. ``registered_objects`` are the only paths any adapter may
    open; the development snapshot is added once materialized."""

    registered_objects: frozenset[str]
    ledger: OpenedObjectLedger
    dev_start: str = DEV_START
    dev_end: str = DEV_END

    @staticmethod
    def _norm(path: str) -> str:
        return os.path.normpath(path).replace("\\", "/")

    def guard_object(self, path: str) -> str:
        """Assert ``path`` is a registered development object (no traversal, no unregistered)."""
        norm = self._norm(path)
        if ".." in norm.split("/"):
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"path traversal rejected: {path}",
            )
        registered = {self._norm(p) for p in self.registered_objects}
        if norm not in registered:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"object not in the registered development manifest: {path}",
            )
        return norm

    def guard_range(self, first_date: str, last_date: str) -> None:
        """Assert the requested [first, last] range lies wholly within development bounds."""
        if first_date > last_date:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"inverted range {first_date}..{last_date}",
            )
        if first_date < self.dev_start or last_date > self.dev_end:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"range {first_date}..{last_date} escapes development bounds "
                f"{self.dev_start}..{self.dev_end} (validation/OOS forbidden)",
            )

    def guarded_read(
        self,
        path: str,
        first_date: str,
        last_date: str,
        purpose: str,
        reader: str,
        row_count: int,
        retrieval_timestamp: str = "",
    ) -> str:
        """Full gate: object + range checks, then record the read. Returns the normalized path."""
        norm = self.guard_object(path)
        self.guard_range(first_date, last_date)
        self.ledger.record(
            object_identity=norm,
            partition="DEVELOPMENT",
            purpose=purpose,
            reader=reader,
            query_range=f"{first_date}..{last_date}",
            row_count=row_count,
            retrieval_timestamp=retrieval_timestamp,
        )
        return norm
