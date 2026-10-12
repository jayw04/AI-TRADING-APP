"""Default-DENY completeness check for a RANGE-002 fetch-authorization record.

    python -I scripts/research/range002/fetch_authorization_check.py record.json

Exit status 0 = ALLOW (the record is complete and every required permission is an explicit
``true``), 1 = DENY. Stdlib only, reads one file, makes no network call and fetches nothing.
A complete record is NOT an authorization: only the owner committing it as a dated record in
Git is. The checker exists so that a missing or blank answer can never read as consent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

RECORD_TYPE = "range002.fetch_authorization.v1"

#: dotted paths that must be an explicit ``true`` (null, false, missing or any other value = DENY)
REQUIRED_TRUE = (
    "vendor.answers.storage_permitted",
    "vendor.answers.aws_hosting_permitted",
    "vendor.answers.derived_outputs_shareable_with_validator",
    "vendor.answers.raw_identity_rows_retention_permitted",
    "vendor.answers.delisted_coverage_confirmed",
    "vendor.answers.timestamp_convention_confirmed",
    "aws.version_pinned",
    "aws.checksum_required",
    "aws.encrypted_at_rest",
)
#: dotted paths that must be a non-blank string
REQUIRED_TEXT = (
    "issued_by",
    "issued_on",
    "owner_record_ref",
    "vendor.name",
    "vendor.product",
    "vendor.entitlement_ref",
    "vendor.answers.retention_term",
    "vendor.answers.rate_limit_scope",
    "vendor.answers.source_document_ref",
    "vendor.answers.answer_received_on",
    "aws.account_id",
    "aws.region",
    "aws.service",
    "aws.resource_ref",
    "aws.data_class",
    "aws.retention",
    "aws.resource_authorization_ref",
    "scope.symbols_ref",
    "scope.date_start",
    "scope.date_end",
    "scope.partition",
)


def _get(node: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def evaluate(record: Any) -> tuple[str, list[str]]:
    """Return ``("ALLOW" | "DENY", reasons)``. Anything not explicitly satisfied is a reason."""
    reasons: list[str] = []
    if not isinstance(record, dict) or record.get("record_type") != RECORD_TYPE:
        return "DENY", [f"record_type must be {RECORD_TYPE!r}"]
    if record.get("decision") != "ALLOW":
        reasons.append("decision is not 'ALLOW' (the owner sets it; default DENY)")
    for path in REQUIRED_TRUE:
        if _get(record, path) is not True:
            reasons.append(f"{path} is not an explicit true")
    for path in REQUIRED_TEXT:
        v = _get(record, path)
        if not isinstance(v, str) or not v.strip():
            reasons.append(f"{path} is blank or missing")
    roles = _get(record, "aws.access_roles")
    if (
        not isinstance(roles, list)
        or not roles
        or not all(isinstance(r, str) and r.strip() for r in roles)
    ):
        reasons.append("aws.access_roles must be a non-empty list of names")
    mr = _get(record, "scope.max_requests")
    if type(mr) is not int or mr <= 0:
        reasons.append("scope.max_requests must be a positive integer")
    return ("DENY", reasons) if reasons else ("ALLOW", [])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        record = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"DENY: cannot read record: {exc}")
        return 1
    verdict, reasons = evaluate(record)
    print(verdict)
    for r in reasons:
        print(f"  - {r}")
    return 0 if verdict == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
