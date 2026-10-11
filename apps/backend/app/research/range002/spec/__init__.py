"""RANGE-002 frozen-spec schema, canonical hashing and loader (WP0.2 / WP0.3).

Public surface for the results guard is :class:`SpecView` (read-only) obtained from
:func:`load_frozen`. No spec value for an unresolved P0 decision is ever defaulted here.
"""

from app.research.range002.spec.hashing import canonical_json, content_sha256
from app.research.range002.spec.loader import (
    SpecHashMismatchError,
    SpecSchemaError,
    SpecView,
    SpecViewNotCopyableError,
    load_draft,
    load_frozen,
)
from app.research.range002.spec.schema import (
    DraftSpec,
    FrozenSpec,
    SignoffMissingError,
    SignoffRoleCharactersError,
    SignoffRolesNotDistinctError,
    UnsetP0FieldsError,
    draft_skeleton,
)

__all__ = [
    "DraftSpec",
    "FrozenSpec",
    "SignoffMissingError",
    "SignoffRoleCharactersError",
    "SignoffRolesNotDistinctError",
    "SpecHashMismatchError",
    "SpecSchemaError",
    "SpecView",
    "SpecViewNotCopyableError",
    "UnsetP0FieldsError",
    "canonical_json",
    "content_sha256",
    "draft_skeleton",
    "load_draft",
    "load_frozen",
]
