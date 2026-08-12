"""Canonical verifier for the WS5 authorization body-hash (ADR0043 §17).

Computes ``authorization_body_sha256`` over sections 1-16 of
``ADR0043_LIVE_CANARY_WS5_RUNTIME_PREP_START_001_PROPOSAL.md`` with
``authorized_source_commit`` INCLUDED and the finalization/runtime values
EXCLUDED (replaced by the sentinel ``<EXCLUDED>``).

The verifier fails closed. A document that does not match the expected shape
raises ``CanonicalizationError`` rather than silently producing a different
hash -- a wrong hash is indistinguishable from a tampered body, so structural
drift must be an error.

Structural contract enforced before hashing:

* exactly two fenced operator-record blocks inside section 15 (Stage 1, Stage 2)
  -- or exactly one for the pre-amendment single-stage document, recognised only
  when neither stage heading is present, so its hash stays reproducible;
* exactly one assignment of each excluded scalar;
* ``authorized_source_commit`` present as a full 40-character hex SHA;
* ``authorized_alembic_head`` equal to the frozen governed head.

Usage::

    python hash_ws5_authorization.py <path-to-document.md>
    python hash_ws5_authorization.py --selftest
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

SENTINEL = "<EXCLUDED>"

#: Scalars excluded from the hash; each must appear exactly once (SS17).
EXCLUDED_SCALARS = (
    "runtime_name",
    "authorization_sha",
    "expires_on",
    "database_identity",
)

#: Frozen governed schema head (SS4A). A document naming a different head is
#: not this authorization.
EXPECTED_ALEMBIC_HEAD = "b2d8f4c6a901"

#: Operator-record blocks required inside section 15. The two-stage contract
#: (amendment 1 onward) requires exactly two -- Stage 1 and Stage 2. The legacy
#: single-stage section 15 required exactly one; that shape is still hashable so
#: the pre-amendment hash stays reproducible as a regression anchor, but it is
#: recognised only when BOTH stage headings are absent. A two-stage document with
#: one or three fences, or a legacy document with two, is an error either way.
SECTION_15_FENCES_TWO_STAGE = 2
SECTION_15_FENCES_LEGACY = 1

#: Fenced block, tolerating an optional language label on the opening fence.
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+-]*\n.*?^```", re.MULTILINE | re.DOTALL)

_FIXTURES = Path(__file__).with_name("fixtures")

#: Regression fixtures: filename -> expected body hash. The original pins the
#: pre-amendment hash so canonicalization changes stay behaviour-preserving.
SELFTEST_FIXTURES = {
    "ws5_authorization_original.md": (
        "99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0"
    ),
    "ws5_authorization_amendment1.md": (
        "52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae"
    ),
}


class CanonicalizationError(ValueError):
    """The document does not match the structure section 17 requires."""


def extract_body(text: str) -> str:
    """Sections 1-16: from the line starting '## 1.' up to (excluding) '## 17.'."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("## 1."))
    except StopIteration:
        raise CanonicalizationError(
            "no '## 1.' heading: not a WS5 authorization body"
        ) from None
    try:
        end = next(i for i, ln in enumerate(lines) if ln.startswith("## 17."))
    except StopIteration:
        raise CanonicalizationError(
            "no '## 17.' heading: body boundary undefined"
        ) from None
    if end <= start:
        raise CanonicalizationError("'## 17.' precedes '## 1.': malformed document")
    return "\n".join(lines[start:end])


def _split_section_15(body: str) -> tuple[list[str], str, list[str]]:
    """Return (before, section-15 text, after). Raises if section 15 is absent."""
    lines = body.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## 15.")), None)
    if start is None:
        raise CanonicalizationError("section 15 not found in the hashed body")
    end = next(
        (i for i, ln in enumerate(lines) if i > start and ln.startswith("## ")),
        len(lines),
    )
    return lines[:start], "\n".join(lines[start:end]), lines[end:]


def check_structure(body: str) -> None:
    """Fail closed on any deviation from the section 17 shape."""
    for key in EXCLUDED_SCALARS:
        found = re.findall(rf"(?m)^\s*{re.escape(key)}\s*=\s*.*$", body)
        if len(found) != 1:
            raise CanonicalizationError(
                f"excluded scalar {key!r} must appear exactly once, found {len(found)}"
            )

    commit = re.search(r"(?m)^\s*authorized_source_commit\s*=\s*(\S+)\s*$", body)
    if commit is None:
        raise CanonicalizationError(
            "authorized_source_commit is absent from the hashed body"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", commit.group(1)):
        raise CanonicalizationError(
            f"authorized_source_commit must be a full 40-char hex SHA, got {commit.group(1)!r}"
        )

    head = re.search(r"(?m)^\s*authorized_alembic_head\s*=\s*(\S+)\s*$", body)
    if head is None:
        raise CanonicalizationError(
            "authorized_alembic_head is absent from the hashed body"
        )
    if head.group(1) != EXPECTED_ALEMBIC_HEAD:
        raise CanonicalizationError(
            f"authorized_alembic_head must be {EXPECTED_ALEMBIC_HEAD}, got {head.group(1)!r}"
        )

    _, section15, _ = _split_section_15(body)
    has_stage_1 = re.search(r"(?m)^### 15\.1\b", section15) is not None
    has_stage_2 = re.search(r"(?m)^### 15\.2\b", section15) is not None
    if has_stage_1 != has_stage_2:
        raise CanonicalizationError(
            "section 15 declares only one stage heading; the two-stage contract "
            "requires both 15.1 and 15.2"
        )
    two_stage = has_stage_1 and has_stage_2
    expected = SECTION_15_FENCES_TWO_STAGE if two_stage else SECTION_15_FENCES_LEGACY
    shape = "two-stage" if two_stage else "legacy single-stage"
    fences = _FENCE_RE.findall(section15)
    if len(fences) != expected:
        raise CanonicalizationError(
            f"{shape} section 15 must contain exactly {expected} operator-record "
            f"fenced block(s), found {len(fences)}"
        )


def apply_exclusions(body: str) -> str:
    # Scalar key = value lines (replace the value only).
    for key in EXCLUDED_SCALARS:
        body = re.sub(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$", rf"\1{SENTINEL}", body)

    # Every fenced block inside section 15, including its opening fence and any
    # language label. Structural rather than keyed on a first field, so it covers
    # the 15.1 Stage-1 block, the 15.2 Stage-2 block, and any future section 15
    # block. Scoped to section 15 so the hashed fenced blocks in sections 4, 4A,
    # 7, 8, and 14 are left intact.
    head, section15, tail = _split_section_15(body)
    section15 = _FENCE_RE.sub(f"```\n{SENTINEL}\n```", section15)
    return "\n".join(head + section15.split("\n") + tail)


def canonicalize(body: str) -> bytes:
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in body.split("\n")]
    return "\n".join(lines).rstrip("\n").encode("utf-8")


def compute(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8")
    body = extract_body(text)
    check_structure(body)
    return hashlib.sha256(canonicalize(apply_exclusions(body))).hexdigest()


def selftest() -> int:
    failures = 0
    for name, expected in SELFTEST_FIXTURES.items():
        fixture = _FIXTURES / name
        if not fixture.exists():
            print(f"MISSING  {name}")
            failures += 1
            continue
        actual = compute(fixture)
        ok = actual == expected
        print(f"{'PASS    ' if ok else 'FAIL    '}{name}  {actual}")
        if not ok:
            print(f"         expected {expected}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest())
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    try:
        print(compute(sys.argv[1]))
    except CanonicalizationError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(3) from None
