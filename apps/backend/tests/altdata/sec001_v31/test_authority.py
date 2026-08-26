"""The frozen authority must be LOADED from governed artifacts, never configured."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from app.altdata.sec001_v31.authority import (
    ENVELOPE_PATH,
    ENVELOPE_SHA256,
    MANIFEST_PATH,
    MANIFEST_SHA256,
    SELECTION_PATH,
    SELECTION_SHA256,
    AcquisitionAuthority,
    AuthorityError,
    NotAuthorized,
)
from tests.altdata.sec001_v31.conftest import REPO_ROOT


def test_authority_loads_the_full_verified_chain(authority):
    assert authority.manifest_sha256 == MANIFEST_SHA256
    assert authority.selection_sha256 == SELECTION_SHA256
    assert authority.envelope_sha256 == ENVELOPE_SHA256
    assert authority.selected_envelope == "B"
    assert len(authority.authorized_keys) == 452


def test_every_frozen_parameter_comes_from_the_manifest(authority):
    assert authority.permitted_forms == frozenset(
        {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
    )
    assert authority.max_index_requests == 200
    assert authority.max_document_requests == 1200
    assert authority.ceiling_bytes == 1_048_576
    assert authority.stop_threshold_bytes == 983_040
    assert authority.rate_limit_per_sec == 5.0
    assert authority.halt_statuses == (403,)
    assert authority.cutoff_utc.isoformat() == "2026-08-26T16:11:22+00:00"
    assert authority.allowed_origins == frozenset({"https://www.sec.gov", "https://data.sec.gov"})
    assert len(authority.retained_field_schema) == 7


def test_authority_is_frozen_and_not_overridable(authority):
    """Caps are governed state, not a knob a caller can turn."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        authority.max_document_requests = 99_999  # type: ignore[misc]


@pytest.mark.parametrize(
    "path,sha",
    [
        (MANIFEST_PATH, MANIFEST_SHA256),
        (SELECTION_PATH, SELECTION_SHA256),
        (ENVELOPE_PATH, ENVELOPE_SHA256),
    ],
)
def test_a_tampered_governed_artifact_fails_closed(tmp_path: Path, path: Path, sha: str):
    for p in (MANIFEST_PATH, SELECTION_PATH, ENVELOPE_PATH):
        dst = tmp_path / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / p, dst)

    target = tmp_path / path
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["_tamper"] = True
    target.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(AuthorityError, match="sha256 mismatch"):
        AcquisitionAuthority.load(tmp_path)


def test_a_missing_artifact_fails_closed(tmp_path: Path):
    with pytest.raises(AuthorityError, match="missing"):
        AcquisitionAuthority.load(tmp_path)


def test_authorized_keys_are_exact_four_tuples(authority, envelope_keys):
    cik, form, accession, accepted = envelope_keys[0]
    assert authority.is_authorized(cik, form, accession, accepted)
    # every component must match exactly -- a near miss is not authorization
    assert not authority.is_authorized(cik + 1, form, accession, accepted)
    assert not authority.is_authorized(cik, "8-K", accession, accepted)
    assert not authority.is_authorized(cik, form, "0000000000-00-000000", accepted)
    assert not authority.is_authorized(cik, form, accession, "2026-01-01T00:00:00.000Z")


def test_require_authorized_raises_for_an_unknown_filing(authority):
    with pytest.raises(NotAuthorized, match="not one of the 452"):
        authority.require_authorized(
            1652044, "10-Q", "9999999999-99-999999", "2026-01-01T00:00:00.000Z"
        )


def test_deferred_forms_are_never_authorized(authority, envelope_keys):
    for form in ("8-K", "8-A12B", "6-K"):
        assert form not in authority.permitted_forms
        assert form in authority.deferred_forms or form == "8-A12B"
    cik, _, accession, accepted = envelope_keys[0]
    assert not authority.is_authorized(cik, "8-K", accession, accepted)


def test_origin_enforcement(authority):
    assert authority.origin_allowed("https://www.sec.gov/Archives/edgar/data/1/2/x.htm")
    assert authority.origin_allowed("https://data.sec.gov/submissions/CIK0001652044.json")
    for bad in (
        "https://evil.example.com/x.htm",
        "http://www.sec.gov/Archives/x.htm",  # wrong scheme
        "https://www.sec.gov.evil.com/x.htm",
        "https://sec.gov/Archives/x.htm",  # not a frozen origin
    ):
        assert not authority.origin_allowed(bad), bad
        with pytest.raises(NotAuthorized):
            authority.require_origin(bad)


def test_archive_url_is_built_from_governed_identifiers(authority, envelope_keys):
    cik, _, accession, _ = envelope_keys[0]
    url = authority.archive_url(cik, accession, "abc-20260630.htm")
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert accession.replace("-", "") in url
    assert authority.origin_allowed(url)


def test_archive_url_refuses_an_unauthorized_accession(authority):
    with pytest.raises(NotAuthorized, match="not in the authorized envelope"):
        authority.archive_url(1652044, "9999999999-99-999999", "x.htm")


def test_all_authorized_keys_are_permitted_forms_and_within_cutoff(authority):
    from app.altdata.sec001_v31.clock import accepted_at_utc

    for cik, form, accession, accepted in authority.authorized_keys:
        assert form in authority.permitted_forms
        assert accepted_at_utc(accepted) <= authority.cutoff_utc
        assert isinstance(cik, int) and accession.count("-") == 2
