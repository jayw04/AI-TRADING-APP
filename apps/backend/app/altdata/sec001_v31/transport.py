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

import json
import os
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

GZIP_MAGIC: Final = bytes((0x1F, 0x8B))
IDENTITY_ENCODINGS: Final[frozenset[str | None]] = frozenset({None, "", "identity"})
REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})


class CrawlHalt(BaseException):
    """SEC returned a halt status. Acquisition stops; a human resumes it."""


class BudgetExceeded(RuntimeError):
    """A frozen manifest request cap would be exceeded."""


class AcquisitionEncodingError(RuntimeError):
    """An encoded representation reached, or would have reached, the parser (Defect E)."""


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "index_requests": self.index_requests,
                    "document_requests": self.document_requests,
                    "retries": self.retries,
                    "acquired": sorted(self.acquired),
                    "events": self.events,
                    "updated_utc": _utc_now(),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

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
        self, url: str, *, window_bytes: int | None = None, start: int = 0
    ) -> FetchOutcome:
        """Fetch one bounded document window from a frozen SEC origin. GET only."""
        if self._halted:
            raise CrawlHalt("fetcher is latched after a halt status; no further requests")
        self.authority.require_origin(url)

        limit = min(window_bytes or self.stop_threshold, self.stop_threshold)
        headers = {"Range": f"bytes={start}-{start + limit - 1}", "Accept-Encoding": "identity"}
        target = url
        redirects = 0

        for attempt in range(1, self.retry_max_attempts + 1):
            self._throttle()
            self.ledger.charge_document(target)
            with self._client.stream("GET", target, headers=headers) as r:
                status = r.status_code
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

                enc = (r.headers.get("content-encoding") or "").strip().lower() or None
                if enc not in IDENTITY_ENCODINGS:
                    raise AcquisitionEncodingError(
                        f"ranged request answered with content-encoding {enc!r}; range offsets "
                        "would refer to the compressed representation (Defect E)"
                    )

                cr_start, cr_end, total = self._content_range(r.headers.get("content-range"))

                # A 200 means Range was ignored: the body is the document from byte 0. That
                # is fine for the first window and fatal for a continuation, which would
                # otherwise append a second copy of the prefix as though it were the tail.
                if status == 200 and start > 0:
                    raise RangeIntegrityError(
                        f"continuation requested start={start} but the server ignored Range and "
                        "returned 200 from byte 0; the window cannot be appended"
                    )
                if status == 206:
                    if cr_start is None:
                        raise RangeIntegrityError("206 response without a parsable Content-Range")
                    if cr_start != start:
                        raise RangeIntegrityError(
                            f"206 returned start={cr_start}, requested start={start}"
                        )

                buf = bytearray()
                truncated = False
                for chunk in r.iter_bytes(65536):
                    if not buf and chunk[:2] == GZIP_MAGIC:
                        raise AcquisitionEncodingError(
                            "parser-facing body begins with gzip magic (Defect E)"
                        )
                    take = limit - len(buf)
                    if len(chunk) >= take:
                        buf.extend(chunk[:take])
                        truncated = True
                        break
                    buf.extend(chunk)

                assert len(buf) <= self.ceiling, "hard byte ceiling breached"

                if status == 206 and cr_end is not None and not truncated:
                    expected = cr_end - (cr_start or 0) + 1
                    if len(buf) != expected:
                        raise RangeIntegrityError(
                            f"206 body length {len(buf)} disagrees with its own Content-Range "
                            f"({cr_start}-{cr_end}), which declares {expected}"
                        )

                if total is not None and cr_end is not None:
                    eof = cr_end + 1 >= total
                else:
                    eof = not truncated
                    total = start + len(buf) if eof else None

                return FetchOutcome(
                    FETCH_OK,
                    body=bytes(buf),
                    truncated=truncated,
                    bytes_consumed=len(buf),
                    http_status=status,
                    attempts=attempt,
                    eof_reached=eof,
                    total_bytes=total,
                )
        return FetchOutcome(FETCH_UNAVAILABLE, attempts=self.retry_max_attempts)

    def get_document_complete(
        self, url: str, *, max_continuations: int = 0, max_cumulative_bytes: int | None = None
    ) -> FetchOutcome:
        """Read successive bounded windows until EOF, or fail closed.

        ⚠ Continuation is opt-in and off by default; ``authority.LIVE_MAX_CONTINUATIONS`` is
        the only live-authorized setting. Every continuation is a further document request
        against the sealed cap, so a nonzero policy must be frozen prospectively rather than
        chosen after seeing which real filings exceed the first window.
        """
        budget = max_cumulative_bytes or self.stop_threshold
        body = bytearray()
        offset = 0
        used = 0
        last: FetchOutcome | None = None

        while True:
            window = min(self.stop_threshold, budget - len(body))
            if window <= 0:
                break
            out = self.get_document(url, window_bytes=window, start=offset)
            last = out
            if out.status != FETCH_OK:
                return out
            body.extend(out.body)
            offset += out.bytes_consumed
            if out.eof_reached:
                return FetchOutcome(
                    FETCH_OK,
                    body=bytes(body),
                    truncated=False,
                    bytes_consumed=len(body),
                    http_status=out.http_status,
                    attempts=out.attempts,
                    eof_reached=True,
                    total_bytes=out.total_bytes,
                    continuations=used,
                )
            if out.bytes_consumed == 0 or used >= max_continuations:
                break
            used += 1

        return FetchOutcome(
            FETCH_OK,
            body=bytes(body),
            truncated=True,
            bytes_consumed=len(body),
            http_status=last.http_status if last else None,
            attempts=last.attempts if last else 0,
            eof_reached=False,
            total_bytes=last.total_bytes if last else None,
            continuations=used,
        )
