"""Acquisition orchestration: preflight refusals, CIK-once, multi-class, layer separation."""

from __future__ import annotations

import ast
from datetime import datetime

import httpx
import pytest

from app.altdata.sec001_v31 import acquire as acquire_mod
from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.acquire import (
    ACQUIRED,
    INDEX_COVER_CIK_MISMATCH,
    REFUSED_CUTOFF,
    REFUSED_DUPLICATE,
    REFUSED_FORM,
    AcquisitionPolicy,
    CoverAcquisition,
)
from app.altdata.sec001_v31.layers import FilingMetadata, TransportLocator
from app.altdata.sec001_v31.transport import BoundedFetcher, CreateOnceStore, RequestLedger
from tests.altdata.sec001_v31.fixtures import ALPHABET_CLASSES, cover_doc

PERMITTED = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"})
CUTOFF = datetime.fromisoformat("2026-08-26T16:11:22+00:00")

ACC = "0001652044-26-000070"
META = FilingMetadata(
    cik=1652044, form="10-Q", accession=ACC, accepted_at="2026-07-23T01:15:54.000Z"
)
LOCATOR = TransportLocator(
    cik=1652044,
    accession=ACC,
    primary_document="goog-20260630.htm",
    url="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000070/goog-20260630.htm",
)


def build(tmp_path, body: bytes, *, doc_cap=1200, calls=None):
    def handler(_r: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(_r.url))
        return httpx.Response(
            206,
            content=body,
            headers={"Content-Range": f"bytes 0-{len(body) - 1}/{len(body)}"},
        )

    led = RequestLedger(
        max_index_requests=200, max_document_requests=doc_cap, max_total_retries=200
    )
    f = BoundedFetcher(
        led,
        user_agent="TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com",
        ceiling_bytes=1_048_576,
        stop_threshold_bytes=983_040,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )
    store = CreateOnceStore(tmp_path)
    return CoverAcquisition(AcquisitionPolicy(PERMITTED, CUTOFF), f, store), led


# --------------------------------- case 8: non-permitted form refused BEFORE any fetch
@pytest.mark.parametrize("form", ["8-K", "8-A12B", "25", "6-K", "S-1", "4"])
def test_non_permitted_form_is_refused_before_a_document_request(tmp_path, form):
    calls: list[str] = []
    acq, led = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES), calls=calls)
    meta = FilingMetadata(cik=1652044, form=form, accession=ACC, accepted_at=META.accepted_at)

    r = acq.acquire(meta, LOCATOR)

    assert r.status == REFUSED_FORM
    assert r.document_requests_spent == 0
    assert led.document_requests == 0, "a refused form must not cost a request"
    assert calls == [], "no HTTP call may be made for a non-permitted form"


# ------------------------------------- case 9: post-cutoff refused BEFORE any fetch
def test_acceptance_after_the_frozen_cutoff_is_refused_before_a_document_request(tmp_path):
    calls: list[str] = []
    acq, led = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES), calls=calls)
    meta = FilingMetadata(
        cik=1652044, form="10-Q", accession=ACC, accepted_at="2026-08-27T09:00:00.000Z"
    )

    r = acq.acquire(meta, LOCATOR)

    assert r.status == REFUSED_CUTOFF
    assert led.document_requests == 0 and calls == []


def test_cutoff_uses_the_conservative_eastern_reading(tmp_path):
    """13:00 stamped 'Z' is 17:00 UTC on an Eastern clock -- after a 16:11:22Z cutoff."""
    acq, led = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES))
    meta = FilingMetadata(
        cik=1652044, form="10-Q", accession=ACC, accepted_at="2026-08-26T13:00:00.000Z"
    )
    assert acq.acquire(meta, LOCATOR).status == REFUSED_CUTOFF
    assert led.document_requests == 0

    earlier = FilingMetadata(
        cik=1652044, form="10-Q", accession=ACC, accepted_at="2026-08-26T11:00:00.000Z"
    )
    assert acq.acquire(earlier, LOCATOR).status == ACQUIRED


# ------------------------- case 6: one accession, multiple classes, ONE acquisition
def test_one_accession_supporting_two_classes_is_one_fetch_and_two_observations(tmp_path):
    calls: list[str] = []
    acq, led = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES), calls=calls)

    r = acq.acquire(META, LOCATOR)

    assert r.status == ACQUIRED and r.parse_status == cover_parser.STATUS_BOUND
    assert len(calls) == 1, "CIK-once: one accession is fetched once"
    assert led.document_requests == 1
    assert len(r.observations) == 2
    assert {o.trading_symbol for o in r.observations} == {"GOOG", "GOOGL"}
    assert len(set(r.artifact_identities)) == 2


# ------------------------------------- case 7: duplicate accession -> no second fetch
def test_duplicate_cik_form_accession_produces_no_second_acquisition(tmp_path):
    calls: list[str] = []
    acq, led = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES), calls=calls)

    first = acq.acquire(META, LOCATOR)
    second = acq.acquire(META, LOCATOR)

    assert first.status == ACQUIRED
    assert second.status == REFUSED_DUPLICATE
    assert second.document_requests_spent == 0
    assert len(calls) == 1 and led.document_requests == 1


# ---------------------- case 3: filename ticker contradicts the cover page: zero effect
def test_primary_document_filename_ticker_has_zero_identity_effect(tmp_path):
    """The locator says 'goog'; the cover page declares only Class A / GOOGL.

    A filename-derived shortcut would return GOOG. The observation must be GOOGL.
    """
    only_class_a = [ALPHABET_CLASSES[0]]
    acq, _ = build(tmp_path, cover_doc(classes=only_class_a))
    misleading = TransportLocator(
        cik=1652044, accession=ACC, primary_document="goog-20260630.htm", url=LOCATOR.url
    )

    r = acq.acquire(META, misleading)

    assert len(r.observations) == 1
    obs = r.observations[0]
    assert obs.trading_symbol == "GOOGL"
    assert "Class A" in obs.security_12b_title
    assert "goog-20260630" not in str(obs.to_record())


def test_locator_repr_does_not_leak_the_symbol_bearing_filename():
    assert "goog-20260630.htm" not in repr(LOCATOR)
    assert "redacted" in repr(LOCATOR)


def test_acquire_never_passes_the_locator_to_the_parser():
    """Structural: the only locator attribute the orchestrator reads is ``url``."""
    src = acquire_mod.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    reads = {
        n.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "locator"
    }
    assert reads == {"url"}, f"orchestrator reads locator attributes {reads}"

    parse_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "parse_cover_identity"
    ]
    assert parse_calls, "expected the parser to be called"
    for call in parse_calls:
        names = {
            a.value.id
            for a in ast.walk(call)
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)
        }
        assert "locator" not in names, "locator reached the parser"


# ------------------------------------------ cover CIK disagreeing with the index record
def test_cover_cik_disagreeing_with_the_index_record_has_its_own_failure_state(tmp_path):
    """Fail closed, but as a FILING-identity conflict -- never as a competing security
    binding. An index CIK is acquisition metadata, not an admissible binding."""
    acq, _ = build(tmp_path, cover_doc(cik="0000320193", classes=ALPHABET_CLASSES))
    r = acq.acquire(META, LOCATOR)

    assert r.parse_status == INDEX_COVER_CIK_MISMATCH
    assert r.parse_status != cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.diagnostics["reason"] == "cover_cik_disagrees_with_index"
    assert r.diagnostics["index_cik"] == 1652044
    assert r.diagnostics["cover_cik"] == 320193
    assert "DISPUTED" in r.diagnostics["consequence"]
    assert r.observations == [] and r.artifact_identities == []
    assert list(tmp_path.glob("*.json")) == []


# ------------------------------------------------- disputed evidence yields no artifact
def test_ticker_only_document_yields_no_observation_and_no_artifact(tmp_path):
    acq, _ = build(tmp_path, cover_doc(classes=[("GOOGL", "", "", "c-a")]))
    r = acq.acquire(META, LOCATOR)
    assert r.parse_status == cover_parser.STATUS_DISPUTED_TICKER_ONLY
    assert r.observations == [] and r.artifact_identities == []
    assert list(tmp_path.glob("*.json")) == []


# ----------------------------------- case 18: observations reconstructable to identity
def test_every_observation_is_reconstructable_to_its_immutable_identity(tmp_path):
    acq, _ = build(tmp_path, cover_doc(classes=ALPHABET_CLASSES))
    r = acq.acquire(META, LOCATOR)

    for obs, ident in zip(r.observations, r.artifact_identities, strict=True):
        cik_s, acc, variant, obs_id = ident.split("/")
        assert int(cik_s) == obs.cik == META.cik
        assert acc == obs.accession == ACC
        assert variant == "PRIMARY_DOCUMENT_COVER"
        assert obs_id == obs.observation_id(variant)
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_evidence_unavailable_fetch_produces_no_observation(tmp_path):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    led = RequestLedger(max_index_requests=200, max_document_requests=1200, max_total_retries=200)
    f = BoundedFetcher(
        led,
        user_agent="ua",
        ceiling_bytes=1_048_576,
        stop_threshold_bytes=983_040,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )
    acq = CoverAcquisition(AcquisitionPolicy(PERMITTED, CUTOFF), f, CreateOnceStore(tmp_path))
    r = acq.acquire(META, LOCATOR)
    assert r.parse_status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.observations == []


def test_non_eof_response_yields_evidence_unavailable_and_no_artifact(tmp_path):
    """A bounded read that did not reach EOF cannot produce a binding, however complete
    the class tuples in the prefix appear."""
    body = cover_doc(classes=ALPHABET_CLASSES)

    def handler(_r: httpx.Request) -> httpx.Response:
        # a prefix of a much larger document: Content-Range total exceeds what was served
        return httpx.Response(
            206,
            content=body,
            headers={"Content-Range": f"bytes 0-{len(body) - 1}/{len(body) * 40}"},
        )

    led = RequestLedger(max_index_requests=200, max_document_requests=1200, max_total_retries=200)
    f = BoundedFetcher(
        led,
        user_agent="ua",
        ceiling_bytes=1_048_576,
        stop_threshold_bytes=983_040,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )
    acq = CoverAcquisition(AcquisitionPolicy(PERMITTED, CUTOFF), f, CreateOnceStore(tmp_path))

    r = acq.acquire(META, LOCATOR)

    assert r.parse_status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "bounded_read_did_not_reach_eof"
    assert r.observations == [] and r.artifact_identities == []
    assert list(tmp_path.glob("*.json")) == []
