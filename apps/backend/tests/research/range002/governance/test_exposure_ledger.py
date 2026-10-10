from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import exposure_ledger as ledger_module
from app.research.range002.governance.errors import (
    ExposureLedgerError,
    ExposureLedgerNotSignedError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import DateRange

from .conftest import SIGNED_LEDGER, UNSIGNED_LEDGER


def _doc() -> dict[str, Any]:
    return json.loads(SIGNED_LEDGER)


def _load(doc: Any) -> ExposureLedger:
    return ExposureLedger.from_text(json.dumps(doc))


def test_loads_signed_ledger() -> None:
    led = ExposureLedger.from_text(SIGNED_LEDGER)
    assert led.is_signed
    led.require_signed()
    assert [e.id for e in led.entries] == ["syn-rng001-window"]
    assert led.entries[0].window == DateRange(date(2026, 1, 2), date(2026, 6, 12))


def test_unsigned_loads_but_require_signed_refuses() -> None:
    led = ExposureLedger.from_text(UNSIGNED_LEDGER)
    assert not led.is_signed
    with pytest.raises(ExposureLedgerNotSignedError):
        led.require_signed()


def test_overlap_queries_are_inclusive() -> None:
    led = ExposureLedger.from_text(SIGNED_LEDGER)
    assert led.overlaps(DateRange(date(2026, 6, 12), date(2026, 6, 30)))  # touches end
    assert led.overlaps(DateRange(date(2025, 12, 1), date(2026, 1, 2)))  # touches start
    assert not led.overlaps(DateRange(date(2022, 1, 1), date(2025, 12, 31)))
    assert not led.overlaps(DateRange(date(2026, 6, 13), date(2026, 7, 1)))


def test_hash_is_canonical_not_byte_level(tmp_path: Path) -> None:
    """Re-indenting or reordering keys must not move the hash; changing content must."""
    p = tmp_path / "exposure_ledger.json"
    p.write_bytes(SIGNED_LEDGER.encode("utf-8"))
    a, b = ExposureLedger.from_file(p), ExposureLedger.from_text(SIGNED_LEDGER)
    assert a.sha256 == b.sha256
    compact = json.dumps(_doc(), separators=(",", ":"), sort_keys=True)
    assert ExposureLedger.from_text(compact).sha256 == a.sha256
    assert a.sha256 != ExposureLedger.from_text(UNSIGNED_LEDGER).sha256
    changed = _doc()
    changed["entries"][0]["description"] = "different"
    assert _load(changed).sha256 != a.sha256


def test_hash_matches_spec_canonical_convention() -> None:
    from app.research.range002.spec.hashing import content_sha256

    assert ExposureLedger.from_text(SIGNED_LEDGER).sha256 == content_sha256(_doc())


def test_no_yaml_dependency() -> None:
    assert "yaml" not in Path(ledger_module.__file__).read_text(encoding="utf-8").replace(
        "PyYAML", ""
    ).replace("YAML", "").lower().replace("exposure_ledger.yaml", "")


def _mut(fn):
    def apply() -> Any:
        d = copy.deepcopy(_doc())
        fn(d)
        return d

    return apply


@pytest.mark.parametrize(
    "mutate",
    [
        _mut(lambda d: d.update(schema_version=2)),
        _mut(lambda d: d.pop("schema_version")),
        _mut(lambda d: d.update(extra=1)),
        _mut(lambda d: d["entries"][0].pop("source")),
        _mut(lambda d: d["entries"][0].update(x=1)),
        _mut(lambda d: d["entries"][0].update(start="2026-07-01")),  # start > end
        _mut(lambda d: d["entries"][0].update(start="not-a-date")),
        _mut(lambda d: d["entries"][0].update(start=5)),
        _mut(lambda d: d["entries"][0].update(description="")),
        _mut(lambda d: d.update(entries="nope")),
        _mut(lambda d: d.update(signoff=3)),
        _mut(lambda d: d["signoff"].update(extra=1)),
        _mut(lambda d: d["signoff"].pop("signed_by")),
        _mut(lambda d: d.update(entries=["nope"])),
        lambda: ["a", "b"],
    ],
)
def test_schema_violations_fail_closed(mutate) -> None:
    with pytest.raises(ExposureLedgerError):
        _load(mutate())


@pytest.mark.parametrize(
    "raw",
    [
        "a: [unclosed",
        '{"schema_version": 1, "schema_version": 1, "signoff": null, "entries": []}',
        '{"schema_version": NaN, "signoff": null, "entries": []}',
        "schema_version: 1\nsignoff: null\nentries: []\n",  # YAML is not accepted
        "",
    ],
)
def test_not_strict_json_fails_closed(raw: str) -> None:
    with pytest.raises(ExposureLedgerError):
        ExposureLedger.from_text(raw)


def test_invalid_utf8_fails_closed() -> None:
    with pytest.raises(ExposureLedgerError):
        ExposureLedger.from_bytes(b"\xff\xfe{}")


def test_duplicate_ids_rejected() -> None:
    doc = _doc()
    doc["entries"].append(copy.deepcopy(doc["entries"][0]))
    with pytest.raises(ExposureLedgerError, match="duplicate"):
        _load(doc)


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ExposureLedgerError):
        ExposureLedger.from_file(tmp_path / "absent.json")


def test_empty_entries_allowed() -> None:
    doc = _doc()
    doc["entries"] = []
    assert _load(doc).entries == ()
