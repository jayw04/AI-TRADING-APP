"""Acquisition orchestration: envelope binding, locator authentication, atomic custody."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.acquire import (
    ACQUIRED,
    INDEX_COVER_CIK_MISMATCH,
    REFUSED_CUTOFF,
    REFUSED_DUPLICATE,
    REFUSED_FORM,
    REFUSED_NOT_IN_ENVELOPE,
    CoverAcquisition,
)
from app.altdata.sec001_v31.layers import FilingMetadata, LocatorMismatch, TransportLocator
from tests.altdata.sec001_v31.conftest import make_fetcher, ranged_response, read_committed
from tests.altdata.sec001_v31.fixtures import ALPHABET_CLASSES, cover_doc


@pytest.fixture
def authorized(envelope_keys):
    """A REAL authorized filing from Envelope B."""
    cik, form, accession, accepted = envelope_keys[0]
    return FilingMetadata(cik=cik, form=form, accession=accession, accepted_at=accepted)


@pytest.fixture
def locator(authority, authorized):
    return TransportLocator(
        cik=authorized.cik,
        accession=authorized.accession,
        primary_document="goog-20260630.htm",
        url=authority.archive_url(authorized.cik, authorized.accession, "goog-20260630.htm"),
    )


def build(authority, ledger, store, body: bytes, calls=None, **kw):
    def handler(r: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(r.url))
        return ranged_response(body, r)

    return CoverAcquisition(
        authority, make_fetcher(authority, ledger, handler), store, ledger, **kw
    )


def doc_for(meta: FilingMetadata, classes=None) -> bytes:
    return cover_doc(cik=f"{meta.cik:010d}", classes=classes or ALPHABET_CLASSES)


# ===================================================== envelope binding (P0)
def test_a_filing_outside_the_authorized_envelope_is_refused_before_any_request(
    authority, ledger, store, authorized
):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    # plausible but not one of the 452: same CIK and form, invented accession
    rogue = FilingMetadata(
        cik=authorized.cik,
        form=authorized.form,
        accession="0001652044-26-999999",
        accepted_at=authorized.accepted_at,
    )
    r = acq.acquire(
        rogue,
        TransportLocator(
            rogue.cik,
            rogue.accession,
            "x.htm",
            f"https://www.sec.gov/Archives/edgar/data/{rogue.cik}/000165204426999999/x.htm",
        ),
    )

    assert r.status == REFUSED_NOT_IN_ENVELOPE
    assert r.diagnostics["authorized_count"] == 452
    assert calls == [] and ledger.document_requests == 0


def test_an_authorized_filing_proceeds(authority, ledger, store, authorized, locator):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)
    assert r.status == ACQUIRED and len(calls) == 1


@pytest.mark.parametrize("form", ["8-K", "8-A12B", "6-K", "S-1", "4"])
def test_non_permitted_form_refused_before_any_request(
    authority, ledger, store, authorized, locator, form
):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    meta = FilingMetadata(authorized.cik, form, authorized.accession, authorized.accepted_at)
    r = acq.acquire(meta, locator)
    assert r.status == REFUSED_FORM and calls == [] and ledger.document_requests == 0


def test_post_cutoff_refused_before_any_request(authority, ledger, store, authorized, locator):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    meta = FilingMetadata(
        authorized.cik, authorized.form, authorized.accession, "2026-08-27T09:00:00.000Z"
    )
    r = acq.acquire(meta, locator)
    assert r.status == REFUSED_CUTOFF and calls == [] and ledger.document_requests == 0


# ===================================================== locator authentication (P0)
def test_a_locator_for_a_different_accession_is_rejected(authority, ledger, store, authorized):
    """Metadata for authorized accession A + a URL pointing at accession B.

    Without authentication the observation would be stamped A while carrying B's bytes.
    """
    acq = build(authority, ledger, store, doc_for(authorized))
    other = TransportLocator(
        cik=authorized.cik,
        accession="0001652044-26-000099",
        primary_document="x.htm",
        url=f"https://www.sec.gov/Archives/edgar/data/{authorized.cik}/000165204426000099/x.htm",
    )
    with pytest.raises(LocatorMismatch, match="locator identifies"):
        acq.acquire(authorized, other)
    assert ledger.document_requests == 0


def test_a_locator_for_a_different_cik_is_rejected(authority, ledger, store, authorized, locator):
    acq = build(authority, ledger, store, doc_for(authorized))
    wrong = TransportLocator(authorized.cik + 1, authorized.accession, "x.htm", locator.url)
    with pytest.raises(LocatorMismatch):
        acq.acquire(authorized, wrong)


def test_a_locator_url_not_containing_its_accession_is_rejected(
    authority, ledger, store, authorized
):
    acq = build(authority, ledger, store, doc_for(authorized))
    bad = TransportLocator(
        authorized.cik,
        authorized.accession,
        "x.htm",
        f"https://www.sec.gov/Archives/edgar/data/{authorized.cik}/000000000000000000/x.htm",
    )
    with pytest.raises(LocatorMismatch, match="does not contain accession"):
        acq.acquire(authorized, bad)


def test_primary_document_filename_ticker_still_has_zero_identity_effect(
    authority, ledger, store, authorized, locator
):
    """Filename says 'goog'; the cover declares only Class A / GOOGL."""
    acq = build(authority, ledger, store, doc_for(authorized, [ALPHABET_CLASSES[0]]))
    r = acq.acquire(authorized, locator)
    assert len(r.observations) == 1
    assert r.observations[0].trading_symbol == "GOOGL"
    assert "goog-20260630" not in str(r.observations[0].to_record())


def test_locator_repr_does_not_leak_the_filename(locator):
    assert "goog-20260630.htm" not in repr(locator) and "redacted" in repr(locator)


# ===================================================== CIK-once, durable
def test_duplicate_is_refused_and_survives_a_new_orchestrator(
    authority, ledger, store, authorized, locator
):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    assert acq.acquire(authorized, locator).status == ACQUIRED

    # a NEW orchestrator over the SAME durable ledger, as a restart would produce
    acq2 = build(authority, ledger, store, doc_for(authorized), calls)
    r = acq2.acquire(authorized, locator)
    assert r.status == REFUSED_DUPLICATE
    assert len(calls) == 1 and ledger.document_requests == 1


# ===================================================== multi-class + atomic custody
def test_one_accession_two_classes_is_one_fetch_and_one_atomic_commit(
    authority, ledger, store, authorized, locator
):
    calls: list[str] = []
    acq = build(authority, ledger, store, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)

    assert r.parse_status == cover_parser.STATUS_BOUND
    assert len(calls) == 1 and ledger.document_requests == 1
    assert {o.trading_symbol for o in r.observations} == {"GOOG", "GOOGL"}

    doc = read_committed(store, authorized.cik, authorized.accession, authority.source_variant)
    assert len(doc["observations"]) == 2
    assert len(list(store.root.glob("*.json"))) == 1, "one atomic object per accession"


def test_provenance_is_retained_beside_the_seven_fields_never_inside_them(
    authority, ledger, store, authorized, locator
):
    acq = build(authority, ledger, store, doc_for(authorized), None)
    acq.acquire(authorized, locator)
    doc = read_committed(store, authorized.cik, authorized.accession, authority.source_variant)

    for rec in doc["observations"]:
        assert set(rec) == set(authority.retained_field_schema)
    prov = doc["provenance"]
    assert len(prov["body_sha256"]) == 64
    assert prov["eof_reached"] is True
    assert prov["manifest_sha256"] == authority.manifest_sha256
    assert prov["envelope_sha256"] == authority.envelope_sha256


# ===================================================== failure states
def test_cover_cik_mismatch_has_its_own_state_and_writes_nothing(
    authority, ledger, store, authorized, locator
):
    acq = build(authority, ledger, store, cover_doc(cik="0000320193", classes=ALPHABET_CLASSES))
    r = acq.acquire(authorized, locator)
    assert r.parse_status == INDEX_COVER_CIK_MISMATCH
    assert r.parse_status != cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.diagnostics["cover_cik"] == 320193 and r.diagnostics["index_cik"] == authorized.cik
    assert "DISPUTED" in r.diagnostics["consequence"]
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_ticker_only_document_writes_nothing(authority, ledger, store, authorized, locator):
    acq = build(authority, ledger, store, doc_for(authorized, [("GOOGL", "", "", "c-a")]))
    r = acq.acquire(authorized, locator)
    assert r.parse_status == cover_parser.STATUS_DISPUTED_TICKER_ONLY
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_non_eof_response_yields_evidence_unavailable_and_writes_nothing(
    authority, ledger, store, authorized, locator
):
    body = doc_for(authorized)

    def handler(r: httpx.Request) -> httpx.Response:
        return ranged_response(body, r, total=len(body) * 40)  # a prefix of a larger document

    acq = CoverAcquisition(authority, make_fetcher(authority, ledger, handler), store, ledger)
    r = acq.acquire(authorized, locator)

    assert r.parse_status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "bounded_read_did_not_reach_eof"
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_every_observation_is_reconstructable_to_its_immutable_identity(
    authority, ledger, store, authorized, locator
):
    acq = build(authority, ledger, store, doc_for(authorized), None)
    r = acq.acquire(authorized, locator)
    for obs, ident in zip(r.observations, r.artifact_identities, strict=True):
        cik_s, acc, variant, obs_id = ident.split("/")
        assert int(cik_s) == obs.cik and acc == obs.accession
        assert variant == authority.source_variant and obs_id == obs.observation_id(variant)
