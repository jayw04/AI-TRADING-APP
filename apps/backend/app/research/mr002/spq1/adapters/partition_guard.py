"""Mandatory development-partition guard (Phase 2A).

Runs BEFORE any adapter read and records the ACTUAL completed read. Authorization validates that the
partition is DEVELOPMENT, the requested range lies wholly within the frozen development bounds, and
the object is a registered development object (else INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS).
Completion records the executed query, actual returned row count, actual min/max date, and a result
hash; if the returned rows fall outside the authorized bounds the read fails closed. A pre-read
authorization alone is never reported as an opened-object proof.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..refusals import refuse
from . import DEV_END, DEV_START


@dataclass(frozen=True)
class ReadAuthorization:
    object_identity: str
    first_date: str
    last_date: str
    purpose: str
    reader: str
    seq: int


@dataclass
class OpenedObjectLedger:
    """Mandatory ledger of ACTUAL completed reads (evidence). Timestamps excluded from det hashes."""

    entries: list[dict[str, object]] = field(default_factory=list)
    _authorized: int = 0

    def next_seq(self) -> int:
        s = self._authorized
        self._authorized += 1
        return s

    def record_completed(self, entry: dict[str, object]) -> None:
        self.entries.append(entry)


@dataclass(frozen=True)
class PartitionGuard:
    """Development-only access boundary."""

    registered_objects: frozenset[str]
    ledger: OpenedObjectLedger
    dev_start: str = DEV_START
    dev_end: str = DEV_END

    @staticmethod
    def _norm(path: str) -> str:
        return os.path.normpath(path).replace("\\", "/")

    def guard_object(self, path: str) -> str:
        norm = self._norm(path)
        if ".." in norm.split("/"):
            raise refuse("INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS", f"path traversal: {path}")
        if norm not in {self._norm(p) for p in self.registered_objects}:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"object not in the registered development manifest: {path}",
            )
        return norm

    def guard_range(self, first_date: str, last_date: str, allow_pre_window: bool = False) -> None:
        if first_date > last_date:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS", f"inverted range {first_date}..{last_date}"
            )
        # The upper bound (no future / validation / OOS leakage) is always enforced. The lower bound
        # is enforced only for windowed reads (relaxed for pre-existing identity/PIT rows).
        if last_date > self.dev_end or (not allow_pre_window and first_date < self.dev_start):
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"range {first_date}..{last_date} escapes development bounds "
                f"{self.dev_start}..{self.dev_end} (validation/OOS forbidden)",
            )

    def authorize_read(
        self, path: str, first_date: str, last_date: str, purpose: str, reader: str,
        allow_pre_window: bool = False,
    ) -> ReadAuthorization:
        """Validate object + range and issue a read authorization token (no read yet)."""
        norm = self.guard_object(path)
        self.guard_range(first_date, last_date, allow_pre_window=allow_pre_window)
        return ReadAuthorization(norm, first_date, last_date, purpose, reader, self.ledger.next_seq())

    def record_completed_read(
        self,
        token: ReadAuthorization,
        object_sha256: str,
        query_identity: str,
        actual_min_date: str | None,
        actual_max_date: str | None,
        row_count: int,
        result_sha256: str,
        completion_timestamp: str = "",
        allow_pre_window: bool = False,
    ) -> None:
        """Record the ACTUAL read; a returned row outside the authorized bounds fails closed.

        ``allow_pre_window`` relaxes ONLY the lower bound (for identity/PIT rows whose effective date
        legitimately predates the development window); the upper bound (no future/validation/OOS
        leakage) is always enforced.
        """
        if (
            not allow_pre_window
            and actual_min_date is not None
            and actual_min_date < token.first_date
        ):
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"result min {actual_min_date} < authorized {token.first_date}",
            )
        if actual_max_date is not None and actual_max_date > token.last_date:
            raise refuse(
                "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS",
                f"result max {actual_max_date} > authorized {token.last_date}",
            )
        self.ledger.record_completed(
            {
                "seq": token.seq,
                "object_identity": token.object_identity,
                "object_sha256": object_sha256,
                "partition": "DEVELOPMENT",
                "declared_range": f"{token.first_date}..{token.last_date}",
                "query_identity": query_identity,
                "actual_min_date": actual_min_date,
                "actual_max_date": actual_max_date,
                "result_row_count": row_count,
                "result_set_sha256": result_sha256,
                "reader_implementation_identity": token.reader,
                "purpose": token.purpose,
                "completion_timestamp": completion_timestamp,
                "status": "COMPLETED",
            }
        )
