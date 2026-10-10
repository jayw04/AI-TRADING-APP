"""Deep-freeze helper for the values a spec view hands to the results guard (round 4, N4).

``deep_freeze`` returns an immutable COPY: mappings become ``types.MappingProxyType`` over a
private dict, lists and tuples become tuples, pydantic models become frozen mappings of their
fields. Scalars and dates pass through. Anything else is refused (fail closed) rather than
shared by reference.

What this defends (Level 1, accidental misuse / casual bypass): code holding the ORIGINAL dict
or list (for example the loaded draft's ``p3.criteria``) can no longer change what the guard
sees by mutating it, and the guard-visible values cannot be item-assigned.

What it does NOT defend (Level 2, design-only): code execution in this process. Reaching the
private dict behind a ``MappingProxyType`` (for example through ``gc.get_referents``) or
rebinding module attributes is outside the threat model; Python has no truly immutable
mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel


def deep_freeze(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str | date):
        return value
    if isinstance(value, BaseModel):
        return deep_freeze(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(deep_freeze(v) for v in value)
    raise TypeError(f"cannot deep-freeze a value of type {type(value).__name__}")


# Spec handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = ("deep_freeze",)
