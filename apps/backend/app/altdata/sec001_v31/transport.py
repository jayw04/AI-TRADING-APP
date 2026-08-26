"""Bounded, accounted, origin-locked, fail-closed transport for the WP0A-Q tranche.

Carries forward the Defect-E/F controls the V3 crawl paid for, plus the request-integrity
controls the harness review found missing.

**Origin is enforced, redirects are not automatic.** The fetcher previously accepted an
arbitrary URL and ran an ``httpx.Client`` with ``follow_redirects=True``. That broke two
frozen controls at once: the authorized-domain scope, and exact request accounting — one
``charge_document()`` could become several real HTTP requests. Now every URL is checked
against the manifest's origins before the request, redirects are **off**, and a 3xx is
refused unless redirect following has been explicitly enabled, in which case each hop is
origin-validated and separately charged.

**Range responses are validated, not trusted.** Parsing only ``(end, total)`` was not
enough. A 206 must return the *start* that was asked for, and its body length must agree
with its own ``Content-Range``. Crucially, when a continuation asks for ``start > 0`` and
the server ignores ``Range`` and replies ``200``, the body is the document *prefix* again —
appending it as the next window would assemble a corrupt document. That fails closed.

**Bounded streaming, never materialise-then-slice.** ``.content`` / ``.read()`` are never
called: there is no point at which the whole document exists in memory and is then trimmed.

**403 latches globally.** ``CrawlHalt`` derives from ``BaseException`` for the same reason
``KeyboardInterrupt`` does: the surrounding code is fail-soft and an ``except Exception``
would swallow the halt and issue another request to a host that has just blocked us.

**Accounting survives process restart.** ``DurableLedger`` persists counts, the
acquired-key set and actual-send timestamps, seeded from the step-1 custody record so a
restart cannot silently turn 28/200 index requests back into 0/200. Per-accession lifecycle
and evidence publication live in ``custody`` -- counters alone cannot describe the states
between "request sent" and "evidence sealed", which is where exactly-once actually breaks.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

from app.altdata.sec001_v31.authority import (
    STEP1_DOCUMENT_REQUESTS_SPENT,
    STEP1_INDEX_REQUESTS_SPENT,
    AcquisitionAuthority,
    NotAuthorized,
)
from app.altdata.sec001_v31.custody import atomic_write_json

GZIP_MAGIC: Final = bytes((0x1F, 0x8B))
IDENTITY_ENCODINGS: Final[frozenset[str | None]] = frozenset({None, "", "identity"})
REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})


class CrawlHalt(BaseException):
    """SEC returned a halt status. Acquisition stops; a human resumes it."""


class BudgetExceeded(RuntimeError):
    """A frozen manifest request cap would be exceeded."""


class AcquisitionEncodingError(RuntimeError):
    """An encoded representation reached, or would have reached, the parser (Defect E)."""


#: What a response actually turned out to be. Recorded before it is adjudicated.
RANGE_HONORED_206: Final = "RANGE_HONORED_206"
RANGE_IGNORED_200_START0: Final = "RANGE_IGNORED_200_START0"
INVALID_200_CONTINUATION: Final = "INVALID_200_CONTINUATION"


class RangeIntegrityError(RuntimeError):
    """A ranged response cannot be trusted to be the window that was requested."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class DurableLedger:
    """Request accounting and CIK-once state that survives a process restart.

    Seeded from step-1 custody: the envelope derivation already spent 28 index requests, and
    a fresh process must not reset that. Every state change is flushed atomically, so an
    interrupted run resumes with the requests it actually made already counted.
    """

    path: Path
    max_index_requests: int
    max_document_requests: int
    max_total_retries: int
    index_requests: int = STEP1_INDEX_REQUESTS_SPENT
    document_requests: int = STEP1_DOCUMENT_REQUESTS_SPENT
    retries: int = 0
    acquired: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(cls, path: Path, authority: AcquisitionAuthority) -> DurableLedger:
        led = cls(
            path=path,
            max_index_requests=authority.max_index_requests,
            max_document_requests=authority.max_document_requests,
            max_total_retries=authority.max_total_retries,
        )
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
            led.index_requests = int(state["index_requests"])
            led.document_requests = int(state["document_requests"])
            led.retries = int(state["retries"])
            led.acquired = set(state.get("acquired", []))
            led.events = list(state.get("events", []))
        else:
            led._flush()
        return led

    def _flush(self) -> None:
        """Durable, via the same primitive the accession journal uses.

        Review finding: this previously wrote a temp file and ``os.replace``d it with no
        ``fsync`` of either the file or its directory. ``charge_document`` is supposed to
        account for a request *before* it goes on the wire, and an accounting record that
        can be lost by the same host failure the request survives does not do that -- the
        journal would show REQUEST_INTENT while the ledger forgot the spend.
        """
        atomic_write_json(
            self.path,
            {
                "index_requests": self.index_requests,
                "document_requests": self.document_requests,
                "retries": self.retries,
                "acquired": sorted(self.acquired),
                "events": self.events,
                "updated_utc": _utc_now(),
            },
        )

    # ---- accounting -----------------------------------------------------------------
    def charge_document(self, url: str) -> None:
        if self.document_requests >= self.max_document_requests:
            raise BudgetExceeded(f"max_document_requests={self.max_document_requests} reached")
        self.document_requests += 1
        self.events.append(
            {"kind": "document", "url": url, "sent_utc": _utc_now(), "n": self.document_requests}
        )
        self._flush()

    def charge_index(self, url: str = "") -> None:
        if self.index_requests >= self.max_index_requests:
            raise BudgetExceeded(f"max_index_requests={self.max_index_requests} reached")
        self.index_requests += 1
        self.events.append(
            {"kind": "index", "url": url, "sent_utc": _utc_now(), "n": self.index_requests}
        )
        self._flush()

    def record_response(self, **facts: Any) -> None:
        """Durably record what a response WAS, before anything adjudicates it.

        Attempt #1 lost window 1's HTTP status because the ledger recorded only that a
        request had been sent. The ordering here is deliberate and is the point of the
        method: response fact recorded -> validation -> state transition. A validation that
        raises can no longer erase the evidence of what it raised about.
        """
        self.events.append({"kind": "response", "at": _utc_now(), **facts})
        self._flush()

    def charge_retry(self) -> None:
        if self.retries >= self.max_total_retries:
            raise BudgetExceeded(f"max_total_retries={self.max_total_retries} reached")
        self.retries += 1
        self._flush()

    # ---- CIK-once -------------------------------------------------------------------
    @staticmethod
    def acquisition_key(cik: int, form: str, accession: str) -> str:
        return f"{cik:010d}|{form}|{accession}"

    def already_acquired(self, cik: int, form: str, accession: str) -> bool:
        return self.acquisition_key(cik, form, accession) in self.acquired

    def mark_acquired(self, cik: int, form: str, accession: str) -> None:
        self.acquired.add(self.acquisition_key(cik, form, accession))
        self._flush()


@dataclass
class FetchOutcome:
    status: str
    body: bytes = b""
    truncated: bool = False
    bytes_consumed: int = 0
    http_status: int | None = None
    attempts: int = 0
    eof_reached: bool = False
    total_bytes: int | None = None
    continuations: int = 0
    reason: str | None = None
    content_type: str | None = None
    disposition: str | None = None
    content_length: int | None = None
    retained_sha256: str | None = None
    """The declared ``Content-Type``, retained prospectively.

    Added after the locator-discovery record could not state one: the outcome simply did not
    carry it, so an evidence contract that required it had nothing honest to write. Recording
    it here means later index and document responses can satisfy that contract at the time of
    the request, which is the only time it is knowable without making another one.
    """


FETCH_OK: Final = "OK"
FETCH_UNAVAILABLE: Final = "EVIDENCE_UNAVAILABLE"


class BoundedFetcher:
    """GET-only, origin-locked, bounded document fetcher with a sticky halt latch."""

    def __init__(
        self,
        authority: AcquisitionAuthority,
        ledger: DurableLedger,
        *,
        user_agent: str,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
        max_redirects: int = 0,
    ) -> None:
        self.authority = authority
        self.ledger = ledger
        self.ceiling = authority.ceiling_bytes
        self.stop_threshold = authority.stop_threshold_bytes
        self.retry_statuses = set(authority.retry_statuses)
        self.halt_statuses = set(authority.halt_statuses)
        self.retry_max_attempts = authority.retry_max_attempts
        self.max_redirects = max_redirects
        self._halted = False
        self._interval = 1.0 / max(0.1, authority.rate_limit_per_sec)
        self._last = 0.0
        self._sleep = sleep
        self._rng = random.Random("SEC001_V3_1_WP0AQ_COVER")
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=False,  # every hop is validated and charged explicitly
        )

    @property
    def halted(self) -> bool:
        return self._halted

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self._interval:
            self._sleep(self._interval - gap)
        self._last = time.monotonic()

    @staticmethod
    def _content_range(value: str | None) -> tuple[int | None, int | None, int | None]:
        """Parse ``Content-Range: bytes S-E/T`` into (start, end, total)."""
        if not value:
            return None, None, None
        m = re.search(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value)
        if not m:
            return None, None, None
        total = int(m.group(3)) if m.group(3) != "*" else None
        return int(m.group(1)), int(m.group(2)), total

    def get_document(
        self,
        url: str,
        *,
        window_bytes: int | None = None,
        start: int = 0,
        aggregate_ceiling: int | None = None,
        attempt_id: str = "-",
        window_number: int = 1,
    ) -> FetchOutcome:
        """One bounded document read, on one of two prospectively frozen paths.

        **Range honored (206).** The response is a window: at most ``window_bytes``, its
        ``Content-Range`` start must equal the requested start, and continuation may follow.

        **Range ignored (200 at start 0).** The server declined to partition the document, so
        this single response has to carry the whole body. It is bounded-streamed to the
        *aggregate* ceiling rather than truncated at one window -- the ceiling the size census
        already approved. Defect F is untouched: still incremental, still bounded, still no
        ``.content`` and no materialise-then-slice. A 50 MB body stops at the ceiling.

        **Range ignored at start > 0.** That body is the document's prefix again. Appending it
        would assemble a corrupt document. Fail closed, always.
        """
        if self._halted:
            raise CrawlHalt("fetcher is latched after a halt status; no further requests")
        self.authority.require_origin(url)

        window = min(window_bytes or self.stop_threshold, self.stop_threshold)
        ceiling = aggregate_ceiling or self.stop_threshold
        headers = {
            "Range": f"bytes={start}-{start + window - 1}",
            "Accept-Encoding": "identity",
        }
        target = url
        redirects = 0

        for attempt in range(1, self.retry_max_attempts + 1):
            self._throttle()
            self.ledger.charge_document(target)
            with self._client.stream("GET", target, headers=headers) as r:
                status = r.status_code
                cr_raw = r.headers.get("content-range")
                clen = r.headers.get("content-length")
                enc = (r.headers.get("content-encoding") or "").strip().lower() or None
                cr_start, cr_end, total = self._content_range(cr_raw)

                # ---- record the response BEFORE anything can adjudicate it ------------
                self.ledger.record_response(
                    attempt_id=attempt_id,
                    window_number=window_number,
                    url=target,
                    requested_start=start,
                    requested_end=start + window - 1,
                    http_status=status,
                    content_range_raw=cr_raw,
                    content_length=int(clen) if clen and clen.isdigit() else None,
                    content_type=r.headers.get("content-type"),
                    content_encoding=enc,
                    phase="headers",
                )

                if status in self.halt_statuses:
                    self._halted = True
                    raise CrawlHalt(f"EDGAR returned {status} for {target}")

                if status in REDIRECT_STATUSES:
                    location = r.headers.get("location", "")
                    if redirects >= self.max_redirects or not location:
                        return FetchOutcome(
                            FETCH_UNAVAILABLE,
                            http_status=status,
                            attempts=attempt,
                            reason="redirect_refused",
                        )
                    nxt = str(httpx.URL(target).join(location))
                    try:
                        self.authority.require_origin(nxt)
                    except NotAuthorized:
                        return FetchOutcome(
                            FETCH_UNAVAILABLE,
                            http_status=status,
                            attempts=attempt,
                            reason="redirect_off_origin",
                        )
                    redirects += 1
                    target = nxt
                    continue

                if status in self.retry_statuses:
                    if attempt == self.retry_max_attempts:
                        return FetchOutcome(FETCH_UNAVAILABLE, http_status=status, attempts=attempt)
                    self.ledger.charge_retry()
                    delay = min(60.0, 2.0 ** (attempt - 1))
                    self._sleep(delay * (1.0 + self._rng.uniform(-0.25, 0.25)))
                    continue

                if status not in (200, 206):
                    return FetchOutcome(
                        FETCH_UNAVAILABLE,
                        http_status=status,
                        attempts=attempt,
                        reason="unexpected_status",
                    )

                if enc not in IDENTITY_ENCODINGS:
                    raise AcquisitionEncodingError(
                        f"ranged request answered with content-encoding {enc!r}; range offsets "
                        "would refer to the compressed representation (Defect E)"
                    )

                # ---- which of the two frozen paths is this? --------------------------
                if status == 200 and start > 0:
                    self.ledger.record_response(
                        attempt_id=attempt_id,
                        window_number=window_number,
                        disposition=INVALID_200_CONTINUATION,
                        phase="disposition",
                    )
                    raise RangeIntegrityError(
                        f"continuation requested start={start} but the server ignored Range and "
                        "returned 200 from byte 0; the window cannot be appended"
                    )

                if status == 206:
                    disposition = RANGE_HONORED_206
                    cap = window
                    if cr_start is None:
                        raise RangeIntegrityError("206 response without a parsable Content-Range")
                    if cr_start != start:
                        raise RangeIntegrityError(
                            f"206 returned start={cr_start}, requested start={start}"
                        )
                else:
                    disposition = RANGE_IGNORED_200_START0
                    cap = ceiling
                    declared = int(clen) if clen and clen.isdigit() else None
                    if declared is not None and declared >= ceiling:
                        # Refuse BEFORE reading a body we already know cannot qualify.
                        self.ledger.record_response(
                            attempt_id=attempt_id,
                            window_number=window_number,
                            disposition=disposition,
                            content_length=declared,
                            phase="refused_content_length_at_or_above_ceiling",
                        )
                        return FetchOutcome(
                            FETCH_UNAVAILABLE,
                            http_status=status,
                            attempts=attempt,
                            reason="content_length_at_or_above_aggregate_ceiling",
                            disposition=disposition,
                            content_length=declared,
                        )

                # ---- bounded stream. No .content, no .read(), no slice-after-the-fact.
                buf = bytearray()
                truncated = False
                for chunk in r.iter_bytes(65536):
                    if not buf and chunk[:2] == GZIP_MAGIC:
                        raise AcquisitionEncodingError(
                            "parser-facing body begins with gzip magic (Defect E)"
                        )
                    take = cap - len(buf)
                    if len(chunk) >= take:
                        buf.extend(chunk[:take])
                        truncated = True
                        break
                    buf.extend(chunk)

                assert len(buf) <= cap
                digest = hashlib.sha256(buf).hexdigest()

                if total is not None and cr_end is not None:
                    eof = cr_end + 1 >= total
                else:
                    eof = not truncated
                    total = start + len(buf) if eof else None

                self.ledger.record_response(
                    attempt_id=attempt_id,
                    window_number=window_number,
                    disposition=disposition,
                    retained_bytes=len(buf),
                    retained_sha256=digest,
                    truncated=truncated,
                    eof_reached=eof,
                    phase="body",
                )

                if status == 206 and cr_end is not None and not truncated:
                    expected = cr_end - (cr_start or 0) + 1
                    if len(buf) != expected:
                        raise RangeIntegrityError(
                            f"206 body length {len(buf)} disagrees with its own Content-Range "
                            f"({cr_start}-{cr_end}), which declares {expected}"
                        )

                return FetchOutcome(
                    FETCH_OK,
                    body=bytes(buf),
                    truncated=truncated,
                    bytes_consumed=len(buf),
                    http_status=status,
                    attempts=attempt,
                    eof_reached=eof,
                    total_bytes=total,
                    content_type=r.headers.get("content-type"),
                    disposition=disposition,
                    content_length=int(clen) if clen and clen.isdigit() else None,
                    retained_sha256=digest,
                )
        return FetchOutcome(FETCH_UNAVAILABLE, attempts=self.retry_max_attempts)

    def get_index(self, url: str) -> FetchOutcome:
        """Fetch one SEC *index* document, charged against the index budget.

        Same origin lock, halt latch, retry policy and bounded streaming as a document
        fetch; only the budget differs. Locator resolution is an index operation and must
        not be paid for out of the 1,200 document requests.
        """
        if self._halted:
            raise CrawlHalt("fetcher is latched after a halt status; no further requests")
        self.authority.require_origin(url)

        for attempt in range(1, self.retry_max_attempts + 1):
            self._throttle()
            self.ledger.charge_index(url)
            with self._client.stream("GET", url) as r:
                status = r.status_code
                if status in self.halt_statuses:
                    self._halted = True
                    raise CrawlHalt(f"EDGAR returned {status} for {url}")
                if status in REDIRECT_STATUSES:
                    return FetchOutcome(
                        FETCH_UNAVAILABLE,
                        http_status=status,
                        attempts=attempt,
                        reason="redirect_refused",
                    )
                if status in self.retry_statuses:
                    if attempt == self.retry_max_attempts:
                        return FetchOutcome(FETCH_UNAVAILABLE, http_status=status, attempts=attempt)
                    self.ledger.charge_retry()
                    delay = min(60.0, 2.0 ** (attempt - 1))
                    self._sleep(delay * (1.0 + self._rng.uniform(-0.25, 0.25)))
                    continue
                if status != 200:
                    return FetchOutcome(
                        FETCH_UNAVAILABLE,
                        http_status=status,
                        attempts=attempt,
                        reason="unexpected_status",
                    )
                buf = bytearray()
                truncated = False
                for chunk in r.iter_bytes(65536):
                    take = self.stop_threshold - len(buf)
                    if len(chunk) >= take:
                        buf.extend(chunk[:take])
                        truncated = True
                        break
                    buf.extend(chunk)
                return FetchOutcome(
                    FETCH_OK,
                    body=bytes(buf),
                    truncated=truncated,
                    bytes_consumed=len(buf),
                    http_status=status,
                    attempts=attempt,
                    eof_reached=not truncated,
                    content_type=r.headers.get("content-type"),
                )
        return FetchOutcome(FETCH_UNAVAILABLE, attempts=self.retry_max_attempts)

    def get_document_complete(
        self,
        url: str,
        *,
        max_continuations: int = 0,
        max_cumulative_bytes: int | None = None,
        declared_size: int | None = None,
        attempt_id: str = "-",
    ) -> FetchOutcome:
        """Acquire one complete document on whichever frozen path the server chooses.

        If the first response is a Range-ignored 200 it already carries the whole body, so no
        continuation follows. If it is a 206, contiguous windows continue up to the frozen
        window count -- the ninth is refused before its request, not left to a byte budget.

        ``declared_size`` is the locator's authoritative size. On success the retained byte
        count must equal it exactly; a disagreement fails closed rather than being accepted.
        """
        ceiling = max_cumulative_bytes or (max_continuations + 1) * self.stop_threshold
        max_windows = max_continuations + 1
        body = bytearray()
        offset = 0
        windows = 0
        last: FetchOutcome | None = None

        while True:
            if windows >= max_windows:
                break
            window = min(self.stop_threshold, ceiling - len(body))
            if window <= 0:
                break

            out = self.get_document(
                url,
                window_bytes=window,
                start=offset,
                aggregate_ceiling=ceiling,
                attempt_id=attempt_id,
                window_number=windows + 1,
            )
            windows += 1
            last = out
            if out.status != FETCH_OK:
                return out

            if len(body) != offset:
                raise RangeIntegrityError(
                    f"assembly is not contiguous: {len(body)} bytes held but next offset is "
                    f"{offset}"
                )
            body.extend(out.body)
            offset += out.bytes_consumed

            if out.eof_reached:
                if out.total_bytes is not None and len(body) != out.total_bytes:
                    raise RangeIntegrityError(
                        f"assembled {len(body)} bytes but the server states the document is "
                        f"{out.total_bytes}"
                    )
                if declared_size is not None and len(body) != declared_size:
                    raise RangeIntegrityError(
                        f"assembled {len(body)} bytes but the locator declares {declared_size}"
                    )
                return FetchOutcome(
                    FETCH_OK,
                    body=bytes(body),
                    truncated=False,
                    bytes_consumed=len(body),
                    http_status=out.http_status,
                    attempts=out.attempts,
                    eof_reached=True,
                    total_bytes=out.total_bytes,
                    continuations=windows - 1,
                    content_type=out.content_type,
                    disposition=out.disposition,
                    content_length=out.content_length,
                    retained_sha256=hashlib.sha256(body).hexdigest(),
                )

            # A Range-ignored 200 carries the whole document or nothing; there is no window
            # two to ask for, so a truncated one is simply over the ceiling.
            if out.disposition == RANGE_IGNORED_200_START0 or out.bytes_consumed == 0:
                break

        return FetchOutcome(
            FETCH_OK,
            body=bytes(body),
            truncated=True,
            bytes_consumed=len(body),
            http_status=last.http_status if last else None,
            attempts=last.attempts if last else 0,
            eof_reached=False,
            total_bytes=last.total_bytes if last else None,
            continuations=max(0, windows - 1),
            content_type=last.content_type if last else None,
            disposition=last.disposition if last else None,
            retained_sha256=hashlib.sha256(body).hexdigest(),
        )
