"""The frozen canary rule: never spend a scarce bracket, never spend a foregone conclusion."""

from __future__ import annotations

import json

import pytest

from app.altdata.sec001_v31.canary import (
    CANARY_MAX_DOCUMENT_BYTES,
    ELIGIBLE,
    INELIGIBLE_SIZE_UNKNOWN,
    INELIGIBLE_TOO_LARGE,
    candidate_order,
    first_candidate,
    is_out_of_population,
    screen,
)


def test_the_19_bracket_accessions_come_from_the_hash_verified_authority(authority):
    assert len(authority.bracket_accessions) == 19


def test_canary_module_reads_no_file(authority):
    """Review finding: re-reading the envelope/selection after verification was a TOCTOU
    hole -- a local edit could shrink the bracket list and promote a scarce boundary filing
    into the canary slot, which require_authorized() cannot catch."""
    import ast
    import inspect

    from app.altdata.sec001_v31 import canary as canary_mod

    tree = ast.parse(inspect.getsource(canary_mod))
    called = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    called |= {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    for forbidden in ("open", "read_text", "read_bytes", "loads", "load"):
        assert forbidden not in called, f"canary.py must not read files: {forbidden}"


def test_selection_is_driven_by_verified_ordered_keys(authority):
    assert len(authority.ordered_keys) == 452
    assert authority.ordered_keys[0][2] in authority.bracket_accessions
    assert len({k[2] for k in authority.ordered_keys}) == 452


def test_out_of_population_detection_for_schema_discovery(authority):
    """Discovery must target an accession outside Envelope B entirely."""
    assert is_out_of_population(authority, "0000000000-00-000000") is True
    for k in list(authority.ordered_keys)[:5]:
        assert is_out_of_population(authority, k[2]) is False


def test_envelope_Bs_own_first_entry_IS_a_bracket_and_is_therefore_excluded(authority):
    """The reason the rule exists: an unfiltered 'first entry' picks the scarcest candidate."""
    cik, _form, accession, accepted = authority.ordered_keys[0]
    assert accession in authority.bracket_accessions
    assert accession == "0001193125-20-283796"
    assert cik == 97210 and accepted.startswith("2020-11-02")


def test_candidate_set_is_envelope_B_minus_exactly_the_19_brackets(authority):
    order = candidate_order(authority)
    assert len(order) == 452 - 19 == 433
    brackets = authority.bracket_accessions
    assert not any(c.accession in brackets for c in order)


def test_order_is_envelope_B_key_order_preserved_not_re_sorted(authority):
    order = candidate_order(authority)
    positions = [c.position for c in order]
    assert positions == sorted(positions), "B's own order must be preserved"
    assert positions[0] == 1, "position 0 is the excluded bracket, so selection advances to 1"


def test_the_first_candidate_is_deterministic_and_not_a_bracket(authority):
    c = first_candidate(authority)
    assert c.accession not in authority.bracket_accessions
    assert (c.cik, c.form, c.accession) == (97210, "10-K", "0001193125-21-050735")
    assert c.accepted_at == "2021-02-22T21:04:39.000Z"


def test_every_candidate_is_still_authorized_under_envelope_B(authority):
    for c in candidate_order(authority):
        assert authority.is_authorized(c.cik, c.form, c.accession, c.accepted_at)


def test_envelope_B_remains_the_sole_authority(authority):
    """The bracket list is an exclusion filter for canary selection, not an authority change."""
    order = {c.accession for c in candidate_order(authority)}
    assert len(order) == 433
    assert len(authority.authorized_keys) == 452, "authority is still all of B"
    for acc in authority.bracket_accessions:
        assert acc not in order
        assert any(k[2] == acc for k in authority.ordered_keys), "still authorized, just not canary"


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
