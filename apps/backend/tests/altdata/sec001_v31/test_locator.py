"""The locator must be AUTHENTIC, not merely well-formed — and resolving it is exactly-once."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from app.altdata.sec001_v31.authority import NotAuthorized
from app.altdata.sec001_v31.custody import AccessionState, InterruptedAcquisition
from app.altdata.sec001_v31.locator import (
    RESOLVER_ACCESSION_MISMATCH,
    RESOLVER_INDEX_UNAVAILABLE,
    RESOLVER_NO_PRIMARY_DOCUMENT,
    RESOLVER_SCHEMA_UNSUPPORTED,
    RESOLVER_UNSAFE_DOCUMENT_NAME,
    LocatorResolutionError,
    LocatorResolver,
    index_url,
)
from tests.altdata.sec001_v31.conftest import make_fetcher


@pytest.fixture
def target(envelope_keys):
    cik, form, accession, accepted = envelope_keys[0]
    return cik, form, accession, accepted


def index_body(accession: str, items: list[dict]) -> bytes:
    """A filing-detail page in the REAL shape established by the governed fixture.

    Synthetic, but structurally faithful: the ``Document Format Files`` summary, the frozen
    five-column header, and a Document cell that is an anchor plus decoration rather than a
    bare filename. Tests that need the genuine article use ``test_filing_detail``.
    """
    rows = ""
    for it in items:
        name = it.get("name", "")
        doc = f'<a href="/ix?doc=/Archives/x/{name}">{name}</a> &nbsp;&nbsp;<span>iXBRL</span>'
        size = "" if it.get("size") is None else it.get("size")
        rows += (
            "<tr>"
            f"<td>{it.get('seq', '1')}</td><td>{it.get('type', '')}</td>"
            f"<td>{doc}</td><td>{it.get('type', '')}</td><td>{size}</td>"
            "</tr>"
        )
    return (
        f"<html><body><p>Accession Number: {accession}</p>"
        '<table class="tableFile" summary="Document Format Files">'
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        f"{rows}</table></body></html>"
    ).encode()


def primary(form: str, name: str = "ter-20240630.htm", size: int | str = 512_000) -> dict:
    return {"name": name, "type": form, "size": size}


def resolver(authority, ledger, journal, body: bytes, calls=None, status: int = 200):
    def handler(r: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(r.url))
        return httpx.Response(status, content=body)

    return LocatorResolver(authority, make_fetcher(authority, ledger, handler), journal)


# ============================================================ happy path
def test_resolution_takes_only_the_filename_and_size_from_sec(authority, ledger, journal, target):
    cik, form, accession, accepted = target
    body = index_body(
        accession, [primary(form), {"name": "ex31.htm", "type": "EX-31.1", "size": 9}]
    )
    res = resolver(authority, ledger, journal, body).resolve(cik, accession)

    assert res.primary_document == "ter-20240630.htm"
    assert res.document_size == 512_000
    # form and accepted_at come from the SEALED envelope, not from SEC
    assert res.form == form and res.accepted_at == accepted
    assert res.url == authority.archive_url(cik, accession, "ter-20240630.htm")
    assert res.index_body_sha256 == hashlib.sha256(body).hexdigest()
    assert journal.state_of(accession) is AccessionState.LOCATOR_RESOLVED


def test_the_index_request_is_charged_to_the_INDEX_budget_not_the_document_budget(
    authority, ledger, journal, target
):
    cik, form, accession, _ = target
    before_idx, before_doc = ledger.index_requests, ledger.document_requests
    resolver(authority, ledger, journal, index_body(accession, [primary(form)])).resolve(
        cik, accession
    )
    assert ledger.index_requests == before_idx + 1
    assert ledger.document_requests == before_doc, "locator work must not spend document budget"


def test_resolution_is_exactly_once_and_replays_without_a_new_request(
    authority, ledger, journal, target
):
    cik, form, accession, _ = target
    calls: list[str] = []
    r = resolver(authority, ledger, journal, index_body(accession, [primary(form)]), calls)
    first = r.resolve(cik, accession)
    second = r.resolve(cik, accession)
    assert first == second
    assert len(calls) == 1, "a resolved accession must not spend another index request"


def test_a_crash_mid_lookup_is_visible_and_not_silently_repeated(
    authority, ledger, journal, target
):
    cik, form, accession, _ = target
    journal.transition(accession, cik, form, AccessionState.LOCATOR_REQUEST_SENT)
    calls: list[str] = []
    r = resolver(authority, ledger, journal, index_body(accession, [primary(form)]), calls)
    with pytest.raises(InterruptedAcquisition):
        r.resolve(cik, accession)
    assert calls == []


# ============================================================ fail-closed paths
def test_a_page_for_a_different_accession_fails_closed(authority, ledger, journal, target):
    cik, form, accession, _ = target
    body = index_body("9999999999-99-999999", [primary(form)])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_ACCESSION_MISMATCH


def test_no_item_typed_as_the_form_fails_closed(authority, ledger, journal, target):
    cik, _form, accession, _ = target
    body = index_body(accession, [{"name": "ex31.htm", "type": "EX-31.1", "size": 9}])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_NO_PRIMARY_DOCUMENT


def test_two_items_typed_as_the_form_fail_closed_rather_than_picking_one(
    authority, ledger, journal, target
):
    cik, form, accession, _ = target
    body = index_body(accession, [primary(form, "a.htm"), primary(form, "b.htm")])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_SCHEMA_UNSUPPORTED


@pytest.mark.parametrize("size", [None, "", 0, "not-a-number"])
def test_a_non_authoritative_size_fails_closed(authority, ledger, journal, target, size):
    """The canary screen needs a real size; guessing one would defeat the screen."""
    cik, form, accession, _ = target
    body = index_body(accession, [primary(form, size=size)])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_SCHEMA_UNSUPPORTED


@pytest.mark.parametrize("name", ["../../etc/passwd", "sub/dir.htm", "x.htm?a=1"])
def test_an_unsafe_filename_from_sec_is_still_refused(authority, ledger, journal, target, name):
    cik, form, accession, _ = target
    body = index_body(accession, [primary(form, name=name)])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_UNSAFE_DOCUMENT_NAME


def test_an_empty_document_name_fails_closed_in_the_parser(authority, ledger, journal, target):
    cik, form, accession, _ = target
    body = index_body(accession, [primary(form, name="")])
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, body).resolve(cik, accession)
    assert e.value.reason == RESOLVER_SCHEMA_UNSUPPORTED


def test_an_unavailable_index_fails_closed(authority, ledger, journal, target):
    cik, _form, accession, _ = target
    with pytest.raises(LocatorResolutionError) as e:
        resolver(authority, ledger, journal, b"", status=404).resolve(cik, accession)
    assert e.value.reason == RESOLVER_INDEX_UNAVAILABLE


# ============================================================ authority binding
def test_an_unauthorized_accession_cannot_be_resolved(authority, ledger, journal):
    with pytest.raises(NotAuthorized):
        resolver(authority, ledger, journal, b"{}").resolve(1652044, "9999999999-99-999999")


def test_a_cik_that_does_not_own_the_accession_is_refused(authority, ledger, journal, target):
    cik, _form, accession, _ = target
    with pytest.raises(NotAuthorized, match="is authorized under CIK"):
        resolver(authority, ledger, journal, b"{}").resolve(cik + 1, accession)


def test_index_url_is_the_filing_detail_page_not_the_directory_listing(authority, target):
    cik, _form, accession, _ = target
    u = index_url(authority, cik, accession)
    assert u.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert u.endswith(f"/{accession}-index.html")
    assert not u.endswith("/index.json"), "the directory listing carries no Type column"
    with pytest.raises(NotAuthorized):
        index_url(authority, cik, "9999999999-99-999999")


def test_the_resolved_locator_authenticates_against_its_own_metadata(
    authority, ledger, journal, target
):
    from app.altdata.sec001_v31.layers import FilingMetadata

    cik, form, accession, accepted = target
    res = resolver(authority, ledger, journal, index_body(accession, [primary(form)])).resolve(
        cik, accession
    )
    meta = FilingMetadata(cik=cik, form=form, accession=accession, accepted_at=accepted)
    loc = res.transport_locator()
    loc.assert_matches(meta)
    authority.require_canonical_url(cik, accession, loc.primary_document, loc.url)


# ============================================================ determinate != crash
DETERMINATE = (
    AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
    AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT,
)


def test_a_completed_response_that_fails_to_parse_does_NOT_look_like_a_crash(
    authority, ledger, journal, target
):
    """The defect this closes: every failure used to leave LOCATOR_REQUEST_SENT, so a
    determinate schema mismatch was indistinguishable from an interruption and stranded the
    accession. That is how schema discovery would have consumed the very filing it ran on."""
    cik, _form, accession, _ = target
    body = index_body(accession, [{"name": "x.htm", "type": "SOMETHING-ELSE", "size": 10}])

    with pytest.raises(LocatorResolutionError):
        resolver(authority, ledger, journal, body).resolve(cik, accession)

    state = journal.state_of(accession)
    assert state is AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT
    assert state is not AccessionState.LOCATOR_REQUEST_SENT
    from app.altdata.sec001_v31.custody import INTERRUPTED_STATES, RESUMABLE_STATES

    assert state in RESUMABLE_STATES and state not in INTERRUPTED_STATES


def test_the_response_digest_is_retained_on_a_determinate_failure(
    authority, ledger, journal, target
):
    cik, _form, accession, _ = target
    body = index_body(accession, [{"name": "x.htm", "type": "OTHER", "size": 10}])
    with pytest.raises(LocatorResolutionError):
        resolver(authority, ledger, journal, body).resolve(cik, accession)

    rec = journal.get(accession)
    assert rec is not None
    assert rec.detail["index_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert rec.detail["reason"] == RESOLVER_NO_PRIMARY_DOCUMENT
    # the response outcome was recorded on the way through
    states = [h["state"] for h in rec.history]
    assert "LOCATOR_RESPONSE_RECEIVED" in states


def test_a_determinate_verdict_is_replayed_without_a_second_request(
    authority, ledger, journal, target
):
    """Not stranded, but not silently re-requested either: exactly-once still holds."""
    cik, _form, accession, _ = target
    body = index_body(accession, [{"name": "x.htm", "type": "OTHER", "size": 10}])
    calls: list[str] = []
    r = resolver(authority, ledger, journal, body, calls)

    with pytest.raises(LocatorResolutionError):
        r.resolve(cik, accession)
    with pytest.raises(LocatorResolutionError, match="replayed determinate outcome"):
        r.resolve(cik, accession)

    assert len(calls) == 1, "the second call must not spend another index request"
    assert ledger.index_requests == 29  # 28 from step 1 + exactly 1


@pytest.mark.parametrize(
    "items,expected_state",
    [
        (
            [{"name": "x.htm", "type": "OTHER", "size": 10}],
            AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT,
        ),
        ([], AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT),
    ],
)
def test_missing_primary_document_is_its_own_determinate_state(
    authority, ledger, journal, target, items, expected_state
):
    cik, _form, accession, _ = target
    with pytest.raises(LocatorResolutionError):
        resolver(authority, ledger, journal, index_body(accession, items)).resolve(cik, accession)
    assert journal.state_of(accession) is expected_state


def test_an_http_failure_is_also_determinate_not_stranding(authority, ledger, journal, target):
    cik, _form, accession, _ = target
    with pytest.raises(LocatorResolutionError):
        resolver(authority, ledger, journal, b"", status=404).resolve(cik, accession)
    assert journal.state_of(accession) is AccessionState.LOCATOR_SCHEMA_UNSUPPORTED


def test_only_a_genuine_interruption_remains_REQUEST_SENT(authority, ledger, journal, target):
    """A crash with no recorded outcome is the ONLY thing that may look in-flight."""
    cik, form, accession, _ = target

    def exploding(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated interruption")

    from tests.altdata.sec001_v31.conftest import make_fetcher

    r = LocatorResolver(authority, make_fetcher(authority, ledger, exploding), journal)
    with pytest.raises(httpx.HTTPError):
        r.resolve(cik, accession)
    assert journal.state_of(accession) is AccessionState.LOCATOR_REQUEST_SENT
    from app.altdata.sec001_v31.custody import INTERRUPTED_STATES

    assert journal.state_of(accession) in INTERRUPTED_STATES


def test_the_old_directory_listing_representation_is_now_rejected(
    authority, ledger, journal, target
):
    """The superseded model: an accession-directory index.json body must NOT resolve.

    It is not the filing-detail representation, so it lands determinate rather than being
    reinterpreted -- and, post-fix, that costs one index request and strands nothing.
    """
    cik, _form, accession, _ = target
    directory_listing_json = (
        b'{"directory":{"name":"/Archives/edgar/data/x/'
        + accession.replace("-", "").encode()
        + b'","item":[{"name":"d.htm","type":"10-K","size":"5551234"}]}}'
    )
    with pytest.raises(LocatorResolutionError):
        resolver(authority, ledger, journal, directory_listing_json).resolve(cik, accession)
    assert journal.state_of(accession) in DETERMINATE
