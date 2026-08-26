"""Bounded, accounted, fail-closed transport for the WP0A-Q cover-page tranche.

Carries forward the Defect-E/F controls the V3 crawl paid for, with the request-cap
accounting WP0A-Q adds on top.

**Bounded streaming, never materialise-then-slice.** A ranged request is issued, but a
server that ignores ``Range`` and answers ``200`` with the whole document is the normal
case, not an error — so the response is *streamed* and consumption stops at the frozen
threshold. ``httpx``'s ``.content`` / ``.read()`` are never called: there is no point at
which the whole document exists in memory and is then trimmed. Reaching the threshold
without the required fields is ``EVIDENCE_UNAVAILABLE``, never a partial PASS.

**403 latches globally.** ``CrawlHalt`` derives from ``BaseException`` for the same reason
``KeyboardInterrupt`` does: the surrounding code is fail-soft by design and an
``except Exception`` would swallow the halt and issue another request to a host that has
just blocked us. The latch is also sticky on the fetcher, so even ``except BaseException``
somewhere cannot produce a second request.

**Ranged requests force ``Accept-Encoding: identity``.** With a content-encoding applied,
range offsets refer to the *compressed* representation, which is what fed gzip fragments to
the V3 parser across three canaries. A parser-facing body beginning with the gzip magic is
an acquisition failure, never historical absence.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import httpx

GZIP_MAGIC: Final = bytes((0x1F, 0x8B))
IDENTITY_ENCODINGS: Final[frozenset[str | None]] = frozenset({None, "", "identity"})


class CrawlHalt(BaseException):
    """SEC returned a halt status. Acquisition stops; a human resumes it."""


class BudgetExceeded(RuntimeError):
    """A frozen manifest request cap would be exceeded."""


class AcquisitionEncodingError(RuntimeError):
    """An encoded representation reached, or would have reached, the parser (Defect E)."""


class CreateOnceViolation(RuntimeError):
    """An artifact identity already exists. Evidence is never overwritten."""


@dataclass
class RequestLedger:
    """Exact request accounting against the sealed caps."""

    max_index_requests: int
    max_document_requests: int
    max_total_retries: int
    index_requests: int = 0
    document_requests: int = 0
    retries: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def charge_document(self) -> None:
        if self.document_requests >= self.max_document_requests:
            raise BudgetExceeded(f"max_document_requests={self.max_document_requests} reached")
        self.document_requests += 1

    def charge_index(self) -> None:
        if self.index_requests >= self.max_index_requests:
            raise BudgetExceeded(f"max_index_requests={self.max_index_requests} reached")
        self.index_requests += 1

    def charge_retry(self) -> None:
        if self.retries >= self.max_total_retries:
            raise BudgetExceeded(f"max_total_retries={self.max_total_retries} reached")
        self.retries += 1


@dataclass
class FetchOutcome:
    status: str
    body: bytes = b""
    truncated: bool = False
    bytes_consumed: int = 0
    http_status: int | None = None
    attempts: int = 0
    eof_reached: bool = False
    """The document END was actually reached within the bounds.

    The parser's completeness gate reads this and nothing else. It is set only by evidence
    from the response itself -- a ``Content-Range`` whose end is the last byte of the stated
    total, or a body that ended before the requested window was filled -- never inferred
    from how much was read or from what the bytes contained.
    """
    total_bytes: int | None = None
    continuations: int = 0


FETCH_OK: Final = "OK"
FETCH_UNAVAILABLE: Final = "EVIDENCE_UNAVAILABLE"


class BoundedFetcher:
    """GET-only, throttled, bounded document fetcher with a sticky halt latch."""

    def __init__(
        self,
        ledger: RequestLedger,
        *,
        user_agent: str,
        ceiling_bytes: int,
        stop_threshold_bytes: int,
        rate_limit_per_sec: float = 5.0,
        retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
        halt_statuses: tuple[int, ...] = (403,),
        retry_max_attempts: int = 5,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.ledger = ledger
        self.ceiling = ceiling_bytes
        self.stop_threshold = stop_threshold_bytes
        self.retry_statuses = set(retry_statuses)
        self.halt_statuses = set(halt_statuses)
        self.retry_max_attempts = retry_max_attempts
        self._halted = False
        self._interval = 1.0 / max(0.1, rate_limit_per_sec)
        self._last = 0.0
        self._sleep = sleep
        self._rng = random.Random("SEC001_V3_1_WP0AQ_COVER")
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=True,
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
    def _content_range(value: str | None) -> tuple[int | None, int | None]:
        """Parse ``Content-Range: bytes S-E/T`` into (end, total). ``None`` when unstated."""
        if not value:
            return None, None
        m = re.search(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value)
        if not m:
            return None, None
        total = int(m.group(3)) if m.group(3) != "*" else None
        return int(m.group(2)), total

    def get_document(
        self, url: str, *, window_bytes: int | None = None, start: int = 0
    ) -> FetchOutcome:
        """Fetch one bounded document window. GET only.

        ``eof_reached`` is set only from response evidence: a ``Content-Range`` whose end is
        the last byte of the stated total, or a body that ended before the requested window
        was filled. It is never inferred from how much was read or from the content.
        """
        if self._halted:
            raise CrawlHalt("fetcher is latched after a halt status; no further requests")

        limit = min(window_bytes or self.stop_threshold, self.stop_threshold)
        headers = {
            "Range": f"bytes={start}-{start + limit - 1}",
            "Accept-Encoding": "identity",
        }

        for attempt in range(1, self.retry_max_attempts + 1):
            self._throttle()
            self.ledger.charge_document()
            with self._client.stream("GET", url, headers=headers) as r:
                status = r.status_code
                if status in self.halt_statuses:
                    self._halted = True
                    self.ledger.events.append({"url": url, "status": status, "outcome": "HALT"})
                    raise CrawlHalt(f"EDGAR returned {status} for {url}")

                if status in self.retry_statuses:
                    self.ledger.events.append({"url": url, "status": status, "outcome": "RETRY"})
                    if attempt == self.retry_max_attempts:
                        return FetchOutcome(FETCH_UNAVAILABLE, http_status=status, attempts=attempt)
                    self.ledger.charge_retry()
                    delay = min(60.0, 2.0 ** (attempt - 1))
                    self._sleep(delay * (1.0 + self._rng.uniform(-0.25, 0.25)))
                    continue

                if status not in (200, 206):
                    self.ledger.events.append(
                        {"url": url, "status": status, "outcome": "FAIL_CLOSED_STATUS"}
                    )
                    return FetchOutcome(FETCH_UNAVAILABLE, http_status=status, attempts=attempt)

                enc = (r.headers.get("content-encoding") or "").strip().lower() or None
                if enc not in IDENTITY_ENCODINGS:
                    raise AcquisitionEncodingError(
                        f"ranged request answered with content-encoding {enc!r}; range offsets "
                        "would refer to the compressed representation (Defect E)"
                    )

                # A 200 here means the server ignored Range and is sending the whole document.
                # Stream it; never read it whole and slice. Consumption stops at the bound.
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
                    if len(buf) > self.ceiling:  # defence in depth; unreachable via `take`
                        truncated = True
                        break

                assert len(buf) <= self.ceiling, "hard byte ceiling breached"

                end, total = self._content_range(r.headers.get("content-range"))
                if total is not None and end is not None:
                    eof = end + 1 >= total
                else:
                    # No stated total: the only positive evidence of EOF is that the body
                    # ended before the requested window was filled.
                    eof = not truncated
                    total = start + len(buf) if eof else None

                self.ledger.events.append(
                    {
                        "url": url,
                        "status": status,
                        "outcome": "OK",
                        "start": start,
                        "bytes": len(buf),
                        "range_honoured": status == 206,
                        "truncated": truncated,
                        "eof_reached": eof,
                    }
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
                )
        return FetchOutcome(FETCH_UNAVAILABLE, attempts=self.retry_max_attempts)

    def get_document_complete(
        self, url: str, *, max_continuations: int = 0, max_cumulative_bytes: int | None = None
    ) -> FetchOutcome:
        """Read successive bounded windows until EOF, or fail closed.

        ⚠ **Continuation is opt-in and off by default.** ``max_continuations=0`` reproduces
        the single-window behaviour the frozen controls describe. Every continuation is a
        further **document request** against the sealed 1,200 cap, so how many windows a
        filing may consume is a scope decision for the owner, not a default this module
        picks. ``max_cumulative_bytes`` likewise defaults to one window.

        Reaching the frozen bounds without EOF is ``EVIDENCE_UNAVAILABLE`` — never a partial
        pass, and never rescued by however many class tuples the prefix happened to contain.
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


class CreateOnceStore:
    """Immutable artifact store keyed by CIK / accession / source_variant / observation id."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._keys: set[str] = set()

    @staticmethod
    def identity(cik: int, accession: str, source_variant: str, observation_id: str) -> str:
        return f"{cik:010d}/{accession}/{source_variant}/{observation_id}"

    def path_for(self, ident: str) -> Path:
        return self.root / (hashlib.sha256(ident.encode()).hexdigest()[:32] + ".json")

    def put(self, ident: str, record: dict[str, Any]) -> Path:
        p = self.path_for(ident)
        if ident in self._keys or p.exists():
            raise CreateOnceViolation(f"artifact identity already exists: {ident}")
        payload = dict(record)
        payload["_artifact_identity"] = ident
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._keys.add(ident)
        return p
