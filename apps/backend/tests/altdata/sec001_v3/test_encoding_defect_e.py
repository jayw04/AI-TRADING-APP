"""Defect E — an encoded range representation must never reach the frozen parser.

Ruling e88ea53. The pinned client sends ``Accept-Encoding: gzip, deflate``; for a RANGED
request SEC serves a byte range of the COMPRESSED representation. The transport called
``gzip.decompress()`` on that fragment, it raised, and a single line swallowed it::

    except (OSError, zlib.error, EOFError):
        body = raw

So compressed bytes went to the parser as document bytes, and it searched gzip noise.

Two independent errors compounded: range offsets referring to the compressed representation
while the frozen spine assumes document-byte semantics, and a decode failure falling back to
raw instead of failing closed. Either alone would have been visible; together they produced
a plausible, self-consistent and entirely false picture across three canaries.

The remedy is structural rather than clever: for the legacy ranged fallback, obtain the
representation the spine already assumes (``Accept-Encoding: identity``), and fail closed
everywhere else.
"""

from __future__ import annotations

import gzip as _gzip
import hashlib
from pathlib import Path

import httpx
import pytest
from httpx._content import ByteStream

from app.altdata.mr002 import sic_history
from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog
from app.altdata.sec001_v3.fetch import AcquisitionEncodingError, PolicyFetcher

ACC = "0000912057-00-024277"
TXT_URL = f"https://www.sec.gov/Archives/edgar/data/1800/000091205700024277/{ACC}.txt"
SIC_LINE = "STANDARD INDUSTRIAL CLASSIFICATION: PHARMACEUTICAL PREPARATIONS [2834]\n"
GZIP_MAGIC = bytes((0x1F, 0x8B))


def abt_like_document() -> bytes:
    """A byte-faithful miniature of the real diagnostic document.

    The genuine accession has 423 bytes of preamble, ``<SEC-HEADER>`` at 423, the SIC line
    at 748 and ``</SEC-HEADER>`` at 1169 — so an identity 4 KiB window contains all three
    and exactly one range suffices.
    """
    out = bytearray()
    out += b"-----BEGIN PRIVACY-ENHANCED MESSAGE-----\n"
    out += b"X" * (423 - len(out))
    assert len(out) == 423
    out += b"<SEC-HEADER>\n"
    out += b"ACCESSION NUMBER:\t\t" + ACC.encode() + b"\n"
    out += b"CONFORMED SUBMISSION TYPE:\t10-Q\n"
    out += b"Y" * (748 - len(out))
    out += SIC_LINE.encode()
    out += b"Z" * (1169 - len(out))
    out += b"</SEC-HEADER>\n"
    # Deterministic, poorly-compressible filler. With merely repetitive filler the whole
    # document gzips to a few hundred bytes, so a 4 KiB range would return a COMPLETE gzip
    # stream that decodes fine -- and the fragment case under test would never occur.
    seed = hashlib.sha256(b"sec001-v3-defect-e").digest()
    filler = bytearray()
    while len(filler) < 200_000:
        seed = hashlib.sha256(seed).digest()
        filler += seed
    out += bytes(filler)
    return bytes(out)


def raw_response(status: int, body: bytes, headers: dict[str, str]) -> httpx.Response:
    """A response whose ``.stream`` yields RAW wire bytes.

    Fidelity matters here. ``httpx.Response(content=...)`` decodes at ``.stream`` iteration,
    so a mock built that way would raise inside httpx before the transport ever sees the
    bytes -- and would therefore never exercise the guard. The real ``HTTPTransport`` yields
    undecoded wire bytes, which is precisely why the live canary retained gzip. ``stream=``
    reproduces that.
    """
    return httpx.Response(status, headers=headers, stream=ByteStream(body))


def serve(full: bytes, *, encode: bool = False, declare: str | None = None):
    """A handler that 404s index-headers and honours Range over ``full``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "-index-headers.html" in str(request.url):
            return httpx.Response(404)
        payload = _gzip.compress(full, mtime=0) if encode else full
        rng = request.headers.get("range")
        if not rng:
            body = payload
            s0 = 0
        else:
            a, b = rng.removeprefix("bytes=").split("-")
            s0, e0 = int(a), int(b)
            body = payload[s0:e0 + 1]
        headers = {"content-range": f"bytes {s0}-{s0 + len(body) - 1}/{len(payload)}"}
        if declare:
            headers["content-encoding"] = declare
        return raw_response(206 if rng else 200, body, headers)

    return handler


def fetcher(handler, tmp_path: Path) -> PolicyFetcher:
    return PolicyFetcher(
        evidence=EvidenceLog(path=tmp_path / "ev.jsonl"),
        transport=httpx.MockTransport(handler),
        sleep=lambda d: None,
        monotonic=lambda: 0.0,
        decision_dir=tmp_path / "decisions",
        sic_pattern=sic_history.SIC_RE,
    )


# --- 1. identity encoding is forced on the legacy ranged fallback ----------------------


def test_legacy_ranged_fallback_sends_accept_encoding_identity(tmp_path) -> None:
    seen: list[str | None] = []
    full = abt_like_document()

    def handler(request: httpx.Request) -> httpx.Response:
        if "-index-headers.html" in str(request.url):
            return httpx.Response(404)
        seen.append(request.headers.get("accept-encoding"))
        return serve(full)(request)

    f = fetcher(handler, tmp_path)
    with f:
        sic_history.fetch_header_text(f, 1800, ACC)
    assert seen, "the ranged fallback never fired"
    assert all(a == "identity" for a in seen), seen
    assert policy.RANGED_ACCEPT_ENCODING == "identity"


# --- 2. the ABT positive control -------------------------------------------------------


def test_identity_4kib_response_recovers_sic_2834(tmp_path) -> None:
    """The root-cause positive control. One range, SIC 2834, header terminated."""
    full = abt_like_document()
    f = fetcher(serve(full), tmp_path)
    with f:
        text = sic_history.fetch_header_text(f, 1800, ACC)

    assert sic_history.parse_sic(text) == ("2834", "PHARMACEUTICAL PREPARATIONS")
    assert f.header_status[ACC] == policy.ACQ_HEADER_TERMINATED

    rec = f.decisions[ACC]
    kept = Path(rec.artifact_path).read_bytes()
    assert kept[:2] != GZIP_MAGIC
    assert rec.sec_header_open_present and rec.sec_header_close_present
    assert rec.sic_field_present_anywhere and rec.sic_field_present_inside_sec_header
    # </SEC-HEADER> at 1169 is inside the first window, so no second range is permitted
    ranged_attempts = [a for a in rec.attempts if a.range_header]
    assert len(ranged_attempts) == 1, [a.range_header for a in ranged_attempts]
    assert ranged_attempts[0].range_header == "bytes=0-4095"


# --- 3. range offsets refer to document bytes -----------------------------------------


def test_range_offsets_apply_to_document_bytes(tmp_path) -> None:
    full = abt_like_document()
    f = fetcher(serve(full), tmp_path)
    with f:
        sic_history.fetch_header_text(f, 1800, ACC)
    kept = Path(f.decisions[ACC].artifact_path).read_bytes()
    assert kept == full[:len(kept)], "persisted bytes must be a document-offset prefix"


# --- 4/5. encoded or undecodable bodies fail closed -----------------------------------


def test_unexpected_gzip_on_ranged_response_fails_closed(tmp_path) -> None:
    """If the server ignores identity and encodes anyway, acquisition fails explicitly.

    This is the exact Defect E shape: a FRAGMENT of a gzip stream, undecodable alone.
    """
    f = fetcher(serve(abt_like_document(), encode=True, declare="gzip"), tmp_path)
    with f, pytest.raises(AcquisitionEncodingError):
        sic_history.fetch_header_text(f, 1800, ACC)
    assert f.header_status[ACC] == policy.ACQ_ENCODING_UNSUPPORTED
    assert f.header_status[ACC] != policy.ACQ_DOCUMENT_EOF_NO_TERMINATOR
    assert f.header_status[ACC] != policy.ACQ_HEADER_TERMINATED


def test_malformed_encoding_fails_closed_on_a_non_ranged_path(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, b"not really gzip at all",
                            {"content-encoding": "gzip"})

    f = fetcher(handler, tmp_path)
    with f, pytest.raises(AcquisitionEncodingError):
        f.get_text("https://www.sec.gov/plain.txt")


def test_unsupported_encoding_name_fails_closed(tmp_path) -> None:
    """An encoding we do not implement must fail, not silently pass bytes through."""
    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, b"whatever", {"content-encoding": "br"})

    f = fetcher(handler, tmp_path)
    with f, pytest.raises(AcquisitionEncodingError):
        f.get_text("https://www.sec.gov/br.txt")


# --- 6. gzip magic never reaches the parser -------------------------------------------


def test_no_parser_call_receives_gzip_magic(tmp_path) -> None:
    """Value-level backstop. Encoded bytes with NO declared encoding are invisible to the
    hash invariant, so the magic-byte check is what must catch them."""
    payload = _gzip.compress(abt_like_document(), mtime=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, payload, {})  # no content-encoding header

    f = fetcher(handler, tmp_path)
    with f, pytest.raises(AcquisitionEncodingError, match="gzip magic"):
        f.get_text("https://www.sec.gov/c.txt")


# --- 7. the encoded-body integrity invariant, with its zero-length guard --------------


def test_encoded_body_integrity_invariant_zero_length_guard(tmp_path) -> None:
    """The zero-length guard must prevent a SPURIOUS failure, not manufacture one.

    An empty body with a declared encoding hashes identically on both sides -- both are
    sha256(b"") -- so without the ``wire_bytes > 0`` guard the invariant would fire on a
    condition that carries no encoded bytes at all. Note ``gzip.decompress(b"")`` returns
    b"" rather than raising, so decoding genuinely succeeds here.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, b"", {"content-encoding": "gzip"})

    f = fetcher(handler, tmp_path)
    with f:
        assert f.get_text("https://www.sec.gov/empty.txt") == ""


def test_integrity_invariant_fires_when_decoding_silently_did_not_happen(tmp_path) -> None:
    """The invariant itself: declared encoding, non-empty body, wire == parser body.

    This is the signal that was present in every failed canary and that nothing checked.
    Constructed directly on the guard, because a transport cannot produce it once decoding
    is fail-closed -- which is the point.
    """
    from app.altdata.sec001_v3.fetch import _Capture

    f = fetcher(lambda r: raw_response(200, b"x", {}), tmp_path)
    payload = b"pretend this is gzip" * 10
    cap = _Capture(status=200, url=TXT_URL, wire=payload, body=payload,
                   content_encoding="gzip", sent_utc="2026-08-24T00:00:00Z",
                   sent_monotonic_ns=1, range_header="bytes=0-4095",
                   content_range=None, request_accept_encoding="identity",
                   decode_ok=True, decode_error=None)
    with f, pytest.raises(AcquisitionEncodingError, match="byte-identical"):
        f._assert_parser_safe(cap, TXT_URL)
    assert f.header_status[ACC] == policy.ACQ_ENCODING_UNSUPPORTED


def test_identity_declared_encoding_is_allowed(tmp_path) -> None:
    """`identity` means no transformation, so wire == body is correct there and must NOT
    trip the invariant."""
    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, b"plain document bytes",
                            {"content-encoding": "identity"})

    f = fetcher(handler, tmp_path)
    with f:
        assert f.get_text("https://www.sec.gov/id.txt") == "plain document bytes"


def test_correctly_decoded_gzip_still_passes(tmp_path) -> None:
    """Positive control for the invariant: a COMPLETE gzip stream decodes, wire and body
    differ, and the body reaches the parser. This is the -index-headers.html path, which
    is why those 53 observations were never contaminated."""
    doc_bytes = abt_like_document()

    def handler(request: httpx.Request) -> httpx.Response:
        return raw_response(200, _gzip.compress(doc_bytes, mtime=0),
                            {"content-encoding": "gzip"})

    f = fetcher(handler, tmp_path)
    with f:
        text = f.get_text("https://www.sec.gov/ok.txt")
    assert sic_history.parse_sic(text)[0] == "2834"


# --- 11. the decision artifact proves the exact parser input --------------------------


def test_decision_artifact_proves_exact_parser_input(tmp_path) -> None:
    full = abt_like_document()
    f = fetcher(serve(full), tmp_path)
    with f:
        sic_history.fetch_header_text(f, 1800, ACC)
    r = f.decisions[ACC]
    kept = Path(r.artifact_path).read_bytes()

    assert hashlib.sha256(kept).hexdigest() == r.parser_body_sha256 == r.sha256
    assert r.parser_body_length == len(kept)
    assert r.request_accept_encoding == "identity"
    assert r.response_content_encoding in (None, "", "identity")
    assert r.wire_sha256 and r.wire_byte_length
    assert r.attempts and all(a.range_header for a in r.attempts)
    # boundaries are offsets into the persisted bytes, not text positions
    assert kept[r.sec_header_open_offset:].startswith(b"<SEC-HEADER>")
    assert kept[r.sec_header_close_offset:].startswith(b"</SEC-HEADER>")
