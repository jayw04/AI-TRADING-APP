"""Fair-access and failure policy for the V3 crawl.

The tests that matter most here are not the happy paths. They are:

- a 403 halts and *latches*, so no second request can reach a host that just blocked us;
- the MR-002 spine's deliberately broad ``except Exception`` handlers cannot swallow that
  halt, which is the entire reason ``CrawlHalt`` derives from ``BaseException``;
- backoff is bounded and jittered, and applies only to the statuses that may be retried.
"""

from __future__ import annotations

import re

import httpx
import pytest

from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog
from app.altdata.sec001_v3.fetch import CrawlExhausted, CrawlHalt, PolicyFetcher

URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106-index-headers.html"
SUBS = "https://data.sec.gov/submissions/CIK0000320193.json"


def make_fetcher(handler, tmp_path, sleeps: list[float] | None = None) -> PolicyFetcher:
    log = EvidenceLog(path=tmp_path / "source_evidence.jsonl")
    return PolicyFetcher(
        evidence=log,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else (lambda d: None)),
        monotonic=lambda: 0.0,
    )


def read_evidence(tmp_path) -> list[dict]:
    import json

    path = tmp_path / "source_evidence.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- frozen policy surface ------------------------------------------------------------


def _content_range(range_header: str | None) -> dict[str, str]:
    """Echo a spec-compliant Content-Range for the window that was requested."""
    if not range_header:
        return {}
    m = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
    if not m:
        return {}
    return {"content-range": f"bytes {m.group(1)}-{m.group(2)}/999999999"}


def test_frozen_policy_values() -> None:
    assert policy.RATE_LIMIT_PER_SEC == 5.0
    assert policy.USER_AGENT == (
        "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"
    )
    assert policy.HALT_STATUSES == (403,)
    assert policy.HALT_COOLDOWN_SECONDS >= 600
    assert frozenset({"GET"}) == policy.ALLOWED_METHODS
    assert policy.CRAWL_SINCE == "2000-01-01"
    assert "8-K" not in policy.FORMS
    assert policy.FORMS == (
        "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
    )


def test_declared_user_agent_and_rate_are_actually_applied(tmp_path) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        seen["method"] = request.method
        return httpx.Response(200, json={"ok": True})

    with make_fetcher(handler, tmp_path) as f:
        assert f.get_json(SUBS) == {"ok": True}
        # 5 rps single host -> 0.2s minimum spacing, enforced by the pinned client.
        assert f._client._min_interval == pytest.approx(0.2)
    assert seen["ua"] == policy.USER_AGENT
    assert seen["method"] == "GET"


def test_non_get_is_refused_at_the_transport(tmp_path) -> None:
    """The pinned client is already GET-only; the invariant is asserted where a request
    would actually leave the process, so it survives any other route to the transport."""
    f = make_fetcher(lambda r: httpx.Response(200), tmp_path)
    with f, pytest.raises(RuntimeError, match="not permitted"):
        f._recorder.handle_request(httpx.Request("POST", URL))


# --- 403: halt, latch, and non-swallowable --------------------------------------------


def test_403_halts_and_is_not_an_ordinary_exception(tmp_path) -> None:
    f = make_fetcher(lambda r: httpx.Response(403), tmp_path)
    with f:
        with pytest.raises(CrawlHalt) as exc:
            f.get_text(URL)
        assert exc.value.status == 403
        assert f.halted is not None
        assert f.requests_issued == 1  # never retried
    # The whole point: `except Exception` must not see it.
    assert not issubclass(CrawlHalt, Exception)
    assert issubclass(CrawlHalt, BaseException)


def test_halt_latches_so_no_further_request_is_issued(tmp_path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403)

    f = make_fetcher(handler, tmp_path)
    with f:
        with pytest.raises(CrawlHalt):
            f.get_text(URL)
        for _ in range(3):
            with pytest.raises(CrawlHalt):
                f.get_text(URL)
    assert len(calls) == 1, "a halted crawl must not touch SEC again"


def test_spine_fail_soft_handlers_cannot_swallow_a_halt(tmp_path) -> None:
    """The regression this design exists to prevent.

    ``sic_history.fetch_header_text`` catches ``Exception`` and falls back to a ranged read
    of the full-submission archive; ``collect_sic_observations`` catches ``Exception`` per
    filing to stay fail-soft. Both would otherwise turn a 403 into a *second* request.
    """
    from app.altdata.mr002 import sic_history

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403)

    f = make_fetcher(handler, tmp_path)
    with f, pytest.raises(CrawlHalt):
        sic_history.fetch_header_text(f, 320193, "0000320193-23-000106")
    assert len(calls) == 1, "the ranged-read fallback must not fire after a 403"


# --- retry policy ---------------------------------------------------------------------


def test_429_is_retried_then_succeeds(tmp_path) -> None:
    sleeps: list[float] = []
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, text="STANDARD INDUSTRIAL CLASSIFICATION: X [3711]")

    f = make_fetcher(handler, tmp_path, sleeps)
    with f:
        assert "3711" in f.get_text(URL)
    assert attempts["n"] == 3
    assert f.retries == 2
    assert len(sleeps) == 2


def test_backoff_is_bounded_and_jittered(tmp_path) -> None:
    sleeps: list[float] = []
    f = make_fetcher(lambda r: httpx.Response(503), tmp_path, sleeps)
    with f, pytest.raises(CrawlExhausted):
        f.get_text(URL)

    assert len(sleeps) == policy.RETRY_MAX_ATTEMPTS - 1
    jitter = policy.RETRY_JITTER_FRACTION
    for i, delay in enumerate(sleeps, start=1):
        base = min(
            policy.RETRY_BASE_DELAY_SECONDS * (2 ** (i - 1)),
            policy.RETRY_MAX_DELAY_SECONDS,
        )
        assert base * (1 - jitter) <= delay <= base * (1 + jitter)
        assert delay <= policy.RETRY_MAX_DELAY_SECONDS * (1 + jitter)
    # Jittered, not a fixed schedule.
    assert any(abs(d - min(policy.RETRY_BASE_DELAY_SECONDS * 2 ** i, 60)) > 1e-9
               for i, d in enumerate(sleeps))


def test_backoff_schedule_is_deterministic_across_runs(tmp_path) -> None:
    """Seeded jitter: a resumed crawl replays its own schedule, so the evidence log
    stays explainable."""
    runs = []
    for i in range(2):
        sleeps: list[float] = []
        f = make_fetcher(lambda r: httpx.Response(500), tmp_path / f"r{i}", sleeps)
        with f, pytest.raises(CrawlExhausted):
            f.get_text(URL)
        runs.append(sleeps)
    assert runs[0] == runs[1]


def test_non_retryable_status_fails_immediately(tmp_path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    f = make_fetcher(handler, tmp_path)
    with f, pytest.raises(CrawlExhausted):
        f.get_text(URL)
    assert calls["n"] == 1, "404 is a fact about the document, not a transient failure"


# --- evidence -------------------------------------------------------------------------


def test_evidence_recorded_per_attempt_with_digests(tmp_path) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, text="hello")

    f = make_fetcher(handler, tmp_path)
    with f:
        f.context = {"cik": 320193, "ticker": "AAPL", "accession": "0000320193-23-000106",
                     "form": "10-K"}
        assert f.get_text(URL) == "hello"

    records = read_evidence(tmp_path)
    assert len(records) == 2, "one record per attempt, retries included"
    assert [r["outcome"] for r in records] == ["retry", "ok"]

    ok = records[-1]
    import hashlib

    assert ok["http_status"] == 200
    assert ok["uri"] == URL
    assert ok["method"] == "GET"
    assert ok["sha256_body"] == hashlib.sha256(b"hello").hexdigest()
    assert ok["cik"] == 320193
    assert ok["form"] == "10-K"
    assert ok["accession"] == "0000320193-23-000106"
    assert ok["ua"] == policy.USER_AGENT
    assert ok["received_utc"].endswith("Z")


def test_gzip_wire_and_body_digests_differ_and_text_is_correct(tmp_path) -> None:
    """``sha256_wire`` is what arrived; ``sha256_body`` is what the parser saw. Conflating
    them would make provenance and change-detection answer the same question badly."""
    import gzip
    import hashlib

    payload = b"STANDARD INDUSTRIAL CLASSIFICATION: SERVICES [7372]"
    packed = gzip.compress(payload)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=packed, headers={"content-encoding": "gzip"})

    f = make_fetcher(handler, tmp_path)
    with f:
        assert "7372" in f.get_text(URL)

    ok = read_evidence(tmp_path)[-1]
    assert ok["sha256_body"] == hashlib.sha256(payload).hexdigest()
    assert ok["sha256_wire"] == hashlib.sha256(packed).hexdigest()
    assert ok["sha256_wire"] != ok["sha256_body"]
    assert ok["content_encoding"] == "gzip"


def test_accession_and_form_are_stamped_without_extra_requests(tmp_path) -> None:
    """The spine loops filings internally, so provenance is recovered from the traffic
    itself: the accession from the URI, the form from the submissions payload already in
    flight. Re-fetching submissions per filing would be 1,167 wasted fair-access requests.
    """
    subs = {"filings": {"recent": {
        "form": ["10-K", "20-F"],
        "accessionNumber": ["0000320193-23-000106", "0000320193-24-000011"],
        "filingDate": ["2023-11-03", "2024-02-01"],
        "acceptanceDateTime": ["2023-11-03T16:30:00.000Z", "2024-02-01T16:30:00.000Z"],
    }, "files": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/submissions/" in str(request.url):
            return httpx.Response(200, json=subs)
        return httpx.Response(200, text="SEC-HEADER")

    f = make_fetcher(handler, tmp_path)
    with f:
        f.context = {"cik": 320193, "ticker": "AAPL"}
        f.get_json(SUBS)
        f.get_text(
            "https://www.sec.gov/Archives/edgar/data/320193/000032019324000011/"
            "0000320193-24-000011-index-headers.html"
        )

    records = read_evidence(tmp_path)
    # The submissions request is not a filing fetch and must not claim an accession.
    assert records[0]["accession"] is None and records[0]["form"] is None
    assert records[1]["accession"] == "0000320193-24-000011"
    assert records[1]["form"] == "20-F"
    assert f.requests_issued == 2, "provenance must cost no extra requests"


def test_accession_recovered_from_the_full_submission_fallback_url(tmp_path) -> None:
    f = make_fetcher(lambda r: httpx.Response(200, text="x"), tmp_path)
    with f:
        accession, form = f._provenance(
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"
            "0000320193-23-000106.txt"
        )
    assert accession == "0000320193-23-000106"
    assert form is None, "form is unknown until a submissions payload supplies it"


def test_ranged_header_read_is_supported(tmp_path) -> None:
    """Amendment B restored ``get_text(headers=)``. Without it the pre-2014 fallback
    downloads whole multi-megabyte submission archives — the path to a 403.

    Since the header-completion override (Remediation Ruling v1.0 §1), the spine's legacy
    ``bytes=0-4095`` also starts a bounded progressive read. The invariant asserted here is
    that the FIRST range is still byte-identical to the spine's own request, so a filing
    whose header already fits costs exactly what it did before.
    """
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        seen.append(rng)
        # A real 206 MUST carry a Content-Range consistent with the request
        # (RFC 9110 15.3.7); the transport now refuses one that does not.
        return httpx.Response(206, text="SEC-HEADER", headers=_content_range(rng))

    f = make_fetcher(handler, tmp_path)
    with f:
        f.get_text(URL, headers={"Range": policy.LEGACY_HEADER_RANGE})
    assert seen[0] == "bytes=0-4095", "first window must match the spine's legacy request"
    assert all(r and r.startswith("bytes=") for r in seen), seen
    assert len(seen) <= policy.HEADER_COMPLETION_MAX_REQUESTS
