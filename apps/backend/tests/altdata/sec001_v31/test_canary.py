"""The frozen canary rule: never spend a scarce bracket, never spend a foregone conclusion."""

from __future__ import annotations

import json

import pytest

from app.altdata.sec001_v31.canary import (
    CANARY_MAX_DOCUMENT_BYTES,
    ELIGIBLE,
    INELIGIBLE_SIZE_UNKNOWN,
    INELIGIBLE_TOO_LARGE,
    bracket_accessions,
    candidate_order,
    first_candidate,
    screen,
)
from tests.altdata.sec001_v31.conftest import REPO_ROOT


def test_the_19_bracket_accessions_come_from_the_sealed_selection_record():
    brackets = bracket_accessions(REPO_ROOT)
    assert len(brackets) == 19


def test_envelope_Bs_own_first_entry_IS_a_bracket_and_is_therefore_excluded():
    """The reason the rule exists: an unfiltered 'first entry' picks the scarcest candidate."""
    env = json.loads(
        (REPO_ROOT / "artifacts/wp0aq/WP0AQ_COVER_ENVELOPE_V1.json").read_text(encoding="utf-8")
    )
    first_raw = env["acquisition_keys_envelope_B"][0]
    assert first_raw["accession"] in bracket_accessions(REPO_ROOT)
    assert first_raw["accession"] == "0001193125-20-283796"
    assert first_raw["cik"] == 97210 and first_raw["accepted_at"].startswith("2020-11-02")


def test_candidate_set_is_envelope_B_minus_exactly_the_19_brackets(authority):
    order = candidate_order(authority, REPO_ROOT)
    assert len(order) == 452 - 19 == 433
    brackets = bracket_accessions(REPO_ROOT)
    assert not any(c.accession in brackets for c in order)


def test_order_is_envelope_B_key_order_preserved_not_re_sorted(authority):
    order = candidate_order(authority, REPO_ROOT)
    positions = [c.position for c in order]
    assert positions == sorted(positions), "B's own order must be preserved"
    assert positions[0] == 1, "position 0 is the excluded bracket, so selection advances to 1"


def test_the_first_candidate_is_deterministic_and_not_a_bracket(authority):
    c = first_candidate(authority, REPO_ROOT)
    assert c.accession not in bracket_accessions(REPO_ROOT)
    assert (c.cik, c.form, c.accession) == (97210, "10-K", "0001193125-21-050735")
    assert c.accepted_at == "2021-02-22T21:04:39.000Z"


def test_every_candidate_is_still_authorized_under_envelope_B(authority):
    for c in candidate_order(authority, REPO_ROOT):
        assert authority.is_authorized(c.cik, c.form, c.accession, c.accepted_at)


def test_envelope_A_is_not_used_as_authority(authority):
    """A is only an exclusion input; B remains the sole acquisition authority."""
    env = json.loads(
        (REPO_ROOT / "artifacts/wp0aq/WP0AQ_COVER_ENVELOPE_V1.json").read_text(encoding="utf-8")
    )
    a_keys = {r["accession"] for r in env["acquisition_keys_envelope_A"]}
    order = {c.accession for c in candidate_order(authority, REPO_ROOT)}
    assert order == a_keys, "B minus its 19 bracket additions is exactly A, by construction"
    assert len(authority.authorized_keys) == 452, "but authority is still all of B"


# ============================================================ the size screen
def test_the_threshold_is_the_frozen_transport_bound():
    assert CANARY_MAX_DOCUMENT_BYTES == 983_040


@pytest.mark.parametrize("size", [1, 100_000, 983_039])
def test_a_document_below_the_bound_is_eligible(size):
    assert screen(size) == (True, ELIGIBLE)


@pytest.mark.parametrize("size", [983_040, 983_041, 5_000_000])
def test_a_document_at_or_above_the_bound_is_ineligible(size):
    """At the bound the reader fills its window and reports truncation, so equality is out."""
    ok, reason = screen(size)
    assert ok is False and reason == INELIGIBLE_TOO_LARGE


@pytest.mark.parametrize("size", [None, 0, -1])
def test_an_unknown_size_is_ineligible_rather_than_optimistic(size):
    ok, reason = screen(size)
    assert ok is False and reason == INELIGIBLE_SIZE_UNKNOWN


def test_screening_out_a_candidate_spends_no_document_request(
    authority, ledger, journal, envelope_keys
):
    """A failed screen must not consume the accession: it stays resumable."""
    import httpx

    from app.altdata.sec001_v31.custody import RESUMABLE_STATES, AccessionState
    from app.altdata.sec001_v31.locator import LocatorResolver
    from tests.altdata.sec001_v31.conftest import make_fetcher

    cik, form, accession, _ = envelope_keys[0]
    body = json.dumps(
        {
            "directory": {
                "name": f"/Archives/edgar/data/x/{accession.replace('-', '')}",
                "item": [{"name": "big.htm", "type": form, "size": 4_000_000}],
            }
        }
    ).encode()

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    res = LocatorResolver(authority, make_fetcher(authority, ledger, handler), journal).resolve(
        cik, accession
    )

    ok, reason = screen(res.document_size)
    assert ok is False and reason == INELIGIBLE_TOO_LARGE
    assert ledger.document_requests == 0, "no document request may be spent on a foregone result"
    assert journal.state_of(accession) is AccessionState.LOCATOR_RESOLVED
    assert journal.state_of(accession) in RESUMABLE_STATES, "the accession stays UNSPENT"
