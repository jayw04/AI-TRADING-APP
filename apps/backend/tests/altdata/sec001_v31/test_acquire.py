"""Acquisition orchestration: envelope binding, locator authentication, atomic custody."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.acquire import (
    ACQUIRED,
    INCONSISTENT_CUSTODY_STATE,
    INDEX_COVER_CIK_MISMATCH,
    REFUSED_CUTOFF,
    REFUSED_EVIDENCE_UNAVAILABLE,
    REFUSED_FORM,
    REFUSED_NOT_IN_ENVELOPE,
    REFUSED_SEALED,
    CoverAcquisition,
)
from app.altdata.sec001_v31.authority import NotAuthorized
from app.altdata.sec001_v31.custody import AccessionState
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


def build(authority, ledger, store, journal, body: bytes, calls=None):
    def handler(r: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(r.url))
        return ranged_response(body, r)

    return CoverAcquisition(
        authority, make_fetcher(authority, ledger, handler), store, ledger, journal
    )


def doc_for(meta: FilingMetadata, classes=None) -> bytes:
    return cover_doc(cik=f"{meta.cik:010d}", classes=classes or ALPHABET_CLASSES)


# ===================================================== envelope binding (P0)
def test_a_filing_outside_the_authorized_envelope_is_refused_before_any_request(
    authority, ledger, store, journal, authorized
):
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
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


def test_an_authorized_filing_proceeds(authority, ledger, store, journal, authorized, locator):
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)
    assert r.status == ACQUIRED and len(calls) == 1


@pytest.mark.parametrize("form", ["8-K", "8-A12B", "6-K", "S-1", "4"])
def test_non_permitted_form_refused_before_any_request(
    authority, ledger, store, journal, authorized, locator, form
):
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    meta = FilingMetadata(authorized.cik, form, authorized.accession, authorized.accepted_at)
    r = acq.acquire(meta, locator)
    assert r.status == REFUSED_FORM and calls == [] and ledger.document_requests == 0


def test_post_cutoff_refused_before_any_request(
    authority, ledger, store, journal, authorized, locator
):
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    meta = FilingMetadata(
        authorized.cik, authorized.form, authorized.accession, "2026-08-27T09:00:00.000Z"
    )
    r = acq.acquire(meta, locator)
    assert r.status == REFUSED_CUTOFF and calls == [] and ledger.document_requests == 0


# ===================================================== locator authentication (P0)
def test_a_locator_for_a_different_accession_is_rejected(
    authority, ledger, store, journal, authorized
):
    """Metadata for authorized accession A + a URL pointing at accession B.

    Without authentication the observation would be stamped A while carrying B's bytes.
    """
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    other = TransportLocator(
        cik=authorized.cik,
        accession="0001652044-26-000099",
        primary_document="x.htm",
        url=f"https://www.sec.gov/Archives/edgar/data/{authorized.cik}/000165204426000099/x.htm",
    )
    with pytest.raises(LocatorMismatch, match="locator identifies"):
        acq.acquire(authorized, other)
    assert ledger.document_requests == 0


def test_a_locator_for_a_different_cik_is_rejected(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    wrong = TransportLocator(authorized.cik + 1, authorized.accession, "x.htm", locator.url)
    with pytest.raises(LocatorMismatch):
        acq.acquire(authorized, wrong)


def test_a_locator_url_not_containing_its_accession_is_rejected(
    authority, ledger, store, journal, authorized
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    bad = TransportLocator(
        authorized.cik,
        authorized.accession,
        "x.htm",
        f"https://www.sec.gov/Archives/edgar/data/{authorized.cik}/000000000000000000/x.htm",
    )
    with pytest.raises(LocatorMismatch, match="does not contain accession"):
        acq.acquire(authorized, bad)


def test_primary_document_filename_ticker_still_has_zero_identity_effect(
    authority, ledger, store, journal, authorized, locator
):
    """Filename says 'goog'; the cover declares only Class A / GOOGL."""
    acq = build(authority, ledger, store, journal, doc_for(authorized, [ALPHABET_CLASSES[0]]))
    r = acq.acquire(authorized, locator)
    assert len(r.observations) == 1
    assert r.observations[0].trading_symbol == "GOOGL"
    assert "goog-20260630" not in str(r.observations[0].to_record())


def test_locator_repr_does_not_leak_the_filename(locator):
    assert "goog-20260630.htm" not in repr(locator) and "redacted" in repr(locator)


# ===================================================== CIK-once, durable
def test_a_second_acquisition_after_sealing_is_refused_precisely(
    authority, ledger, store, journal, authorized, locator
):
    """CIK-once across a restart. The refusal now names WHY -- generic "duplicate" is gone,
    because every case it covered is expressed by a more precise custody state."""
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    assert acq.acquire(authorized, locator).status == ACQUIRED

    # a NEW orchestrator over the SAME durable stores, as a restart would produce
    acq2 = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = acq2.acquire(authorized, locator)
    assert r.status == REFUSED_SEALED
    assert len(calls) == 1 and ledger.document_requests == 1


def test_there_is_no_generic_duplicate_status(authority):
    import app.altdata.sec001_v31.acquire as acquire_mod

    assert not hasattr(acquire_mod, "REFUSED_DUPLICATE")
    for r in acquire_mod.refusal_reasons():
        assert r != "REFUSED_ALREADY_ACQUIRED"


# ===================================================== multi-class + atomic custody
def test_one_accession_two_classes_is_one_fetch_and_one_atomic_commit(
    authority, ledger, store, journal, authorized, locator
):
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)

    assert r.parse_status == cover_parser.STATUS_BOUND
    assert len(calls) == 1 and ledger.document_requests == 1
    assert {o.trading_symbol for o in r.observations} == {"GOOG", "GOOGL"}

    doc = read_committed(store, authorized.cik, authorized.accession, authority.source_variant)
    assert len(doc["observations"]) == 2
    assert len(list(store.root.glob("*.json"))) == 1, "one atomic object per accession"


def test_provenance_is_retained_beside_the_seven_fields_never_inside_them(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized), None)
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
    authority, ledger, store, journal, authorized, locator
):
    acq = build(
        authority, ledger, store, journal, cover_doc(cik="0000320193", classes=ALPHABET_CLASSES)
    )
    r = acq.acquire(authorized, locator)
    assert r.parse_status == INDEX_COVER_CIK_MISMATCH
    assert r.parse_status != cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.diagnostics["cover_cik"] == 320193 and r.diagnostics["index_cik"] == authorized.cik
    assert "DISPUTED" in r.diagnostics["consequence"]
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_ticker_only_document_writes_nothing(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized, [("GOOGL", "", "", "c-a")]))
    r = acq.acquire(authorized, locator)
    assert r.parse_status == cover_parser.STATUS_DISPUTED_TICKER_ONLY
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_non_eof_response_yields_evidence_unavailable_and_writes_nothing(
    authority, ledger, store, journal, authorized, locator
):
    body = doc_for(authorized)

    def handler(r: httpx.Request) -> httpx.Response:
        return ranged_response(body, r, total=len(body) * 40)  # a prefix of a larger document

    acq = CoverAcquisition(
        authority, make_fetcher(authority, ledger, handler), store, ledger, journal
    )
    r = acq.acquire(authorized, locator)

    assert r.parse_status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "bounded_read_did_not_reach_eof"
    assert r.observations == [] and list(store.root.glob("*.json")) == []


def test_every_observation_is_reconstructable_to_its_immutable_identity(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized), None)
    r = acq.acquire(authorized, locator)
    for obs, ident in zip(r.observations, r.artifact_identities, strict=True):
        cik_s, acc, variant, obs_id = ident.split("/")
        assert int(cik_s) == obs.cik and acc == obs.accession
        assert variant == authority.source_variant and obs_id == obs.observation_id(variant)


# ===================================================== canonical path authentication
def test_an_authorized_accession_paired_with_the_wrong_cik_in_the_path_is_refused(
    authority, ledger, store, journal, authorized
):
    """The accession is real and authorized, but the archive path names another registrant."""
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    wrong_path = TransportLocator(
        cik=authorized.cik,
        accession=authorized.accession,
        primary_document="x.htm",
        url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            f"{authorized.accession.replace('-', '')}/x.htm"
        ),
    )
    with pytest.raises(NotAuthorized, match="not the canonical archive URL"):
        acq.acquire(authorized, wrong_path)
    assert ledger.document_requests == 0
    assert journal.state_of(authorized.accession) is AccessionState.AUTHORIZED


def test_a_non_canonical_but_same_origin_url_containing_the_accession_is_refused(
    authority, ledger, store, journal, authorized
):
    """'same origin + contains the accession' was the old, insufficient check."""
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    sneaky = TransportLocator(
        cik=authorized.cik,
        accession=authorized.accession,
        primary_document="x.htm",
        url=f"https://www.sec.gov/Archives/{authorized.accession}/elsewhere/x.htm",
    )
    with pytest.raises(NotAuthorized, match="not the canonical archive URL"):
        acq.acquire(authorized, sneaky)
    assert ledger.document_requests == 0


@pytest.mark.parametrize("doc", ["../../../etc/passwd", "sub/dir.htm", "x.htm?a=1", "x.htm#f"])
def test_an_unsafe_primary_document_name_is_refused(
    authority, ledger, store, journal, authorized, doc
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    loc = TransportLocator(
        cik=authorized.cik,
        accession=authorized.accession,
        primary_document=doc,
        url=(
            f"https://www.sec.gov/Archives/edgar/data/{authorized.cik}/"
            f"{authorized.accession.replace('-', '')}/{doc}"
        ),
    )
    with pytest.raises(NotAuthorized):
        acq.acquire(authorized, loc)
    assert ledger.document_requests == 0


# ===================================================== continuation is frozen, not a knob
def test_continuation_is_mechanically_bound_to_the_live_authorized_value(
    authority, ledger, store, journal, authorized
):
    from app.altdata.sec001_v31.authority import LIVE_MAX_CONTINUATIONS

    acq = build(authority, ledger, store, journal, doc_for(authorized))
    assert acq.max_continuations == LIVE_MAX_CONTINUATIONS == 7


def test_the_orchestrator_accepts_no_continuation_override(authority, ledger, store, journal):
    """A caller must not be able to instantiate the production orchestrator with 8."""
    import inspect

    params = inspect.signature(CoverAcquisition.__init__).parameters
    assert "max_continuations" not in params


# ===================================================== crash-window integration
def test_a_crash_between_request_and_custody_leaves_a_non_terminal_state(
    authority, ledger, store, journal, authorized, locator
):
    """Publication explodes after the bytes are parsed; the accession must NOT read as
    complete, and the artifact must not exist."""
    from app.altdata.sec001_v31 import custody as custody_mod

    acq = build(authority, ledger, store, journal, doc_for(authorized))
    real = custody_mod.TransactionalEvidenceStore.publish_accession_set

    def boom(self, *a, **k):
        raise OSError("simulated crash during publication")

    custody_mod.TransactionalEvidenceStore.publish_accession_set = boom
    try:
        with pytest.raises(OSError):
            acq.acquire(authorized, locator)
    finally:
        custody_mod.TransactionalEvidenceStore.publish_accession_set = real

    assert journal.state_of(authorized.accession) is AccessionState.PARSED
    assert journal.state_of(authorized.accession) not in {AccessionState.SEALED}
    assert list(store.root.glob("*.json")) == []
    assert [r.accession for r in journal.interrupted()] == [authorized.accession]


def test_a_successful_acquisition_reaches_SEALED_with_a_verified_digest(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    r = acq.acquire(authorized, locator)

    assert r.accession_state == AccessionState.SEALED.value
    rec = journal.get(authorized.accession)
    assert rec is not None and rec.artifact_sha256 is not None
    assert store.verify(
        authorized.cik, authorized.accession, authority.source_variant, rec.artifact_sha256
    )


# ===================================================== journal-first reconciliation (P0)
def test_ledger_acquired_plus_journal_PARSED_raises_rather_than_reporting_duplicate(
    authority, ledger, store, journal, authorized, locator
):
    """The exact defect: a crash between mark_acquired() and sealing.

    The old order consulted the legacy acquired-set first and returned REFUSED_DUPLICATE,
    so the restarted call never reached guard_fresh() and an interrupted acquisition was
    reported as an ordinary duplicate. Journal state is authoritative now.
    """
    from app.altdata.sec001_v31.custody import InterruptedAcquisition

    # reconstruct the post-crash state exactly
    journal.transition(
        authorized.accession, authorized.cik, authorized.form, AccessionState.REQUEST_INTENT
    )
    journal.transition(
        authorized.accession, authorized.cik, authorized.form, AccessionState.REQUEST_SENT
    )
    journal.transition(authorized.accession, authorized.cik, authorized.form, AccessionState.PARSED)
    ledger.mark_acquired(authorized.cik, authorized.form, authorized.accession)
    assert ledger.already_acquired(authorized.cik, authorized.form, authorized.accession)

    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    before = ledger.document_requests

    with pytest.raises(InterruptedAcquisition):
        acq.acquire(authorized, locator)

    assert calls == [], "zero new SEC requests"
    assert ledger.document_requests == before


@pytest.mark.parametrize(
    "state",
    [
        AccessionState.LOCATOR_INTENT,
        AccessionState.LOCATOR_REQUEST_SENT,
        AccessionState.REQUEST_INTENT,
        AccessionState.REQUEST_SENT,
        AccessionState.RESPONSE_RETAINED,
        AccessionState.PARSED,
    ],
)
def test_every_mid_flight_state_raises_regardless_of_the_ledger(
    authority, ledger, store, journal, authorized, locator, state
):
    from app.altdata.sec001_v31.custody import InterruptedAcquisition

    journal.transition(authorized.accession, authorized.cik, authorized.form, state)
    ledger.mark_acquired(authorized.cik, authorized.form, authorized.accession)
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    with pytest.raises(InterruptedAcquisition):
        acq.acquire(authorized, locator)


def test_a_sealed_accession_is_refused_and_its_artifact_verified(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    assert acq.acquire(authorized, locator).accession_state == AccessionState.SEALED.value

    again = build(authority, ledger, store, journal, doc_for(authorized))
    r = again.acquire(authorized, locator)
    assert r.status == REFUSED_SEALED
    assert r.diagnostics["artifact_sha256"]


def test_sealed_but_missing_artifact_is_INCONSISTENT_not_a_refetch(
    authority, ledger, store, journal, authorized, locator
):
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    acq.acquire(authorized, locator)
    store.path_for(authorized.cik, authorized.accession, authority.source_variant).unlink()

    calls: list[str] = []
    again = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = again.acquire(authorized, locator)

    assert r.status == INCONSISTENT_CUSTODY_STATE
    assert r.diagnostics["reason"] == "sealed_but_artifact_missing_or_corrupt"
    assert calls == [], "a broken invariant is adjudicated, never re-fetched"


def test_untouched_journal_but_ledger_says_acquired_is_INCONSISTENT_not_duplicate(
    authority, ledger, store, journal, authorized, locator
):
    """The two stores disagree about whether a request was ever made. Neither answer may
    be acted on, so this is a HOLD rather than an ordinary duplicate refusal."""
    ledger.mark_acquired(authorized.cik, authorized.form, authorized.accession)
    assert journal.state_of(authorized.accession) is AccessionState.AUTHORIZED

    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)

    assert r.status == INCONSISTENT_CUSTODY_STATE
    assert r.diagnostics["reason"] == "ledger_reports_acquired_but_journal_is_not_terminal"
    assert calls == []


def test_a_terminal_evidence_unavailable_accession_is_refused(
    authority, ledger, store, journal, authorized, locator
):
    journal.transition(
        authorized.accession, authorized.cik, authorized.form, AccessionState.EVIDENCE_UNAVAILABLE
    )
    calls: list[str] = []
    acq = build(authority, ledger, store, journal, doc_for(authorized), calls)
    r = acq.acquire(authorized, locator)
    assert r.status == REFUSED_EVIDENCE_UNAVAILABLE and calls == []


def test_locator_resolved_is_resumable_not_interrupted(
    authority, ledger, store, journal, authorized, locator
):
    """A candidate screened out on size has spent no document request and stays available."""
    journal.transition(
        authorized.accession, authorized.cik, authorized.form, AccessionState.LOCATOR_RESOLVED
    )
    acq = build(authority, ledger, store, journal, doc_for(authorized))
    r = acq.acquire(authorized, locator)
    assert r.status == ACQUIRED and r.accession_state == AccessionState.SEALED.value
