"""Transport policy: bounds, halt latch, retry accounting, caps, CREATE-ONCE."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.sec001_v31.transport import (
    FETCH_OK,
    FETCH_UNAVAILABLE,
    AcquisitionEncodingError,
    BoundedFetcher,
    BudgetExceeded,
    CrawlHalt,
    CreateOnceStore,
    CreateOnceViolation,
    RequestLedger,
)

URL = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000070/primary.htm"


def ledger(**kw) -> RequestLedger:
    return RequestLedger(
        max_index_requests=kw.get("idx", 200),
        max_document_requests=kw.get("doc", 1200),
        max_total_retries=kw.get("retries", 200),
    )


def fetcher(handler, *, led=None, ceiling=4096, stop=2048, **kw) -> BoundedFetcher:
    return BoundedFetcher(
        led or ledger(),
        user_agent="TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com",
        ceiling_bytes=ceiling,
        stop_threshold_bytes=stop,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
        **kw,
    )


# ------------------------------------------------- case 15: ignored Range -> 200 full
def test_ignored_range_200_is_bounded_streamed_not_materialised_then_sliced():
    """The server ignores Range and starts sending a 10 MB document.

    Proof of streaming rather than materialise-then-slice: count the chunks the source
    generator is actually asked for. A materialising client would drain all 160 of them.
    """
    total, chunk = 10 * 1024 * 1024, 65536
    pulled = {"n": 0}

    def source():
        for _ in range(total // chunk):
            pulled["n"] += 1
            yield b"A" * chunk

    def handler(_request: httpx.Request) -> httpx.Response:
        # 200, not 206: Range was ignored and the full representation is being sent.
        return httpx.Response(200, content=source())

    f = fetcher(handler, ceiling=1_048_576, stop=983_040)
    out = f.get_document(URL)

    assert out.status == FETCH_OK
    assert out.truncated is True
    assert out.bytes_consumed == 983_040
    assert len(out.body) == 983_040
    assert pulled["n"] == 15, f"drained {pulled['n']} chunks; expected to stop at the bound"
    assert pulled["n"] * chunk < total
    assert out.eof_reached is False, "a bounded prefix of a 10 MB document is NOT EOF"


def test_range_honoured_206_is_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=0-2047"
        assert request.headers["Accept-Encoding"] == "identity"
        assert request.method == "GET"
        return httpx.Response(
            206,
            content=b"x" * 2048,
            headers={"Content-Range": "bytes 0-2047/2048"},
        )

    out = fetcher(handler).get_document(URL)
    assert out.status == FETCH_OK and out.http_status == 206
    assert out.eof_reached is True and out.total_bytes == 2048


def test_hard_ceiling_is_never_breached():
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"z" * 100_000)

    out = fetcher(handler, ceiling=4096, stop=2048).get_document(URL)
    assert len(out.body) <= 4096 and out.bytes_consumed == 2048


# ----------------------------------------------------------- case 13: 403 latches
def test_403_halts_and_latches_so_no_second_request_is_possible():
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403)

    f = fetcher(handler)
    with pytest.raises(CrawlHalt):
        f.get_document(URL)
    assert f.halted is True
    assert calls["n"] == 1

    # even a caller that swallows BaseException cannot produce a second request
    with pytest.raises(CrawlHalt):
        f.get_document(URL)
    assert calls["n"] == 1, "latch leaked a second request to a host that blocked us"


def test_halt_is_not_an_ordinary_exception():
    assert issubclass(CrawlHalt, BaseException) and not issubclass(CrawlHalt, Exception)


# ------------------------------------------- case 14: 429/5xx bounded retry accounting
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_status_is_retried_then_fails_closed_with_exact_accounting(status):
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    led = ledger()
    out = fetcher(handler, led=led).get_document(URL)

    assert out.status == FETCH_UNAVAILABLE
    assert calls["n"] == 5, "retry_max_attempts not honoured"
    assert led.document_requests == 5, "every attempt must be charged"
    assert led.retries == 4, "retries are attempts minus the initial try"


def test_retry_then_success_is_accounted():
    seq = [503, 503, 200]

    def handler(_r: httpx.Request) -> httpx.Response:
        s = seq.pop(0)
        return httpx.Response(s, content=b"ok" if s == 200 else b"")

    led = ledger()
    out = fetcher(handler, led=led).get_document(URL)
    assert out.status == FETCH_OK and out.attempts == 3
    assert led.document_requests == 3 and led.retries == 2


def test_retry_budget_is_itself_capped():
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    led = ledger(retries=1)
    with pytest.raises(BudgetExceeded):
        fetcher(handler, led=led).get_document(URL)


# --------------------------------------------------- case 17: caps cannot be exceeded
def test_document_request_cap_is_enforced():
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x")

    led = ledger(doc=2)
    f = fetcher(handler, led=led)
    f.get_document(URL)
    f.get_document(URL)
    with pytest.raises(BudgetExceeded):
        f.get_document(URL)
    assert led.document_requests == 2


def test_index_and_document_budgets_are_separate():
    led = ledger(idx=1, doc=1)
    led.charge_index()
    led.charge_document()
    with pytest.raises(BudgetExceeded):
        led.charge_index()
    with pytest.raises(BudgetExceeded):
        led.charge_document()


# --------------------------------------------------------- Defect E: encoded responses
def test_content_encoded_response_to_a_ranged_request_fails_closed():
    """A server that ignores ``Accept-Encoding: identity`` and answers a ranged request with
    an encoded representation. httpx would transparently decode it and hand the parser
    plausible-looking bytes whose range offsets refer to the *compressed* stream — the
    Defect-E failure. The declared encoding is therefore the guard, not the body content."""
    import gzip

    payload = gzip.compress(b"<html>cover page</html>")

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=payload, headers={"Content-Encoding": "gzip"})

    with pytest.raises(AcquisitionEncodingError):
        fetcher(handler).get_document(URL)


def test_gzip_magic_reaching_the_parser_fails_closed():
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bytes((0x1F, 0x8B)) + b"rest")

    with pytest.raises(AcquisitionEncodingError):
        fetcher(handler).get_document(URL)


def test_unexpected_status_fails_closed_without_retry():
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    led = ledger()
    out = fetcher(handler, led=led).get_document(URL)
    assert out.status == FETCH_UNAVAILABLE and led.document_requests == 1


# ------------------------------------------------------------ case 16: CREATE-ONCE
def test_artifact_identity_is_create_once(tmp_path):
    store = CreateOnceStore(tmp_path)
    ident = CreateOnceStore.identity(
        1652044, "0001652044-26-000070", "PRIMARY_DOCUMENT_COVER", "abc"
    )
    store.put(ident, {"cik": 1652044})
    with pytest.raises(CreateOnceViolation):
        store.put(ident, {"cik": 1652044, "tampered": True})


def test_create_once_survives_a_fresh_store_over_the_same_root(tmp_path):
    ident = CreateOnceStore.identity(
        1652044, "0001652044-26-000070", "PRIMARY_DOCUMENT_COVER", "abc"
    )
    CreateOnceStore(tmp_path).put(ident, {"cik": 1652044})
    with pytest.raises(CreateOnceViolation):
        CreateOnceStore(tmp_path).put(ident, {"cik": 1652044})


def test_artifact_identity_is_reconstructable(tmp_path):
    store = CreateOnceStore(tmp_path)
    ident = CreateOnceStore.identity(
        1652044, "0001652044-26-000070", "PRIMARY_DOCUMENT_COVER", "obs1"
    )
    p = store.put(ident, {"cik": 1652044})
    import json

    assert json.loads(p.read_text())["_artifact_identity"] == ident
    assert ident == "0001652044/0001652044-26-000070/PRIMARY_DOCUMENT_COVER/obs1"


# ================================================================
# Bounded continuation — opt-in, budget-charged, EOF-or-nothing
# ================================================================
def _ranged_server(total: int, window_cap: int | None = None):
    """A well-behaved byte-range server over a document of `total` bytes."""
    served: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers["Range"]
        start, end = (int(x) for x in rng.removeprefix("bytes=").split("-"))
        end = min(end, total - 1)
        if window_cap is not None:
            end = min(end, start + window_cap - 1)
        served.append((start, end))
        body = bytes((start + i) % 251 for i in range(end - start + 1))
        return httpx.Response(
            206, content=body, headers={"Content-Range": f"bytes {start}-{end}/{total}"}
        )

    return handler, served


def test_continuation_is_off_by_default_so_a_large_document_is_not_eof():
    handler, served = _ranged_server(total=3_000_000)
    led = ledger()
    out = fetcher(handler, led=led, ceiling=1_048_576, stop=983_040).get_document_complete(URL)

    assert out.eof_reached is False, "default must not silently continue"
    assert len(served) == 1 and led.document_requests == 1
    assert out.bytes_consumed == 983_040


def test_continuation_reaches_eof_across_windows_and_charges_each_one():
    total = 2_500_000
    handler, served = _ranged_server(total=total)
    led = ledger()
    f = fetcher(handler, led=led, ceiling=1_048_576, stop=983_040)

    out = f.get_document_complete(URL, max_continuations=8, max_cumulative_bytes=total)

    assert out.eof_reached is True
    assert out.bytes_consumed == total
    assert out.truncated is False
    assert len(served) == 3, f"windows served: {served}"
    assert led.document_requests == 3, "every continuation is a document request"
    assert served[0][0] == 0 and served[1][0] == 983_040


def test_continuation_that_exhausts_its_budget_without_eof_is_not_eof():
    handler, served = _ranged_server(total=10_000_000)
    led = ledger()
    f = fetcher(handler, led=led, ceiling=1_048_576, stop=983_040)

    out = f.get_document_complete(URL, max_continuations=2, max_cumulative_bytes=10_000_000)

    assert out.eof_reached is False
    assert out.truncated is True
    assert len(served) == 3 and led.document_requests == 3


def test_continuation_respects_the_document_request_cap():
    handler, _ = _ranged_server(total=10_000_000)
    led = ledger(doc=2)
    f = fetcher(handler, led=led, ceiling=1_048_576, stop=983_040)
    with pytest.raises(BudgetExceeded):
        f.get_document_complete(URL, max_continuations=8, max_cumulative_bytes=10_000_000)
    assert led.document_requests == 2


def test_small_document_reaches_eof_in_one_window():
    handler, served = _ranged_server(total=5_000)
    out = fetcher(handler, ceiling=1_048_576, stop=983_040).get_document_complete(URL)
    assert out.eof_reached is True and out.bytes_consumed == 5_000 and len(served) == 1
