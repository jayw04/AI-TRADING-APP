"""The fetch-authorization record defaults to DENY. SYNTHETIC records only."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import fetch_authorization_check as chk  # noqa: E402

REPO = Path(__file__).resolve().parents[6]
TEMPLATE = (
    REPO
    / "docs/implementation/evidence/range_002/RANGE-002_Fetch_Authorization_Record_TEMPLATE_v0.1.json"
)


def complete() -> dict:  # type: ignore[type-arg]
    return {
        "record_type": chk.RECORD_TYPE,
        "decision": "ALLOW",
        "issued_by": "synthetic-owner",
        "issued_on": "2000-01-01",
        "owner_record_ref": "synthetic/record.md",
        "vendor": {
            "name": "synthetic-vendor",
            "product": "synthetic-product",
            "entitlement_ref": "ENT-0",
            "answers": {
                "storage_permitted": True,
                "retention_term": "synthetic",
                "aws_hosting_permitted": True,
                "derived_outputs_shareable_with_validator": True,
                "raw_identity_rows_retention_permitted": True,
                "delisted_coverage_confirmed": True,
                "rate_limit_scope": "per key",
                "timestamp_convention_confirmed": True,
                "source_document_ref": "synthetic-doc",
                "answer_received_on": "2000-01-02",
            },
        },
        "aws": {
            "account_id": "000000000000",
            "region": "synthetic-region-1",
            "service": "s3",
            "resource_ref": "synthetic-bucket",
            "data_class": "vendor-licensed",
            "retention": "synthetic",
            "access_roles": ["research"],
            "version_pinned": True,
            "checksum_required": True,
            "encrypted_at_rest": True,
            "resource_authorization_ref": "synthetic/auth.md",
        },
        "scope": {
            "symbols_ref": "synthetic.txt",
            "date_start": "2000-01-01",
            "date_end": "2000-01-31",
            "partition": "development-only",
            "max_requests": 10,
        },
    }


def test_the_shipped_template_is_deny_and_every_blank_is_reported() -> None:
    verdict, reasons = chk.evaluate(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    assert verdict == "DENY"
    assert any("decision" in r for r in reasons)
    assert len(reasons) >= len(chk.REQUIRED_TRUE) + len(chk.REQUIRED_TEXT)


def test_a_fully_answered_record_is_complete() -> None:
    assert chk.evaluate(complete()) == ("ALLOW", [])


@pytest.mark.parametrize("path", chk.REQUIRED_TRUE)
@pytest.mark.parametrize("bad", [None, False, "true", 1])
def test_any_permission_that_is_not_an_explicit_true_denies(path: str, bad: object) -> None:
    rec = complete()
    node = rec
    *parents, leaf = path.split(".")
    for p in parents:
        node = node[p]
    node[leaf] = bad
    verdict, reasons = chk.evaluate(rec)
    assert verdict == "DENY" and any(path in r for r in reasons)


@pytest.mark.parametrize("path", chk.REQUIRED_TEXT)
def test_any_blank_or_missing_text_answer_denies(path: str) -> None:
    for mutate in ("blank", "missing"):
        rec = copy.deepcopy(complete())
        node = rec
        *parents, leaf = path.split(".")
        for p in parents:
            node = node[p]
        if mutate == "blank":
            node[leaf] = "   "
        else:
            del node[leaf]
        assert chk.evaluate(rec)[0] == "DENY"


def test_decision_defaults_to_deny_and_structure_must_be_right() -> None:
    rec = complete()
    rec["decision"] = "DENY"
    assert chk.evaluate(rec)[0] == "DENY"
    rec2 = complete()
    rec2["aws"]["access_roles"] = []
    assert chk.evaluate(rec2)[0] == "DENY"
    rec3 = complete()
    rec3["scope"]["max_requests"] = 0
    assert chk.evaluate(rec3)[0] == "DENY"
    assert chk.evaluate({"record_type": "other"})[0] == "DENY"
    assert chk.evaluate("not a dict")[0] == "DENY"
