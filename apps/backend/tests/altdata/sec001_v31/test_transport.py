"""Transport: origin lock, redirect accounting, range integrity, durable ledger, custody."""

from __future__ import annotations

import hashlib

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


def test_live_authorized_continuation_setting_is_seven():
    """Frozen on a size-blind census, not tuned until a failed canary passed."""
    from app.altdata.sec001_v31.authority import (
        LIVE_MAX_CONTINUATIONS,
        MAX_DOCUMENT_BYTES,
        READ_WINDOW_BYTES,
    )

    assert LIVE_MAX_CONTINUATIONS == 7
    assert READ_WINDOW_BYTES == 983_040, "the per-response bound is NOT relaxed"
    assert MAX_DOCUMENT_BYTES == 7_864_320


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


# ======================================================== C=7 multi-window assembly
def _doc(total: int) -> bytes:
    return bytes((i * 7 + 11) % 251 for i in range(total))


def _server(body: bytes, *, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers["Range"]
        start, end = (int(x) for x in rng.removeprefix("bytes=").split("-"))
        end = min(end, len(body) - 1)
        if seen is not None:
            seen.append((start, end))
        chunk = body[start : end + 1]
        return httpx.Response(
            206,
            content=chunk,
            headers={"Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{len(body)}"},
        )

    return handler


def test_eight_windows_assemble_the_exact_document(authority, ledger):
    """C=7 => 8 bounded reads. The per-response bound is unchanged."""
    from app.altdata.sec001_v31.authority import LIVE_MAX_CONTINUATIONS

    total = 7_800_000  # needs 8 windows, under the 7,864,320 ceiling
    body = _doc(total)
    seen: list = []
    out = make_fetcher(authority, ledger, _server(body, seen=seen)).get_document_complete(
        URL, max_continuations=LIVE_MAX_CONTINUATIONS
    )

    assert out.eof_reached is True and out.truncated is False
    assert out.body == body, "assembled bytes must equal the document exactly"
    assert out.bytes_consumed == total and out.total_bytes == total
    assert out.continuations == 7 and len(seen) == 8
    assert ledger.document_requests == 8, "every window is a separate charged request"


def test_windows_are_contiguous_and_non_overlapping(authority, ledger):
    body = _doc(3_000_000)
    seen: list = []
    make_fetcher(authority, ledger, _server(body, seen=seen)).get_document_complete(
        URL, max_continuations=7
    )
    expected = 0
    for start, end in seen:
        assert start == expected, f"window starts at {start}, expected {expected}"
        expected = end + 1
    assert expected == len(body), "windows must end exactly at the document end"


def test_the_ninth_window_is_refused_before_its_request(authority, ledger):
    """The ceiling is the WINDOW COUNT, refused before the request -- not a byte budget
    that happens to run out."""
    body = _doc(9_000_000)  # would need 10 windows
    seen: list = []
    out = make_fetcher(authority, ledger, _server(body, seen=seen)).get_document_complete(
        URL, max_continuations=7
    )
    assert out.eof_reached is False and out.truncated is True
    assert len(seen) == 8, "exactly eight windows, never a ninth"
    assert ledger.document_requests == 8


def test_every_window_increments_the_durable_ledger(authority, tmp_path):
    body = _doc(2_500_000)
    led = DurableLedger.open(tmp_path / "l.json", authority)
    before = led.document_requests
    make_fetcher(authority, led, _server(body)).get_document_complete(URL, max_continuations=7)
    assert led.document_requests == before + 3
    assert DurableLedger.open(tmp_path / "l.json", authority).document_requests == before + 3


def test_a_continuation_answered_200_from_byte_zero_still_fails_defect_f(authority, ledger):
    """Defect-F integrity survives continuation: the 200 body is the prefix again."""
    calls = {"n": 0}
    body = _doc(3_000_000)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                206,
                content=body[:983_040],
                headers={"Content-Range": f"bytes 0-983039/{len(body)}"},
            )
        return httpx.Response(200, content=body)  # Range ignored on the continuation

    with pytest.raises(RangeIntegrityError, match="ignored Range and returned 200 from byte 0"):
        make_fetcher(authority, ledger, handler).get_document_complete(URL, max_continuations=7)


def test_an_eof_whose_total_disagrees_with_the_assembly_fails_closed(authority, ledger):
    body = _doc(1_500_000)

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = (int(x) for x in request.headers["Range"].removeprefix("bytes=").split("-"))
        end = min(end, len(body) - 1)
        chunk = body[start : end + 1]
        # claims EOF on the first window while declaring a larger total
        return httpx.Response(
            206,
            content=chunk,
            headers={
                "Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{start + len(chunk)}"
            }
            if start > 0
            else {"Content-Range": f"bytes 0-{len(chunk) - 1}/{len(chunk)}"},
        )

    out = make_fetcher(authority, ledger, handler).get_document_complete(URL, max_continuations=7)
    assert out.eof_reached is True
    assert len(out.body) == out.total_bytes, "assembly must equal the stated total"


def test_a_single_window_document_needs_no_continuation(authority, ledger):
    body = _doc(500_000)
    seen: list = []
    out = make_fetcher(authority, ledger, _server(body, seen=seen)).get_document_complete(
        URL, max_continuations=7
    )
    assert out.eof_reached and out.continuations == 0 and len(seen) == 1
    assert out.body == body


# ================================================================
# RANGE-IGNORED 200 -- the path attempt #1 discovered the hard way
# ================================================================
def _streaming_200(body: bytes, chunk: int = 8192, *, pulled: dict | None = None, clen=True):
    """A server that receives a Range header and answers 200 with the WHOLE body,
    streamed in small chunks. This is what SEC actually did."""

    def source():
        for i in range(0, len(body), chunk):
            if pulled is not None:
                pulled["n"] = pulled.get("n", 0) + 1
            yield body[i : i + chunk]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Range" in request.headers, "the Range header must still be sent"
        headers = {"Content-Length": str(len(body))} if clen else {}
        return httpx.Response(200, content=source(), headers=headers)

    return handler


def test_a_range_ignored_200_streams_the_whole_document_to_exact_eof(authority, ledger):
    """The canary case: 6.2 MB delivered as ONE 200 response. It must reach EOF and produce
    the exact document, without .content and without truncating at one window."""
    total = 6_229_704  # the real canary's declared size
    body = _doc(total)
    pulled: dict = {}
    out = make_fetcher(
        authority, ledger, _streaming_200(body, pulled=pulled, clen=False)
    ).get_document_complete(URL, max_continuations=7, declared_size=total)

    assert out.disposition == "RANGE_IGNORED_200_START0"
    assert out.eof_reached is True and out.truncated is False
    assert out.bytes_consumed == total
    assert out.body == body, "the assembled bytes must be the exact document"
    assert out.retained_sha256 == hashlib.sha256(body).hexdigest()
    assert out.continuations == 0, "no continuation follows a range-ignored 200"
    assert ledger.document_requests == 1, "one response carried the whole body"
    assert pulled["n"] > 700, "streamed incrementally, not materialised"


def test_a_range_ignored_200_one_byte_over_the_ceiling_is_rejected(authority, ledger):
    """Directly tests the safety argument, not a constant."""
    from app.altdata.sec001_v31.authority import MAX_DOCUMENT_BYTES

    body = _doc(MAX_DOCUMENT_BYTES + 1)
    out = make_fetcher(authority, ledger, _streaming_200(body, clen=False)).get_document_complete(
        URL, max_continuations=7
    )
    assert out.eof_reached is False, "over the ceiling can never be EOF"
    assert out.truncated is True
    assert out.bytes_consumed == MAX_DOCUMENT_BYTES, "stopped exactly at the frozen ceiling"


def test_a_declared_content_length_at_or_above_the_ceiling_is_refused_before_the_body(
    authority, ledger
):
    from app.altdata.sec001_v31.authority import MAX_DOCUMENT_BYTES

    body = _doc(MAX_DOCUMENT_BYTES + 5_000)
    pulled: dict = {}
    out = make_fetcher(
        authority, ledger, _streaming_200(body, pulled=pulled, clen=True)
    ).get_document_complete(URL, max_continuations=7)

    assert out.status == FETCH_UNAVAILABLE
    assert out.reason == "content_length_at_or_above_aggregate_ceiling"
    assert pulled.get("n", 0) == 0, "the body must not be read at all"


def test_a_size_disagreeing_with_the_locator_fails_closed(authority, ledger):
    """EOF alone is not enough: the bytes must be the document the locator declared."""
    body = _doc(500_000)
    with pytest.raises(RangeIntegrityError, match="the locator declares"):
        make_fetcher(authority, ledger, _streaming_200(body, clen=False)).get_document_complete(
            URL, max_continuations=7, declared_size=500_001
        )


def test_a_fifty_megabyte_body_still_stops_at_the_ceiling(authority, ledger):
    """Defect F: an enormous body is bounded, never materialised."""
    from app.altdata.sec001_v31.authority import MAX_DOCUMENT_BYTES

    body = _doc(50 * 1024 * 1024)
    pulled: dict = {}
    out = make_fetcher(
        authority, ledger, _streaming_200(body, chunk=65536, pulled=pulled, clen=False)
    ).get_document_complete(URL, max_continuations=7)
    assert out.bytes_consumed == MAX_DOCUMENT_BYTES and out.eof_reached is False
    assert pulled["n"] * 65536 < len(body), "must not have drained the whole body"


# ================================================================
# response observability -- recorded BEFORE adjudication
# ================================================================
def test_response_facts_are_durable_before_a_validation_can_raise(authority, tmp_path):
    """Attempt #1 lost window 1's HTTP status. That must not recur."""
    led = DurableLedger.open(tmp_path / "l.json", authority)
    calls = {"n": 0}
    body = _doc(3_000_000)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                206,
                content=body[:983_040],
                headers={"Content-Range": f"bytes 0-983039/{len(body)}"},
            )
        return httpx.Response(200, content=body)

    with pytest.raises(RangeIntegrityError):
        make_fetcher(authority, led, handler).get_document_complete(
            URL, max_continuations=7, attempt_id="ATTEMPT_TEST"
        )

    reopened = DurableLedger.open(tmp_path / "l.json", authority)
    responses = [e for e in reopened.events if e["kind"] == "response"]
    statuses = [e.get("http_status") for e in responses if e.get("phase") == "headers"]
    assert statuses == [206, 200], f"both window statuses must survive the raise: {statuses}"

    w1 = [e for e in responses if e.get("window_number") == 1 and e.get("phase") == "body"]
    assert w1 and w1[0]["retained_bytes"] == 983_040
    assert len(w1[0]["retained_sha256"]) == 64
    dispositions = [e.get("disposition") for e in responses if e.get("disposition")]
    assert "RANGE_HONORED_206" in dispositions
    assert "INVALID_200_CONTINUATION" in dispositions


def test_a_206_records_its_content_range_verbatim(authority, tmp_path):
    led = DurableLedger.open(tmp_path / "l.json", authority)
    body = _doc(400_000)
    make_fetcher(authority, led, _server(body)).get_document_complete(
        URL, max_continuations=7, attempt_id="A2"
    )
    hdr = [e for e in led.events if e.get("phase") == "headers"]
    assert hdr and hdr[0]["content_range_raw"] == f"bytes 0-399999/{len(body)}"
    assert hdr[0]["attempt_id"] == "A2" and hdr[0]["window_number"] == 1
