"""Canonical JSON and the stable ``spec_sha256`` (WP0.2).

Why this does not reuse ``app.validation.governed_corpus.canonical_json``: that encoder is
tuned for corpus manifests (``default=str``, no NaN guard, int 5 and float 5.0 hash
differently) and importing it drags in the validation package. A spec hash must (a) refuse
non-finite numbers, (b) treat 5 and 5.0 as the same value so a file round-trip cannot move the
hash, and (c) never stringify an unknown type silently. Same encoding family (sorted keys,
compact separators, ASCII), stricter rules.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


class CanonicalisationError(ValueError):
    """The payload contains a value that has no single canonical encoding."""


def _normalise(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalisationError(f"{path}: non-finite number {value!r}")
        # 5.0 and 5 are the same spec value; -0.0 and 0 likewise.
        return int(value) if value == int(value) else value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalisationError(f"{path}: non-string key {k!r}")
            out[k] = _normalise(v, f"{path}.{k}")
        return out
    if isinstance(value, list | tuple):
        return [_normalise(v, f"{path}[{i}]") for i, v in enumerate(value)]
    raise CanonicalisationError(f"{path}: unsupported type {type(value).__name__}")


def canonical_json(payload: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, finite numbers only."""
    return json.dumps(
        _normalise(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CanonicalisationError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    raise CanonicalisationError(f"non-finite constant {name} is not allowed")


def _parse_finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # "1e999" overflows to inf without going through parse_constant
        raise CanonicalisationError(f"non-finite number {text!r} (float overflow) is not allowed")
    return value


def loads_strict(raw: bytes | str) -> Any:
    """Parse governed JSON: duplicate keys and NaN/Infinity are refused (a repeat key could hide
    a value from a reviewer). Shared by the spec loader and the exposure ledger so both files obey
    one serialization rule: strict JSON in, ``canonical_json`` for hashing."""
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except CanonicalisationError:
        raise
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise CanonicalisationError(f"invalid JSON: {exc}") from exc


def content_sha256(payload: Any) -> str:
    """SHA-256 hex digest of the canonical JSON encoding of ``payload``."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def file_sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed (same contract as governed_corpus.file_sha256)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


# Spec handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = ("canonical_json", "content_sha256", "file_sha256", "loads_strict")
