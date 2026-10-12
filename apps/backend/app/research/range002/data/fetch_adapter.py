"""Vendor-fetch adapter, BUILD scope: pagination, validation, journal and storage gates against a
MOCK transport. No network code exists in this module and no real vendor call can be made.

A transport is any callable ``PageRequest -> PageResponse`` injected by the caller. The real
vendor transport is deliberately NOT built: ``vendor_transport`` refuses unless a complete
``FetchAuthorization`` (permitted-use reference, entitlement reference, storage permission) is
supplied, and even then raises ``NotImplementedError``. Real fetching and any storage of fetched
data remain conditional on that authorization and on the vendor's permitted-use answer.

What the adapter enforces, so a mock-tested pipeline cannot drift when a real transport lands:
the request must be RAW, SIP and carry an explicit ``asof`` decision; every page respects the
declared ``limit``; timestamps are strictly increasing and inside the requested window across
pages; a repeated page token is a defect; completed chunks are journaled so a resume never
re-requests or double-writes them; and writing into the research store needs ``storage_permitted``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import DataDefectError

REQUIRED_ADJUSTMENT = "raw"
REQUIRED_FEED = "sip"


class FetchNotAuthorizedError(PermissionError):
    """A fetch or a storage write was attempted without the authorization it is conditional on."""


@dataclass(frozen=True)
class FetchAuthorization:
    authorization_id: str
    permitted_use_ref: str
    entitlement_ref: str
    storage_permitted: bool


@dataclass(frozen=True)
class PageRequest:
    symbol: str
    start_utc: datetime
    end_utc: datetime
    feed: str
    adjustment: str
    asof: str  # YYYY-MM-DD, or "-" to skip symbol mapping: an explicit decision, never a default
    limit: int
    page_token: str | None


@dataclass(frozen=True)
class RawBar:
    t: datetime  # bar START, naive UTC
    o: float
    h: float
    low: float
    c: float
    v: int
    n: int | None
    vw: float | None


@dataclass(frozen=True)
class PageResponse:
    bars: tuple[RawBar, ...]
    next_page_token: str | None


@dataclass(frozen=True)
class FetchResult:
    symbol: str
    bars: tuple[RawBar, ...]
    pages: int
    adjustment: str  # the adjustment actually requested; written to minute_bars.basis


def _authorized(auth: FetchAuthorization | None) -> FetchAuthorization:
    if auth is None or not all(
        x.strip() for x in (auth.authorization_id, auth.permitted_use_ref, auth.entitlement_ref)
    ):
        raise FetchNotAuthorizedError("a complete FetchAuthorization is required")
    return auth


@requires_capability
def vendor_transport(
    capability: object, authorization: FetchAuthorization | None
) -> Callable[[PageRequest], PageResponse]:
    """The real vendor transport is intentionally not part of BUILD scope."""
    _authorized(authorization)
    raise NotImplementedError("the real vendor transport is not built; BUILD scope uses mocks")


@requires_capability
def fetch_symbol_window(
    capability: object,
    transport: Callable[[PageRequest], PageResponse],
    *,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    feed: str,
    adjustment: str,
    asof: str,
    limit: int,
    max_pages: int,
) -> FetchResult:
    if adjustment != REQUIRED_ADJUSTMENT:
        raise DataDefectError(f"adjustment must be {REQUIRED_ADJUSTMENT!r}, got {adjustment!r}")
    if feed != REQUIRED_FEED:
        raise DataDefectError(f"feed must be {REQUIRED_FEED!r}, got {feed!r}")
    if not asof.strip() or limit <= 0 or max_pages <= 0 or start_utc >= end_utc:
        raise DataDefectError("asof, limit, max_pages and a non-empty window are required")
    bars: list[RawBar] = []
    seen_tokens: set[str] = set()
    token: str | None = None
    pages = 0
    while True:
        if pages >= max_pages:
            raise DataDefectError(f"{symbol}: exceeded max_pages={max_pages}")
        resp = transport(
            PageRequest(symbol, start_utc, end_utc, feed, adjustment, asof, limit, token)
        )
        pages += 1
        if len(resp.bars) > limit:
            raise DataDefectError(f"{symbol}: page of {len(resp.bars)} exceeds limit {limit}")
        for b in resp.bars:
            if not (start_utc <= b.t < end_utc):
                raise DataDefectError(f"{symbol}: bar {b.t} outside the requested window")
            if bars and b.t <= bars[-1].t:
                raise DataDefectError(f"{symbol}: duplicate or out-of-order bar at {b.t}")
            if not (b.low <= min(b.o, b.c) and b.h >= max(b.o, b.c)) or b.v < 0:
                raise DataDefectError(f"{symbol}: inconsistent bar at {b.t}")
            bars.append(b)
        token = resp.next_page_token
        if token is None:
            return FetchResult(symbol, tuple(bars), pages, adjustment)
        if token in seen_tokens:
            raise DataDefectError(f"{symbol}: page token repeated (pagination loop)")
        seen_tokens.add(token)


@requires_capability
def store_fetched_bars(
    capability: object,
    con: Any,
    result: FetchResult,
    *,
    authorization: FetchAuthorization | None,
    journal: set[tuple[str, str]],
    chunk_key: str,
) -> int:
    """Write one fetched chunk into ``minute_bars`` (idempotent per ``(symbol, chunk_key)``)."""
    auth = _authorized(authorization)
    if not auth.storage_permitted:
        raise FetchNotAuthorizedError("storing fetched data is not permitted by the authorization")
    key = (result.symbol, chunk_key)
    if key in journal:
        return 0
    con.execute(
        "CREATE TABLE IF NOT EXISTS minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE,"
        " high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    if result.adjustment != REQUIRED_ADJUSTMENT:
        raise DataDefectError(
            f"{result.symbol}: refusing to store bars fetched with adjustment "
            f"{result.adjustment!r}; only {REQUIRED_ADJUSTMENT!r} is stored"
        )
    for b in result.bars:
        con.execute(
            "INSERT INTO minute_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [result.symbol, b.t, b.o, b.h, b.low, b.c, b.v, result.adjustment],
        )
    journal.add(key)
    return len(result.bars)


@requires_capability
def fetch_and_store(
    capability: object,
    transport: Callable[[PageRequest], PageResponse],
    con: Any,
    chunks: Sequence[tuple[str, datetime, datetime]],
    *,
    authorization: FetchAuthorization | None,
    journal: set[tuple[str, str]],
    feed: str,
    adjustment: str,
    asof: str,
    limit: int,
    max_pages: int,
) -> int:
    """Fetch and store every chunk not already journaled; returns rows written."""
    _authorized(authorization)
    written = 0
    for symbol, start, end in chunks:
        chunk_key = f"{start.isoformat()}|{end.isoformat()}"
        if (symbol, chunk_key) in journal:
            continue
        res = fetch_symbol_window(
            capability, transport, symbol=symbol, start_utc=start, end_utc=end, feed=feed,
            adjustment=adjustment, asof=asof, limit=limit, max_pages=max_pages,
        )  # fmt: skip
        written += store_fetched_bars(
            capability, con, res, authorization=authorization, journal=journal, chunk_key=chunk_key
        )
    return written
