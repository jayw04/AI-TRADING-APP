"""Mechanical guarantee that the crawler cannot emit a coverage quantity.

CoverageFreeze v1.0 §4 states the anti-peek control as a premise: "the coverage
measurement tool emits coverage statistics only ... this is a mechanical guarantee, not an
instruction to be careful." The converse obligation lands here. The *crawler* must emit no
coverage quantity at all, because a coverage number produced during acquisition — before
the one-shot adjudication artifact spends ``5b26ffa2…`` — is exactly the peek the freeze
exists to prevent.

Being careful is not a control. So every byte this package writes goes through
``dump_json`` / ``dump_jsonl`` below, and those refuse, at runtime, to serialize any
structure carrying a forbidden name at any depth. There is no "unchecked" writer in the
package and no flag that disables the check.

The guard is deliberately name-based rather than value-based. A coverage number is not
identifiable by its value — 0.95 is just a float — so the only thing that can be forbidden
mechanically is the vocabulary. That means the guard is exact-match and case-sensitive on
the ten frozen names, and it is checked against the actual field lists of the package's own
dataclasses at import time (``assert_dataclass_clean``), so a future edit that adds a
forbidden field to an emitted record fails on import, not on the crawl's last write.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

#: The ten quantities that belong to the coverage-adjudication artifact and to nothing
#: else. Frozen by CoverageFreeze v1.0 §2-§3 and the 2026-08-24 handoff.
FORBIDDEN_COVERAGE_FIELDS: Final[frozenset[str]] = frozenset({
    "name_coverage_pct",
    "slot_coverage_pct",
    "window_coverage_pct",
    "qualifying_slot_count",
    "failing_slot_count",
    "earliest_qualifying_start",
    "final_evaluation_start",
    "theta_name_pass",
    "theta_window_pass",
    "coverage_gate_result",
})


class ForbiddenCoverageField(RuntimeError):
    """Raised when a coverage quantity reaches the serializer.

    Not a ``ValueError``: this is a governance stop, and it must not be mistaken for
    ordinary bad input that a caller might reasonably swallow.
    """

    def __init__(self, field: str, path: str) -> None:
        super().__init__(
            f"forbidden coverage field {field!r} at {path or '<root>'}: the SEC-001 V3 crawl "
            f"emits facts only. Coverage adjudication is a separate one-shot artifact that "
            f"spends the coverage-freeze token; it is not produced during acquisition."
        )
        self.field = field
        self.path = path


def _walk(obj: Any, path: str) -> None:
    """Depth-first check of every mapping key reachable from ``obj``."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        obj = dataclasses.asdict(obj)
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            name = str(key)
            if name in FORBIDDEN_COVERAGE_FIELDS:
                raise ForbiddenCoverageField(name, path)
            _walk(value, f"{path}.{name}" if path else name)
        return
    # str/bytes are Sequences; they carry no keys and must not be iterated element-wise.
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for i, value in enumerate(obj):
            _walk(value, f"{path}[{i}]")
        return
    if isinstance(obj, (set, frozenset)):
        for value in obj:
            _walk(value, f"{path}{{}}")


def assert_no_forbidden_fields(obj: Any) -> None:
    """Raise ``ForbiddenCoverageField`` if any forbidden name appears at any depth."""
    _walk(obj, "")


def assert_dataclass_clean(*types: type) -> None:
    """Import-time assertion that emitted record types declare no forbidden field.

    Catches the failure one edit earlier than the serializer would: a developer who adds
    ``coverage_gate_result`` to an evidence record gets an ImportError, not a crawl that
    runs for hours and dies on its final write.
    """
    for tp in types:
        if not dataclasses.is_dataclass(tp):
            raise TypeError(f"{tp!r} is not a dataclass")
        for f in dataclasses.fields(tp):
            if f.name in FORBIDDEN_COVERAGE_FIELDS:
                raise ForbiddenCoverageField(f.name, f"{tp.__module__}.{tp.__qualname__}")


def _default(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"{type(obj).__name__} is not JSON-serializable in the V3 crawl")


def dumps(obj: Any) -> str:
    """The package's only object->JSON path. Guard first, serialize second."""
    assert_no_forbidden_fields(obj)
    return json.dumps(obj, default=_default, sort_keys=True, separators=(",", ":"))


def dump_json(obj: Any, path: Path) -> None:
    """Write one JSON document, guarded, LF-terminated, atomically."""
    text = dumps(obj) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


def append_jsonl(obj: Any, path: Path) -> None:
    """Append one guarded JSONL record.

    Append rather than rewrite: the raw evidence log is the crawl's audit trail, and a
    crawl that is killed mid-flight must leave every record it already earned.
    """
    line = dumps(obj) + "\n"
    with path.open("ab") as fh:
        fh.write(line.encode("utf-8"))
