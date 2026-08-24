"""The policy layer between the V3 crawl and the pinned EDGAR client.

``app/altdata/sec/client.py`` (blob ``6c1d7006…``) is read-only, throttled, GET-only and
deliberately has **no** retry or backoff. That absence is correct — a general-purpose
client that silently retries is a client that can hammer a source without its caller
knowing. Retry policy is a decision of the *crawl*, so it lives here.

Nothing in this module modifies the pinned client. It composes with two seams the client
already exposes: the ``transport=`` constructor argument (documented for offline tests,
used here to capture wire bytes for evidence) and the ``headers=`` keyword on ``get_text``
that Amendment B restored — the one whose absence in the host's older ``258c570d`` copy
would have turned every pre-2014 filing into a multi-megabyte download.

Two design points that are load-bearing rather than stylistic:

**``CrawlHalt`` derives from ``BaseException``.** The MR-002 spine catches broadly —
``fetch_header_text`` wraps its primary fetch in ``except Exception`` to fall back to a
ranged read, and ``collect_sic_observations`` wraps each filing in ``except Exception`` to
stay fail-soft. Both are right for their purpose, and both would swallow a 403 and issue
*another* request to a host that has just blocked us. A halt is not an error the spine is
entitled to handle, so it is raised as a ``BaseException`` for the same reason
``KeyboardInterrupt`` is. The halt also latches on the fetcher, so even a hypothetical
``except BaseException`` somewhere cannot produce a second request.

**Jitter is seeded.** Backoff randomness exists to avoid synchronising with other clients,
not to sample anything. Seeding it from the frozen crawl id makes a resumed crawl replay
its own schedule, which keeps the evidence log explainable.
"""

from __future__ import annotations

import gzip
import hashlib
import random
import re
import time
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.altdata.sec.client import EdgarClient
from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog, SourceEvidence, sha256_hex, utc_now_iso


class CrawlHalt(BaseException):
    """SEC returned a halt status (403). The crawl stops; a human resumes it.

    Deliberately *not* an ``Exception`` — see the module docstring.
    """

    def __init__(self, status: int, uri: str) -> None:
        super().__init__(
            f"EDGAR returned {status} for {uri} — crawl halted. State is preserved. "
            f"Cool down at least {policy.HALT_COOLDOWN_SECONDS}s and resume explicitly; "
            f"do not retry, do not change the User-Agent, do not raise the rate."
        )
        self.status = status
        self.uri = uri


class CrawlExhausted(RuntimeError):
    """A retryable status kept recurring until the attempt budget ran out."""


#: EDGAR accession numbers are ``NNNNNNNNNN-YY-NNNNNN`` and appear verbatim in both the
#: ``-index-headers.html`` URL and the full-submission ``.txt`` URL.
_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")


@dataclass
class _Capture:
    status: int
    url: str
    wire: bytes
    body: bytes
    content_encoding: str | None


def _decode(raw: bytes, encoding: str | None) -> bytes:
    """Undo the content-encoding the pinned client advertises (gzip, deflate).

    Done here with the stdlib rather than by handing the bytes back to httpx, so the
    evidence digests do not depend on httpx internals.
    """
    if not encoding:
        return raw
    enc = encoding.strip().lower()
    if enc == "gzip":
        return gzip.decompress(raw)
    if enc == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


class RecordingTransport(httpx.BaseTransport):
    """Wraps a real transport, capturing wire bytes and status for the evidence log.

    Also the enforcement point for GET-only: the pinned client is already GET-only, but the
    invariant is asserted where a request actually leaves the process, so it holds even if
    someone later reaches the transport by another path.
    """

    def __init__(self, inner: httpx.BaseTransport | None = None) -> None:
        self._inner = inner if inner is not None else httpx.HTTPTransport()
        self.last: _Capture | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method.upper() not in policy.ALLOWED_METHODS:
            raise RuntimeError(
                f"{request.method} is not permitted by the SEC-001 V3 crawl policy "
                f"(allowed: {sorted(policy.ALLOWED_METHODS)})"
            )
        response = self._inner.handle_request(request)
        # Iterate the stream rather than calling ``.read()``: ``read()`` would apply
        # httpx's content decoder, and these must be the bytes as they arrived.
        raw = b"".join(cast("Iterable[bytes]", response.stream))
        response.close()

        encoding = response.headers.get("content-encoding")
        try:
            body = _decode(raw, encoding)
        except (OSError, zlib.error, EOFError):
            body = raw  # malformed encoding: record what arrived, let the caller fail

        self.last = _Capture(
            status=response.status_code,
            url=str(request.url),
            wire=raw,
            body=body,
            content_encoding=encoding,
        )
        # Hand the caller a decoded, identity-encoded response so ``r.text`` is correct.
        headers = [
            (k, v)
            for k, v in response.headers.raw
            if k.lower() not in (b"content-encoding", b"content-length")
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=body,
            extensions=response.extensions,
        )


class PolicyFetcher:
    """Satisfies the spine's ``_Fetcher`` protocol, under V3 crawl policy.

    Passed straight into ``sic_history.collect_sic_observations`` as ``client``.
    """

    def __init__(
        self,
        *,
        evidence: EvidenceLog,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._recorder = RecordingTransport(transport)
        self._client = EdgarClient(
            user_agent=policy.USER_AGENT,
            rate_limit_per_sec=policy.RATE_LIMIT_PER_SEC,
            transport=self._recorder,
        )
        self._evidence = evidence
        self._sleep = sleep
        self._monotonic = monotonic
        self._rng = random.Random(hashlib.sha256(policy.JITTER_SEED.encode()).digest())
        self._halted: CrawlHalt | None = None
        #: provenance stamped onto evidence records; set by the driver per identity
        self.context: dict[str, Any] = {}
        #: accession -> form, harvested from submissions payloads as they pass through
        self._form_by_accession: dict[str, str] = {}
        self.requests_issued = 0
        self.retries = 0

    # -- lifecycle ---------------------------------------------------------------------

    def __enter__(self) -> PolicyFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def halted(self) -> CrawlHalt | None:
        return self._halted

    # -- backoff -----------------------------------------------------------------------

    def _backoff_delay(self, attempt: int) -> float:
        """Bounded exponential with symmetric jitter. ``attempt`` is 1-based."""
        base = policy.RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        capped = min(base, policy.RETRY_MAX_DELAY_SECONDS)
        f = policy.RETRY_JITTER_FRACTION
        return capped * (1.0 + self._rng.uniform(-f, f))

    # -- the guarded request loop ------------------------------------------------------

    def _run(self, call: Callable[[], Any], uri: str) -> Any:
        if self._halted is not None:
            # Latched: never issue another request after a halt, whatever the caller does.
            raise self._halted

        last_detail = ""
        for attempt in range(1, policy.RETRY_MAX_ATTEMPTS + 1):
            requested = utc_now_iso()
            started = self._monotonic()
            status: int | None = None
            outcome = "error"
            detail: str | None = None
            result: Any = None
            halt: CrawlHalt | None = None
            retryable = False

            try:
                result = call()
                self.requests_issued += 1
                status = self._recorder.last.status if self._recorder.last else None
                outcome = "ok"
            except httpx.HTTPStatusError as exc:
                self.requests_issued += 1
                status = exc.response.status_code
                detail = f"HTTPStatusError {status}"
                if status in policy.HALT_STATUSES:
                    outcome = "halt"
                    halt = CrawlHalt(status, uri)
                elif status in policy.RETRY_STATUSES:
                    outcome = "retry"
                    retryable = True
                    retry_after = exc.response.headers.get("retry-after")
                    if retry_after:
                        detail = f"{detail} retry-after={retry_after}"
                else:
                    outcome = "error"
            except httpx.HTTPError as exc:
                # Transport-level failure: no status was received. Retryable.
                self.requests_issued += 1
                detail = f"{type(exc).__name__}: {exc}"
                outcome = "retry"
                retryable = True

            self._emit(uri, attempt, requested, started, status, outcome, detail)

            if halt is not None:
                self._halted = halt
                raise halt
            if outcome == "ok":
                return result
            if not retryable:
                raise CrawlExhausted(f"{uri}: {detail}")

            last_detail = detail or ""
            self.retries += 1
            if attempt < policy.RETRY_MAX_ATTEMPTS:
                self._sleep(self._backoff_delay(attempt))

        self._emit(
            uri, policy.RETRY_MAX_ATTEMPTS, utc_now_iso(), self._monotonic(),
            None, "exhausted", last_detail,
        )
        raise CrawlExhausted(
            f"{uri}: still failing after {policy.RETRY_MAX_ATTEMPTS} attempts ({last_detail})"
        )

    # -- filing provenance --------------------------------------------------------------

    def _index_submissions(self, payload: Any) -> None:
        """Harvest accession -> form from a submissions payload as it passes through.

        The spine fetches submissions and then loops filings internally, so the driver has
        no per-filing hook to stamp provenance with. Reading the mapping off the response
        that is already in flight keeps every header fetch attributable without issuing a
        single extra request — which matters when the alternative is 1,167 duplicate
        submissions calls against a fair-access budget.
        """
        if not isinstance(payload, dict):
            return
        blocks: list[Any] = [payload]
        filings = payload.get("filings")
        if isinstance(filings, dict) and isinstance(filings.get("recent"), dict):
            blocks.append(filings["recent"])
        for block in blocks:
            if not isinstance(block, dict):
                continue
            forms = block.get("form")
            accessions = block.get("accessionNumber")
            if not isinstance(forms, list) or not isinstance(accessions, list):
                continue
            for accession, form in zip(accessions, forms, strict=False):
                if accession and form:
                    self._form_by_accession[str(accession)] = str(form)

    def _provenance(self, uri: str) -> tuple[str | None, str | None]:
        """(accession, form) for this URI, or (None, None) for a non-filing request."""
        explicit = self.context.get("accession")
        accession = str(explicit) if explicit else None
        if accession is None:
            match = _ACCESSION_RE.search(uri)
            accession = match.group(1) if match else None
        if accession is None:
            return None, None
        form = self.context.get("form") or self._form_by_accession.get(accession)
        return accession, (str(form) if form else None)

    def _emit(
        self,
        uri: str,
        attempt: int,
        requested: str,
        started: float,
        status: int | None,
        outcome: str,
        detail: str | None,
    ) -> None:
        cap = self._recorder.last
        used = cap if (cap is not None and outcome != "exhausted") else None
        accession, form = self._provenance(uri)
        self._evidence.record(SourceEvidence(
            uri=uri,
            method="GET",
            attempt=attempt,
            requested_utc=requested,
            http_status=status,
            received_utc=utc_now_iso(),
            elapsed_ms=int((self._monotonic() - started) * 1000),
            outcome=outcome,
            sha256_wire=sha256_hex(used.wire) if used else None,
            sha256_body=sha256_hex(used.body) if used else None,
            wire_bytes=len(used.wire) if used else None,
            body_bytes=len(used.body) if used else None,
            content_encoding=used.content_encoding if used else None,
            cik=self.context.get("cik"),
            ticker=self.context.get("ticker"),
            accession=accession,
            form=form,
            detail=detail,
            crawl_id=policy.CRAWL_ID,
            ua=policy.USER_AGENT,
        ))

    # -- the spine's _Fetcher protocol -------------------------------------------------

    def get_json(self, url: str) -> Any:
        payload = self._run(lambda: self._client.get_json(url), url)
        self._index_submissions(payload)
        return payload

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        return self._run(lambda: self._client.get_text(url, headers=headers), url)
