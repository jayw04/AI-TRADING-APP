"""RANGE-002 RETURN-BLIND symbol-mapping probe (Alpaca market-data bars endpoint).

    python -I mapping_probe.py --out FILE --max-requests N --key-env K --secret-env S \\
        --window-minutes 60 --probe VENDOR_TICKER,REQUEST_SYMBOL,YYYY-MM-DD,ASOF [--probe ...]

Purpose: establish, BEFORE a governed attempt is spent, whether a request symbol (and an ``asof``
mapping date) returns historical bars for a named day. It answers only: HTTP status, number of bars,
first and last bar timestamp, and the symbol the vendor echoed.

RETURN-BLIND BY CONSTRUCTION: the response is parsed for the bar timestamp field ``t`` and the
echoed symbol only. No open, high, low, close, volume, trade count or VWAP value is read into
any variable that is printed, written or returned, and the output schema has no field for one. The
tool never imports the governed fetch transport or the results guard: it is not a results run, it
makes no strategy computation, and it does not consume or imply a P3A attempt. Its use is an explicit,
owner-scoped authorization, and each execution is recorded in the exposure ledger as kind
``return_blind_probe`` (which lists the access but does not block a later planned run, because no
price, volume or result value is observed).

Hard request cap (``--max-requests``, required, counts retries); a 429 is retried at most twice with
back-off; any other non-200 status is recorded and not retried. Credentials come only from the
environment variables named on the command line and never appear in the output or exceptions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://data.alpaca.markets/v2/stocks"
_ET = ZoneInfo("America/New_York")
EXIT_OK, EXIT_REFUSED = 0, 2
TOOL_VERSION = "1.0.0"

#: output schema: the ONLY fields a probe record can carry (no price/volume field exists)
RECORD_FIELDS = (
    "vendor_ticker",
    "request_symbol",
    "day",
    "asof",
    "http_status",
    "bars",
    "first_bar_utc",
    "last_bar_utc",
    "symbol_echo",
    "error_kind",
)


class ProbeRefusal(RuntimeError):
    """The probe was not run or stopped; the message never contains a credential value."""


@dataclass(frozen=True)
class ProbeItem:
    vendor_ticker: str
    request_symbol: str
    day: date
    asof: str  # YYYY-MM-DD or "-"


HttpGet = Callable[[str, Mapping[str, str], Mapping[str, str]], tuple[int, Any]]


def parse_probe(text: str) -> ProbeItem:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4 or not all(parts):
        raise ProbeRefusal(
            f"--probe needs VENDOR_TICKER,REQUEST_SYMBOL,YYYY-MM-DD,ASOF; got {text!r}"
        )
    vendor, symbol, day_text, asof = parts
    day = date.fromisoformat(day_text)
    if asof != "-":
        date.fromisoformat(asof)
    return ProbeItem(vendor, symbol, day, asof)


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def window(day: date, minutes: int) -> tuple[datetime, datetime]:
    """[09:30 ET, 09:30 ET + minutes) on ``day``, as aware ET datetimes."""
    start = datetime.combine(day, dtime(9, 30), tzinfo=_ET)
    return start, start + timedelta(minutes=minutes)


def _httpx_get(timeout_s: float) -> HttpGet:
    import httpx

    client = httpx.Client(timeout=timeout_s, follow_redirects=False)

    def get(url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> tuple[int, Any]:
        try:
            resp = client.get(url, params=dict(params), headers=dict(headers))
        except httpx.HTTPError as exc:  # type name only: the message could echo request details
            raise ProbeRefusal(f"HTTP transport failure: {type(exc).__name__}") from None
        try:
            body: Any = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body

    return get


def run_probe(
    items: list[ProbeItem],
    *,
    max_requests: int,
    window_minutes: int,
    key: str,
    secret: str,
    http_get: HttpGet,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if max_requests <= 0 or window_minutes <= 0 or window_minutes > 390:
        raise ProbeRefusal("max-requests must be positive and window-minutes in 1..390")
    if len(items) > max_requests:
        raise ProbeRefusal(
            f"{len(items)} probes exceed the hard cap of {max_requests} requests; nothing sent"
        )
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    attempts = 0
    records: list[dict[str, Any]] = []
    for it in items:
        start, end = window(it.day, window_minutes)
        params = {
            "timeframe": "1Min",
            "feed": "sip",
            "adjustment": "raw",
            "asof": it.asof,
            "start": _rfc3339(start),
            "end": _rfc3339(end - timedelta(seconds=1)),
            "limit": "1000",
            "sort": "asc",
        }
        url = f"{BASE_URL}/{it.request_symbol}/bars"
        status: int = 0
        body: Any = None
        for retry in range(3):
            if attempts >= max_requests:
                raise ProbeRefusal(f"hard request cap {max_requests} reached; stopped")
            attempts += 1
            status, body = http_get(url, params, headers)
            if status != 429:
                break
            sleep(2.0 * (retry + 1))
        rec: dict[str, Any] = {
            "vendor_ticker": it.vendor_ticker,
            "request_symbol": it.request_symbol,
            "day": it.day.isoformat(),
            "asof": it.asof,
            "http_status": status,
            "bars": None,
            "first_bar_utc": None,
            "last_bar_utc": None,
            "symbol_echo": None,
            "error_kind": None,
        }
        if status == 200 and isinstance(body, dict):
            bars = body.get("bars")
            candidates = (
                [b.get("t") for b in bars if isinstance(b, dict)] if isinstance(bars, list) else []
            )
            stamps: list[str] = [t for t in candidates if isinstance(t, str)]
            rec["bars"] = len(stamps)
            rec["first_bar_utc"] = min(stamps) if stamps else None
            rec["last_bar_utc"] = max(stamps) if stamps else None
            echo = body.get("symbol")
            rec["symbol_echo"] = echo if isinstance(echo, str) else None
            if isinstance(body.get("next_page_token"), str):
                rec["error_kind"] = "MORE_PAGES_NOT_FOLLOWED"
        else:
            rec["error_kind"] = f"HTTP_{status}"
        assert tuple(rec) == RECORD_FIELDS
        records.append(rec)
    return {
        "schema": "range002.mapping_probe.v1",
        "tool_version": TOOL_VERSION,
        "return_blind": True,
        "values_read": ["t", "symbol", "next_page_token(presence)"],
        "feed": "sip",
        "adjustment": "raw",
        "timeframe": "1Min",
        "window_minutes": window_minutes,
        "requests_made": attempts,
        "max_requests": max_requests,
        "executed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "records": records,
    }


def main(argv: list[str] | None = None, *, http_get: HttpGet | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--max-requests", required=True, type=int)
    p.add_argument("--window-minutes", required=True, type=int)
    p.add_argument("--key-env", required=True)
    p.add_argument("--secret-env", required=True)
    p.add_argument("--probe", required=True, action="append")
    a = p.parse_args(argv)
    try:
        if a.out.exists():
            raise ProbeRefusal(f"{a.out} already exists; never overwritten")
        if not a.out.parent.is_dir():
            raise ProbeRefusal(f"{a.out.parent} is not an existing directory")
        key, secret = os.environ.get(a.key_env), os.environ.get(a.secret_env)
        if not key or not secret:
            raise ProbeRefusal(
                f"environment variables {a.key_env} / {a.secret_env} are not both set"
            )
        items = [parse_probe(t) for t in a.probe]
        out = run_probe(
            items,
            max_requests=a.max_requests,
            window_minutes=a.window_minutes,
            key=key,
            secret=secret,
            http_get=http_get or _httpx_get(30.0),
        )
    except (ProbeRefusal, ValueError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {out['requests_made']} request(s), {len(out['records'])} record(s)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
