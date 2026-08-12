"""Pinned-object reading, injectable so qualification never touches AWS.

Every governed input is addressed by bucket, key, **Version ID** and SHA-256. An unpinned read, an
object outside the registered set, or a checksum mismatch is refused: the run must not be able to
consume bytes it cannot name exactly.

Two implementations share one contract:

* ``FixtureReader`` serves bytes from a local fixture directory and is what synthetic qualification
  uses. It has no AWS dependency at all - not an unused import, not a lazily-constructed client -
  so a qualification run physically cannot reach the sealed store.
* ``S3PinnedReader`` is the real reader. It is constructed only by the governed run, and it is the
  single place a credential is ever used.

The reader is injected rather than imported, so the qualified code path and the real code path are
the same path with a different reader.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol


class PinnedReadRefused(Exception):
    """A read that cannot be proven to be the registered object. Never retried."""


@dataclass(frozen=True)
class PinnedObject:
    """One governed input, addressed exactly."""

    bucket: str
    key: str
    version_id: str
    sha256: str

    @property
    def partition(self) -> str:
        return self.key.split("/", 1)[0].upper()

    def verify(self, payload: bytes) -> None:
        actual = hashlib.sha256(payload).hexdigest()
        if actual != self.sha256:
            raise PinnedReadRefused(
                f"checksum mismatch for {self.key}@{self.version_id}: {actual} != {self.sha256}"
            )


class PinnedObjectReader(Protocol):
    """The contract both readers implement."""

    def read(self, obj: PinnedObject) -> bytes: ...


class FixtureReader:
    """Local, hermetic, AWS-free. Used by synthetic qualification."""

    reader_kind = "FIXTURE"

    def __init__(self, root: str):
        self._root = root
        self.reads: list[tuple[str, str]] = []

    def read(self, obj: PinnedObject) -> bytes:
        if not obj.version_id:
            raise PinnedReadRefused(f"unpinned read of {obj.key}")
        path = os.path.join(self._root, obj.key.replace("/", os.sep))
        if not os.path.exists(path):
            raise PinnedReadRefused(f"fixture absent for {obj.key}")
        with open(path, "rb") as fh:
            payload = fh.read()
        obj.verify(payload)
        self.reads.append((obj.key, obj.version_id))
        return payload


class S3PinnedReader:
    """The real reader. Constructed only by the governed run; the sole point a credential is used.

    Deliberately does no client work at construction time: building a client is not a read, but a
    reader that connects eagerly invites a probe before PRE_ACCESS_READY.
    """

    reader_kind = "S3"

    def __init__(self, client_factory):
        self._client_factory = client_factory
        self._client = None
        self.reads: list[tuple[str, str]] = []

    def read(self, obj: PinnedObject) -> bytes:
        if not obj.version_id:
            raise PinnedReadRefused(f"unpinned read of {obj.key}")
        if self._client is None:
            self._client = self._client_factory()
        response = self._client.get_object(Bucket=obj.bucket, Key=obj.key, VersionId=obj.version_id)
        payload = response["Body"].read()
        obj.verify(payload)
        self.reads.append((obj.key, obj.version_id))
        return payload
