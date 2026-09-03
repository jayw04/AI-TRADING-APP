"""Regression fixtures for the 2026-08-24 canary defects.

Defect A -- the frozen spine's legacy ``Range: bytes=0-4095`` fallback recovered ZERO SIC
for pre-2014 filings: a perfect 53/53 split against index-header fetches, every ranged body
exactly 4,096 bytes. The SIC line simply lies beyond the first 4 KiB.

Defect B -- ``requested_utc`` was stamped before the fair-access throttle slept, so the
evidence log could not substantiate the very rate policy it exists to demonstrate.

The single most important assertion here is the one separating ``no_pit_sic`` from
``ACQUISITION_HEADER_INCOMPLETE``. The first is a fact about historical evidence; the second
is a failure of our machinery. Conflating them would let a bug present as missing history
and silently move the evaluation start date.
"""

from __future__ import annotations

import httpx
import pytest

from app.altdata.mr002 import sic_history
from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog
from app.altdata.sec001_v3.fetch import PolicyFetcher

ACC = "0000320193-01-500001"
TXT_URL = f"https://www.sec.gov/Archives/edgar/data/320193/000032019301500001/{ACC}.txt"

SIC_LINE = "STANDARD INDUSTRIAL CLASSIFICATION: PHARMACEUTICAL PREPARATIONS [2834]\n"


def make(handler, tmp_path, sleeps=None) -> PolicyFetcher:
    return PolicyFetcher(
        evidence=EvidenceLog(path=tmp_path / "ev.jsonl"),
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else (lambda d: None)),
        monotonic=lambda: 0.0,
    )


def ranged(body: bytes):
    """A MockTransport handler modelling a pre-2014 accession.

    Real EDGAR 404s ``-index-headers.html`` for those filings, which is precisely what
    drives the frozen spine into its legacy ranged fallback. The fixture must reproduce
    that, or the code path under test never executes.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "-index-headers.html" in str(request.url):
            return httpx.Response(404)
        rng = request.headers.get("range")
        if not rng:
            return httpx.Response(200, content=body)
        first, last = rng.removeprefix("bytes=").split("-")
        s, e = int(first), int(last)
        chunk = body[s:e + 1]
        if not chunk:
            return httpx.Response(416, content=b"")
        return httpx.Response(206, content=chunk, headers={
            "content-range": f"bytes {s}-{s + len(chunk) - 1}/{len(body)}"})

    return handler


def doc(sic_at: int | None, close_at: int, total: int) -> bytes:
    """Synthetic full-submission archive: optional SIC at an offset, header close, filler."""
    buf = bytearray(b"<SEC-HEADER>\n" + b"X" * total)
    if sic_at is not None:
        buf[sic_at:sic_at + len(SIC_LINE)] = SIC_LINE.encode()
    tag = policy.SEC_HEADER_CLOSE_TAG.encode()
    buf[close_at:close_at + len(tag)] = tag
    return bytes(buf)


# --- fixture 1: SIC beyond byte 4095 (the canary defect) ------------------------------


def test_sic_beyond_4095_is_recovered(tmp_path) -> None:
    """The exact 2026-08-24 failure. Under the old behaviour this returned 4,096 bytes
    and no SIC; the override must complete the header and recover it."""
    body = doc(sic_at=9000, close_at=12000, total=40000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    sic, name = sic_history.parse_sic(text)
    assert sic == "2834", "SIC beyond the legacy 4 KiB window must be recovered"
    assert name == "PHARMACEUTICAL PREPARATIONS"
    assert f.header_status[ACC] == policy.ACQ_HEADER_COMPLETE
    assert f.requests_issued > 1, "completion requires more than the single legacy window"


def test_sic_within_first_window_costs_one_request(tmp_path) -> None:
    """The common case must not get more expensive: the first window is byte-identical
    to the spine's own legacy request."""
    body = doc(sic_at=100, close_at=2000, total=40000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text)[0] == "2834"
    # 1 x the 404'd index-headers probe (the spine's own first attempt) + exactly 1 ranged
    # window. The override adds nothing when the header already fits in 4 KiB.
    assert f.requests_issued == 2
    assert f.header_status[ACC] == policy.ACQ_HEADER_COMPLETE


# --- fixture 2/3: complete header with and without SIC --------------------------------


def test_complete_header_with_sic(tmp_path) -> None:
    body = doc(sic_at=5000, close_at=6000, total=20000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text)[0] == "2834"
    assert f.header_status[ACC] == policy.ACQ_HEADER_COMPLETE


def test_complete_header_legitimately_without_sic(tmp_path) -> None:
    """A header that closes with no SIC is EVIDENCE, not failure -- it must report
    HEADER_COMPLETE so downstream can treat it as an honest no_pit_sic."""
    body = doc(sic_at=None, close_at=6000, total=20000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text) == (None, None)
    assert f.header_status[ACC] == policy.ACQ_HEADER_COMPLETE, \
        "a legitimately SIC-less header is complete, not an acquisition failure"


# --- fixture 4: cap exceeded is an ACQUISITION failure, never no_pit_sic ---------------


def test_cap_exceeded_is_acquisition_failure_not_no_pit_sic(tmp_path) -> None:
    """The load-bearing distinction. A header that never closes within the frozen 1 MiB
    cap must be reported as OUR failure, so it can never be counted as missing history."""
    big = 2 * 1024 * 1024
    body = bytearray(b"<SEC-HEADER>\n" + b"X" * big)  # no close tag, no SIC
    f = make(ranged(bytes(body)), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text) == (None, None)
    assert f.header_status[ACC] == policy.ACQ_HEADER_INCOMPLETE
    assert f.header_status[ACC] != "no_pit_sic"


def test_cap_is_frozen_at_one_mebibyte() -> None:
    assert policy.HEADER_COMPLETION_CAP_BYTES == 1048576
    assert policy.HEADER_COMPLETION_WINDOWS[-1] == policy.HEADER_COMPLETION_CAP_BYTES
    assert policy.HEADER_COMPLETION_WINDOWS[0] == 4096, \
        "first window must match the spine's legacy request exactly"
    assert list(policy.HEADER_COMPLETION_WINDOWS) == sorted(policy.HEADER_COMPLETION_WINDOWS)


def test_override_never_fetches_the_whole_file(tmp_path) -> None:
    """Bounded progressive ranges only -- never an unbounded whole-file GET."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "-index-headers.html" in str(request.url):
            return httpx.Response(404)
        seen.append(request.headers.get("range"))
        return httpx.Response(206, content=b"Y" * 4096,
                              headers={"content-range": "bytes 0-4095/999999999"})

    f = make(handler, tmp_path)
    with f:
        sic_history.fetch_header_text(f, 320193, ACC)
    assert all(r is not None and r.startswith("bytes=") for r in seen), seen
    assert f.header_status[ACC] == policy.ACQ_HEADER_INCOMPLETE


def test_override_fires_only_for_the_legacy_range(tmp_path) -> None:
    """A different Range must pass straight through, untouched by the override."""
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("range"))
        return httpx.Response(206, content=b"nope")

    f = make(handler, tmp_path)
    with f:
        f.get_text(TXT_URL, headers={"Range": "bytes=100-200"})
    assert calls == ["bytes=100-200"]
    assert ACC not in f.header_status


# --- fixture 5: 403 still emits exactly one request -----------------------------------


def test_403_still_emits_exactly_one_request_under_override(tmp_path) -> None:
    """The override must not weaken the halt latch -- including on the ranged path."""
    from app.altdata.sec001_v3.fetch import CrawlHalt

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403)

    f = make(handler, tmp_path)
    with f, pytest.raises(CrawlHalt):
        sic_history.fetch_header_text(f, 320193, ACC)
    assert len(calls) == 1, "a 403 must not trigger progressive range escalation"


# --- fixture 6: retries stay rate-throttled -------------------------------------------


def test_retries_on_the_ranged_path_stay_throttled(tmp_path) -> None:
    sleeps: list[float] = []
    attempts = {"n": 0}
    body = doc(sic_at=9000, close_at=12000, total=40000)
    inner = ranged(body)

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 2:
            return httpx.Response(503)
        return inner(request)

    f = make(handler, tmp_path, sleeps)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text)[0] == "2834"
    assert f.retries == 1
    assert len(sleeps) == 1 and sleeps[0] > 0


# --- fixture 7: actual-send intervals prove the rate policy ---------------------------


def test_transmission_evidence_is_recorded_and_post_throttle(tmp_path) -> None:
    """Defect B. ``requested_utc`` is attempt-start; ``sent_monotonic_ns`` is stamped
    inside the transport immediately before transmission and is the clock used for rate
    proof."""
    import json

    body = doc(sic_at=9000, close_at=12000, total=40000)
    f = make(ranged(body), tmp_path)
    with f:
        sic_history.fetch_header_text(f, 320193, ACC)

    recs = [json.loads(x) for x in (tmp_path / "ev.jsonl").read_text().splitlines() if x]
    assert recs, "no evidence written"
    for r in recs:
        assert r["sent_utc"], "every attempt must carry a transmission wall clock"
        assert isinstance(r["sent_monotonic_ns"], int)
    # Range evidence is asserted only on the ranged full-submission fetches; the spine's
    # 404'd index-headers probe is a plain GET and correctly records no Range.
    ranged_recs = [r for r in recs if r["uri"].endswith(".txt")]
    assert ranged_recs, "the ranged fallback should have fired"
    for r in ranged_recs:
        assert r["range_header"] is not None, "range requests must record their Range header"
        assert r["content_range"] is not None, "and the served Content-Range"
    index_recs = [r for r in recs if "-index-headers.html" in r["uri"]]
    assert index_recs and all(r["range_header"] is None for r in index_recs)
    # monotonic send stamps are non-decreasing
    stamps = [r["sent_monotonic_ns"] for r in recs]
    assert stamps == sorted(stamps)


def test_send_deltas_measure_the_real_throttle(tmp_path) -> None:
    """With the real clock (no injected sleep), consecutive transmissions must be at least
    the frozen minimum interval apart. This is the assertion the first canary could not
    make, because it was measuring pre-throttle timestamps."""
    import json
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    f = PolicyFetcher(
        evidence=EvidenceLog(path=tmp_path / "ev2.jsonl"),
        transport=httpx.MockTransport(handler),
        sleep=time.sleep,          # real throttle behaviour
        monotonic=time.monotonic,
    )
    with f:
        for _ in range(3):
            f.get_json("https://data.sec.gov/submissions/CIK0000000320.json")

    recs = [json.loads(x) for x in (tmp_path / "ev2.jsonl").read_text().splitlines() if x]
    stamps = [r["sent_monotonic_ns"] for r in recs]
    deltas = [(stamps[i + 1] - stamps[i]) / 1e9 for i in range(len(stamps) - 1)]
    assert deltas, "need at least two transmissions"
    min_interval = 1.0 / policy.RATE_LIMIT_PER_SEC
    for d in deltas:
        assert d >= min_interval * 0.98, f"send delta {d:.4f}s below {min_interval}s"
