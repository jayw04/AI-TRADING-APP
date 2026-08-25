"""Defect F — the transport must be PULL-bounded, not merely retention-bounded.

Ruling 7C boundary 3: consuming a 422 MB entity and then keeping 1 MiB is a FAIL. These
tests therefore assert against what the implementation *pulls from the stream*, not
against what it stores.

The central device is ``ExplodingStream``: a stream whose first chunks carry a complete
SEC header and whose remainder **raises** if it is ever requested. A correct
implementation obtains its decision bytes, finalises hashes and evidence, closes the
response, and never touches the remainder. The old
``raw = b"".join(response.stream)`` line detonates it immediately.
"""

from __future__ import annotations

import hashlib

import httpx
import pytest

from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.fetch import (
    ConsumptionCeilingExceeded,
    RangeContractViolation,
    RecordingTransport,
    _classify_range,
    _consumption_stop_threshold,
)

HEADER = (
    b"<SEC-HEADER>0000065984-14-000065.txt : 20140227\n"
    b"STANDARD INDUSTRIAL CLASSIFICATION: ELECTRIC SERVICES [4911]\n"
    b"</SEC-HEADER>\n"
)


class Detonated(AssertionError):
    """Raised when the implementation pulls past the governed stopping point."""


class ExplodingStream(httpx.SyncByteStream):
    """Yields ``head`` in chunks, then detonates if asked for more.

    Must be a real ``SyncByteStream``: httpx materialises a plain iterable at Response
    construction time, which would detonate before the transport ran.
    """

    def __init__(self, head: bytes, chunk: int = 4096, *, detonate: bool = True) -> None:
        self._head = head
        self._chunk = chunk
        # detonate=False models a legitimately SHORT entity that simply ends. Consuming
        # all of it is correct there, so exhaustion must not be treated as a failure.
        self._detonate = detonate
        self.chunks_requested = 0
        self.bytes_yielded = 0

    def __iter__(self):
        offset = 0
        while offset < len(self._head):
            piece = self._head[offset : offset + self._chunk]
            offset += len(piece)
            self.chunks_requested += 1
            self.bytes_yielded += len(piece)
            yield piece
        if self._detonate:
            # Anything beyond the head is the 422 MB remainder Defect F used to drain.
            self.chunks_requested += 1
            raise Detonated(
                "implementation pulled past the ceiling - the remainder was consumed"
            )

    def close(self) -> None:  # httpx calls this on Response.close()
        return None


class _StubTransport(httpx.BaseTransport):
    def __init__(self, status: int, headers: dict[str, str], stream) -> None:
        self._status = status
        self._headers = headers
        self._stream = stream

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            self._status, headers=self._headers, stream=self._stream
        )


def _get(transport: RecordingTransport, url: str, headers: dict[str, str] | None = None):
    request = httpx.Request("GET", url, headers=headers or {})
    return transport.handle_request(request)


# ---------------------------------------------------------------- the decisive test


def test_ignored_range_200_does_not_drain_the_remainder() -> None:
    """THE Defect-F test: a 200 to a ranged request must not pull the whole entity."""
    head = HEADER + b"X" * 20_000
    stream = ExplodingStream(head)
    inner = _StubTransport(
        200,
        # The server claims an enormous entity, exactly as EDGAR did for the canary
        # accession. Content-Length is metadata, NOT permission to consume.
        {"content-length": "422424674"},
        stream,
    )
    transport = RecordingTransport(inner)

    # Would raise Detonated under the pre-repair implementation.
    _get(transport, "https://example.test/big.txt", {"Range": "bytes=0-4095"})

    cap = transport.last
    assert cap is not None
    assert cap.range_class == policy.RANGE_CLASS_200_IGNORED
    assert cap.range_honored is False
    assert cap.response_content_length == 422_424_674
    # Bounded by the REQUESTED window, not by the entity size.
    assert cap.wire_bytes_consumed <= 4096 + 4096, cap.wire_bytes_consumed
    assert cap.wire_bytes_consumed < 422_424_674
    assert cap.wire_truncated_at_ceiling is True


def test_wire_consumed_sha256_binds_exactly_the_pulled_bytes() -> None:
    """Digest covers what was consumed - no second full read to compute it."""
    head = HEADER + b"Y" * 20_000
    stream = ExplodingStream(head)
    transport = RecordingTransport(_StubTransport(200, {}, stream))
    _get(transport, "https://example.test/big.txt", {"Range": "bytes=0-4095"})

    cap = transport.last
    assert cap is not None
    expected = hashlib.sha256(head[: cap.wire_bytes_consumed]).hexdigest()
    assert cap.wire_consumed_sha256 == expected
    assert len(cap.wire) == cap.wire_bytes_consumed


def test_stream_is_not_drained_after_the_stopping_condition() -> None:
    """Early close: no chunk is requested once the ceiling is reached."""
    head = HEADER + b"Z" * 100_000
    stream = ExplodingStream(head, chunk=4096)
    transport = RecordingTransport(_StubTransport(200, {}, stream))
    _get(transport, "https://example.test/big.txt", {"Range": "bytes=0-4095"})

    # One chunk crosses the ceiling and we stop: strictly fewer chunks than the head
    # would need, and far fewer than the full entity.
    assert stream.chunks_requested <= 2
    assert stream.bytes_yielded <= 8192


# ---------------------------------------------------------------- classification


def test_valid_206_is_accepted_and_marked_honored() -> None:
    body = HEADER
    transport = RecordingTransport(
        _StubTransport(
            206,
            {"content-range": f"bytes 0-{len(body) - 1}/999999"},
            ExplodingStream(body, detonate=False),
        )
    )
    _get(transport, "https://example.test/f.txt", {"Range": "bytes=0-4095"})
    cap = transport.last
    assert cap is not None
    assert cap.range_class == policy.RANGE_CLASS_206_VALIDATED
    assert cap.range_honored is True


def test_206_without_content_range_is_REFUSED() -> None:
    transport = RecordingTransport(_StubTransport(206, {}, ExplodingStream(HEADER)))
    with pytest.raises(RangeContractViolation):
        _get(transport, "https://example.test/f.txt", {"Range": "bytes=0-4095"})


def test_206_with_inconsistent_content_range_is_REFUSED() -> None:
    """A window we did not ask for must never be accepted as if we had."""
    transport = RecordingTransport(
        _StubTransport(
            206, {"content-range": "bytes 8192-12287/999999"}, ExplodingStream(HEADER)
        )
    )
    with pytest.raises(RangeContractViolation):
        _get(transport, "https://example.test/f.txt", {"Range": "bytes=0-4095"})


def test_no_silent_third_state() -> None:
    """Every ranged outcome is a named class or a refusal - never an unlabelled pass."""
    named = {policy.RANGE_CLASS_206_VALIDATED, policy.RANGE_CLASS_200_IGNORED}
    for status, content_range in ((206, "bytes 0-4095/99"), (200, None)):
        cls, _honored, refusal = _classify_range("bytes=0-4095", status, content_range)
        assert refusal is None
        assert cls in named
    # Unclassifiable shapes produce a refusal reason rather than a success class.
    _cls, _h, refusal = _classify_range("bytes=0-4095", 206, None)
    assert refusal is not None


# ---------------------------------------------------------------- ceiling arithmetic


def test_stop_threshold_is_the_window_capped_by_the_guard_band() -> None:
    """The helper returns a STOP POINT, deliberately below the hard ceiling.

    Stopping AT the ceiling would let a maximal final chunk carry actual
    consumption above it - the P0 this guard band exists to close.
    """
    assert _consumption_stop_threshold("bytes=0-4095") == 4096
    assert _consumption_stop_threshold("bytes=0-16383") == 16384
    # Large or unranged requests stop a full chunk short of the hard ceiling.
    assert (
        _consumption_stop_threshold("bytes=0-99999999")
        == policy.CONSUMPTION_STOP_THRESHOLD_BYTES
    )
    assert _consumption_stop_threshold(None) == policy.CONSUMPTION_STOP_THRESHOLD_BYTES
    # The guard band is exactly one maximal upstream chunk wide.
    assert (
        policy.RESPONSE_CONSUMPTION_CEILING_BYTES
        - policy.CONSUMPTION_STOP_THRESHOLD_BYTES
        == policy.MAX_UPSTREAM_CHUNK_BYTES
    )


def test_unranged_request_is_classified_and_not_range_honored() -> None:
    transport = RecordingTransport(
        _StubTransport(200, {}, ExplodingStream(HEADER, detonate=False))
    )
    _get(transport, "https://example.test/index-headers.html")
    cap = transport.last
    assert cap is not None
    assert cap.range_class == policy.RANGE_CLASS_UNRANGED
    assert cap.range_honored is False


# ------------------------------------------------- HARD BOUND under adversarial chunks


class AdversarialChunkStream(httpx.SyncByteStream):
    """Creeps to just under the stop threshold, then offers one enormous chunk.

    Models the case the guard band exists for: consumption sits one byte below the
    stop threshold and one more maximal read still follows. A "stop asking after
    the ceiling" implementation would let that read carry consumption above the
    governed ceiling.
    """

    def __init__(self, approach: int, giant: int) -> None:
        self._approach = approach
        self._giant = giant
        self.bytes_yielded = 0
        self.giant_was_pulled = False

    def __iter__(self):
        remaining = self._approach
        while remaining > 0:
            piece = b"A" * min(policy.MAX_UPSTREAM_CHUNK_BYTES, remaining)
            remaining -= len(piece)
            self.bytes_yielded += len(piece)
            yield piece
        self.giant_was_pulled = True
        self.bytes_yielded += self._giant
        yield b"B" * self._giant

    def close(self) -> None:
        return None


def test_max_upstream_chunk_matches_the_pinned_transport() -> None:
    """M is PROVED from the pinned implementation, never assumed.

    If httpcore changes its read size, this fails loudly rather than silently
    widening the overshoot the guard band is sized against.
    """
    from httpcore._sync.http11 import HTTP11Connection

    assert HTTP11Connection.READ_NUM_BYTES == policy.MAX_UPSTREAM_CHUNK_BYTES


def test_hard_ceiling_holds_under_an_adversarial_final_chunk() -> None:
    """THE hard-bound test: actual consumption never exceeds the governed ceiling."""
    hard = policy.RESPONSE_CONSUMPTION_CEILING_BYTES
    # Creep to one byte below the stop threshold, then offer the largest chunk the
    # PROVED upstream contract permits. This is the true worst case: the guard band
    # must absorb it without the hard ceiling being exceeded.
    stream = AdversarialChunkStream(
        approach=policy.CONSUMPTION_STOP_THRESHOLD_BYTES - 1,
        giant=policy.MAX_UPSTREAM_CHUNK_BYTES,
    )
    transport = RecordingTransport(
        _StubTransport(200, {"content-length": "422424674"}, stream)
    )
    _get(transport, "https://example.test/huge.txt", {"Range": "bytes=0-99999999"})

    cap = transport.last
    assert cap is not None
    # The binding assertion.
    assert cap.wire_bytes_consumed <= hard, cap.wire_bytes_consumed
    # Worst case is absorbed by the guard band rather than refused.
    assert stream.giant_was_pulled is True, "the worst-case chunk must be exercised"
    assert stream.bytes_yielded <= hard
    assert cap.wire_bytes_consumed == policy.CONSUMPTION_STOP_THRESHOLD_BYTES - 1 + (
        policy.MAX_UPSTREAM_CHUNK_BYTES
    )
    # Evidence still binds exactly what was pulled.
    assert len(cap.wire) == cap.wire_bytes_consumed
    assert cap.wire_consumed_sha256 == hashlib.sha256(cap.wire).hexdigest()


def test_hard_ceiling_is_enforced_even_if_the_guard_band_is_wrong() -> None:
    """Fail-closed backstop: an oversized first chunk is refused, not accepted."""

    class OneGiantChunk(httpx.SyncByteStream):
        def __iter__(self):
            yield b"C" * (policy.RESPONSE_CONSUMPTION_CEILING_BYTES * 4)

        def close(self) -> None:
            return None

    transport = RecordingTransport(_StubTransport(200, {}, OneGiantChunk()))
    with pytest.raises(ConsumptionCeilingExceeded):
        _get(transport, "https://example.test/huge.txt", {"Range": "bytes=0-4095"})


# ------------------------------------------- GATE 5: pre-artifact storage reserve guard


def test_preartifact_invariant_arithmetic() -> None:
    """The frozen invariant, stated once and asserted."""
    assert policy.TERMINAL_RESERVE_BYTES == 2 * 1024 * 1024 * 1024
    assert policy.MAX_NEXT_ARTIFACT_FOOTPRINT == (
        policy.RESPONSE_CONSUMPTION_CEILING_BYTES + policy.MAX_UPSTREAM_CHUNK_BYTES
    )
    assert policy.PREARTIFACT_FREE_REQUIRED_BYTES == (
        policy.TERMINAL_RESERVE_BYTES
        + policy.MAX_NEXT_ARTIFACT_FOOTPRINT
        + policy.METADATA_ALLOWANCE_BYTES
    )
    # The reserve must dominate: normal acquisition can never nibble it away.
    assert policy.TERMINAL_RESERVE_BYTES > 1000 * policy.MAX_NEXT_ARTIFACT_FOOTPRINT


def test_guard_is_NOT_an_Exception_so_the_spine_cannot_swallow_it() -> None:
    """Same reasoning as CrawlHalt.

    The MR-002 spine wraps each filing in ``except Exception`` to stay fail-soft. A guard
    derived from Exception would be swallowed and acquisition would continue straight
    into the evidence reserve.
    """
    from app.altdata.sec001_v3.fetch import TerminalStorageReserve

    assert issubclass(TerminalStorageReserve, BaseException)
    assert not issubclass(TerminalStorageReserve, Exception)


def test_guard_trips_on_the_GOVERNED_RULE_not_on_filesystem_pressure(
    tmp_path, monkeypatch
) -> None:
    """Refuses the next artifact while the filesystem still has ample ordinary space.

    This is the point of the reserve: the stop is caused by the governed rule, not by
    the disk actually filling up. ENOSPC must never again be the control mechanism.
    """
    import shutil as _shutil

    from app.altdata.sec001_v3 import fetch as fetch_mod
    from app.altdata.sec001_v3.fetch import TerminalStorageReserve

    # Ample real space, but below the governed requirement.
    ample_but_insufficient = policy.PREARTIFACT_FREE_REQUIRED_BYTES - 1
    monkeypatch.setattr(
        fetch_mod.shutil,
        "disk_usage",
        lambda p: _shutil._ntuple_diskusage(  # type: ignore[attr-defined]
            10**15, 10**15 - ample_but_insufficient, ample_but_insufficient
        ),
    )

    class _F:
        _decision_dir = tmp_path

    with pytest.raises(TerminalStorageReserve) as ei:
        fetch_mod.PolicyFetcher._require_storage_headroom(_F())  # type: ignore[arg-type]

    # Still ~2 GiB of genuinely free space at the moment of refusal.
    assert ei.value.free >= policy.TERMINAL_RESERVE_BYTES
    assert ei.value.required == policy.PREARTIFACT_FREE_REQUIRED_BYTES


def test_guard_allows_acquisition_with_one_byte_of_headroom(tmp_path, monkeypatch) -> None:
    import shutil as _shutil

    from app.altdata.sec001_v3 import fetch as fetch_mod

    ok = policy.PREARTIFACT_FREE_REQUIRED_BYTES
    monkeypatch.setattr(
        fetch_mod.shutil,
        "disk_usage",
        lambda p: _shutil._ntuple_diskusage(10**15, 10**15 - ok, ok),  # type: ignore[attr-defined]
    )

    class _F:
        _decision_dir = tmp_path

    fetch_mod.PolicyFetcher._require_storage_headroom(_F())  # type: ignore[arg-type]


def test_guard_measures_nearest_existing_ancestor(tmp_path, monkeypatch) -> None:
    """A capacity CHECK must not create directories as a side effect."""
    import shutil as _shutil

    from app.altdata.sec001_v3 import fetch as fetch_mod

    missing = tmp_path / "not" / "yet" / "created"
    seen: list = []

    def _probe(p):
        seen.append(p)
        return _shutil._ntuple_diskusage(10**15, 0, 10**15)  # type: ignore[attr-defined]

    monkeypatch.setattr(fetch_mod.shutil, "disk_usage", _probe)

    class _F:
        _decision_dir = missing

    fetch_mod.PolicyFetcher._require_storage_headroom(_F())  # type: ignore[arg-type]
    assert seen and seen[0].exists()
    assert not missing.exists(), "the check must not create the directory"
