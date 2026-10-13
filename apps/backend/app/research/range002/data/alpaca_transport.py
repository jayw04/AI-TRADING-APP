"""Real Alpaca market-data transport for the RANGE-002 minute fetch (PageRequest -> PageResponse).

Research plane only: this module imports no order-path, broker or trading-SDK module and talks
HTTPS to ``data.alpaca.markets`` bars endpoint alone. It is handed to the adapter through
``fetch_adapter.vendor_transport`` AFTER that function's authorization gate, so constructing it is
conditional on a complete ``FetchAuthorization`` and a results-guard capability.

Discipline:
  * credentials are read ONLY from the environment variables named by the caller; the values are
    never logged, never put in an exception, never returned by any accessor. Every exception text
    is built from the status code and exception TYPE, never from headers or a vendor body;
  * the request must be SIP + raw adjustment (the adapter checks too; this is the second wall);
  * an explicit requests-per-minute limiter (no default), bounded retry with backoff on 429/5xx,
    and a hard cap on HTTP attempts that fails closed;
  * the response is strictly parsed: unknown shape, wrong symbol echo, non-finite or non-numeric
    values are DataDefectError. A bar is never repaired or fabricated.

UNVERIFIED against the live service (documented, relied on from the public API description): the
response envelope ``{"bars": [{"t","o","h","l","c","v","n","vw"}], "symbol", "next_page_token"}``,
RFC3339 UTC ``t`` labelling the interval START, ``limit`` max 10000, ``asof`` accepting ``-``.
The run's convention-check evidence exists to confirm the labelling empirically.
"""

from __future__ import annotations

import math
import os
import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.research.range002.data.fetch_adapter import (
    REQUIRED_ADJUSTMENT,
    REQUIRED_FEED,
    PageRequest,
    PageResponse,
    RawBar,
)
from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import DataDefectError

BASE_URL = "https://data.alpaca.markets"
BARS_PATH = "/v2/stocks/{symbol}/bars"
TIMEFRAME = "1Min"
MAX_LIMIT = 10_000
_MAX_BACKOFF_S = 60.0


class TransportError(RuntimeError):
    """Network/HTTP failure. The message never carries a header, a key or a vendor body."""


class RequestCapExceededError(TransportError):
    """The configured HTTP-attempt cap was reached; the next request was NOT sent (fail closed)."""


@dataclass(frozen=True)
class HttpReply:
    status: int
    headers: Mapping[str, str]  # lower-cased names
    body: Any  # parsed JSON (dict) or None


_HttpGet = Callable[[str, Mapping[str, str], Mapping[str, str]], HttpReply]


@dataclass(frozen=True)
class AlpacaTransportConfig:
    key_env: str
    secret_env: str
    requests_per_minute: int
    max_retries: int
    max_requests: int
    timeout_s: float = 30.0
    base_url: str = BASE_URL
    # seams (tests inject; production leaves them None)
    environ: Mapping[str, str] | None = None
    http_get: _HttpGet | None = None
    clock: Callable[[], float] | None = None
    sleep: Callable[[float], None] | None = None


def _httpx_get_factory(timeout_s: float) -> _HttpGet:
    import httpx

    client = httpx.Client(timeout=timeout_s, follow_redirects=False)

    def get(url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> HttpReply:
        try:
            resp = client.get(url, params=dict(params), headers=dict(headers))
        except httpx.HTTPError as exc:  # type name only: the message may echo request details
            raise TransportError(f"HTTP transport failure: {type(exc).__name__}") from None
        body: Any = None
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError:
                raise DataDefectError("vendor response is not valid JSON") from None
        return HttpReply(resp.status_code, {k.lower(): v for k, v in resp.headers.items()}, body)

    return get


def _to_rfc3339(dt: datetime) -> str:
    """A NAIVE UTC datetime as RFC3339 ``YYYY-MM-DDTHH:MM:SSZ``."""
    if dt.tzinfo is not None:
        raise DataDefectError("request datetimes must be naive UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(text: object) -> datetime:
    if not isinstance(text, str):
        raise DataDefectError("bar timestamp is not a string")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise DataDefectError("bar timestamp is not RFC3339") from None
    if dt.tzinfo is None:
        raise DataDefectError("bar timestamp carries no UTC offset")
    return dt.astimezone(UTC).replace(tzinfo=None)


def _num(bar: Mapping[str, Any], key: str) -> float:
    v = bar.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise DataDefectError(f"bar field {key!r} missing or not a finite number")
    return float(v)


def _int(bar: Mapping[str, Any], key: str, *, required: bool) -> int | None:
    v = bar.get(key)
    if v is None and not required:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise DataDefectError(f"bar field {key!r} missing or not a finite number")
    if v != int(v):
        raise DataDefectError(f"bar field {key!r} is not integral")
    return int(v)


def _parse_bar(raw: object) -> RawBar:
    if not isinstance(raw, dict):
        raise DataDefectError("bar is not an object")
    vw: float | None = None
    if raw.get("vw") is not None:
        vw = _num(raw, "vw")
    v = _int(raw, "v", required=True)
    assert v is not None
    return RawBar(
        t=_parse_ts(raw.get("t")),
        o=_num(raw, "o"),
        h=_num(raw, "h"),
        low=_num(raw, "l"),
        c=_num(raw, "c"),
        v=v,
        n=_int(raw, "n", required=False),
        vw=vw,
    )


class _AlpacaBarsTransport:
    """``PageRequest -> PageResponse``. One instance per run; counters are observable."""

    def __init__(self, cfg: AlpacaTransportConfig) -> None:
        if cfg.requests_per_minute <= 0 or cfg.max_requests <= 0 or cfg.max_retries < 0:
            raise ValueError("requests_per_minute and max_requests must be > 0, max_retries >= 0")
        if cfg.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        env = os.environ if cfg.environ is None else cfg.environ
        key, secret = env.get(cfg.key_env, ""), env.get(cfg.secret_env, "")
        missing = [n for n, v in ((cfg.key_env, key), (cfg.secret_env, secret)) if not v.strip()]
        if missing:  # the NAMES of the variables, never a value
            raise TransportError(f"credential environment variable(s) not set: {missing}")
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self._secrets = (key, secret)
        self._cfg = cfg
        self._get = cfg.http_get or _httpx_get_factory(cfg.timeout_s)
        self._clock = cfg.clock or _time.monotonic
        self._sleep = cfg.sleep or _time.sleep
        self._interval = 60.0 / cfg.requests_per_minute
        self._next_at: float | None = None
        self.http_attempts = 0  # every HTTP attempt, including retries
        self.pages_ok = 0

    def __repr__(self) -> str:  # never expose headers
        return f"_AlpacaBarsTransport(attempts={self.http_attempts}, pages_ok={self.pages_ok})"

    def _scrub(self, text: str) -> str:
        for s in self._secrets:
            if s:
                text = text.replace(s, "***")
        return text

    def _pace(self) -> None:
        now = self._clock()
        if self._next_at is not None and now < self._next_at:
            self._sleep(self._next_at - now)
            now = self._next_at
        self._next_at = now + self._interval

    def _build(self, req: PageRequest) -> tuple[str, dict[str, str]]:
        if req.feed != REQUIRED_FEED or req.adjustment != REQUIRED_ADJUSTMENT:
            raise DataDefectError(
                f"transport sends only feed={REQUIRED_FEED!r} adjustment={REQUIRED_ADJUSTMENT!r}"
            )
        if not 0 < req.limit <= MAX_LIMIT:
            raise DataDefectError(f"limit must be in 1..{MAX_LIMIT}")
        if not req.symbol or "/" in req.symbol or not req.asof.strip():
            raise DataDefectError("a plain symbol and an explicit asof are required")
        params = {
            "timeframe": TIMEFRAME,
            "start": _to_rfc3339(req.start_utc),
            "end": _to_rfc3339(req.end_utc),
            "limit": str(req.limit),
            "adjustment": req.adjustment,
            "feed": req.feed,
            "asof": req.asof,
            "sort": "asc",
        }
        if req.page_token is not None:
            params["page_token"] = req.page_token
        url = self._cfg.base_url.rstrip("/") + BARS_PATH.format(symbol=quote(req.symbol, safe=""))
        return url, params

    def _send(self, req: PageRequest) -> PageResponse:
        url, params = self._build(req)
        retries = 0
        while True:
            if self.http_attempts >= self._cfg.max_requests:
                raise RequestCapExceededError(
                    f"max_requests={self._cfg.max_requests} reached; request not sent"
                )
            self._pace()
            self.http_attempts += 1
            try:
                reply = self._get(url, params, self._headers)
            except TransportError as exc:
                raise TransportError(self._scrub(str(exc))) from None
            if reply.status == 200:
                break
            if reply.status == 429 or reply.status >= 500:
                if retries >= self._cfg.max_retries:
                    raise TransportError(
                        f"vendor HTTP {reply.status} after {retries} retries (bounded)"
                    )
                retries += 1
                self._sleep(self._backoff(retries, reply.headers))
                continue
            raise TransportError(f"vendor HTTP {reply.status} (not retried)")
        self.pages_ok += 1
        return self._parse(req, reply.body)

    @staticmethod
    def _backoff(retry_no: int, headers: Mapping[str, str]) -> float:
        raw = headers.get("retry-after")
        try:
            if raw is not None:
                return max(0.0, min(float(raw), _MAX_BACKOFF_S))
        except ValueError:
            pass
        return min(2.0**retry_no, _MAX_BACKOFF_S)

    @staticmethod
    def _parse(req: PageRequest, body: Any) -> PageResponse:
        if not isinstance(body, dict):
            raise DataDefectError("vendor response is not an object")
        echoed = body.get("symbol")
        if echoed is not None and echoed != req.symbol:
            raise DataDefectError(f"vendor response symbol {echoed!r} != requested {req.symbol!r}")
        raw_bars = body.get("bars")
        if raw_bars is None:
            raw_bars = []
        if not isinstance(raw_bars, list):
            raise DataDefectError("vendor 'bars' is not a list")
        token = body.get("next_page_token")
        if token is not None and (not isinstance(token, str) or not token):
            raise DataDefectError("vendor next_page_token is not a non-empty string")
        return PageResponse(tuple(_parse_bar(b) for b in raw_bars), token)


@requires_capability
def build_alpaca_transport(
    capability: object, cfg: AlpacaTransportConfig
) -> Callable[[PageRequest], PageResponse]:
    """The transport as a plain callable. ``transport.__dict__["http_attempts"]()`` returns the
    number of HTTP attempts made so far (a safety-cap and manifest input)."""
    inst = _AlpacaBarsTransport(cfg)

    def transport(req: PageRequest) -> PageResponse:
        return inst._send(req)

    transport.__dict__["http_attempts"] = lambda: inst.http_attempts
    return transport
