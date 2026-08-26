"""Transport: origin lock, redirect accounting, range integrity, durable ledger, custody."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.sec001_v31.authority import NotAuthorized
from app.altdata.sec001_v31.transport import (
    FETCH_OK,
    FETCH_UNAVAILABLE,
    AcquisitionEncodingError,
    BudgetExceeded,
    CrawlHalt,
    DurableLedger,
    RangeIntegrityError,
)
from tests.altdata.sec001_v31.conftest import make_fetcher, ranged_response

URL = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000070/primary.htm"
OFF_ORIGIN = "https://evil.example.com/primary.htm"


# ======================================================== origin lock
def test_a_url_outside_the_frozen_origins_is_refused_before_any_request(authority, ledger):
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return httpx.Response(200, content=b"x")

    f = make_fetcher(authority, ledger, handler)
    with pytest.raises(NotAuthorized, match="outside the frozen SEC origins"):
        f.get_document(OFF_ORIGIN)
    assert calls == [] and ledger.document_requests == 0


# ======================================================== redirects
def test_redirects_are_refused_by_default_and_charged_exactly_once(authority, ledger):
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return httpx.Response(302, headers={"Location": "/Archives/edgar/data/1/2/other.htm"})

    out = make_fetcher(authority, ledger, handler).get_document(URL)
    assert out.status == FETCH_UNAVAILABLE and out.reason == "redirect_refused"
    assert len(calls) == 1, "a refused redirect must not be followed"
    assert ledger.document_requests == 1, "exactly one charge for one real request"


def test_an_allowed_redirect_hop_is_validated_and_separately_charged(authority, ledger):
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        if "primary.htm" in str(r.url):
            return httpx.Response(302, headers={"Location": "/Archives/edgar/data/1/2/final.htm"})
        return ranged_response(b"<html>ok</html>", r)

    f = make_fetcher(authority, ledger, handler, max_redirects=1)
    out = f.get_document(URL)

    assert out.status == FETCH_OK
    assert len(calls) == 2
    assert ledger.document_requests == 2, "each hop is a real request and must be charged"


def test_a_redirect_leaving_the_frozen_origin_fails_closed(authority, ledger):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": OFF_ORIGIN})

    out = make_fetcher(authority, ledger, handler, max_redirects=3).get_document(URL)
    assert out.status == FETCH_UNAVAILABLE and out.reason == "redirect_off_origin"


def test_production_client_does_not_follow_redirects_automatically(authority, ledger):
    from app.altdata.sec001_v31.transport import BoundedFetcher

    f = BoundedFetcher(authority, ledger, user_agent="ua")
    try:
        assert f._client.follow_redirects is False
    finally:
        f.close()


# ======================================================== range integrity
def test_206_returning_a_different_start_than_requested_fails_closed(authority, ledger):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206, content=b"y" * 100, headers={"Content-Range": "bytes 500-599/10000"}
        )

    with pytest.raises(RangeIntegrityError, match="returned start=500, requested start=0"):
        make_fetcher(authority, ledger, handler).get_document(URL, start=0)


def test_206_body_length_disagreeing_with_its_content_range_fails_closed(authority, ledger):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=b"z" * 10, headers={"Content-Range": "bytes 0-99/10000"})

    with pytest.raises(RangeIntegrityError, match="disagrees with its own Content-Range"):
        make_fetcher(authority, ledger, handler).get_document(URL)


def test_206_without_a_parsable_content_range_fails_closed(authority, ledger):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=b"z" * 10)

    with pytest.raises(RangeIntegrityError, match="without a parsable Content-Range"):
        make_fetcher(authority, ledger, handler).get_document(URL)


def test_a_continuation_answered_with_range_ignored_200_fails_closed(authority, ledger):
    """The defect this catches: the 200 body is the document PREFIX again. Appending it as
    the next window would assemble a corrupt document out of two copies of the front."""

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"PREFIX" * 1000)

    f = make_fetcher(authority, ledger, handler)
    with pytest.raises(RangeIntegrityError, match="ignored Range and returned 200 from byte 0"):
        f.get_document(URL, start=983_040)


def test_range_ignored_200_is_still_fine_for_the_FIRST_window(authority, ledger):
    total, chunk = 10 * 1024 * 1024, 65536
    pulled = {"n": 0}

    def source():
        for _ in range(total // chunk):
            pulled["n"] += 1
            yield b"A" * chunk

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=source())

    out = make_fetcher(authority, ledger, handler).get_document(URL)
    assert out.status == FETCH_OK and out.truncated is True
    assert out.bytes_consumed == 983_040 and out.eof_reached is False
    assert pulled["n"] == 15, "streamed, not materialised then sliced"


# ======================================================== halt / retry / caps
def test_403_halts_and_latches(authority, ledger):
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403)

    f = make_fetcher(authority, ledger, handler)
    with pytest.raises(CrawlHalt):
        f.get_document(URL)
    assert f.halted is True
    with pytest.raises(CrawlHalt):
        f.get_document(URL)
    assert calls["n"] == 1


def test_halt_is_not_an_ordinary_exception():
    assert issubclass(CrawlHalt, BaseException) and not issubclass(CrawlHalt, Exception)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_status_is_bounded_and_exactly_accounted(authority, ledger, status):
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    out = make_fetcher(authority, ledger, handler).get_document(URL)
    assert out.status == FETCH_UNAVAILABLE
    assert calls["n"] == 5 and ledger.document_requests == 5 and ledger.retries == 4


def test_encoded_response_to_a_ranged_request_fails_closed(authority, ledger):
    import gzip

    payload = gzip.compress(b"<html>cover</html>")

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=payload, headers={"Content-Encoding": "gzip"})

    with pytest.raises(AcquisitionEncodingError):
        make_fetcher(authority, ledger, handler).get_document(URL)


def test_gzip_magic_reaching_the_parser_fails_closed(authority, ledger):
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bytes((0x1F, 0x8B)) + b"rest")

    with pytest.raises(AcquisitionEncodingError):
        make_fetcher(authority, ledger, handler).get_document(URL)


# ======================================================== durable ledger
def test_ledger_is_seeded_from_step1_custody(ledger):
    assert ledger.index_requests == 28, "the envelope derivation already spent 28"
    assert ledger.document_requests == 0
    assert ledger.max_index_requests == 200 and ledger.max_document_requests == 1200


def test_ledger_survives_a_process_restart(tmp_path, authority):
    p = tmp_path / "led.json"
    a = DurableLedger.open(p, authority)
    a.charge_document(URL)
    a.charge_document(URL)
    a.mark_acquired(1652044, "10-Q", "0001652044-26-000070")

    reopened = DurableLedger.open(p, authority)
    assert reopened.index_requests == 28, "a restart must not reset 28/200 to 0/200"
    assert reopened.document_requests == 2
    assert reopened.already_acquired(1652044, "10-Q", "0001652044-26-000070")


def test_ledger_records_actual_send_timestamps(ledger):
    ledger.charge_document(URL)
    ev = [e for e in ledger.events if e["kind"] == "document"]
    assert ev and ev[-1]["sent_utc"].endswith("Z") and ev[-1]["url"] == URL


def test_index_budget_accounts_the_28_already_spent(ledger):
    for _ in range(172):
        ledger.charge_index("https://data.sec.gov/submissions/x.json")
    assert ledger.index_requests == 200
    with pytest.raises(BudgetExceeded):
        ledger.charge_index("https://data.sec.gov/submissions/y.json")


def test_document_cap_is_enforced(tmp_path, authority):
    led = DurableLedger.open(tmp_path / "l.json", authority)
    led.max_document_requests = 2

    def handler(_r: httpx.Request) -> httpx.Response:
        return ranged_response(b"x", _r)

    f = make_fetcher(authority, led, handler)
    f.get_document(URL)
    f.get_document(URL)
    with pytest.raises(BudgetExceeded):
        f.get_document(URL)


# ======================================================== continuation
def test_continuation_is_off_by_default(authority, ledger):
    body = b"B" * 3_000_000

    def handler(r: httpx.Request) -> httpx.Response:
        return ranged_response(body, r)

    out = make_fetcher(authority, ledger, handler).get_document_complete(URL)
    assert out.eof_reached is False and ledger.document_requests == 1


def test_continuation_reaches_eof_across_windows_and_charges_each(authority, ledger):
    total = 2_500_000
    body = bytes((i % 251) for i in range(total))

    def handler(r: httpx.Request) -> httpx.Response:
        return ranged_response(body, r)

    out = make_fetcher(authority, ledger, handler).get_document_complete(
        URL, max_continuations=8, max_cumulative_bytes=total
    )
    assert out.eof_reached is True and out.bytes_consumed == total
    assert out.body == body, "windows must reassemble the exact document"
    assert ledger.document_requests == 3


def test_live_authorized_continuation_setting_is_zero():
    from app.altdata.sec001_v31.authority import LIVE_MAX_CONTINUATIONS

    assert LIVE_MAX_CONTINUATIONS == 0


# ======================================================== ledger durability
def test_ledger_writes_are_fsynced_like_the_journal(authority, tmp_path, monkeypatch):
    """An accounting record written BEFORE a request goes on the wire is worth nothing if
    the same host failure can lose it. The ledger must use the journal's durable primitive."""
    import app.altdata.sec001_v31.custody as custody_mod

    synced: list[str] = []
    real_fsync = custody_mod.os.fsync

    def watching(fd):
        synced.append("fsync")
        return real_fsync(fd)

    monkeypatch.setattr(custody_mod.os, "fsync", watching)
    led = DurableLedger.open(tmp_path / "l.json", authority)
    synced.clear()
    led.charge_document("https://www.sec.gov/x")
    assert synced, "charge_document must fsync before the caller may issue the request"


def test_ledger_uses_the_shared_atomic_primitive():
    import ast
    import inspect

    from app.altdata.sec001_v31 import transport as t

    src = inspect.getsource(DurableLedger._flush)
    tree = ast.parse(src.lstrip())
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "atomic_write_json" in called
    assert hasattr(t, "atomic_write_json")


def test_a_partially_written_ledger_never_replaces_the_good_one(authority, tmp_path, monkeypatch):
    import app.altdata.sec001_v31.custody as custody_mod

    p = tmp_path / "l.json"
    led = DurableLedger.open(p, authority)
    led.charge_document("https://www.sec.gov/a")
    good = p.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("crash during replace")

    monkeypatch.setattr(custody_mod.os, "replace", boom)
    with pytest.raises(OSError):
        led.charge_document("https://www.sec.gov/b")

    assert p.read_text(encoding="utf-8") == good, "the previous durable state must survive"
    assert list(tmp_path.glob("*.tmp")) == [], "no temporary must be left behind"


def test_index_charges_are_durable_and_survive_reopen(authority, tmp_path):
    p = tmp_path / "l.json"
    led = DurableLedger.open(p, authority)
    led.charge_index("https://data.sec.gov/submissions/x.json")
    assert DurableLedger.open(p, authority).index_requests == 29  # 28 from step 1 + 1
