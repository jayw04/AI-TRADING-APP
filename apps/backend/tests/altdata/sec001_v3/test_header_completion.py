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

from pathlib import Path

import re

import httpx
import pytest

from app.altdata.mr002 import sic_history
from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog
from app.altdata.sec001_v3.fetch import CrawlExhausted, PolicyFetcher

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


def _content_range(range_header: str | None) -> dict[str, str]:
    """Echo a spec-compliant Content-Range for the window that was requested."""
    if not range_header:
        return {}
    m = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
    if not m:
        return {}
    return {"content-range": f"bytes {m.group(1)}-{m.group(2)}/999999999"}


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
    assert f.header_status[ACC] == policy.ACQ_HEADER_TERMINATED
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
    assert f.header_status[ACC] == policy.ACQ_HEADER_TERMINATED


# --- fixture 2/3: complete header with and without SIC --------------------------------


def test_complete_header_with_sic(tmp_path) -> None:
    body = doc(sic_at=5000, close_at=6000, total=20000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text)[0] == "2834"
    assert f.header_status[ACC] == policy.ACQ_HEADER_TERMINATED


def test_complete_header_legitimately_without_sic(tmp_path) -> None:
    """A header that closes with no SIC is EVIDENCE, not failure -- it must report
    HEADER_COMPLETE so downstream can treat it as an honest no_pit_sic."""
    body = doc(sic_at=None, close_at=6000, total=20000)
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text) == (None, None)
    assert f.header_status[ACC] == policy.ACQ_HEADER_TERMINATED, \
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
        rng = request.headers.get("range")
        seen.append(rng)
        # Echo the granted window. The old fixture hardcoded bytes 0-4095, which
        # misdescribed itself from the second progressive window onward.
        return httpx.Response(206, content=b"Y" * 4096, headers=_content_range(rng))

    f = make(handler, tmp_path)
    with f:
        sic_history.fetch_header_text(f, 320193, ACC)
    assert all(r is not None and r.startswith("bytes=") for r in seen), seen
    assert f.header_status[ACC] == policy.ACQ_HEADER_INCOMPLETE


def test_override_fires_only_for_the_legacy_range(tmp_path) -> None:
    """A different Range must pass straight through, untouched by the override."""
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        calls.append(rng)
        return httpx.Response(206, content=b"nope", headers=_content_range(rng))

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


# --- fixture 8: Defect C -- a failed attempt must not inherit prior evidence -----------


def test_transport_failure_does_not_inherit_previous_capture(tmp_path) -> None:
    """Defect C, found by the v1.2 canary.

    A transport-level failure produces no response. Before the fix, ``_emit`` reused the
    previous attempt's capture, so the failed record carried another request's digests and
    ``sent_monotonic_ns`` -- fabricated provenance, and a duplicate send stamp that
    corrupted the fair-access timing proof (one record in 337 produced a 0.0000s gap).
    """
    import json

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text="first response body")
        raise httpx.ConnectError("simulated transport failure")

    f = make(handler, tmp_path)
    with f:
        assert f.get_text("https://www.sec.gov/a.txt") == "first response body"
        with pytest.raises(CrawlExhausted):
            f.get_text("https://www.sec.gov/b.txt")

    recs = [json.loads(x) for x in (tmp_path / "ev.jsonl").read_text().splitlines() if x]
    ok = [r for r in recs if r["outcome"] == "ok"]
    failed = [r for r in recs if r["outcome"] in ("retry", "error", "exhausted")]
    assert ok and failed

    for r in failed:
        assert r["sha256_body"] is None, "a failed attempt must carry no body digest"
        assert r["sha256_wire"] is None
        assert r["sent_monotonic_ns"] is None, \
            "a failed attempt must not inherit the previous attempt's send stamp"
        assert r["http_status"] is None

    # No send stamp may be duplicated across attempts.
    stamps = [r["sent_monotonic_ns"] for r in recs if r["sent_monotonic_ns"] is not None]
    assert len(stamps) == len(set(stamps)), "duplicate send stamps corrupt the rate proof"


def test_rate_proof_ignores_unsent_attempts(tmp_path) -> None:
    """Attempts that never reached the wire carry no stamp, so they cannot manufacture a
    zero-length gap in the timing evidence."""
    import json
    import time

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 2:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    f = PolicyFetcher(
        evidence=EvidenceLog(path=tmp_path / "ev3.jsonl"),
        transport=httpx.MockTransport(handler),
        sleep=time.sleep,
        monotonic=time.monotonic,
    )
    with f:
        for _ in range(3):
            f.get_json("https://data.sec.gov/submissions/CIK0000000320.json")

    recs = [json.loads(x) for x in (tmp_path / "ev3.jsonl").read_text().splitlines() if x]
    stamps = sorted(r["sent_monotonic_ns"] for r in recs if r["sent_monotonic_ns"] is not None)
    deltas = [(stamps[i + 1] - stamps[i]) / 1e9 for i in range(len(stamps) - 1)]
    assert deltas, "need at least two real transmissions"
    assert all(d >= 0.196 for d in deltas), deltas


# --- fixture 9: Defect D -- three-way status, no collapsing to "complete" --------------


def test_eof_without_terminator_is_not_header_terminated(tmp_path) -> None:
    """Defect D. A document read to EOF with no ``</SEC-HEADER>`` anywhere is a
    SOURCE-FORMAT fact, not evidence completeness.

    This is the real ABT case: accession 0000912057-00-024277 returned all 28,350 bytes
    with no terminator and no SIC. Collapsing it into "complete" launders a source anomaly
    into apparent completeness -- and raising the byte ceiling could never fix it, because
    there is nothing further to read.
    """
    body = b"<SEC-HEADER>\nACCESSION NUMBER: x\n" + b"Z" * 20000  # no close tag, no SIC
    f = make(ranged(body), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 320193, ACC)
    assert sic_history.parse_sic(text) == (None, None)
    assert f.header_status[ACC] == policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR
    assert f.header_status[ACC] != policy.ACQ_HEADER_TERMINATED
    assert f.header_status[ACC] != policy.ACQ_HEADER_INCOMPLETE


def test_three_statuses_are_mutually_distinct() -> None:
    vals = {policy.ACQ_HEADER_INDEX, policy.ACQ_HEADER_TERMINATED,
            policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR, policy.ACQ_HEADER_INCOMPLETE}
    assert len(vals) == 4
    assert policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR == "DOCUMENT_EOF_NO_SEC_HEADER_TERMINATOR"
    assert "COMPLETE" not in policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR


# --- fixture 10: bounded decision-byte retention ---------------------------------------


def test_decision_bytes_retained_for_every_outcome(tmp_path) -> None:
    """Retention is not outcome-dependent: bytes are kept whether or not a SIC was found.

    Keeping evidence only where the result was interesting is how a corpus acquires a
    selection bias nobody can later measure.
    """
    cases = {
        "terminated_with_sic": (doc(sic_at=9000, close_at=12000, total=40000),
                                policy.ACQ_HEADER_TERMINATED),
        "terminated_no_sic": (doc(sic_at=None, close_at=6000, total=20000),
                              policy.ACQ_HEADER_TERMINATED),
        "eof_no_terminator": (b"<SEC-HEADER>\n" + b"Z" * 20000,
                              policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR),
    }
    for name, (body, expected) in cases.items():
        d = tmp_path / name
        f = PolicyFetcher(evidence=EvidenceLog(path=d / "ev.jsonl"),
                          transport=httpx.MockTransport(ranged(body)),
                          sleep=lambda x: None, monotonic=lambda: 0.0,
                          decision_dir=d / "decisions",
                          sic_pattern=sic_history.SIC_RE)
        with f:
            sic_history.fetch_header_text(f, 320193, ACC)
        assert f.header_status[ACC] == expected, name
        rec = f.decisions[ACC]
        assert rec.byte_length > 0, name
        assert rec.artifact_path and Path(rec.artifact_path).exists(), name
        kept = Path(rec.artifact_path).read_bytes()
        import hashlib
        assert hashlib.sha256(kept).hexdigest() == rec.sha256, name
        assert rec.attempts, "constituent request evidence must be recorded"
        assert sum(a.byte_length for a in rec.attempts) >= rec.byte_length


def test_artifact_is_exactly_the_parser_facing_bytes(tmp_path) -> None:
    """Ruling e88ea53, owner-ratified: the artifact is EXACTLY what the parser received.

    Supersedes the earlier "trim at the closing tag" rule. A trimmed artifact is a *prefix*
    of the parser input, so it can resemble the decision but never reproduce it
    byte-for-byte. Boundaries are recorded as offsets into the persisted bytes instead.
    """
    import hashlib

    body = doc(sic_at=5000, close_at=6000, total=40000)
    f = PolicyFetcher(evidence=EvidenceLog(path=tmp_path / "ev.jsonl"),
                      transport=httpx.MockTransport(ranged(body)),
                      sleep=lambda x: None, monotonic=lambda: 0.0,
                      decision_dir=tmp_path / "d", sic_pattern=sic_history.SIC_RE)
    with f:
        sic_history.fetch_header_text(f, 320193, ACC)
    rec = f.decisions[ACC]
    kept = Path(rec.artifact_path).read_bytes()

    # the identity that makes the artifact reproduce the decision
    assert rec.parser_body_sha256 == rec.sha256
    assert hashlib.sha256(kept).hexdigest() == rec.parser_body_sha256
    assert rec.parser_body_length == len(kept)
    assert not kept.endswith(b"</SEC-HEADER>"), \
        "the artifact must NOT be trimmed at the closing tag any more"

    # boundaries survive as OFFSETS INTO THE PERSISTED BYTES, not by truncation
    assert rec.sec_header_open_offset >= 0
    assert rec.sec_header_close_offset > rec.sec_header_open_offset
    assert kept[rec.sec_header_open_offset:].startswith(b"<SEC-HEADER>")
    assert kept[rec.sec_header_close_offset:].startswith(b"</SEC-HEADER>")


def test_decision_predicates_are_independent(tmp_path) -> None:
    """The five structural predicates are orthogonal observations. None of them may be
    read as `no_pit_sic` -- that is a downstream determination about historical evidence."""
    body = b"<SEC-HEADER>\n" + SIC_LINE.encode() + b"more\n</SEC-HEADER>\ntail"
    f = PolicyFetcher(evidence=EvidenceLog(path=tmp_path / "ev.jsonl"),
                      transport=httpx.MockTransport(ranged(body)),
                      sleep=lambda x: None, monotonic=lambda: 0.0,
                      decision_dir=tmp_path / "d", sic_pattern=sic_history.SIC_RE)
    with f:
        sic_history.fetch_header_text(f, 320193, ACC)
    r = f.decisions[ACC]
    assert r.sec_header_open_present
    assert r.sec_header_close_present
    assert r.sic_field_present_anywhere
    assert r.sic_field_present_inside_sec_header
    assert r.document_complete
    assert "no_pit_sic" not in repr(r)
